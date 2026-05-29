# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Nemotron Omni assistant decomposed into Pipecat Subagents.

The session is split into four cooperating agents sharing a single
``AgentBus``:

* ``OmniTransportAgent`` owns transport I/O, VAD/turn detection, TTS, and
  routes user frames to ``SpeakerOmniAgent`` through a ``BusBridge``.
* ``SpeakerOmniAgent`` wraps ``NvidiaOmniMultimodalService`` and is the only
  agent allowed to emit spoken responses.
* ``MediaAnalyzerWorker`` analyzes uploaded image/audio/video attachments
  on demand and reports back over the bus.
* ``WebcamAgent`` produces rolling scene summaries from the browser webcam stream.

The transport agent funnels analyzer results back to the speaker so the
assistant remains the single source of TTS output.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.runner.types import RunnerArguments
from pipecat_subagents.runner import AgentRunner

from cascaded.omni_assistant.pipeline import _create_transport
from cascaded.omni_assistant_subagents.subagents.media_analyzer import MediaAnalyzerWorker
from cascaded.omni_assistant_subagents.subagents.speaker import SpeakerOmniAgent
from cascaded.omni_assistant_subagents.subagents.transport import OmniTransportAgent
from cascaded.omni_assistant_subagents.subagents.webcam import WebcamAgent
from utils import is_nvcf, load_prompt_catalog, load_service_entry, parse_json_dict, resolve_prompt

load_dotenv(override=True)


def _agent_prompt_content(catalog: dict, agent_name: str, prompt_name: str) -> str:
    """Read one nested agent prompt from the local prompt catalog."""
    agent_prompts = catalog.get("agent_prompts")
    if not isinstance(agent_prompts, dict):
        return ""
    agent = agent_prompts.get(agent_name)
    if not isinstance(agent, dict):
        return ""
    prompt = agent.get(prompt_name)
    if not isinstance(prompt, dict):
        return ""
    content = prompt.get("content")
    return content.strip() if isinstance(content, str) else ""


async def bot(runner_args: RunnerArguments) -> None:
    """Build and run the Omni subagents pipeline for one session."""
    transport = _create_transport(runner_args)
    body = runner_args.body if isinstance(runner_args.body, dict) else {}
    session_id = str(body.get("session_id") or "").strip()
    prompt_catalog = load_prompt_catalog(__file__)

    prompt_key, base_system_content = resolve_prompt(
        __file__,
        body.get("prompt_content", ""),
        body.get("prompt_key", ""),
    )
    logger.info(
        f"Starting Nemotron Omni subagents pipeline (prompt={prompt_key}, agents=transport,speaker,media,webcam)"
    )

    default_llm = load_service_entry("llm", "")
    default_tts = load_service_entry("tts", "")

    model_id = body.get("model_id", "") or default_llm.get("model_id", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
    base_url = body.get("base_url", "") or default_llm.get("base_url", "https://integrate.api.nvidia.com/v1")
    system_prompt_override = body.get("system_prompt", "") or default_llm.get("system_prompt", "")
    extra_params = parse_json_dict(
        body.get("extra_params", "") or default_llm.get("extra_params", ""),
        "extra_params",
    )

    system_content = base_system_content
    if system_prompt_override:
        system_content = f"{base_system_content}\n\n{system_prompt_override}".strip()
    context = LLMContext([{"role": "system", "content": system_content}])

    tts_server = body.get("tts_server", "") or default_tts.get("server", "grpc.nvcf.nvidia.com:443")
    tts_ssl = is_nvcf(tts_server)
    tts_voice = body.get("tts_voice_id", "") or default_tts.get("voice_id", "Magpie-Multilingual.EN-US.Aria")
    api_key = os.getenv("NVIDIA_API_KEY")

    runner = AgentRunner(handle_sigint=runner_args.handle_sigint)
    transport_agent = OmniTransportAgent(
        bus=runner.bus,
        transport=transport,
        context=context,
        api_key=api_key,
        tts_server=tts_server,
        tts_ssl=tts_ssl,
        tts_voice=tts_voice,
        runner_args=runner_args,
        session_id=session_id,
    )
    speaker_agent = SpeakerOmniAgent(
        bus=runner.bus,
        context=context,
        api_key=api_key,
        base_url=base_url,
        model_id=model_id,
        extra_params=extra_params,
        audio_response_instruction=_agent_prompt_content(prompt_catalog, "SpeakerAgent", "audio_response_instruction"),
        media_analysis_prompt_handler=transport_agent.queue_media_analysis_prompt,
        uploaded_attachment_available=transport_agent.has_uploaded_attachment,
    )
    media_analyzer_agent = MediaAnalyzerWorker(
        bus=runner.bus,
        api_key=api_key,
        base_url=base_url,
        model_id=model_id,
        extra_params=extra_params,
        system_prompt=_agent_prompt_content(prompt_catalog, "MediaAnalyzerAgent", "analysis_system_prompt"),
    )
    webcam_agent = WebcamAgent(
        bus=runner.bus,
        api_key=api_key,
        base_url=base_url,
        model_id=model_id,
        extra_params=extra_params,
        summary_system_prompt=_agent_prompt_content(prompt_catalog, "WebcamAgent", "summary_system_prompt"),
    )

    await runner.add_agent(transport_agent)
    await runner.add_agent(media_analyzer_agent)
    await runner.add_agent(webcam_agent)
    await runner.add_agent(speaker_agent)
    await runner.run()
