# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Visual stop/continue state machine for transport orchestration."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger
from pipecat.processors.aggregators.llm_context import LLMContext

from cascaded.omni_assistant_subagents.subagents.utils import normalize_visual_control
from utils import parse_env_float

VISUAL_CONTROL_LISTENING = "listening"
VISUAL_CONTROL_CONFIRMING_STOP = "confirming_stop"
VISUAL_CONTROL_STOPPED = "visually_stopped"


class VisualControlController:
    """Own webcam-driven stop, confirm, and continue transitions."""

    def __init__(
        self,
        *,
        context: LLMContext,
        emit_update: Callable[..., Awaitable[None]],
        interrupt_for_stop: Callable[[], Awaitable[None]],
        ask_stop_confirmation: Callable[[], Awaitable[None]],
        continue_after_visual_resume: Callable[[], Awaitable[None]],
        start_pending_media_analysis: Callable[[], Awaitable[None]],
    ) -> None:
        """Initialize visual-control thresholds and callbacks."""
        self._context = context
        self._emit_update = emit_update
        self._interrupt_for_stop = interrupt_for_stop
        self._ask_stop_confirmation = ask_stop_confirmation
        self._continue_after_visual_resume = continue_after_visual_resume
        self._start_pending_media_analysis = start_pending_media_analysis
        self._state = VISUAL_CONTROL_LISTENING
        self._stop_interrupt_confidence = parse_env_float(
            "WEBCAM_VISUAL_STOP_INTERRUPT_CONFIDENCE", 0.75, min_value=0.0
        )
        self._stop_confirm_confidence = parse_env_float("WEBCAM_VISUAL_STOP_CONFIRM_CONFIDENCE", 0.45, min_value=0.0)
        self._continue_confidence = parse_env_float("WEBCAM_VISUAL_CONTINUE_CONFIDENCE", 0.75, min_value=0.0)
        self._cooldown_secs = parse_env_float("WEBCAM_VISUAL_CONTROL_COOLDOWN_SECONDS", 2.0, min_value=0.1)
        self._last_action_at = 0.0
        self._last_intent_observed = "none"

    @property
    def state(self) -> str:
        """Return the current visual-control state."""
        return self._state

    def is_stopped(self) -> bool:
        """Return whether visual control currently suppresses assistant speech."""
        return self._state == VISUAL_CONTROL_STOPPED

    async def reset_by_user_voice(self) -> None:
        """Resume normal visual listening after an explicit user voice turn."""
        if self._state == VISUAL_CONTROL_LISTENING:
            return
        previous_state = self._state
        self._state = VISUAL_CONTROL_LISTENING
        # Keep cooldown alive from now so the same lingering stop pose cannot
        # immediately re-trigger interruption right after the user spoke.
        self._last_action_at = time.monotonic()
        # Require a non-stop frame before another stop can trigger.
        self._last_intent_observed = "stop"
        logger.info(f"Visual barge-in state reset by user voice: previous_state={previous_state}")
        self._context.add_message(
            {
                "role": "system",
                "content": (
                    "The user spoke after a visual stop or stop confirmation. "
                    "Resume normal listening and allow future visual stop signals."
                ),
            }
        )
        await self._emit_update(
            visual_control=normalize_visual_control({}),
            action="voice_resume",
            frame={},
            state=self._state,
        )

    async def handle(self, visual_control: dict[str, Any], *, frame: dict[str, Any]) -> None:
        """Apply LLM-scored visual barge-in control from the webcam stream."""
        intent = str(visual_control.get("intent") or "none")
        confidence = float(visual_control.get("confidence") or 0.0)
        reason = str(visual_control.get("reason") or "")
        now = time.monotonic()
        previous_intent = self._last_intent_observed
        self._last_intent_observed = intent

        if intent == "none":
            if self._state == VISUAL_CONTROL_CONFIRMING_STOP and now - self._last_action_at >= self._cooldown_secs:
                self._state = VISUAL_CONTROL_LISTENING
                await self._emit_update(
                    visual_control=visual_control,
                    action="stop_confirmation_expired",
                    frame=frame,
                    state=self._state,
                )
                await self._start_pending_media_analysis()
            return

        if intent == previous_intent:
            logger.debug(
                f"Skipping visual_control={intent} because previous observed intent was already {previous_intent}"
            )
            return

        cooldown_active = now - self._last_action_at < self._cooldown_secs
        should_bypass_cooldown = (
            intent == "continue"
            and confidence >= self._continue_confidence
            and self._state in {VISUAL_CONTROL_CONFIRMING_STOP, VISUAL_CONTROL_STOPPED}
        ) or (
            intent == "stop"
            and confidence >= self._stop_interrupt_confidence
            and self._state == VISUAL_CONTROL_CONFIRMING_STOP
        )
        if cooldown_active and not should_bypass_cooldown:
            return

        if intent == "stop":
            await self._handle_stop(visual_control, confidence, reason, frame, now)
            return

        if (
            intent == "continue"
            and confidence >= self._continue_confidence
            and self._state in {VISUAL_CONTROL_CONFIRMING_STOP, VISUAL_CONTROL_STOPPED}
        ):
            await self._handle_continue(visual_control, frame, now)

    async def _handle_stop(
        self,
        visual_control: dict[str, Any],
        confidence: float,
        reason: str,
        frame: dict[str, Any],
        now: float,
    ) -> None:
        if confidence >= self._stop_interrupt_confidence:
            if self._state != VISUAL_CONTROL_STOPPED:
                self._state = VISUAL_CONTROL_STOPPED
                self._last_action_at = now
                self._context.add_message(
                    {
                        "role": "system",
                        "content": (
                            "The user visually asked the assistant to stop speaking now. "
                            f"Confidence: {confidence:.2f}. Reason: {reason or 'clear visual stop signal'}."
                        ),
                    }
                )
                await self._emit_update(
                    visual_control=visual_control,
                    action="stop_interrupt",
                    frame=frame,
                    state=self._state,
                )
                await self._interrupt_for_stop()
            return

        if confidence >= self._stop_confirm_confidence and self._state == VISUAL_CONTROL_LISTENING:
            self._state = VISUAL_CONTROL_CONFIRMING_STOP
            self._last_action_at = now
            self._context.add_message(
                {
                    "role": "system",
                    "content": (
                        "A possible visual stop signal was detected. "
                        f"Confidence: {confidence:.2f}. Reason: {reason or 'ambiguous visual stop signal'}."
                    ),
                }
            )
            await self._emit_update(
                visual_control=visual_control,
                action="stop_confirm",
                frame=frame,
                state=self._state,
            )
            await self._ask_stop_confirmation()

    async def _handle_continue(self, visual_control: dict[str, Any], frame: dict[str, Any], now: float) -> None:
        self._state = VISUAL_CONTROL_LISTENING
        self._last_action_at = now
        self._context.add_message(
            {
                "role": "user",
                "content": (
                    "The user visually asked the assistant to continue speaking. "
                    "Briefly acknowledge the visual cue, then continue the prior thread or any pending result."
                ),
            }
        )
        await self._emit_update(
            visual_control=visual_control,
            action="continue_resume",
            frame=frame,
            state=self._state,
        )
        await self._continue_after_visual_resume()
        await self._start_pending_media_analysis()
