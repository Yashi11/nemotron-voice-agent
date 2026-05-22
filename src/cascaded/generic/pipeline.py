# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Generic cascaded pipeline: NVIDIA STT -> Nemotron LLM -> NVIDIA TTS with function calling.

Uses pipecat's built-in NVIDIA classes directly:
  - NvidiaSTTService  (Parakeet streaming ASR)
  - NvidiaLLMService  (NIM-compatible LLM)
  - NvidiaTTSService  (Magpie TTS)
"""

import asyncio
import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame, TTSUpdateSettingsFrame
from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.aggregators.llm_text_processor import LLMTextProcessor
from pipecat.processors.frameworks.rtvi import RTVIObserverParams
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame
from pipecat.runner.types import RunnerArguments
from pipecat.services.nvidia.llm import NvidiaLLMService, NvidiaLLMSettings
from pipecat.services.nvidia.stt import NvidiaSTTService
from pipecat.services.nvidia.tts import NvidiaTTSService, NvidiaTTSSettings
from pipecat.transports.base_transport import TransportParams
from pipecat.turns.user_mute import MuteUntilFirstBotCompleteUserMuteStrategy
from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.utils.context.llm_context_summarization import (
    DEFAULT_SUMMARIZATION_PROMPT,
    LLMContextSummarizationUtil,
)

import config_store
from cascaded.generic.tools import TOOL_HANDLERS, build_tools_schema
from cascaded.shared.audio_recorder import create_audio_recorder
from cascaded.shared.multilingual_processor import (
    SKIP_TTS_AGGREGATIONS,
    MultilingualTextAggregator,
    RTVISpokenTextEmitter,
    get_lang_codes,
    make_language_handler,
)
from cascaded.shared.nemotron_speech_text_filter import NemotronSpeechTextFilter
from cascaded.shared.prewarm import prewarm_tts
from tracing import IS_TRACING_ENABLED
from utils import (
    is_nvcf,
    load_ipa_dictionary,
    load_service_entry,
    normalize_lang_code,
    parse_env_bool,
    parse_env_float,
    parse_env_int,
    parse_json_dict,
    resolve_prompt,
    resolve_tools_available,
)

load_dotenv(override=True)
CHAT_HISTORY_RECENT_TURNS = parse_env_int("CHAT_HISTORY_RECENT_TURNS", 10)


async def _build_multilingual_pipeline(
    tts_server: str,
    tts_voice: str,
) -> tuple[MultilingualTextAggregator, LLMTextProcessor, RTVISpokenTextEmitter, str]:
    """Prewarm the voice catalog and build the bare multilingual processors.

    The language handler is wired after the ``PipelineTask`` is created so it
    can call ``task.queue_frame`` directly (see ``bot()``).
    """
    if not config_store.get("tts"):
        await asyncio.to_thread(prewarm_tts, tts_server, tts_voice)
    aggregator = MultilingualTextAggregator()
    text_processor = LLMTextProcessor(text_aggregator=aggregator)
    return aggregator, text_processor, RTVISpokenTextEmitter(), get_lang_codes()


def _build_user_aggregator_params() -> LLMUserAggregatorParams:
    """Return user-turn configuration, defaulting to Pipecat smart turn."""
    if not parse_env_bool("USE_SILERO_VAD_TURN_DETECTION", default=False):
        return LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
            user_mute_strategies=[MuteUntilFirstBotCompleteUserMuteStrategy()],
        )

    stop_secs = parse_env_float("SILERO_VAD_STOP_SECS", 0.5, min_value=0.0)
    return LLMUserAggregatorParams(
        vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=stop_secs)),
        user_mute_strategies=[MuteUntilFirstBotCompleteUserMuteStrategy()],
        user_turn_strategies=UserTurnStrategies(
            stop=[SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.0)],
        ),
    )


def _build_context_messages(base_prompt: str, system_prompt: str = "") -> list[dict]:
    """Build initial context messages.

    Branch on whether the service defines a ``system_prompt`` (services.yaml):
      * Some models (e.g. reasoning-control variants) require the system role
        to carry only a control directive and put all instructions in the
        user message. When a non-empty ``system_prompt`` is configured, the
        prompt catalog content is placed in a separate ``user`` message.
      * Nano / Super have an empty ``system_prompt``.  Their chat template
        appends tool definitions into the system section alongside whatever
        system content is there, so keeping the assistant instructions in
        the system role is both consistent with the template and preserves
        tool-calling reliability.
    """
    if system_prompt:
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": base_prompt},
        ]
    return [{"role": "system", "content": base_prompt}]


async def _apply_pinned_prompt_summary(
    *,
    context: LLMContext,
    llm: NvidiaLLMService,
    preserve_prompt_messages: int,
    recent_turns: int,
    summary_system_prompt: str = "",
) -> None:
    """Summarize old chat turns while preserving the initial prompt messages."""
    if recent_turns < 1:
        return

    messages = list(context.get_messages())
    preserve_count = max(0, preserve_prompt_messages)
    recent_start = _find_recent_turn_start(messages[preserve_count:], recent_turns)
    if recent_start <= 0:
        return

    pinned_messages = messages[:preserve_count]
    chat_messages = messages[preserve_count:]
    messages_to_summarize = chat_messages[:recent_start]
    recent_messages = chat_messages[recent_start:]

    if not messages_to_summarize:
        return

    try:
        summary_text = await _generate_history_summary(
            llm=llm,
            messages_to_summarize=messages_to_summarize,
            summary_system_prompt=summary_system_prompt,
        )
    except Exception as exc:
        logger.warning(f"Chat history summarization failed; keeping existing context: {exc}")
        return

    if context.get_messages() != messages:
        logger.debug("Skipped applying chat history summary because context changed during summarization")
        return

    summary_message = {
        "role": "user",
        "content": f"Conversation summary of earlier turns: {summary_text}",
    }
    context.set_messages([*pinned_messages, summary_message, *recent_messages])
    logger.info(
        "Applied pinned prompt chat summary "
        f"(preserved={preserve_count}, summarized={len(messages_to_summarize)}, "
        f"recent={len(recent_messages)}, total={len(context.get_messages())})"
    )


async def _generate_history_summary(
    *,
    llm: NvidiaLLMService,
    messages_to_summarize: list[dict],
    summary_system_prompt: str = "",
) -> str:
    """Generate a concise text summary for older chat messages."""
    transcript = LLMContextSummarizationUtil.format_messages_for_summary(messages_to_summarize)
    if not transcript.strip():
        raise ValueError("no transcript content available to summarize")

    summary_context = LLMContext(
        messages=[
            {
                "role": "user",
                "content": f"{DEFAULT_SUMMARIZATION_PROMPT}\n\nConversation history:\n{transcript}",
            }
        ]
    )
    summary_coro = llm.run_inference(
        summary_context,
        max_tokens=None,
        system_instruction=summary_system_prompt or None,
    )

    summary_text = await asyncio.wait_for(summary_coro, timeout=45)

    if not summary_text or not summary_text.strip():
        raise ValueError("LLM returned an empty summary")
    return summary_text.strip()


def _find_recent_turn_start(messages: list[dict], recent_turns: int) -> int:
    """Return the first message index for the last N user turns."""
    turns_seen = 0
    for index in range(len(messages) - 1, -1, -1):
        msg = messages[index]
        if isinstance(msg, dict) and msg.get("role") == "user":
            turns_seen += 1
            if turns_seen == recent_turns:
                return index
    return 0


async def bot(runner_args: RunnerArguments) -> None:
    """Build and run the NVIDIA cascaded pipeline for a single session."""
    transport = _create_transport(runner_args)
    body = runner_args.body if isinstance(runner_args.body, dict) else {}
    prompt_key, base_system_content = resolve_prompt(
        __file__,
        body.get("prompt_content", ""),
        body.get("prompt_key", ""),
    )
    logger.info(f"Starting generic cascaded pipeline (tools={list(TOOL_HANDLERS)}, prompt={prompt_key})")
    default_llm = load_service_entry("llm", "")
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

    # --- LLM ---
    model_id = body.get("model_id", "") or default_llm.get("model_id", "nvidia/nemotron-3-nano-30b-a3b")
    base_url = body.get("base_url", "") or default_llm.get("base_url", "https://integrate.api.nvidia.com/v1")
    system_prompt = body.get("system_prompt", "") or default_llm.get("system_prompt", "")
    extra_params = parse_json_dict(
        body.get("extra_params", "") or default_llm.get("extra_params", ""),
        label="extra_params",
    )

    logger.info(
        f"LLM: model={model_id}, base_url={base_url}, "
        f"system_prompt={'<' + system_prompt + '>' if system_prompt else '(none)'}, "
        f"extra_params={extra_params or '(none)'}"
    )

    llm_settings = NvidiaLLMSettings(model=model_id)
    if extra_params:
        llm_settings.extra = extra_params
    llm = NvidiaLLMService(
        api_key=os.getenv("NVIDIA_API_KEY"),
        base_url=base_url,
        settings=llm_settings,
    )

    tools_available = resolve_tools_available(__file__, prompt_key)
    tools_schema, registered_tools = build_tools_schema(__file__, tools_available)
    tools_enabled = tools_schema is not None

    if tools_enabled:
        for name in registered_tools:
            llm.register_function(name, TOOL_HANDLERS[name])
            logger.info(f"Registered tool handler: {name}")
    else:
        logger.info(f"Tool calling disabled for prompt_key={prompt_key!r} (no tools_available in prompts.yaml)")

    # --- TTS ---
    tts_server = body.get("tts_server", "") or default_tts.get("server", "grpc.nvcf.nvidia.com:443")
    tts_ssl = is_nvcf(tts_server)
    tts_voice = body.get("tts_voice_id", "") or default_tts.get("voice_id", "Magpie-Multilingual.EN-US.Aria")

    is_multilingual = "multilingual" in prompt_key.lower()
    custom_dictionary = load_ipa_dictionary()

    tts = NvidiaTTSService(
        api_key=os.getenv("NVIDIA_API_KEY"),
        server=tts_server,
        settings=NvidiaTTSSettings(voice=tts_voice),
        use_ssl=tts_ssl,
        text_filters=[NemotronSpeechTextFilter()],
        custom_dictionary=custom_dictionary,
        skip_aggregator_types=list(SKIP_TTS_AGGREGATIONS) if is_multilingual else [],
    )

    multilingual_aggregator = None
    multilingual_text_processor = None
    multilingual_rtvi_emitter = None
    lang_codes = ""

    if is_multilingual:
        (
            multilingual_aggregator,
            multilingual_text_processor,
            multilingual_rtvi_emitter,
            lang_codes,
        ) = await _build_multilingual_pipeline(tts_server, tts_voice)
        logger.info(f"Multilingual mode: {lang_codes or '(no voices discovered)'}")

    logger.info(
        f"TTS: server={tts_server}, ssl={tts_ssl}, voice={tts_voice}, "
        f"multilingual={is_multilingual}, text_filters=[NemotronSpeechTextFilter]"
    )

    # --- Context ---
    if lang_codes:
        base_system_content = base_system_content.replace("{lang_codes}", lang_codes)

    messages = _build_context_messages(base_system_content, system_prompt)

    if tools_enabled:
        context = LLMContext(messages, tools=tools_schema, tool_choice="auto")
    else:
        context = LLMContext(messages)
    preserve_prompt_messages = len(messages)

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=_build_user_aggregator_params(),
    )
    logger.info(
        f"Chat history summarization enabled: recent_turns={CHAT_HISTORY_RECENT_TURNS}, "
        f"preserve_prompt_messages={preserve_prompt_messages}"
    )

    audio_recorder = create_audio_recorder()

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            *([multilingual_text_processor] if multilingual_text_processor else []),
            *([multilingual_rtvi_emitter] if multilingual_rtvi_emitter else []),
            tts,
            transport.output(),
            *([audio_recorder] if audio_recorder else []),
            assistant_aggregator,
        ]
    )

    latency_observer = UserBotLatencyObserver()
    summary_lock = asyncio.Lock()

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(aggregator, message):
        async with summary_lock:
            await _apply_pinned_prompt_summary(
                context=context,
                llm=llm,
                preserve_prompt_messages=preserve_prompt_messages,
                recent_turns=CHAT_HISTORY_RECENT_TURNS,
                summary_system_prompt=system_prompt,
            )

    # Forward custom latency samples over RTVI so the benchmark can stay fully
    # client-driven and avoid server log scraping.
    @latency_observer.event_handler("on_first_bot_speech_latency")
    async def on_first_bot_speech(observer, latency):
        logger.info(f"First bot speech latency: {latency:.3f}s")
        await task.queue_frame(
            RTVIServerMessageFrame(
                data={
                    "type": "user-bot-latency",
                    "latency": round(latency, 3),
                    "first": True,
                }
            )
        )

    @latency_observer.event_handler("on_latency_measured")
    async def on_latency(observer, latency):
        logger.info(f"User→Bot latency: {latency:.3f}s")
        await task.queue_frame(
            RTVIServerMessageFrame(
                data={
                    "type": "user-bot-latency",
                    "latency": round(latency, 3),
                    "first": False,
                }
            )
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

    rtvi_params = None
    if is_multilingual:
        rtvi_params = RTVIObserverParams(ignored_sources=[llm])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        observers=[latency_observer],
        enable_tracing=IS_TRACING_ENABLED,
        rtvi_observer_params=rtvi_params,
    )

    @user_aggregator.event_handler("on_user_turn_stopped")
    async def on_user_turn_stopped(aggregator, strategy, message):
        await task.queue_frame(
            RTVIServerMessageFrame(
                data={
                    "type": "user-turn-finalized",
                    "timestamp": getattr(message, "timestamp", None),
                    "transcript": getattr(message, "content", None),
                    "user_id": getattr(message, "user_id", None),
                }
            )
        )

    if multilingual_aggregator is not None:

        async def _notify_language_switched(language: str, voice_id: str) -> None:
            await task.queue_frame(
                RTVIServerMessageFrame(
                    data={
                        "type": "language-switched",
                        "language": language,
                        "voice_id": voice_id,
                    }
                )
            )

        multilingual_aggregator.set_on_language(
            make_language_handler(tts, task, on_language_switched=_notify_language_switched)
        )

    @task.rtvi.event_handler("on_client_ready")
    async def on_client_connected(rtvi):
        logger.info("Client connected")
        if audio_recorder:
            await audio_recorder.start_recording()
        context.add_message({"role": "user", "content": "Please introduce yourself to the user."})
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await task.cancel()

    async def _apply_set_voice(payload: dict) -> None:
        voice_id = payload.get("voice_id", "")
        language = payload.get("language", "")
        if not voice_id:
            return
        settings_kwargs: dict = {"voice": voice_id}
        if language:
            settings_kwargs["language"] = normalize_lang_code(language)
        await task.queue_frame(
            TTSUpdateSettingsFrame(
                delta=NvidiaTTSSettings(**settings_kwargs),
                service=tts,
            )
        )
        logger.info(f"Voice switched → {voice_id}, language={settings_kwargs.get('language', '(unchanged)')}")

    @task.rtvi.event_handler("on_client_message")
    async def on_client_message(rtvi, message):
        payload = message.data if isinstance(message.data, dict) else {}
        if message.type == "set-voice":
            await _apply_set_voice(payload)

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    await runner.run(task)


def _create_transport(runner_args: RunnerArguments):
    """Create a transport from runner arguments (WebRTC or WebSocket)."""
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
            audio_in_sample_rate=16000,
            audio_out_enabled=True,
            audio_out_sample_rate=16000,
            audio_out_10ms_chunks=parse_env_int("AUDIO_OUT_10MS_CHUNKS", 10),
            add_wav_header=False,
            serializer=ProtobufFrameSerializer(params=FrameSerializer.InputParams(ignore_rtvi_messages=False)),
        ),
    )
