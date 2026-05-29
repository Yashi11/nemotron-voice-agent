# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Speech-to-Speech pipeline using OpenAI Realtime API format.

Supports OpenAI Realtime or any compatible endpoint (e.g. Nemotron Voice Chat).
Turn detection, ASR, LLM, and TTS all run inside the S2S service — no separate
STT/TTS services needed. Pipecat handles transport and pipeline orchestration.
"""

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.frames.frames import LLMRunFrame
from pipecat.observers.loggers.transcription_log_observer import (
    TranscriptionLogObserver,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.runner.types import RunnerArguments
from pipecat.services.openai.realtime.events import (
    AudioConfiguration,
    AudioInput,
    InputAudioTranscription,
    SemanticTurnDetection,
    SessionProperties,
)
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
from pipecat.transports.base_transport import TransportParams

import speech_to_speech.nemotron_compat  # noqa: F401 — monkey-patches Pipecat event parser
from speech_to_speech.nvcf_realtime import NVCFRealtimeLLMService
from tracing import IS_TRACING_ENABLED
from utils import load_service_entry, resolve_prompt

load_dotenv(override=True)


async def bot(runner_args: RunnerArguments) -> None:
    """Build and run the S2S pipeline for a single session."""
    body = runner_args.body if isinstance(runner_args.body, dict) else {}
    default_s2s = load_service_entry("s2s", "")

    base_url = body.get("s2s_server", "") or default_s2s.get("server", "wss://grpc.nvcf.nvidia.com/v1/realtime")
    model = body.get("s2s_model", "") or default_s2s.get("model", "")
    function_id = body.get("s2s_function_id", "") or default_s2s.get("function_id", "")
    api_key = os.getenv("NVIDIA_API_KEY", "")

    _, instructions = resolve_prompt(__file__, body.get("prompt_content", ""), body.get("prompt_key", ""))

    key_hint = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else api_key
    logger.info(
        f"Starting S2S pipeline — endpoint: {base_url}, model: {model or '(none)'}, "
        f"function_id: {function_id or '(none)'}, api_key: {key_hint}"
    )

    transport = _create_transport(runner_args)

    session_properties = SessionProperties(
        model=model or None,
        audio=AudioConfiguration(
            input=AudioInput(
                transcription=InputAudioTranscription(),
                turn_detection=SemanticTurnDetection(),
            ),
        ),
        instructions=instructions,
    )

    llm = NVCFRealtimeLLMService(
        api_key=api_key,
        base_url=base_url,
        function_id=function_id,
        settings=OpenAIRealtimeLLMService.Settings(
            session_properties=session_properties,
        ),
    )

    context = LLMContext([])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context)

    pipeline = Pipeline(
        [
            transport.input(),
            user_aggregator,
            llm,
            transport.output(),
            assistant_aggregator,
        ],
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=24000,
            audio_out_sample_rate=24000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        observers=[TranscriptionLogObserver()],
        enable_tracing=IS_TRACING_ENABLED,
    )

    @task.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        logger.info("S2S client ready")
        context.add_message({"role": "user", "content": "Please introduce yourself to the user."})
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("S2S client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    await runner.run(task)


def _create_transport(runner_args: RunnerArguments):
    """Create a transport from runner arguments (WebRTC or WebSocket)."""
    from pipecat.runner.types import SmallWebRTCRunnerArguments

    if isinstance(runner_args, SmallWebRTCRunnerArguments):
        from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

        return SmallWebRTCTransport(
            params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
            webrtc_connection=runner_args.webrtc_connection,
        )

    from pipecat.serializers.base_serializer import FrameSerializer
    from pipecat.serializers.protobuf import ProtobufFrameSerializer
    from pipecat.transports.websocket.fastapi import (
        FastAPIWebsocketParams,
        FastAPIWebsocketTransport,
    )

    websocket = getattr(runner_args, "websocket", None)
    if websocket is None:
        raise TypeError(f"Unsupported runner args type: {type(runner_args)}")

    return FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_in_sample_rate=24000,
            audio_out_enabled=True,
            audio_out_sample_rate=24000,
            audio_out_10ms_chunks=10,
            add_wav_header=False,
            serializer=ProtobufFrameSerializer(params=FrameSerializer.InputParams(ignore_rtvi_messages=False)),
        ),
    )
