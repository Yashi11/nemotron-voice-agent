# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD 2-Clause License

"""Voice Agent WebRTC Pipeline.

This module sets up a real-time speech-to-speech pipeline using WebRTC,
enabling interactive voice agents with dynamic UI features like system prompt
editing and TTS voice switching in real time.
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from enum import Enum
from pathlib import Path

import uvicorn
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    InputAudioRawFrame,
    TTSAudioRawFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import (
    IceServer,
    SmallWebRTCConnection,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from nvidia_pipecat.frames.riva import RivaFetchVoicesFrame
from nvidia_pipecat.processors.audio_util import AudioRecorder
from nvidia_pipecat.processors.nvidia_context_aggregator import (
    NvidiaTTSResponseCacher,
    create_nvidia_context_aggregator,
)
from nvidia_pipecat.processors.nvidia_rtvi import NvidiaRTVIInput, NvidiaRTVIObserver
from nvidia_pipecat.processors.transcript_synchronization import (
    BotTranscriptSynchronization,
    UserTranscriptSynchronization,
)
from nvidia_pipecat.services.nvidia_llm import NvidiaLLMService
from nvidia_pipecat.services.riva_speech import RivaASRService, RivaTTSService

load_dotenv(override=True)

PROMPT_FILE = Path(os.getenv("PROMPT_FILE_PATH", str(Path(__file__).parent / "prompt.yaml")))
MULTILINGUAL_MODE = os.getenv("ENABLE_MULTILINGUAL", "false").lower() == "true"


class VADProfile(Enum):
    """VAD Profile options."""

    SILERO = "Silero"  # Transport Silero VAD analyzer
    RIVA = "Riva"  # Riva ASR VAD


VAD_PROFILE = VADProfile(os.getenv("VAD_PROFILE", VADProfile.RIVA))


def _load_prompts() -> dict:
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(f"Prompt catalog not found at {PROMPT_FILE}")
    try:
        data = yaml.safe_load(PROMPT_FILE.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in prompt catalog {PROMPT_FILE}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Prompt catalog at {PROMPT_FILE} must be a mapping.")
    return data


PROMPTS = _load_prompts()


def _resolve_system_prompt(selector: str) -> str:
    """Resolve prompt selector by traversing nested YAML path."""
    parts = [segment for segment in selector.split("/") if segment]
    if len(parts) < 2:
        raise ValueError("SYSTEM_PROMPT_SELECTOR must be in '<model>/<prompt>' format.")

    entry = PROMPTS
    traversed: list[str] = []
    for part in parts:
        traversed.append(part)
        if not isinstance(entry, dict) or part not in entry:
            raise KeyError(f"Prompt path '{'/'.join(traversed)}' not found in prompt catalog.")
        entry = entry[part]

    if isinstance(entry, dict) and "content" in entry:
        return entry["content"]

    raise KeyError(f"Prompt entry for selector '{selector}' is missing 'content'.")


def _inject_prompt_variables(prompt: str, **variables) -> str:
    """Inject variables into prompt placeholders like {lang_codes}."""
    try:
        return prompt.format(**variables)
    except KeyError:
        return prompt


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store connections by pc_id
pcs_map: dict[str, SmallWebRTCConnection] = {}


ice_servers = (
    [
        IceServer(
            urls=os.getenv("TURN_SERVER_URL", ""),
            username=os.getenv("TURN_USERNAME", ""),
            credential=os.getenv("TURN_PASSWORD", ""),
        )
    ]
    if os.getenv("TURN_SERVER_URL")
    else []
)


async def run_bot(webrtc_connection):
    """Run the voice agent bot with WebRTC connection and WebSocket.

    Args:
        webrtc_connection: The WebRTC connection for audio streaming
    """
    stream_id = uuid.uuid4()
    transport_params = TransportParams(
        audio_in_enabled=True,
        audio_in_sample_rate=16000,
        audio_out_sample_rate=22050,
        audio_out_enabled=True,
        audio_out_10ms_chunks=5,
        vad_analyzer=SileroVADAnalyzer() if VAD_PROFILE == VADProfile.SILERO else None,
    )

    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=transport_params,
    )

    llm = NvidiaLLMService(
        api_key=os.getenv("NVIDIA_API_KEY"),
        base_url=os.getenv("NVIDIA_LLM_URL", "https://integrate.api.nvidia.com/v1"),
        model=os.getenv("NVIDIA_LLM_MODEL", "meta/llama-3.1-8b-instruct"),
    )

    # ASR service config - add extended stop_history for multilingual mode
    stt_config = {
        "server": os.getenv("RIVA_ASR_URL", "grpc.nvcf.nvidia.com:443"),
        "api_key": os.getenv("NVIDIA_API_KEY"),
        "language": os.getenv("RIVA_ASR_LANGUAGE", "en-US"),
        "sample_rate": 16000,
        "generate_interruptions": VAD_PROFILE == VADProfile.RIVA,
        "model": os.getenv("RIVA_ASR_MODEL", "parakeet-1.1b-en-US-asr-streaming-silero-vad-sortformer"),
    }
    if MULTILINGUAL_MODE:
        stt_config.update(stop_history=900, stop_history_eou=900)

    stt = RivaASRService(**stt_config)

    # Load IPA dictionary with error handling
    ipa_file = Path(__file__).parent / "ipa.json"
    try:
        with open(ipa_file, encoding="utf-8") as f:
            ipa_dict = json.load(f)
    except FileNotFoundError as e:
        logger.error(f"IPA dictionary file not found at {ipa_file}")
        raise FileNotFoundError(f"IPA dictionary file not found at {ipa_file}") from e
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in IPA dictionary file: {e}")
        raise ValueError(f"Invalid JSON in IPA dictionary file: {e}") from e
    except Exception as e:
        logger.error(f"Error loading IPA dictionary: {e}")
        raise

    tts = RivaTTSService(
        server=os.getenv("RIVA_TTS_URL", "grpc.nvcf.nvidia.com:443"),
        api_key=os.getenv("NVIDIA_API_KEY"),
        voice_id=os.getenv("RIVA_TTS_VOICE_ID", "Magpie-Multilingual.EN-US.Aria"),
        model=os.getenv("RIVA_TTS_MODEL", "magpie_tts_ensemble-Magpie-Multilingual"),
        language=os.getenv("RIVA_TTS_LANGUAGE", "en-US"),
        sample_rate=22050,
        zero_shot_audio_prompt_file=(
            Path(os.getenv("ZERO_SHOT_AUDIO_PROMPT")) if os.getenv("ZERO_SHOT_AUDIO_PROMPT") else None
        ),
        custom_dictionary=ipa_dict,
    )

    # Create audio_dumps directory if it doesn't exist
    audio_dumps_dir = Path(__file__).parent / "audio_dumps"
    audio_dumps_dir.mkdir(exist_ok=True)

    asr_recorder = AudioRecorder(
        output_file=str(audio_dumps_dir / f"asr_recording_{stream_id}.wav"),
        params=transport_params,
        frame_type=InputAudioRawFrame,
    )

    tts_recorder = AudioRecorder(
        output_file=str(audio_dumps_dir / f"tts_recording_{stream_id}.wav"),
        params=transport_params,
        frame_type=TTSAudioRawFrame,
    )

    # Used to synchronize the user and bot transcripts in the UI
    stt_transcript_synchronization = UserTranscriptSynchronization()
    tts_transcript_synchronization = BotTranscriptSynchronization()

    if MULTILINGUAL_MODE:
        prompt_selector = os.getenv(
            "SYSTEM_PROMPT_SELECTOR", "llama-3_3-nemotron-super-49b-v1_5/multilingual_voice_assistant"
        ).strip()
        lang_codes = ", ".join(tts.list_available_voices().keys())
        system_prompt = _inject_prompt_variables(_resolve_system_prompt(prompt_selector), lang_codes=lang_codes)
        logger.info(f"Loaded multilingual prompt: {prompt_selector} with languages: {lang_codes}")
    else:
        prompt_selector = os.getenv("SYSTEM_PROMPT_SELECTOR", "llama-3.1-8b-instruct/flowershop").strip()
        system_prompt = _resolve_system_prompt(prompt_selector)
        logger.info(f"Loaded prompt: {prompt_selector}")

    messages = [{"role": "system", "content": system_prompt}]
    context = OpenAILLMContext(messages)

    # Configure speculative speech processing based on environment variable
    enable_speculative_speech = os.getenv("ENABLE_SPECULATIVE_SPEECH", "true").lower() == "true"
    raw_chat_history = os.getenv("CHAT_HISTORY_LIMIT")
    try:
        chat_history_limit = int(raw_chat_history) if raw_chat_history is not None else 20
    except ValueError:
        logger.warning(f"Invalid CHAT_HISTORY_LIMIT {raw_chat_history!r}, falling back to default 20")
        chat_history_limit = 20

    if enable_speculative_speech:
        context_aggregator = create_nvidia_context_aggregator(
            context, send_interims=True, chat_history_limit=chat_history_limit
        )
        tts_response_cacher = NvidiaTTSResponseCacher()
    else:
        context_aggregator = create_nvidia_context_aggregator(
            context, send_interims=False, chat_history_limit=chat_history_limit
        )
        tts_response_cacher = None

    # Create NVIDIA RTVI input processor with application-specific message handlers
    rtvi_input = NvidiaRTVIInput(
        transport=transport,
        context=context,
    )

    pipeline = Pipeline(
        [
            transport.input(),  # WebRTC input from client
            rtvi_input,  # NVIDIA RTVI input processor with Client-specific message handlers
            asr_recorder,
            stt,  # Speech-To-Text
            stt_transcript_synchronization,
            context_aggregator.user(),
            llm,  # LLM
            tts,  # Text-To-Speech
            tts_recorder,
            *([tts_response_cacher] if tts_response_cacher else []),
            tts_transcript_synchronization,
            transport.output(),  # WebRTC output to client
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            enable_usage_metrics=True,
            send_initial_empty_metrics=True,
            start_metadata={"stream_id": stream_id},
        ),
        observers=[NvidiaRTVIObserver(rtvi_input)],
    )

    @rtvi_input.event_handler("on_client_ready")
    async def on_client_ready(rtvi_input):
        try:
            await rtvi_input.set_bot_ready()
            await task.queue_frames(
                [
                    RivaFetchVoicesFrame(),
                    RTVIServerMessageFrame(data={"type": "system_prompt", "prompt": messages[0]["content"]}),
                ]
            )
        except Exception as e:
            logger.error(f"Error on client ready: {e}")
            await rtvi_input.send_error(str(e))

    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)


@app.post("/offer")
async def offer(request: Request):
    """Offer endpoint for handling voice agent connections.

    Args:
        request: The request to handle
    """
    request = await request.json()
    pc_id = request.get("pc_id")

    if pc_id and pc_id in pcs_map:
        pipecat_connection = pcs_map[pc_id]
        logger.info(f"Reusing existing connection for pc_id: {pc_id}")
        await pipecat_connection.renegotiate(sdp=request["sdp"], type=request["type"])
    else:
        pipecat_connection = SmallWebRTCConnection(ice_servers)
        await pipecat_connection.initialize(sdp=request["sdp"], type=request["type"])

        @pipecat_connection.event_handler("closed")
        async def handle_disconnected(webrtc_connection: SmallWebRTCConnection):
            pc_id = webrtc_connection.pc_id

            # Remove from connections map
            pcs_map.pop(pc_id, None)

        asyncio.create_task(run_bot(pipecat_connection))

    answer = pipecat_connection.get_answer()
    pcs_map[answer["pc_id"]] = pipecat_connection

    return answer


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebRTC demo")
    parser.add_argument("--host", default="0.0.0.0", help="Host for HTTP server (default: localhost)")
    parser.add_argument("--port", type=int, default=7860, help="Port for HTTP server (default: 7860)")
    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()

    logger.remove(0)
    if args.verbose:
        logger.add(sys.stderr, level="TRACE")
    else:
        logger.add(sys.stderr, level="DEBUG")

    uvicorn.run(app, host=args.host, port=args.port)
