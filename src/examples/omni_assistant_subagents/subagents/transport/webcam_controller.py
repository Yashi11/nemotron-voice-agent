# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Webcam streaming control for the transport agent.

This is the ``omni-video-stream`` style capability: while the browser webcam is
on, frames are uploaded continuously and each fresh frame is sent to the
``WebcamAgent`` (reasoning-off, rolling visual memory) for a one-sentence
description. There is no scene-change gate and no speech-conditioned gating: each fresh
observation is streamed to the client UI and mirrored into the Speaker's pinned
subagents board (its "live eyes"), updated in one place so the Speaker always
knows what it currently sees.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from io import BytesIO
from typing import Any

from loguru import logger
from PIL import Image
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame

from examples.omni_assistant_subagents.subagents.transport.subagent_state_board import SubagentStateBoard
from examples.omni_assistant_subagents.subagents.webcam import WEBCAM_SUMMARY_TASK_NAME, WebcamAgent
from webcam_frame_store import (
    clear_session_webcam_frame_data,
    latest_webcam_frame,
    register_webcam_frame_listener,
)

_CAMERA_OFF_STATE = "the camera is OFF right now — there is nothing visible live"
_CAMERA_ON_STATE = "the camera just turned on; the live view is loading"
_NOOP_OBSERVATION = "no notable change"
_STREAM_INTERVAL_MS = 800
_WINDOW_SECONDS = 8.0
_SCREEN_FINGERPRINT_SIZE = (64, 36)
_SCREEN_CHANGED_PIXEL_DELTA = 18
_SCREEN_CHANGED_PIXEL_RATIO = 0.08
_SCREEN_CHANGED_MEAN_DELTA = 6.0


def _screen_fingerprint(data: bytes) -> bytes | None:
    """Return a tiny grayscale representation suitable for inexpensive change checks."""
    try:
        with Image.open(BytesIO(data)) as image:
            return image.convert("L").resize(_SCREEN_FINGERPRINT_SIZE).tobytes()
    except (OSError, ValueError):
        return None


def _has_material_screen_change(previous: bytes | None, current: bytes | None) -> bool:
    """Detect a display change while tolerating JPEG noise and minor animation."""
    if current is None:
        return False
    if previous is None or len(previous) != len(current):
        return True
    deltas = [abs(before - after) for before, after in zip(previous, current, strict=True)]
    if not deltas:
        return False
    mean_delta = sum(deltas) / len(deltas)
    changed_ratio = sum(delta >= _SCREEN_CHANGED_PIXEL_DELTA for delta in deltas) / len(deltas)
    return mean_delta >= _SCREEN_CHANGED_MEAN_DELTA or changed_ratio >= _SCREEN_CHANGED_PIXEL_RATIO


def _is_noop_observation(observation: str) -> bool:
    """Whether an observation reports no new scene content (a bare "No notable change.")."""
    return observation.strip().rstrip(".").strip().lower() == _NOOP_OBSERVATION


class WebcamController:
    """Own webcam availability and continuous frame-streaming dispatch."""

    def __init__(
        self,
        *,
        session_id: str,
        board: SubagentStateBoard,
        request_job: Callable[..., Awaitable[str]],
        queue_frame: Callable[[Any], Awaitable[None]],
        conversation_provider: Callable[[], str] | None = None,
        worker_name: str = WebcamAgent.AGENT_NAME,
        task_name: str = WEBCAM_SUMMARY_TASK_NAME,
        frame_source: str = "webcam",
        board_agent_name: str = WebcamAgent.AGENT_NAME,
        update_type: str = "webcam-agent-update",
        upload_control_type: str = "webcam-upload-control",
        inactive_state: str = _CAMERA_OFF_STATE,
        starting_state: str = _CAMERA_ON_STATE,
        minimum_dispatch_interval_ms: int = _STREAM_INTERVAL_MS,
        initial_window_seconds: float = _WINDOW_SECONDS,
        detect_frame_changes: bool = False,
        stable_refresh_interval_ms: int | None = None,
        two_stage_initial_analysis: bool = False,
    ) -> None:
        """Initialize continuous webcam streaming state for one session.

        ``board`` is the Speaker's pinned subagents board, into which the live webcam
        observation is mirrored as the assistant's "eyes". ``conversation_provider``
        returns a short rendering of the recent conversation so the webcam analyzer can
        decide which visible details to emphasize for the current topic.
        """
        self._session_id = session_id
        self._board = board
        self._request_job = request_job
        self._queue_frame = queue_frame
        self._conversation_provider = conversation_provider
        self._worker_name = worker_name
        self._task_name = task_name
        self._frame_source = frame_source
        self._board_agent_name = board_agent_name
        self._update_type = update_type
        self._upload_control_type = upload_control_type
        self._inactive_state = inactive_state
        self._starting_state = starting_state
        self._minimum_dispatch_interval_ms = max(_STREAM_INTERVAL_MS, minimum_dispatch_interval_ms)
        self._detect_frame_changes = detect_frame_changes
        self._two_stage_initial_analysis = two_stage_initial_analysis
        self._initial_fast_pending = two_stage_initial_analysis
        self._pending_full_analysis = False
        self._stable_refresh_interval_ms = max(
            self._minimum_dispatch_interval_ms,
            stable_refresh_interval_ms or self._minimum_dispatch_interval_ms,
        )
        self._summary_loop_task: asyncio.Task[None] | None = None
        self._upload_control_task: asyncio.Task[None] | None = None
        self._frame_event: asyncio.Event | None = None
        self._unregister_frame_listener = None
        self._summary_task_id = ""
        self._last_dispatched_sequence = 0
        self._last_dispatched_at = 0.0
        self._last_analyzed_fingerprint: bytes | None = None
        self._dispatched_fingerprint: bytes | None = None
        self._latest_observation = ""
        self._board_state = ""
        self._enabled = False
        self._explicitly_disabled = False
        self._epoch = 0
        self._summary_epoch = -1
        self._stream_interval_ms = _STREAM_INTERVAL_MS
        self._window_seconds = initial_window_seconds

    def start_summary_loop(self) -> None:
        """Start the background loop that streams fresh frames to the WebcamAgent."""
        if self._summary_loop_task and not self._summary_loop_task.done():
            return
        loop = asyncio.get_running_loop()
        self._frame_event = asyncio.Event()
        self._unregister_frame_listener = register_webcam_frame_listener(
            self._session_id,
            lambda: loop.call_soon_threadsafe(self._notify_frame_uploaded),
            source=self._frame_source,
        )
        self._summary_loop_task = asyncio.create_task(self._run_summary_loop())
        self._set_board_state(self._inactive_state)

    def stop_summary_loop(self) -> None:
        """Stop the webcam streaming loop for this session."""
        if self._summary_loop_task and not self._summary_loop_task.done():
            self._summary_loop_task.cancel()
        if self._upload_control_task and not self._upload_control_task.done():
            self._upload_control_task.cancel()
        if self._unregister_frame_listener:
            self._unregister_frame_listener()
        self._summary_loop_task = None
        self._upload_control_task = None
        self._frame_event = None
        self._unregister_frame_listener = None
        self._summary_task_id = ""

    async def apply_webcam_state(self, payload: dict[str, Any]) -> None:
        """Start/stop continuous webcam uploads when the browser toggles the camera."""
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            logger.warning(f"Ignoring webcam-state with non-boolean enabled: {enabled!r}")
            return
        if enabled == self._enabled:
            return
        self._enabled = enabled
        self._epoch += 1
        if enabled:
            self._explicitly_disabled = False
            self._initial_fast_pending = self._two_stage_initial_analysis
            self._pending_full_analysis = False
            self._set_board_state(self._starting_state)
            await self._start_continuous_uploads()
        else:
            self._explicitly_disabled = True
            if self._upload_control_task and not self._upload_control_task.done():
                self._upload_control_task.cancel()
            clear_session_webcam_frame_data(self._session_id)
            self._pending_full_analysis = False
            self._latest_observation = ""
            self._set_board_state(self._inactive_state)
            await self._emit_upload_control(active=False)
        logger.info(f"Browser webcam state changed: enabled={enabled}")

    async def set_window_seconds(self, payload: dict[str, Any]) -> None:
        """Set the video window (chunk) size from the UI's chunk-size control."""
        raw = payload.get("seconds", payload.get("window_seconds"))
        try:
            seconds = float(raw)
        except (TypeError, ValueError):
            return
        self._window_seconds = max(1.0, min(60.0, seconds))
        logger.info(f"Webcam video window set to {self._window_seconds}s")

    def _conversation_context(self) -> str:
        """Recent conversation text for the webcam analyzer, or "" if unavailable."""
        if self._conversation_provider is None:
            return ""
        try:
            return (self._conversation_provider() or "").strip()
        except Exception as exc:
            logger.debug(f"Webcam conversation context unavailable: {exc}")
            return ""

    def current_visual_status(self) -> str:
        """A fresh, per-turn line stating what the assistant can see right now.

        Injected next to the user's turn (see the Speaker service) so each reply is
        grounded in the LATEST live view instead of the older, top-pinned board note.
        Reflects the camera state and most recent meaningful observation, mirroring
        the single "what you currently see" board state. The Speaker frames it, so this
        carries the state alone and no framing of its own.
        """
        if not self._enabled:
            return self._inactive_state
        state = self._board_state.strip()
        if not state or state in (self._inactive_state, self._starting_state):
            return self._starting_state
        return state

    @property
    def is_enabled(self) -> bool:
        """Whether this controller currently has an explicitly enabled live source."""
        return self._enabled

    @property
    def visual_availability(self) -> str:
        """Return a source-local availability value for Speaker grounding."""
        if not self._enabled:
            return "off"
        if self._board_state.strip() in ("", self._inactive_state, self._starting_state):
            return "loading"
        return "live"

    async def handle_summary_response(self, task_id: str, response: dict[str, Any]) -> bool:
        """Stream one completed frame observation to the client UI and pinned board."""
        if self._summary_task_id == task_id:
            self._summary_task_id = ""
            if self._detect_frame_changes:
                self._last_analyzed_fingerprint = self._dispatched_fingerprint
                self._dispatched_fingerprint = None
        if not self._enabled or self._summary_epoch != self._epoch:
            return False
        observation = str(response.get("observation") or "").strip()
        if not observation:
            return False
        focus = str(response.get("focus") or "").strip()
        visual_control = response.get("visual_control") if isinstance(response.get("visual_control"), dict) else {}
        frame = response.get("frame") if isinstance(response.get("frame"), dict) else {}
        self._latest_observation = observation
        if self._two_stage_initial_analysis and response.get("detail_level") == "fast":
            self._pending_full_analysis = True
            self._wake_summary_loop()
        if not _is_noop_observation(observation):
            self._set_board_state(observation)
        await self._emit_agent_update(
            observation=observation,
            focus=focus,
            visual_control=visual_control,
            frame=frame,
        )
        logger.debug(f"Webcam frame observation: observation_chars={len(observation)}")
        return True

    def _set_board_state(self, text: str) -> None:
        """Mirror the live webcam state into the Speaker's pinned board (deduped, no log dump).

        A camera-state note is this pipeline's own word on what the camera is doing, so it
        goes on the board as a plain fact; only a frame observation is the WebcamAgent's
        own output and stays quoted as untrusted data.
        """
        if text == self._board_state:
            return
        self._board_state = text
        self._board.set_findings(
            self._board_agent_name,
            text,
            trusted=text in (self._inactive_state, self._starting_state),
        )

    def _notify_frame_uploaded(self) -> None:
        """Wake the streaming loop when the browser uploads a fresh frame."""
        if not self._enabled:
            if self._explicitly_disabled:
                return
            self._enabled = True
            self._epoch += 1
            self._set_board_state(self._starting_state)
            if self._upload_control_task is None or self._upload_control_task.done():
                self._upload_control_task = asyncio.create_task(self._start_continuous_uploads())
            logger.info("Browser webcam state inferred enabled from fresh frame upload")
        self._wake_summary_loop()

    def _wake_summary_loop(self) -> None:
        """Wake the streaming loop."""
        if self._frame_event:
            self._frame_event.set()

    async def _run_summary_loop(self) -> None:
        """Send each fresh webcam frame to the WebcamAgent as soon as it arrives."""
        try:
            while True:
                if self._frame_event:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(
                            self._frame_event.wait(),
                            timeout=self._stream_interval_ms / 1000.0,
                        )
                    self._frame_event.clear()
                else:
                    await asyncio.sleep(self._stream_interval_ms / 1000.0)
                if self._summary_task_id or not self._enabled:
                    continue
                frame = latest_webcam_frame(self._session_id, source=self._frame_source)
                followup = self._pending_full_analysis
                if frame is None or (frame.sequence == self._last_dispatched_sequence and not followup):
                    continue
                elapsed_ms = (time.monotonic() - self._last_dispatched_at) * 1000
                fingerprint = _screen_fingerprint(frame.data) if self._detect_frame_changes else None
                if self._detect_frame_changes:
                    changed = _has_material_screen_change(self._last_analyzed_fingerprint, fingerprint)
                    refresh_due = elapsed_ms >= self._stable_refresh_interval_ms
                    if not changed and not refresh_due and not followup:
                        continue
                    logger.info(
                        "Shared-screen analysis triggered: "
                        f"sequence={frame.sequence}, changed={changed}, refresh_due={refresh_due}, "
                        f"elapsed_ms={elapsed_ms:.0f}"
                    )
                elif elapsed_ms < self._minimum_dispatch_interval_ms:
                    continue
                self._last_dispatched_sequence = frame.sequence
                self._last_dispatched_at = time.monotonic()
                dispatch_epoch = self._epoch
                try:
                    self._summary_task_id = await self._request_job(
                        self._worker_name,
                        name=self._task_name,
                        payload={
                            "session_id": self._session_id,
                            "frame": frame.metadata(),
                            "window_seconds": self._window_seconds,
                            "conversation_context": self._conversation_context(),
                            "source": self._frame_source,
                            "detail_level": "fast" if self._initial_fast_pending else "full",
                        },
                        timeout=60.0,
                    )
                    self._summary_epoch = dispatch_epoch
                    if self._initial_fast_pending:
                        self._initial_fast_pending = False
                    if followup:
                        self._pending_full_analysis = False
                    if self._detect_frame_changes:
                        self._dispatched_fingerprint = fingerprint
                    logger.debug(
                        f"{self._frame_source.capitalize()} frame dispatched: "
                        f"task_id={self._summary_task_id}, frame_sequence={frame.sequence}"
                    )
                except Exception as exc:
                    self._summary_task_id = ""
                    logger.warning(f"Failed to dispatch webcam frame: {exc}")
        except asyncio.CancelledError:
            logger.debug("Webcam streaming loop cancelled")

    async def _start_continuous_uploads(self) -> None:
        """Tell the browser to upload frames continuously at the streaming interval."""
        await self._emit_upload_control(active=True, interval_ms=self._stream_interval_ms, label="streaming")

    async def _emit_agent_update(
        self,
        *,
        observation: str,
        focus: str,
        visual_control: dict[str, Any],
        frame: dict[str, Any],
    ) -> None:
        """Emit the latest webcam frame observation to the client UI."""
        await self._queue_frame(
            RTVIServerMessageFrame(
                data={
                    "type": self._update_type,
                    "agent": self._worker_name,
                    "observation": observation,
                    "focus": focus,
                    "event_reason": "",
                    "proactive_message": "",
                    "visual_control": visual_control,
                    "propagated": True,
                    "frame": frame,
                }
            )
        )

    async def _emit_upload_control(self, *, active: bool, interval_ms: int = 0, label: str = "") -> None:
        """Tell the browser how to capture webcam frames for the current server state."""
        await self._queue_frame(
            RTVIServerMessageFrame(
                data={
                    "type": self._upload_control_type,
                    "action": "repeat" if active else "idle",
                    "active": active,
                    "mode": "stream" if active else "idle",
                    "interval_ms": interval_ms if active else 0,
                    "label": label,
                }
            )
        )
