# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Webcam upload control and summary-loop state for the transport agent."""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame

from cascaded.omni_assistant_subagents.subagents.transport.speaker_context import SpeakerContextManager
from cascaded.omni_assistant_subagents.subagents.utils import (
    normalize_user_intent,
    normalize_visual_control,
)
from cascaded.omni_assistant_subagents.subagents.webcam import WEBCAM_SUMMARY_TASK_NAME, WebcamAgent
from utils import parse_env_bool, parse_env_float, parse_env_int
from webcam_frame_store import (
    clear_session_webcam_frame_data,
    latest_webcam_frame,
    register_webcam_frame_listener,
)

_WEBCAM_UPLOAD_IDLE = "idle"
_WEBCAM_UPLOAD_USER = "user_speaking"
_WEBCAM_UPLOAD_ASSISTANT = "assistant_speaking"


@dataclass(frozen=True)
class WebcamSummaryResult:
    """Published webcam summary data that transport uses for visual control."""

    visual_control: dict[str, Any]
    frame: dict[str, Any]


class WebcamController:
    """Own webcam availability, upload control, and background summary dispatch."""

    def __init__(
        self,
        *,
        session_id: str,
        speaker_context: SpeakerContextManager,
        request_task: Callable[..., Awaitable[str]],
        queue_frame: Callable[[Any], Awaitable[None]],
        is_visual_control_stopped: Callable[[], bool],
    ) -> None:
        """Initialize webcam summary and upload-control state for one session."""
        self._session_id = session_id
        self._speaker_context = speaker_context
        self._request_task = request_task
        self._queue_frame = queue_frame
        self._is_visual_control_stopped = is_visual_control_stopped
        self._summary_loop_task: asyncio.Task[None] | None = None
        self._frame_event: asyncio.Event | None = None
        self._unregister_frame_listener = None
        self._summary_task_id = ""
        self._last_summary_sequence = 0
        self._latest_observation = ""
        self._observations: list[str] = []
        self._enabled = False
        self._disabled_at = 0.0
        self._user_visible: bool | None = None
        self._user_intent = "idle"
        self._user_voice_turn_active = False
        self._assistant_speaking = False
        self._greet_on_first_sight = parse_env_bool("WEBCAM_GREET_ON_FIRST_SIGHT", default=True)
        self._greeted_visible_user = False
        self._first_sight_greeting_pending = False
        self._observation_limit = parse_env_int("WEBCAM_CONTEXT_OBSERVATION_LIMIT", 3, min_value=1)
        self._summary_interval_secs = parse_env_float("WEBCAM_SUMMARY_INTERVAL_SECONDS", 1.5, min_value=1.0)
        self._summary_min_gap_secs = parse_env_float("WEBCAM_SUMMARY_MIN_GAP_SECONDS", 2.5, min_value=0.5)
        self._last_summary_completed_at = 0.0
        self._user_upload_interval_ms = parse_env_int("WEBCAM_USER_SPEAKING_UPLOAD_INTERVAL_MS", 1000, min_value=250)
        self._assistant_upload_interval_ms = parse_env_int(
            "WEBCAM_ASSISTANT_SPEAKING_UPLOAD_INTERVAL_MS", 1200, min_value=250
        )
        self._reenable_grace_secs = parse_env_float("WEBCAM_REENABLE_GRACE_SECONDS", 2.0, min_value=0.0)

    def start_summary_loop(self) -> None:
        """Start a small background loop that requests selected webcam scene summaries."""
        if self._summary_loop_task and not self._summary_loop_task.done():
            return
        loop = asyncio.get_running_loop()
        self._frame_event = asyncio.Event()
        self._unregister_frame_listener = register_webcam_frame_listener(
            self._session_id,
            lambda: loop.call_soon_threadsafe(self._notify_frame_uploaded),
        )
        self._summary_loop_task = asyncio.create_task(self._run_summary_loop())

    def stop_summary_loop(self) -> None:
        """Stop the webcam summary loop for this session."""
        if self._summary_loop_task and not self._summary_loop_task.done():
            self._summary_loop_task.cancel()
        if self._unregister_frame_listener:
            self._unregister_frame_listener()
        self._summary_loop_task = None
        self._frame_event = None
        self._unregister_frame_listener = None
        self._summary_task_id = ""

    def refresh_input_state_context(self) -> None:
        """Keep one compact message describing currently available visual inputs."""
        self._speaker_context.replace_input_state_message(
            webcam_enabled=self._enabled,
            webcam_user_visible=self._user_visible,
            webcam_user_intent=self._user_intent,
        )

    async def on_user_voice_turn_started(self) -> None:
        """Start short-lived webcam memory updates for the active user turn."""
        self._user_voice_turn_active = True
        self.refresh_input_state_context()
        await self._emit_upload_control(
            mode=_WEBCAM_UPLOAD_USER,
            interval_ms=self._user_upload_interval_ms,
            label="capturing while you speak",
        )
        self._wake_summary_loop()

    async def on_user_voice_turn_stopped(self) -> None:
        """Update webcam capture policy once the user turn reaches EOU."""
        self._user_voice_turn_active = False
        if self._assistant_speaking:
            await self._emit_upload_control(
                mode=_WEBCAM_UPLOAD_ASSISTANT,
                interval_ms=self._assistant_upload_interval_ms,
                label="capturing while assistant speaks",
            )
        else:
            await self._emit_upload_control(mode=_WEBCAM_UPLOAD_IDLE)

    async def on_assistant_speaking_started(self) -> None:
        """Track active assistant speech for webcam visual-control scoring."""
        self._assistant_speaking = True
        if self._first_sight_greeting_pending:
            self._clear_first_sight_context()
        if not self._user_voice_turn_active:
            await self._emit_upload_control(
                mode=_WEBCAM_UPLOAD_ASSISTANT,
                interval_ms=self._assistant_upload_interval_ms,
                label="capturing while assistant speaks",
            )

    async def on_assistant_speaking_stopped(self) -> None:
        """Track when assistant speech has stopped."""
        self._assistant_speaking = False
        if not self._user_voice_turn_active:
            await self._emit_upload_control(mode=_WEBCAM_UPLOAD_IDLE)

    async def apply_webcam_state(self, payload: dict[str, Any]) -> None:
        """Record browser webcam availability for Speaker routing decisions."""
        enabled = payload.get("enabled") is True
        if enabled == self._enabled:
            return
        self._enabled = enabled
        self._disabled_at = 0.0
        if not enabled:
            self._disabled_at = time.monotonic()
            self._user_visible = None
            self._user_intent = "idle"
            clear_session_webcam_frame_data(self._session_id)
            self._first_sight_greeting_pending = False
            self._replace_webcam_context_message()
            if not self._user_voice_turn_active:
                await self._emit_upload_control(mode=_WEBCAM_UPLOAD_IDLE)
        self.refresh_input_state_context()
        logger.info(f"Browser webcam state changed: enabled={enabled}")

    async def handle_summary_response(self, task_id: str, response: dict[str, Any]) -> WebcamSummaryResult | None:
        """Record a completed background webcam scene observation."""
        if self._summary_task_id == task_id:
            self._summary_task_id = ""
        self._last_summary_completed_at = time.monotonic()
        if not self._enabled:
            logger.debug("Dropping webcam summary response because browser webcam state is off")
            self._user_visible = None
            self.refresh_input_state_context()
            return None

        observation = _normalize_webcam_observation_identity(str(response.get("observation") or "").strip())
        if not observation:
            return None
        frame = response.get("frame") if isinstance(response.get("frame"), dict) else {}
        event_reason = str(response.get("event_reason") or "").strip()
        user_visible = response.get("user_visible") is True
        user_intent = normalize_user_intent(response.get("user_intent"))
        speaker_context = str(response.get("speaker_context") or "").strip()
        visual_control = normalize_visual_control(response.get("visual_control"))
        should_publish = bool(response.get("publish"))
        webcam_is_live = self._enabled
        self._user_visible = user_visible if webcam_is_live else None
        self._user_intent = user_intent if webcam_is_live else "idle"
        self.refresh_input_state_context()
        await self._emit_agent_update(
            observation=observation,
            event_reason=event_reason,
            visual_control=visual_control,
            frame=frame,
            propagated=should_publish,
        )
        if not should_publish:
            logger.debug("Webcam summary skipped semantic propagation")
            return None

        created_at = str(frame.get("created_at") or "")
        entry_observation = f"{observation} Reason: {event_reason}" if event_reason else observation
        entry = f"{created_at}: {entry_observation}" if created_at else entry_observation
        self._latest_observation = entry_observation
        self._observations.append(entry)
        del self._observations[: -self._observation_limit]
        self._replace_webcam_context_message()
        logger.debug(
            f"Webcam scene observation: {observation!r}, user_visible={user_visible}, "
            f"user_intent={user_intent!r}, visual_control={visual_control}"
        )
        if webcam_is_live:
            self._maybe_greet_visible_user(user_visible, speaker_context)
            return WebcamSummaryResult(visual_control=visual_control, frame=frame)
        return None

    def _notify_frame_uploaded(self) -> None:
        """Wake the summary loop when the browser uploads a fresh frame."""
        if not self._enabled:
            if self._disabled_at and time.monotonic() - self._disabled_at < self._reenable_grace_secs:
                logger.debug("Ignoring webcam frame upload during camera-off grace window")
                return
            self._enabled = True
            self._disabled_at = 0.0
            self.refresh_input_state_context()
            logger.info("Browser webcam state inferred enabled from fresh frame upload")
        self._wake_summary_loop()

    def _wake_summary_loop(self) -> None:
        """Wake the summary loop without changing webcam availability."""
        if self._frame_event:
            self._frame_event.set()

    async def _run_summary_loop(self) -> None:
        """Ask WebcamAgent for scene summaries as soon as new frames arrive."""
        try:
            while True:
                if self._frame_event:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(
                            self._frame_event.wait(),
                            timeout=self._summary_interval_secs,
                        )
                    self._frame_event.clear()
                else:
                    await asyncio.sleep(self._summary_interval_secs)
                if self._summary_task_id:
                    continue
                if not self._enabled:
                    continue
                allow_first_sighting = (
                    self._greet_on_first_sight and not self._greeted_visible_user and not self._latest_observation
                )
                if not (self._user_voice_turn_active or self._assistant_speaking or allow_first_sighting):
                    continue
                frame = latest_webcam_frame(self._session_id)
                if frame is None or frame.sequence == self._last_summary_sequence:
                    continue
                now = time.monotonic()
                gap = now - self._last_summary_completed_at
                if self._last_summary_completed_at and gap < self._summary_min_gap_secs and not allow_first_sighting:
                    logger.debug(
                        f"Throttling webcam summary: only {gap:.2f}s since last completion "
                        f"(min_gap={self._summary_min_gap_secs:.2f}s)"
                    )
                    continue
                self._last_summary_sequence = frame.sequence
                try:
                    self._summary_task_id = await self._request_task(
                        WebcamAgent.AGENT_NAME,
                        name=WEBCAM_SUMMARY_TASK_NAME,
                        payload={
                            "session_id": self._session_id,
                            "frame": frame.metadata(),
                            "assistant_speaking": self._assistant_speaking,
                            "first_sighting": allow_first_sighting,
                        },
                        timeout=60.0,
                    )
                    logger.debug(
                        f"Webcam summary dispatched: task_id={self._summary_task_id}, frame_sequence={frame.sequence}"
                    )
                except Exception as exc:
                    self._summary_task_id = ""
                    logger.warning(f"Failed to dispatch webcam summary task: {exc}")
        except asyncio.CancelledError:
            logger.debug("Webcam summary loop cancelled")

    def _maybe_greet_visible_user(self, user_visible: bool, speaker_context: str) -> None:
        """Greet once when the live webcam first clearly shows the user."""
        if (
            not self._greet_on_first_sight
            or self._greeted_visible_user
            or not user_visible
            or not speaker_context
            or self._is_visual_control_stopped()
        ):
            return

        self._greeted_visible_user = True
        self._first_sight_greeting_pending = True
        self._speaker_context.add_first_sight_context(speaker_context)

    def _clear_first_sight_context(self) -> None:
        """Remove the one-shot first-sighting instruction after it has been consumed."""
        self._first_sight_greeting_pending = False
        self._speaker_context.clear_first_sight_context()

    def _replace_webcam_context_message(self) -> None:
        """Keep one compact rolling webcam context message in Speaker Omni's context."""
        self._speaker_context.replace_webcam_context_message(
            webcam_enabled=self._enabled,
            webcam_user_visible=self._user_visible,
            latest_observation=self._latest_observation,
            observations=self._observations,
        )

    async def _emit_agent_update(
        self,
        *,
        observation: str,
        event_reason: str,
        visual_control: dict[str, Any],
        frame: dict[str, Any],
        propagated: bool,
    ) -> None:
        """Emit the latest semantic webcam observation to the client UI only."""
        await self._queue_frame(
            RTVIServerMessageFrame(
                data={
                    "type": "webcam-agent-update",
                    "agent": WebcamAgent.AGENT_NAME,
                    "observation": observation,
                    "event_reason": event_reason,
                    "proactive_message": "",
                    "visual_control": visual_control,
                    "propagated": propagated,
                    "frame": frame,
                }
            )
        )

    async def _emit_upload_control(
        self,
        *,
        mode: str,
        interval_ms: int = 0,
        label: str = "",
    ) -> None:
        """Tell the browser how to capture webcam frames for the current server state."""
        active = mode != _WEBCAM_UPLOAD_IDLE
        action = "repeat" if active else "idle"
        await self._queue_frame(
            RTVIServerMessageFrame(
                data={
                    "type": "webcam-upload-control",
                    "action": action,
                    "active": active,
                    "mode": mode,
                    "interval_ms": interval_ms if active else 0,
                    "label": label,
                }
            )
        )


def _normalize_webcam_observation_identity(observation: str) -> str:
    """Avoid feeding demographic third-person descriptions of the current user back to Speaker Omni."""
    normalized = observation.strip()
    normalized = re.sub(
        r"(?i)^the user,\s+(?:a|an)\s+.+?,\s+is\b",
        "The user is",
        normalized,
        count=1,
    )
    normalized = re.sub(
        r"(?i)^the user,\s+(?:a|an)\s+.+?,\s+appears\b",
        "The user appears",
        normalized,
        count=1,
    )
    return normalized
