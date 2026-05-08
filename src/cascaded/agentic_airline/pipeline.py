# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Agentic Airline Voice Agent: Agent with booking, cancellation, and rebooking capabilities.

Uses pipecat's built-in NVIDIA classes directly:
  - NvidiaSTTService  (Parakeet streaming ASR)
  - NvidiaLLMService  (NIM-compatible LLM)
  - NvidiaTTSService  (Magpie TTS)
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import yaml
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame
from pipecat.runner.types import RunnerArguments
from pipecat.services.nvidia.llm import NvidiaLLMService, NvidiaLLMSettings
from pipecat.services.nvidia.stt import NvidiaSTTService
from pipecat.services.nvidia.tts import NvidiaTTSService, NvidiaTTSSettings
from pipecat.transports.base_transport import TransportParams

from cascaded.agentic_airline.agent.bridge import DeepAgentBridgeService
from cascaded.agentic_airline.agent.pnr_injector import CurrentPnrInjector
from cascaded.agentic_airline.agent.router import IntentRouterProcessor
from cascaded.agentic_airline.state.conversation_memory import ConversationMemory
from cascaded.agentic_airline.state.entity_store import EntityStore
from cascaded.agentic_airline.tools import FAST_TOOLS_SCHEMA, build_handlers
from cascaded.agentic_airline.tts_filter import AirlineSpeechTextFilter
from cascaded.shared.audio_recorder import create_audio_recorder
from tracing import IS_TRACING_ENABLED
from utils import (
    is_nvcf,
    load_ipa_dictionary,
    load_service_entry,
    parse_env_bool,
    parse_env_int,
    parse_json_dict,
)

load_dotenv(override=True)

FAST_LLM_CATALOG_CATEGORY = "fast-llm"
CHAT_HISTORY_RECENT_TURNS = parse_env_int("CHAT_HISTORY_RECENT_TURNS", 20)

_FAST_AGENT_PROMPT_FILE = Path(__file__).parent / "prompts" / "fast_agent.yaml"
_FAST_AGENT_PROMPT_KEY = "airline_fast_agent"

# Patterns / keywords that imply a lookup or action worth a tool call.
# Covers domain words, digits, spelled-out numbers / NATO phonetics, and
# 3+ space-separated single characters (e.g. "A B C" or "1 2 3").
# 30B-class tool-calling models fluently emit filler content but often
# drop the tool_call chunk; this pattern selects turns where we force
# ``tool_choice="required"`` so the caller doesn't hear "let me check..."
# with nothing actually running.
_FORCE_TOOL_RE = re.compile(
    r"\b(?:pnr|flight|booking|reservation|rebook|cancel|refund|"
    r"look\s*up|pull\s*up|check|status|confirm\w*|"
    r"standby|relocate|change|move|reschedul\w+|"
    r"switch|another|different|earlier|later|"
    # Spelled-out digits — common in spoken codes.
    r"zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    # NATO phonetics — callers reading back letters of a PNR.
    r"alpha|alfa|bravo|charlie|delta|echo|foxtrot|golf|hotel|india|juliett?|"
    r"kilo|lima|mike|november|oscar|papa|quebec|romeo|sierra|tango|"
    r"uniform|victor|whiskey|x[- ]?ray|yankee|zulu"
    r")\b|\d|"
    # Three-or-more single-character tokens separated by spaces — strongly
    # implies a spelled code (e.g. "A B C 1 2 3" or "1 4 A").
    r"(?:\b\w\s+){2,}\w\b",
    re.IGNORECASE,
)


def _load_fast_agent_prompt() -> str:
    """Read the airline fast-agent system prompt from the package-local YAML."""
    data = yaml.safe_load(_FAST_AGENT_PROMPT_FILE.read_text(encoding="utf-8"))
    return data[_FAST_AGENT_PROMPT_KEY]["content"]


def _apply_chat_history_sliding_window(
    context: LLMContext,
    preserve_prompt_messages: int,
    chat_history_limit: int,
) -> None:
    """Keep the initial prompt messages and the latest sliding window of conversation."""
    if chat_history_limit < 1:
        return
    messages = context.get_messages()
    preserve = max(0, preserve_prompt_messages)
    if len(messages) <= preserve + chat_history_limit:
        return
    context.set_messages(messages[:preserve] + messages[preserve:][-chat_history_limit:])


async def bot(runner_args: RunnerArguments) -> None:
    """Build and run the airline agentic pipeline for one session."""
    stream_id = str(uuid.uuid4())
    logger.info(f"Starting airline agentic pipeline (stream={stream_id})")

    transport = _create_transport(runner_args)
    body = runner_args.body if isinstance(runner_args.body, dict) else {}
    default_fast_llm = load_service_entry(FAST_LLM_CATALOG_CATEGORY, "")
    default_tts = load_service_entry("tts", "")
    default_asr = load_service_entry("asr", "")

    # --- ASR ---
    asr_server = body.get("asr_server", "") or default_asr.get("server", "grpc.nvcf.nvidia.com:443")
    asr_ssl = is_nvcf(asr_server)
    asr_kwargs: dict = {
        "api_key": os.getenv("NVIDIA_API_KEY"),
        "server": asr_server,
        "use_ssl": asr_ssl,
    }
    asr_function_id = body.get("asr_function_id", "") or default_asr.get("function_id", "")
    asr_model = body.get("asr_model", "") or default_asr.get("model", "")
    if asr_function_id or asr_model:
        asr_kwargs["model_function_map"] = {
            "function_id": asr_function_id,
            "model_name": asr_model or "custom-asr",
        }
    stt = NvidiaSTTService(**asr_kwargs, stop_history=400)
    logger.info(f"ASR: server={asr_server}, ssl={asr_ssl}, function_id={asr_function_id or '(default)'}")

    # --- Per-stream state shared by fast-agent tools, router, and orchestrators.
    entity_store = EntityStore(stream_id)
    memory = ConversationMemory(stream_id)

    # --- Fast LLM (Tier-1) ---
    # Resolution order (highest priority first):
    #   1. Per-request body  — lets a client override for one session.
    #   2. services YAML     — Agentic Airline ``fast-llm`` role defaults.
    model_id = body.get("model_id") or default_fast_llm.get("model_id", "nvidia/nemotron-3-nano-30b-a3b")
    base_url = body.get("base_url") or default_fast_llm.get("base_url", "https://integrate.api.nvidia.com/v1")
    extra_params_raw = body.get("extra_params") or default_fast_llm.get("extra_params", "")
    extra_params = parse_json_dict(extra_params_raw)
    llm_settings = NvidiaLLMSettings(model=model_id)
    if extra_params:
        llm_settings.extra = extra_params
    fast_llm = NvidiaLLMService(
        api_key=os.getenv("NVIDIA_API_KEY"),
        base_url=base_url,
        settings=llm_settings,
    )
    logger.info(f"Fast LLM: model={model_id}, base_url={base_url}, extra_params={extra_params or '(none)'}")

    bridge = DeepAgentBridgeService(entity_store=entity_store, memory=memory)

    for name, handler in build_handlers(entity_store, memory, bridge.trigger_from_tool).items():
        fast_llm.register_function(name, handler)
        logger.info(f"Registered fast-agent tool: {name}")

    _orig_build = fast_llm.build_chat_completion_params

    def _smart_build(params_from_context: dict) -> dict:
        result = _orig_build(params_from_context)
        messages = result.get("messages", [])
        last_role = next((m.get("role") for m in reversed(messages) if m.get("role")), None)
        last_user_text = next(
            (
                m.get("content")
                for m in reversed(messages)
                if m.get("role") == "user" and isinstance(m.get("content"), str)
            ),
            None,
        )
        if last_role != "tool" and last_user_text and _FORCE_TOOL_RE.search(last_user_text):
            result["tool_choice"] = "required"
        return result

    fast_llm.build_chat_completion_params = _smart_build

    # --- TTS ---
    tts_server = body.get("tts_server", "") or default_tts.get("server", "grpc.nvcf.nvidia.com:443")
    tts_ssl = is_nvcf(tts_server)
    tts_voice = body.get("tts_voice_id", "") or default_tts.get("voice_id", "Magpie-Multilingual.EN-US.Aria")
    enable_text_filter = parse_env_bool("ENABLE_TTS_TEXT_FILTER", default=True)
    custom_dictionary = load_ipa_dictionary()
    tts = NvidiaTTSService(
        api_key=os.getenv("NVIDIA_API_KEY"),
        server=tts_server,
        settings=NvidiaTTSSettings(voice=tts_voice),
        use_ssl=tts_ssl,
        text_filter=AirlineSpeechTextFilter() if enable_text_filter else None,
        custom_dictionary=custom_dictionary,
    )
    logger.info(f"TTS: server={tts_server}, ssl={tts_ssl}, voice={tts_voice}, text_filter={enable_text_filter}")

    # --- Context + aggregators ---
    system_prompt = _load_fast_agent_prompt()
    context = LLMContext([{"role": "system", "content": system_prompt}], tools=FAST_TOOLS_SCHEMA)
    preserve_prompt_messages = 1

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2))),
    )
    logger.info(f"Chat history sliding window: limit={CHAT_HISTORY_RECENT_TURNS}")

    # --- Agentic layer (bridge already built above) ---

    router = IntentRouterProcessor(memory=memory)

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(aggregator, message):
        _apply_chat_history_sliding_window(context, preserve_prompt_messages, CHAT_HISTORY_RECENT_TURNS)

    pnr_injector = CurrentPnrInjector(entity_store=entity_store)
    audio_recorder = create_audio_recorder()

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            router,  # stamps metadata[intent, requires_deep, extracted_*]
            bridge,  # swallows deep turns; emits filler + deep reply; passes simple through
            pnr_injector,  # rewrites <pnr_state> block on the system message
            fast_llm,  # Tier-1 LLM for simple turns
            tts,
            transport.output(),
            *([audio_recorder] if audio_recorder else []),
            assistant_aggregator,
        ]
    )

    latency_observer = UserBotLatencyObserver()

    @latency_observer.event_handler("on_first_bot_speech_latency")
    async def on_first_bot_speech(observer, latency):
        logger.info(f"TTFA: {latency:.3f}s")
        await task.queue_frame(
            RTVIServerMessageFrame(data={"type": "user-bot-latency", "latency": round(latency, 3), "first": True})
        )

    @latency_observer.event_handler("on_latency_measured")
    async def on_latency(observer, latency):
        logger.info(f"User→Bot latency: {latency:.3f}s")
        await task.queue_frame(
            RTVIServerMessageFrame(data={"type": "user-bot-latency", "latency": round(latency, 3), "first": False})
        )

    @latency_observer.event_handler("on_latency_breakdown")
    async def on_breakdown(observer, breakdown):
        events = breakdown.chronological_events()
        await task.queue_frame(
            RTVIServerMessageFrame(
                data={
                    "type": "latency-breakdown",
                    "vad_smart_turn": round(breakdown.user_turn_secs, 3)
                    if breakdown.user_turn_secs is not None
                    else None,
                    "events": events,
                }
            )
        )
        if events:
            logger.info(f"Latency breakdown: {' | '.join(events)}")

    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        observers=[latency_observer],
        enable_tracing=IS_TRACING_ENABLED,
    )

    @task.rtvi.event_handler("on_client_ready")
    async def on_client_connected(rtvi):
        logger.info("Client connected")
        if audio_recorder:
            await audio_recorder.start_recording()
        context.add_message({"role": "user", "content": "Please introduce yourself briefly."})
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    await runner.run(task)


def _create_transport(runner_args: RunnerArguments):
    """Build a transport from runner arguments (WebRTC or WebSocket)."""
    from pipecat.runner.types import SmallWebRTCRunnerArguments

    if isinstance(runner_args, SmallWebRTCRunnerArguments):
        from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

        return SmallWebRTCTransport(
            params=TransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                audio_out_10ms_chunks=parse_env_int("AUDIO_OUT_10MS_CHUNKS", 5),
            ),
            webrtc_connection=runner_args.webrtc_connection,
        )

    from pipecat.serializers.base_serializer import FrameSerializer
    from pipecat.serializers.protobuf import ProtobufFrameSerializer
    from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport

    websocket = getattr(runner_args, "websocket", None)
    if websocket is None:
        raise TypeError(f"Unsupported runner args type: {type(runner_args)}")

    return FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_in_sample_rate=16000,
            audio_out_enabled=True,
            audio_out_sample_rate=16000,
            audio_out_10ms_chunks=parse_env_int("AUDIO_OUT_10MS_CHUNKS", 10),
            add_wav_header=False,
            serializer=ProtobufFrameSerializer(params=FrameSerializer.InputParams(ignore_rtvi_messages=False)),
        ),
    )
