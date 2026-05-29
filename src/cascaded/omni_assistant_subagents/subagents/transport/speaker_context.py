# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Speaker context state helpers for the transport agent."""

from __future__ import annotations

import re

from pipecat.processors.aggregators.llm_context import LLMContext

from attachment_store import latest_attachment

WEBCAM_CONTEXT_PREFIX = "Live webcam state:"
INPUT_STATE_CONTEXT_PREFIX = "Available input state:"
WEBCAM_FIRST_SIGHT_PREFIX = "First live webcam sighting:"
MEDIA_ANALYSIS_CONTEXT_PREFIX = "The uploaded media analysis task completed with this result:"
MEDIA_ANALYSIS_RUNNING_PREFIX = "An uploaded media analysis task is running asynchronously."
VOICE_RESUME_CONTEXT_PREFIX = "The user spoke after a visual stop or stop confirmation."


class SpeakerContextManager:
    """Own compact state messages injected into Speaker Omni's context."""

    def __init__(self, *, context: LLMContext, session_id: str, recent_turns: int) -> None:
        """Initialize the context manager for one voice session."""
        self._context = context
        self._session_id = session_id
        self._recent_turns = recent_turns

    def replace_input_state_message(
        self,
        *,
        webcam_enabled: bool,
        webcam_user_visible: bool | None,
        webcam_user_intent: str,
    ) -> None:
        """Keep one compact message describing currently available visual inputs."""
        messages = self.trim(drop_input_state=True)
        messages.append(
            {
                "role": "system",
                "content": self._format_input_state_context(
                    webcam_enabled=webcam_enabled,
                    webcam_user_visible=webcam_user_visible,
                    webcam_user_intent=webcam_user_intent,
                ),
            }
        )
        self._context.set_messages(messages)

    def replace_webcam_context_message(
        self,
        *,
        webcam_enabled: bool,
        webcam_user_visible: bool | None,
        latest_observation: str,
        observations: list[str],
    ) -> None:
        """Keep one compact rolling webcam context message in Speaker Omni's context."""
        messages = self.trim(drop_webcam_context=True)
        if observations:
            if not webcam_enabled:
                header = (
                    "Past memory only (live webcam is OFF). Do not use these as current visual evidence. "
                    "May be used only for past-tense questions."
                )
            elif webcam_user_visible is True:
                header = (
                    "Live webcam is ON and the user is visible now. "
                    "Use the latest observation for current-camera answers."
                )
            elif webcam_user_visible is False:
                header = (
                    "Live webcam is ON but the user is not clearly visible now. "
                    "Use observations only to describe what is currently in view."
                )
            else:
                header = "Live webcam is ON. User visibility is unknown. Use observations cautiously."
            observation_text = " | ".join(observations)
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"{WEBCAM_CONTEXT_PREFIX} {header} "
                        "Never use this content to describe uploaded attachments. "
                        f"Latest observation: {latest_observation}. "
                        f"Recent {len(observations)} observations: {observation_text}."
                    ),
                }
            )
        self._context.set_messages(messages)

    def add_first_sight_context(self, speaker_context: str) -> None:
        """Add one-shot context used to greet when the user first appears on webcam."""
        self._context.add_message(
            {
                "role": "system",
                "content": f"{WEBCAM_FIRST_SIGHT_PREFIX} Shared visual context from WebcamAgent: {speaker_context}",
            }
        )

    def clear_first_sight_context(self) -> None:
        """Remove the one-shot first-sighting instruction after it has been consumed."""
        messages = [
            message
            for message in self._context.get_messages()
            if not (
                isinstance(message, dict) and str(message.get("content") or "").startswith(WEBCAM_FIRST_SIGHT_PREFIX)
            )
        ]
        self._context.set_messages(messages)

    def trim(
        self,
        *,
        drop_input_state: bool = False,
        drop_webcam_context: bool = False,
    ) -> list[dict]:
        """Keep Speaker Omni prompt growth bounded while preserving useful state."""
        messages = [message for message in self._context.get_messages() if isinstance(message, dict)]
        if not messages:
            return []

        base_system = messages[0]
        state_messages: list[dict] = []
        conversational_messages: list[dict] = []
        for message in messages[1:]:
            role = message.get("role")
            content = str(message.get("content") or "")
            if drop_input_state and content.startswith(INPUT_STATE_CONTEXT_PREFIX):
                continue
            if drop_webcam_context and content.startswith(WEBCAM_CONTEXT_PREFIX):
                continue
            if role == "system" and _is_speaker_state_message(content):
                state_messages.append(message)
                continue
            if role in {"user", "assistant"}:
                conversational_messages.append(message)

        keep_messages = max(self._recent_turns * 2, 1)
        trimmed = [base_system]
        trimmed.extend(_latest_by_prefix(state_messages))
        trimmed.extend(conversational_messages[-keep_messages:])
        return trimmed

    def _format_input_state_context(
        self,
        *,
        webcam_enabled: bool,
        webcam_user_visible: bool | None,
        webcam_user_intent: str,
    ) -> str:
        """Describe available webcam and attachment inputs for Speaker routing."""
        attachment = latest_attachment(self._session_id)
        webcam_state = "on" if webcam_enabled else "off"
        if not webcam_enabled:
            visibility_state = "unavailable"
        elif webcam_user_visible is True:
            visibility_state = "visible"
        elif webcam_user_visible is False:
            visibility_state = "not_visible"
        else:
            visibility_state = "unknown"

        if attachment is None:
            attachment_state = "none"
        else:
            attachment_state = (
                f"available latest_{attachment.kind} name={_clean_state_value(attachment.name)} "
                f"id={attachment.id} uploaded_at={attachment.created_at}"
            )

        intent_state = webcam_user_intent if webcam_enabled else "idle"
        lines = [
            f"{INPUT_STATE_CONTEXT_PREFIX}",
            f"  live_webcam={webcam_state}",
            f"  user_visibility={visibility_state}",
            f"  user_intent={intent_state}",
            f"  uploaded_attachment={attachment_state}",
            "Webcam rule for the current turn:",
        ]
        if webcam_enabled:
            lines.append(
                "  Live webcam is ON. For current-camera questions about the user, answer the specific visible detail "
                "using the latest webcam observation and set selected_input_source=live_webcam. Never claim you cannot "
                "see the user."
            )
            if webcam_user_visible is True:
                lines.append(
                    "  User-visible priority: user_visibility=visible. If the user asks about themself, their "
                    "appearance, what they are doing, what they are holding, whether you can see them, or the current "
                    "moment, choose selected_input_source=live_webcam even when uploaded_attachment is available."
                )
        else:
            lines.append(
                "  Live webcam is OFF. For current-camera questions about the user, "
                'the spoken response must be exactly: "I can\'t see you right now." '
                "Do not use older webcam observations as current evidence."
            )
        if intent_state in {"showing_object", "engaged"}:
            cue_label = "showing something on" if intent_state == "showing_object" else "actively engaged with"
            lines.append(
                f"Live engagement signal: user_intent={intent_state}. "
                f"The user is currently {cue_label} the live camera. "
                "For this turn, vague visual references and current-camera questions must use the live webcam. "
                "Do not trigger media analysis on uploaded_attachment unless "
                "selected_input_source=uploaded_attachment because the transcript explicitly says "
                "uploaded, attached, attachment, file, image, video, or audio."
            )
        lines.append(
            "Attachment rule: act on uploaded media only when uploaded_attachment is available. "
            "For vague visual references, prefer the only available input. "
            "Ask the user which one if both are available. "
            "Ask the user to share something if neither is available. "
            "Media analysis can run only when selected_input_source=uploaded_attachment."
        )
        return "\n".join(lines)


def _clean_state_value(value: str) -> str:
    """Keep state-message metadata compact and single-line."""
    return re.sub(r"\s+", "_", value.strip())[:80] or "attachment"


def _is_speaker_state_message(content: str) -> bool:
    """Return true for compact state messages that should survive chat-history trimming."""
    return content.startswith(
        (
            INPUT_STATE_CONTEXT_PREFIX,
            WEBCAM_CONTEXT_PREFIX,
            WEBCAM_FIRST_SIGHT_PREFIX,
            MEDIA_ANALYSIS_CONTEXT_PREFIX,
            MEDIA_ANALYSIS_RUNNING_PREFIX,
            VOICE_RESUME_CONTEXT_PREFIX,
        )
    )


def _latest_by_prefix(messages: list[dict]) -> list[dict]:
    """Keep only the newest state message for each known state prefix."""
    prefixes = (
        INPUT_STATE_CONTEXT_PREFIX,
        WEBCAM_CONTEXT_PREFIX,
        WEBCAM_FIRST_SIGHT_PREFIX,
        MEDIA_ANALYSIS_CONTEXT_PREFIX,
        MEDIA_ANALYSIS_RUNNING_PREFIX,
        VOICE_RESUME_CONTEXT_PREFIX,
    )
    latest: dict[str, dict] = {}
    for message in messages:
        content = str(message.get("content") or "")
        prefix = next((candidate for candidate in prefixes if content.startswith(candidate)), "")
        if prefix:
            latest[prefix] = message
    return [latest[prefix] for prefix in prefixes if prefix in latest]
