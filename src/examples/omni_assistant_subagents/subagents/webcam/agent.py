# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Browser webcam vision worker subagent."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger
from pipecat.bus.messages import BusJobRequestMessage
from pipecat.pipeline.job_decorator import job
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.workers.base_worker import BaseWorker

from examples.omni_assistant.nvidia_omni_multimodal_service import (
    NvidiaOmniService,
    NvidiaOmniSettings,
    image_message_part,
    text_message_part,
)
from examples.omni_assistant_subagents.subagents.utils import (
    normalize_user_intent,
    normalize_visual_control,
)
from utils import parse_env_bool, parse_env_float, parse_env_int
from webcam_frame_store import WebcamFrame, get_webcam_frame

WEBCAM_SUMMARY_TASK_NAME = "summarize_webcam_frame"

_SUMMARY_SYSTEM_PROMPT = (
    "Inspect the current webcam frame and summarize task-relevant visible details. "
    "The visible person is the current user. Do not use markdown or bullets. Return strict JSON: "
    '{"observation": "...", "event_reason": "...", '
    '"user_visible": true, "user_intent": "idle", "speaker_context": "", '
    '"visual_control": {"intent": "none", "confidence": 0.0, "reason": ""}}'
)


class WebcamAgent(BaseWorker):
    """Worker that summarizes browser webcam snapshots with Nemotron Omni."""

    AGENT_NAME = "omni_webcam"

    def __init__(
        self,
        name: str | None = None,
        *,
        api_key: str,
        base_url: str,
        model_id: str,
        extra_params: dict[str, Any] | None = None,
        summary_system_prompt: str = "",
    ) -> None:
        """Initialize the webcam vision worker."""
        super().__init__(name or self.AGENT_NAME, active=True)
        self._base_url = base_url
        self._model_id = model_id
        summary_reasoning = parse_env_bool("WEBCAM_SUMMARY_REASONING", default=False)
        self._summary_system_prompt = summary_system_prompt.strip() or _SUMMARY_SYSTEM_PROMPT
        self._summary_max_tokens = parse_env_int("WEBCAM_SUMMARY_MAX_TOKENS", 256, min_value=32)
        self._temporal_context_limit = parse_env_int("WEBCAM_TEMPORAL_CONTEXT_LIMIT", 3, min_value=1)
        self._temperature = parse_env_float("WEBCAM_ANALYZER_TEMPERATURE", 0.2, min_value=0.0)
        self._last_published_observations: dict[str, str] = {}
        self._recent_observations: dict[str, list[dict[str, str | int]]] = {}
        omni_extra = dict(extra_params or {})
        extra_body = dict(omni_extra.get("extra_body") or {})
        extra_body["chat_template_kwargs"] = {
            **dict(extra_body.get("chat_template_kwargs") or {}),
            "enable_thinking": summary_reasoning,
        }
        omni_extra["extra_body"] = extra_body
        self._omni = NvidiaOmniService(
            api_key=api_key,
            base_url=base_url,
            extra=omni_extra,
            settings=NvidiaOmniSettings(
                model=model_id,
                max_tokens=self._summary_max_tokens,
                temperature=self._temperature,
                input_modalities=("image", "text"),
                stream=False,
            ),
        )

    @job(name=WEBCAM_SUMMARY_TASK_NAME)
    async def summarize_webcam_frame(self, message: BusJobRequestMessage) -> None:
        """Summarize one webcam frame for rolling scene memory."""
        payload = message.payload or {}
        frame_metadata = payload.get("frame") if isinstance(payload.get("frame"), dict) else {}
        session_id = str(payload.get("session_id") or "").strip()
        frame_id = str(frame_metadata.get("id") or "").strip()
        assistant_speaking = bool(payload.get("assistant_speaking"))
        frame = get_webcam_frame(session_id, frame_id)
        event_reason = ""
        speaker_context = ""
        user_visible = False
        user_intent = "idle"
        visual_control: dict[str, Any] = normalize_visual_control({})
        if frame is None:
            observation = ""
        else:
            try:
                recent_observations = self._recent_observations.get(session_id, [])
                (
                    observation,
                    event_reason,
                    user_visible,
                    user_intent,
                    speaker_context,
                    visual_control,
                ) = await self._summarize_frame(
                    frame,
                    previous_observation=self._last_published_observations.get(session_id, ""),
                    recent_observations=recent_observations,
                    assistant_speaking=assistant_speaking,
                    first_sighting=bool(payload.get("first_sighting")),
                )
            except Exception as exc:
                logger.exception(f"Webcam summary request failed: {exc}")
                observation = ""
        if observation:
            self._last_published_observations[session_id] = observation
            self._remember_observation(session_id, frame, observation, event_reason)

        await self.send_job_response(
            message.job_id,
            {
                "mode": "summary",
                "publish": bool(observation),
                "observation": observation,
                "event_reason": event_reason,
                "proactive_message": "",
                "user_visible": user_visible,
                "user_intent": user_intent,
                "speaker_context": speaker_context,
                "visual_control": visual_control,
                "frame": frame_metadata,
            },
        )

    async def _summarize_frame(
        self,
        frame: WebcamFrame,
        *,
        previous_observation: str,
        recent_observations: list[dict[str, str | int]],
        assistant_speaking: bool,
        first_sighting: bool,
    ) -> tuple[str, str, bool, str, str, dict[str, Any]]:
        """Call Omni for a short non-spoken scene summary."""
        temporal_context = _format_temporal_context(recent_observations)
        context = LLMContext(
            messages=[
                {"role": "system", "content": self._summary_system_prompt},
                {
                    "role": "user",
                    "content": [
                        image_message_part(frame.data, mime_type=frame.content_type),
                        text_message_part(
                            "Previous published observation: "
                            f"{previous_observation or 'none yet'}. "
                            f"Recent visual timeline, oldest to newest: {temporal_context}. "
                            f"Current frame sequence: {frame.sequence}; captured at {frame.created_at}. "
                            f"Assistant currently speaking: {'yes' if assistant_speaking else 'no'}. "
                            f"First visible-user sighting candidate: {'yes' if first_sighting else 'no'}. "
                            "Compare the current frame with the recent timeline. Track what the user "
                            "was holding or doing before versus what the user is holding or doing now. "
                            "When the assistant is speaking, treat a raised hand or open palm toward the "
                            "camera as a likely stop-control cue unless it is clearly only a wave, with "
                            "confidence 0.75 or higher. "
                            "Return only the strict JSON requested by the system prompt. Keep observation "
                            "to one sentence, event_reason short, and visual_control.reason short."
                        ),
                    ],
                },
            ]
        )
        logger.debug(
            f"Webcam summary Omni request: base_url={self._base_url}, model={self._model_id}, bytes={len(frame.data)}"
        )
        result = await self._omni.run_multimodal_inference(
            context,
            max_tokens=self._summary_max_tokens,
            temperature=self._temperature,
            stream=False,
        )
        raw_content = result.text.strip()
        payload = _extract_json_payload(raw_content)
        if not payload:
            return raw_content, "regular scene update", False, "idle", "", normalize_visual_control({})
        observation = str(payload.get("observation") or "").strip()
        event_reason = str(payload.get("event_reason") or "").strip() or "regular scene update"
        user_visible = payload.get("user_visible") is True
        user_intent = normalize_user_intent(payload.get("user_intent"))
        speaker_context = str(payload.get("speaker_context") or "").strip()
        visual_control = payload.get("visual_control") if isinstance(payload.get("visual_control"), dict) else {}
        return (
            observation,
            event_reason,
            user_visible,
            user_intent,
            speaker_context,
            normalize_visual_control(visual_control),
        )

    def _remember_observation(
        self,
        session_id: str,
        frame: WebcamFrame,
        observation: str,
        event_reason: str,
    ) -> None:
        """Keep a small temporal scene history for the next webcam summary."""
        if not session_id:
            return
        history = self._recent_observations.setdefault(session_id, [])
        history.append(
            {
                "sequence": frame.sequence,
                "created_at": frame.created_at,
                "observation": observation,
                "event_reason": event_reason,
            }
        )
        del history[: -self._temporal_context_limit]


def _format_temporal_context(observations: list[dict[str, str | int]]) -> str:
    """Format recent webcam observations as a compact timeline for the model."""
    if not observations:
        return "none yet"
    entries: list[str] = []
    for observation in observations:
        sequence = observation.get("sequence", "?")
        created_at = str(observation.get("created_at") or "")
        summary = str(observation.get("observation") or "").strip()
        event_reason = str(observation.get("event_reason") or "").strip()
        if not summary:
            continue
        entry = f"frame {sequence}"
        if created_at:
            entry += f" at {created_at}"
        entry += f": {summary}"
        if event_reason:
            entry += f" Change note: {event_reason}"
        entries.append(entry)
    return " | ".join(entries) if entries else "none yet"


def _extract_json_payload(text: str) -> dict[str, Any]:
    """Extract a JSON object from a strict or fenced model response."""
    cleaned = text.strip()
    if not cleaned:
        return {}
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
