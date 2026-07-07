# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Uploaded-media analysis dispatch and follow-up emission."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger
from pipecat.bus.messages import BusJobResponseMessage
from pipecat.frames.frames import LLMFullResponseEndFrame, LLMFullResponseStartFrame, LLMTextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame

from attachment_store import latest_attachment
from examples.omni_assistant_subagents.subagents.media_analyzer import MEDIA_ANALYSIS_TASK_NAME, MediaAnalyzerWorker
from examples.omni_assistant_subagents.subagents.transport.speaker_context import MEDIA_ANALYSIS_RUNNING_PREFIX


class MediaAnalysisController:
    """Own queued uploaded-media analysis and client-visible follow-up output."""

    def __init__(
        self,
        *,
        session_id: str,
        context: LLMContext,
        request_job: Callable[..., Awaitable[str]],
        queue_frame: Callable[[Any], Awaitable[None]],
        is_visual_control_stopped: Callable[[], bool],
        followup_delay_secs: float,
    ) -> None:
        """Initialize uploaded-media dispatch state for one session."""
        self._session_id = session_id
        self._context = context
        self._request_job = request_job
        self._queue_frame = queue_frame
        self._is_visual_control_stopped = is_visual_control_stopped
        self._followup_delay_secs = followup_delay_secs
        self._pending_transcript = ""
        self._pending_prompt = ""
        self._pending_action = "none"
        self._active_attachment_id = ""
        self._completed_attachment_id = ""

    def has_uploaded_attachment(self) -> bool:
        """Return whether this session currently has an uploaded attachment."""
        return latest_attachment(self._session_id) is not None

    async def queue_prompt(
        self,
        transcript: str,
        prompt: str,
        action: str,
        selected_input_source: str,
    ) -> None:
        """Queue Speaker Omni's hidden analyzer prompt after its acknowledgement closes."""
        cleaned_transcript = transcript.strip()
        cleaned_prompt = prompt.strip()
        if not (cleaned_prompt or cleaned_transcript):
            return
        if selected_input_source != "uploaded_attachment":
            logger.info(
                "Ignoring LLM-selected media analysis because selected_input_source is not uploaded_attachment: "
                f"source={selected_input_source!r}, transcript={transcript!r}"
            )
            self._pending_transcript = ""
            self._pending_prompt = ""
            self._pending_action = "none"
            return
        media_action = action if action in {"new", "rerun"} else "new"
        attachment = latest_attachment(self._session_id)
        if attachment is None:
            logger.info(
                f"Ignoring LLM-selected media analysis because no attachment is available: transcript={transcript!r}"
            )
            return
        attachment_id = attachment.id
        if attachment_id == self._active_attachment_id:
            logger.info(
                "Ignoring media analysis prompt because analysis is already active: "
                f"attachment_id={attachment_id}, action={media_action}, transcript={transcript!r}"
            )
            return
        self._pending_transcript = cleaned_transcript
        self._pending_prompt = cleaned_prompt
        self._pending_action = media_action
        logger.info(f"Queued LLM-selected media analysis after ack: action={media_action}, transcript={transcript!r}")

    async def start_pending(self) -> None:
        """Dispatch the LLM-selected analyzer after the ack turn has completed."""
        transcript = self._pending_transcript
        prompt = self._pending_prompt
        action = self._pending_action
        self._pending_transcript = ""
        self._pending_prompt = ""
        self._pending_action = "none"
        if not transcript:
            logger.debug("Bot stopped speaking; no pending media analysis queued")
            return
        attachment = latest_attachment(self._session_id)
        if attachment is None:
            logger.info("LLM selected media analysis, but no attachment is available")
            return
        attachment_metadata = attachment.metadata()
        attachment_id = str(attachment_metadata.get("id") or "")
        if attachment_id == self._active_attachment_id:
            logger.info(
                "Skipping duplicate media analysis dispatch because analysis is already active: "
                f"attachment_id={attachment_id}, action={action}, transcript={transcript!r}"
            )
            return

        self._active_attachment_id = attachment_id
        task_id = await self._request_job(
            MediaAnalyzerWorker.AGENT_NAME,
            name=MEDIA_ANALYSIS_TASK_NAME,
            payload={
                "transcript": transcript,
                "session_id": self._session_id,
                "attachment": attachment_metadata,
                "analysis_prompt": prompt or _default_analysis_prompt(transcript, attachment_metadata, action=action),
                "analysis_action": action,
            },
            timeout=120.0,
        )
        logger.info(
            "Media analysis dispatched: "
            f"task_id={task_id}, action={action}, "
            f"attachment={attachment_metadata.get('name')}, transcript={transcript!r}"
        )
        self._context.add_message(
            {
                "role": "system",
                "content": (
                    f"{MEDIA_ANALYSIS_RUNNING_PREFIX} "
                    "If the user asks for status before it completes, say that it is still running."
                ),
            }
        )

    async def clear_pending_on_interruption(self) -> None:
        """Cancel pending post-ack media work when the ack was interrupted by speech."""
        if not self._pending_transcript:
            return
        logger.info(
            "Clearing pending media analysis because the assistant ack was interrupted: "
            f"transcript={self._pending_transcript!r}"
        )
        self._pending_transcript = ""
        self._pending_prompt = ""
        self._pending_action = "none"

    async def handle_job_response(self, message: BusJobResponseMessage) -> bool:
        """Emit uploaded-media job results. Return whether the response was handled."""
        response = message.response or {}
        answer = str(response.get("answer") or "").strip()
        reasoning = str(response.get("reasoning") or "").strip()
        query = str(response.get("query") or "").strip()
        transcript = str(response.get("transcript") or "").strip()
        attachment = response.get("attachment") if isinstance(response.get("attachment"), dict) else {}
        if not answer:
            return False
        await self._emit_analysis_response(
            answer,
            transcript,
            task_id=message.job_id,
            agent=str(getattr(message, "source", "") or MediaAnalyzerWorker.AGENT_NAME),
            attachment=attachment,
            reasoning=reasoning,
            query=query,
        )
        attachment_id = str(attachment.get("id") or "")
        if attachment_id:
            self._completed_attachment_id = attachment_id
            if self._active_attachment_id == attachment_id:
                self._active_attachment_id = ""
        return True

    async def _emit_analysis_response(
        self,
        answer: str,
        transcript: str,
        *,
        task_id: str,
        agent: str,
        attachment: dict[str, Any],
        reasoning: str,
        query: str,
    ) -> None:
        """Emit analysis completion as its own assistant turn."""
        response_text = _format_analysis_response(answer, attachment)
        spoken_answer = answer.strip()
        kind = str(attachment.get("kind") or "media")
        name = str(attachment.get("name") or "")
        attachment_label = f"uploaded {kind}" + (f" '{name}'" if name else "")
        self._context.add_message(
            {
                "role": "system",
                "content": (
                    f"The uploaded media analysis task completed for the {attachment_label}. "
                    f"Result describes ONLY this attachment: {spoken_answer} "
                    "Do not reuse these details when answering questions about the live webcam."
                ),
            }
        )
        await asyncio.sleep(self._followup_delay_secs)
        if not self._is_visual_control_stopped():
            await self._queue_frame(LLMFullResponseStartFrame())
            await self._queue_frame(LLMTextFrame(text=response_text))
            await self._queue_frame(LLMFullResponseEndFrame())
        else:
            logger.info("Suppressing media analysis speech because the user visually asked the assistant to stop")
        await self._queue_frame(
            RTVIServerMessageFrame(
                data={
                    "type": "agent-task-update",
                    "task_id": task_id,
                    "agent": agent,
                    "status": "done",
                    "stage": "complete",
                    "detail": spoken_answer,
                    "attachment": attachment,
                    "query": query,
                    "reasoning": reasoning,
                    "response": spoken_answer,
                    "spoken_response": response_text,
                }
            )
        )


def _format_analysis_response(answer: str, attachment: dict[str, Any]) -> str:
    """Phrase uploaded media results like a follow-up assistant turn."""
    spoken_answer = answer.strip()
    kind = str(attachment.get("kind") or "media")
    if kind == "video":
        return f"Here is what I found in the uploaded video: {spoken_answer}"
    if kind == "audio":
        return f"Here is what I found in the uploaded audio: {spoken_answer}"
    if kind == "image":
        return f"Here is what I found in the uploaded image: {spoken_answer}"
    return f"Here is what I found in the uploaded media: {spoken_answer}"


def _default_analysis_prompt(transcript: str, attachment: dict[str, Any], *, action: str) -> str:
    kind = str(attachment.get("kind") or "media")
    action_hint = "Re-analyze" if action == "rerun" else "Inspect"
    return (
        f"{action_hint} the uploaded {kind} and answer the user's request: {transcript}. "
        "Describe only what is supported by the media. Be concise and mention uncertainty when needed. "
        "Return plain spoken-aloud prose for TTS. Do not use markdown, bullets, asterisks, or formatting symbols."
    )
