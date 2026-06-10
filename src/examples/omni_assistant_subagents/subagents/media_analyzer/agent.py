# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Nemotron Omni media analyzer worker subagent."""

from __future__ import annotations

from typing import Any

from loguru import logger
from pipecat.bus.messages import BusFrameMessage, BusJobRequestMessage
from pipecat.pipeline.job_decorator import job
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame
from pipecat.workers.base_worker import BaseWorker

from attachment_store import Attachment, get_attachment
from examples.omni_assistant.nvidia_omni_multimodal_service import (
    NvidiaOmniService,
    NvidiaOmniSettings,
    media_message_part,
    text_message_part,
)
from utils import parse_env_float, parse_env_int

MEDIA_ANALYSIS_TASK_NAME = "analyze_media"
_SYSTEM_PROMPT = (
    "You are a careful media analysis worker. Inspect the provided media and answer the task. "
    "Only describe details supported by the media. If uncertain, say so. "
    "Answer in two or three short spoken sentences for TTS. Avoid dense lists, slash-separated terms, "
    "parentheses, markdown, bullets, numbered lists, asterisks, bold text, code formatting, or other visual symbols."
)


class MediaAnalyzerWorker(BaseWorker):
    """Worker that analyzes uploaded media with Nemotron Omni and reports over the bus."""

    AGENT_NAME = "omni_media_analyzer"

    def __init__(
        self,
        name: str | None = None,
        *,
        api_key: str,
        base_url: str,
        model_id: str,
        extra_params: dict[str, Any] | None = None,
        system_prompt: str = "",
    ) -> None:
        """Configure the OpenAI-compatible client and analyzer defaults."""
        super().__init__(name or self.AGENT_NAME, active=True)
        self._base_url = base_url
        self._model_id = model_id
        self._system_prompt = system_prompt.strip() or _SYSTEM_PROMPT
        self._max_tokens = parse_env_int("MEDIA_ANALYZER_MAX_TOKENS", 2048, min_value=64)
        self._temperature = parse_env_float("MEDIA_ANALYZER_TEMPERATURE", 0.2, min_value=0.0)
        omni_extra = dict(extra_params or {})
        extra_body = dict(omni_extra.get("extra_body") or {})
        extra_body["chat_template_kwargs"] = {
            **dict(extra_body.get("chat_template_kwargs") or {}),
            "enable_thinking": True,
        }
        omni_extra["extra_body"] = extra_body
        self._omni = NvidiaOmniService(
            api_key=api_key,
            base_url=base_url,
            extra=omni_extra,
            settings=NvidiaOmniSettings(
                model=model_id,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                input_modalities=("image", "audio", "video", "text"),
                stream=True,
            ),
        )

    @job(name=MEDIA_ANALYSIS_TASK_NAME)
    async def analyze_media(self, message: BusJobRequestMessage) -> None:
        """Analyze one uploaded attachment."""
        payload = message.payload or {}
        requester = message.source
        attachment = payload.get("attachment") if isinstance(payload.get("attachment"), dict) else {}
        transcript = str(payload.get("transcript") or "").strip()
        prompt = str(payload.get("analysis_prompt") or "").strip()
        query = prompt or transcript
        session_id = str(payload.get("session_id") or "").strip()
        attachment_id = str(attachment.get("id") or "").strip()
        reasoning = ""

        await self._emit_update(
            target=requester,
            task_id=message.job_id,
            status="running",
            stage="started",
            detail=f"Analyzing {attachment.get('kind', 'media')} attachment...",
            attachment=attachment,
            query=query,
        )

        stored_attachment = get_attachment(session_id, attachment_id)
        if stored_attachment is None:
            answer = "I could not access the uploaded media for analysis."
        else:
            try:
                answer, reasoning = await self._analyze_attachment(
                    stored_attachment,
                    query,
                    requester=requester,
                    task_id=message.job_id,
                    attachment_metadata=attachment,
                )
            except Exception as exc:
                logger.exception(f"Media analyzer Omni request failed: {exc}")
                answer = "I could not analyze the uploaded media because the analyzer request failed."
                reasoning = ""

        await self.send_job_response(
            message.job_id,
            {
                "answer": answer,
                "reasoning": reasoning,
                "query": query,
                "transcript": transcript,
                "attachment": attachment,
            },
        )

    async def _analyze_attachment(
        self,
        attachment: Attachment,
        prompt: str,
        *,
        requester: str,
        task_id: str,
        attachment_metadata: dict,
    ) -> tuple[str, str]:
        """Call the multimodal Omni endpoint for one attachment."""
        context = LLMContext(
            messages=[
                {"role": "system", "content": self._system_prompt},
                {
                    "role": "user",
                    "content": [
                        media_message_part(
                            attachment.data, modality=attachment.kind, mime_type=attachment.content_type
                        ),
                        text_message_part(prompt),
                    ],
                },
            ]
        )
        logger.info(
            "Media analyzer Omni request: "
            f"base_url={self._base_url}, model={self._model_id}, kind={attachment.kind}, bytes={len(attachment.data)}"
        )
        reasoning = ""

        async def on_reasoning_delta(reasoning_delta: str) -> None:
            nonlocal reasoning
            reasoning += reasoning_delta
            await self._emit_update(
                target=requester,
                task_id=task_id,
                status="running",
                stage="reasoning",
                detail="Reasoning about the uploaded media...",
                attachment=attachment_metadata,
                reasoning_delta=reasoning_delta,
            )

        async def on_text_delta(answer_delta: str) -> None:
            await self._emit_update(
                target=requester,
                task_id=task_id,
                status="running",
                stage="response",
                detail="Drafting media analysis response...",
                attachment=attachment_metadata,
                response_delta=answer_delta,
            )

        result = await self._omni.run_multimodal_inference(
            context,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            stream=True,
            on_reasoning_delta=on_reasoning_delta,
            on_text_delta=on_text_delta,
        )
        answer = result.text.strip()
        reasoning = result.reasoning or reasoning
        if not answer:
            return "The analyzer did not return a usable media description.", reasoning.strip()
        logger.info(f"Media analyzer Omni answer: {answer[:500]!r}")
        return answer, reasoning.strip()

    async def _emit_update(
        self,
        *,
        target: str,
        task_id: str,
        status: str,
        stage: str,
        detail: str,
        attachment: dict,
        query: str = "",
        reasoning_delta: str = "",
        response_delta: str = "",
        reasoning: str = "",
        response: str = "",
    ) -> None:
        """Emit semantic worker progress as a client-visible bus update."""
        await self.bus.send(
            BusFrameMessage(
                source=self.name,
                target=target,
                direction=FrameDirection.DOWNSTREAM,
                frame=RTVIServerMessageFrame(
                    data={
                        "type": "agent-task-update",
                        "task_id": task_id,
                        "agent": self.name,
                        "status": status,
                        "stage": stage,
                        "detail": detail,
                        "attachment": attachment,
                        "query": query,
                        "reasoning_delta": reasoning_delta,
                        "response_delta": response_delta,
                        "reasoning": reasoning,
                        "response": response,
                    }
                ),
            )
        )
