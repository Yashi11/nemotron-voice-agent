# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Voice-agent benchmark runner.

Single-client voice-agent benchmark + result aggregator.

What this script does
-----------------

Default mode (no ``--aggregate-*`` flag): act as **one** synthetic voice
client against a running Nemotron Voice Agent server.

The flow per turn:
  1. Open a wss WebSocket to ``wss://<host>:<port>/api/ws?session_id=...``
     (TLS verification disabled, since the server uses a self-signed cert).
  2. Receive and discard the bot's initial intro utterance.
  3. Stream a WAV file from ``--dataset-dir`` to the server in 32 ms chunks
     (the simulated user "speaking").
  4. After the WAV ends, send PCM silence so VAD sees a clean turn boundary.
  5. Read incoming audio frames; the first chunk that arrives more than
     ``--reverse-barge-in-threshold`` seconds after the user finished is
     counted as the *real* response. Anything earlier is treated as a
     reverse barge-in (the server racing the end of the user's
     utterance) and is drained but not timed.
  6. Server-side timing breakdowns arrive as RTVI ``message`` frames on the
     same WebSocket; they're parsed alongside the audio.

When the metric window (``--metrics-start-time`` → +``--test-duration``)
expires, the client closes the connection, writes its result JSON to
``--result-path``, and exits.

Concurrency is **not handled here.** ``simulate_concurrency.sh`` spawns N
parallel copies with synchronized ``--metrics-start-time`` /
``--session-end-time`` so every worker measures over the same wall-clock
window.

Aggregation modes
-----------------

* ``--aggregate-run-dir DIR`` folds the ``client_*/result_*.json`` files
  under ``DIR`` into a single ``benchmark_summary.json``.
* ``--aggregate-suite-dir DIR`` folds every ``run_<N>_clients/benchmark_summary.json``
  under ``DIR`` into ``results.{tsv,txt,json}`` for the whole sweep.

These modes keep the orchestrator script free of embedded Python; the shell
only has to spawn/wait on processes.
"""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime as dt
import io
import json
import math
import signal
import ssl
import struct
import sys
import time
import wave
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import websockets
from pipecat.frames.protobufs import frames_pb2
from websockets.exceptions import ConnectionClosed

CHUNK_DURATION_MS = 32
WS_CONNECT_TIMEOUT = 30
BOT_INTRO_TIMEOUT = 5
END_OF_RESPONSE_TIMEOUT = 3.0
BARGE_IN_DRAIN_TIMEOUT = 0.5
HARD_DEADLINE_BUFFER = 60
SERVER_METRIC_KEYS = (
    "llm_ttft",
    "tts_ttfb",
    "asr_ttfb",
    "server_e2e",
    "vad_smart_turn",
    "llm_processing_time",
    "llm_tokens_per_sec",
)

_SHUTDOWN_REQUESTED = False


def _signal_handler(signum, frame):
    del frame
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = True
    print(f"\nReceived signal {signum}, shutting down gracefully...")


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def log_error(msg: str) -> None:
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[ERROR] {timestamp} - {msg}", file=sys.stderr, flush=True)


def round3(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.3f}"


def average_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def categorize_processor(processor: str) -> str:
    name = processor.lower()
    if "asr" in name or "stt" in name:
        return "asr"
    if "tts" in name:
        return "tts"
    if "llm" in name:
        return "llm"
    return ""


class RunLogger:
    """Append-only timestamped log writer for a single client run.

    Used as a side channel for turn-by-turn diagnostics so the result JSON
    can stay focused on metrics. Safe to call concurrently from multiple
    coroutines (a per-instance asyncio lock serializes writes).
    """

    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    async def log(self, message: str) -> None:
        timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] {message}\n"
        async with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line)

    async def log_table(self, title: str, rows: list[tuple[str, str]]) -> None:
        await self.log(title)
        if not rows:
            await self.log("  (no rows)")
            return
        width = max(len(label) for label, _ in rows)
        for label, value in rows:
            await self.log(f"  {label.ljust(width)} : {value}")


@dataclass
class ClientResult:
    """Per-client metrics produced by one ``PerfClient.run()``.

    Serialized to ``--result-path`` as JSON. ``--aggregate-run-dir`` reads
    these files back to build the per-run ``benchmark_summary.json``.

    Attributes:
        stream_id: WebSocket session identifier (matches the ``client_<i>_<id>``
            output directory name).
        average_latency: Mean response latency across all timed turns, or
            ``None`` when no turn completed inside the metric window.
        individual_latencies: One entry per timed turn (seconds).
        num_turns: Number of timed turns; ``len(individual_latencies)``.
        glitch_detected: ``True`` when at least one output buffer underrun
            was seen during a timed turn.
        reverse_barge_in_threshold: Echoed-back configuration value (seconds).
        metrics_start_time: Unix epoch when the metric window opened.
        test_duration: Configured length of the metric window (seconds).
        server_metrics: ``{"samples": {...}, "average": {...}, "sample_counts": {...}}``
            for each ``SERVER_METRIC_KEYS`` entry.
        rtvi_messages: Every RTVI message received during the session,
            preserved for offline post-mortem analysis.
        timestamp: ISO-8601 wall-clock time when the result was written.
        error: Human-readable failure reason, or ``None`` on success.
    """

    stream_id: str
    average_latency: float | None
    individual_latencies: list[float]
    num_turns: int
    glitch_detected: bool
    reverse_barge_in_threshold: float
    metrics_start_time: float | None
    test_duration: float
    server_metrics: dict
    rtvi_messages: list[dict[str, Any]]
    timestamp: str
    error: str | None = None


class PerfClient:
    """One synthetic voice client driving a single WebSocket session.

    Owns the full lifecycle for one simulated user:

    * connects to ``wss://<host>:<port>/api/ws``,
    * cycles through ``audio_files`` as user utterances (one per turn),
    * pads gaps with silence so the server's VAD detects clean turn ends,
    * times each real bot response (skipping reverse barge-ins),
    * records RTVI server-side metric samples (``server_metric_samples``),
    * detects audio glitches (output buffer underruns),
    * returns a :class:`ClientResult` summarizing the session.

    Designed to be instantiated once per session by ``async_main`` (default
    mode) — the orchestrator script provides per-client uniqueness by
    spawning N processes, not by reusing this class within one process.
    """

    def __init__(
        self,
        *,
        stream_id: str,
        host: str,
        port: int,
        audio_files: list[Path],
        start_delay: float,
        metrics_start_time: float | None,
        session_end_time: float | None,
        test_duration: float,
        reverse_barge_in_threshold: float,
        audio_output_path: Path | None,
        logger: RunLogger,
    ):
        self.stream_id = stream_id
        self.host = host
        self.port = port
        self.audio_files = audio_files
        self.start_delay = start_delay
        self.metrics_start_time = metrics_start_time
        self.session_end_time = session_end_time
        self.test_duration = test_duration
        self.reverse_barge_in_threshold = reverse_barge_in_threshold
        self.audio_output_path = audio_output_path
        self.logger = logger

        self.latency_values: list[float] = []
        self.timestamps: dict[str, dt.datetime | None] = {"input_audio_file_end": None}
        self.glitch_detected = False
        self.total_reverse_barge_ins = 0
        self.server_metric_samples: dict[str, list[float]] = {key: [] for key in SERVER_METRIC_KEYS}
        self.rtvi_messages: list[dict[str, Any]] = []
        self.running = True
        self.collecting_metrics = False
        self.silence_running = False
        self.silence_event: asyncio.Event | None = None
        self.audio_params: tuple[int, int, int] | None = None
        self._pending_llm_completion_tokens: list[float] = []

    @property
    def uri(self) -> str:
        return f"wss://{self.host}:{self.port}/api/ws?session_id={self.stream_id}"

    async def _process_server_message(self, message: dict) -> None:
        if not isinstance(message, dict):
            return

        message_type = str(message.get("type", "unknown"))
        self.rtvi_messages.append(
            {
                "timestamp": dt.datetime.now().isoformat(),
                "type": message_type,
                "data": message,
            }
        )
        await self.logger.log(f"{self.stream_id} RTVI message: {json.dumps(message, sort_keys=True)}")

        if message_type == "server-message" and isinstance(message.get("data"), dict):
            nested_message = message["data"]
            nested_type = nested_message.get("type")
            if isinstance(nested_type, str):
                message = nested_message
                message_type = nested_type

        if message_type == "user-bot-latency":
            latency = message.get("latency")
            is_first = bool(message.get("first", False))
            if self.collecting_metrics and isinstance(latency, (int, float)) and not is_first:
                self.server_metric_samples["server_e2e"].append(float(latency))
            return

        if message_type == "latency-breakdown":
            vad_smart_turn = message.get("vad_smart_turn")
            if self.collecting_metrics and isinstance(vad_smart_turn, (int, float)):
                self.server_metric_samples["vad_smart_turn"].append(float(vad_smart_turn))
            return

        if message_type != "metrics":
            return

        metrics = message.get("data", {})
        if not isinstance(metrics, dict) or not self.collecting_metrics:
            return

        for item in metrics.get("ttfb", []):
            if not isinstance(item, dict):
                continue
            value = item.get("value")
            processor = str(item.get("processor", ""))
            if not isinstance(value, (int, float)):
                continue
            category = categorize_processor(processor)
            if category == "llm":
                self.server_metric_samples["llm_ttft"].append(float(value))
            elif category == "tts":
                self.server_metric_samples["tts_ttfb"].append(float(value))
            elif category == "asr":
                self.server_metric_samples["asr_ttfb"].append(float(value))

        for item in metrics.get("processing", []):
            if not isinstance(item, dict):
                continue
            value = item.get("value")
            processor = str(item.get("processor", ""))
            if not isinstance(value, (int, float)):
                continue
            if categorize_processor(processor) == "llm":
                processing_time = float(value)
                self.server_metric_samples["llm_processing_time"].append(processing_time)
                if self._pending_llm_completion_tokens:
                    completion_tokens = self._pending_llm_completion_tokens.pop(0)
                    if processing_time > 0:
                        self.server_metric_samples["llm_tokens_per_sec"].append(completion_tokens / processing_time)

        for item in metrics.get("tokens", []):
            if not isinstance(item, dict):
                continue
            completion_tokens = item.get("completion_tokens")
            if isinstance(completion_tokens, (int, float)):
                self._pending_llm_completion_tokens.append(float(completion_tokens))

    async def _recv_audio_frame(self, websocket, timeout: float | None = None) -> bytes:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            if _SHUTDOWN_REQUESTED:
                raise asyncio.CancelledError

            wait_timeout = None
            if deadline is not None:
                wait_timeout = max(deadline - time.monotonic(), 0)
                if wait_timeout == 0:
                    raise TimeoutError

            data = await asyncio.wait_for(websocket.recv(), timeout=wait_timeout)
            try:
                proto = frames_pb2.Frame.FromString(data)
            except Exception as exc:
                log_error(f"Failed to parse protobuf frame: {exc}")
                continue

            which = proto.WhichOneof("frame")
            if which == "audio":
                return data
            if which == "message":
                try:
                    await self._process_server_message(json.loads(proto.message.data))
                except Exception as exc:
                    log_error(f"Failed to parse message frame payload: {exc}")

    def _write_audio_to_wav(self, data: bytes, wf, *, create_new_file: bool = False):
        try:
            proto = frames_pb2.Frame.FromString(data)
            which = proto.WhichOneof("frame")
            if which is None:
                return wf, None, None, None
        except Exception as exc:
            log_error(f"Failed to parse protobuf frame: {exc}")
            return wf, None, None, None

        args = getattr(proto, which)
        sample_rate = getattr(args, "sample_rate", 16000)
        num_channels = getattr(args, "num_channels", 1)
        audio_data = getattr(args, "audio", None)
        if audio_data is None:
            return wf, None, None, None

        try:
            with io.BytesIO(audio_data) as buffer, wave.open(buffer, "rb") as wav_file:
                audio_data = wav_file.readframes(wav_file.getnframes())
                sample_rate = wav_file.getframerate()
                num_channels = wav_file.getnchannels()
        except (wave.Error, EOFError, struct.error):
            pass

        if self.audio_output_path is not None and create_new_file and wf is None:
            output_wav = self.audio_output_path
            try:
                output_wav.parent.mkdir(parents=True, exist_ok=True)
                wf = wave.open(str(output_wav), "wb")  # noqa: SIM115
                wf.setnchannels(num_channels)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
            except Exception as exc:
                log_error(f"Failed to create WAV file {output_wav}: {exc}")
                return None, None, None, None

        if self.audio_output_path is not None and wf is not None:
            try:
                wf.writeframes(audio_data)
            except Exception as exc:
                log_error(f"Failed to write audio data: {exc}")
                return None, None, None, None

        return wf, sample_rate, num_channels, audio_data

    async def _send_audio_file(self, websocket, file_path: Path) -> None:
        assert self.silence_event is not None
        self.silence_event.set()
        await self.logger.log(f"{self.stream_id} sending input audio: {file_path.name}")
        try:
            with wave.open(str(file_path), "rb") as wav_file:
                n_channels = wav_file.getnchannels()
                frame_rate = wav_file.getframerate()
                sample_width = wav_file.getsampwidth()
                chunk_size = int((frame_rate * n_channels * CHUNK_DURATION_MS) / 1000) * sample_width
                self.audio_params = (frame_rate, n_channels, chunk_size)

                while True:
                    chunk = wav_file.readframes(chunk_size // sample_width)
                    if not chunk:
                        break
                    samples_in_chunk = len(chunk) / (sample_width * n_channels)
                    chunk_duration_ms = (samples_in_chunk / frame_rate) * 1000
                    await self.logger.log(
                        f"{self.stream_id} input chunk size={len(chunk)}B "
                        f"duration_ms={chunk_duration_ms:.1f} "
                        f"sample_rate={frame_rate} channels={n_channels}"
                    )
                    audio_frame = frames_pb2.AudioRawFrame(
                        audio=chunk,
                        sample_rate=frame_rate,
                        num_channels=n_channels,
                    )
                    await websocket.send(frames_pb2.Frame(audio=audio_frame).SerializeToString())
                    await asyncio.sleep(CHUNK_DURATION_MS / 1000)
        finally:
            self.timestamps["input_audio_file_end"] = dt.datetime.now()
            await self.logger.log(
                f"{self.stream_id} input audio finished at "
                f"{self.timestamps['input_audio_file_end'].strftime('%H:%M:%S.%f')[:-3]}"
            )
            self.silence_event.clear()

    async def _silence_sender_loop(self, websocket) -> None:
        self.silence_running = True
        try:
            while self.silence_running:
                if _SHUTDOWN_REQUESTED:
                    return
                if self.silence_event is None or self.silence_event.is_set() or self.audio_params is None:
                    await asyncio.sleep(0.1)
                    continue
                frame_rate, n_channels, chunk_size = self.audio_params
                silent_chunk = b"\x00" * chunk_size
                audio_frame = frames_pb2.AudioRawFrame(
                    audio=silent_chunk,
                    sample_rate=frame_rate,
                    num_channels=n_channels,
                )
                await websocket.send(frames_pb2.Frame(audio=audio_frame).SerializeToString())
                await asyncio.sleep(CHUNK_DURATION_MS / 1000)
        except ConnectionClosed:
            return

    async def _receive_initial_bot_intro(self, websocket, wf):
        try:
            data = await self._recv_audio_frame(websocket, timeout=BOT_INTRO_TIMEOUT)
        except TimeoutError:
            await self.logger.log(f"{self.stream_id} no initial bot intro within {BOT_INTRO_TIMEOUT}s")
            return wf
        await self.logger.log(f"{self.stream_id} received initial bot intro")
        wf, _ = await self._drain_utterance(websocket, data, wf, detect_glitches=False)
        return wf

    async def _drain_utterance(self, websocket, first_data: bytes, wf, *, detect_glitches: bool, drain_timeout=None):
        if drain_timeout is None:
            drain_timeout = END_OF_RESPONSE_TIMEOUT

        playback_buffer_duration = 0.0
        last_update_time = None
        chunk_count = 0
        data = first_data

        while True:
            wf, sample_rate, num_channels, audio_data = self._write_audio_to_wav(data, wf, create_new_file=(wf is None))
            if audio_data and sample_rate and num_channels:
                current_time = time.time()
                chunk_count += 1
                samples_in_chunk = len(audio_data) // (num_channels * 2)
                chunk_duration_seconds = samples_in_chunk / sample_rate
                await self.logger.log(
                    f"{self.stream_id} output chunk #{chunk_count} size={len(audio_data)}B "
                    f"duration_ms={chunk_duration_seconds * 1000:.1f}"
                )

                if detect_glitches:
                    if last_update_time is not None:
                        playback_buffer_duration -= current_time - last_update_time
                        if playback_buffer_duration < -0.020:
                            self.glitch_detected = True
                            await self.logger.log(
                                f"{self.stream_id} audio glitch detected: "
                                f"buffer underrun {(-playback_buffer_duration) * 1000:.1f}ms"
                            )
                            playback_buffer_duration = 0
                    playback_buffer_duration += chunk_duration_seconds
                    last_update_time = current_time

            try:
                data = await self._recv_audio_frame(websocket, timeout=drain_timeout)
            except TimeoutError:
                return wf, chunk_count

    async def _process_conversation_turn(self, websocket, audio_file_path: Path, wf):
        self.timestamps["input_audio_file_end"] = None
        await self.logger.log(f"{self.stream_id} turn start using {audio_file_path.name}")
        send_task = asyncio.create_task(self._send_audio_file(websocket, audio_file_path))
        turn_barge_ins = 0
        real_latency = None

        while True:
            data = await self._recv_audio_frame(websocket)
            utterance_start = dt.datetime.now()
            input_end = self.timestamps["input_audio_file_end"]
            is_barge_in = (
                input_end is None or (utterance_start - input_end).total_seconds() < self.reverse_barge_in_threshold
            )
            if is_barge_in:
                wf, _ = await self._drain_utterance(
                    websocket,
                    data,
                    wf,
                    detect_glitches=False,
                    drain_timeout=BARGE_IN_DRAIN_TIMEOUT,
                )
                turn_barge_ins += 1
            else:
                wf, _ = await self._drain_utterance(websocket, data, wf, detect_glitches=True)
                real_latency = (utterance_start - input_end).total_seconds()
                await self.logger.log(f"{self.stream_id} real response latency={real_latency:.3f}s")
                break

        await send_task

        if self.collecting_metrics and real_latency is not None:
            self.latency_values.append(real_latency)
            self.total_reverse_barge_ins += turn_barge_ins
            await self.logger.log(f"{self.stream_id} turn complete latency={real_latency:.3f}s")
        return wf

    async def _continuous_audio_loop(self, websocket, wf):
        turn_index = 0
        while self.running and not _SHUTDOWN_REQUESTED:
            now = time.time()
            if self.session_end_time and now >= self.session_end_time:
                self.collecting_metrics = False
                self.running = False
                await self.logger.log(f"{self.stream_id} session window closed")
                break
            if self.metrics_start_time and now >= self.metrics_start_time and not self.collecting_metrics:
                self.collecting_metrics = True
                await self.logger.log(f"{self.stream_id} metrics collection started")
            if (
                self.metrics_start_time
                and self.collecting_metrics
                and now >= self.metrics_start_time + self.test_duration
            ):
                self.collecting_metrics = False
                self.running = False
                await self.logger.log(f"{self.stream_id} metrics collection stopped")
                break

            audio_file = self.audio_files[turn_index % len(self.audio_files)]
            wf = await self._process_conversation_turn(websocket, audio_file, wf)
            turn_index += 1
            await asyncio.sleep(0.1)
        return wf

    async def run(self) -> ClientResult:
        await self.logger.log(f"{self.stream_id} starting client uri={self.uri}")
        if self.start_delay > 0:
            await self.logger.log(f"{self.stream_id} waiting start_delay={self.start_delay:.2f}s")
            await asyncio.sleep(self.start_delay)

        self.silence_event = asyncio.Event()
        self.silence_event.set()

        fallback_deadline = self.test_duration + HARD_DEADLINE_BUFFER
        if self.session_end_time:
            remaining = self.session_end_time - time.time()
            hard_deadline = max(remaining + 10, 30) if remaining > 0 else 30
        elif self.metrics_start_time:
            remaining = (self.metrics_start_time + self.test_duration + HARD_DEADLINE_BUFFER) - time.time()
            hard_deadline = max(remaining, 60) if remaining > 0 else fallback_deadline
        else:
            hard_deadline = fallback_deadline

        error = None
        try:
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            async with websockets.connect(self.uri, open_timeout=WS_CONNECT_TIMEOUT, ssl=ssl_ctx) as websocket:
                await self.logger.log(f"{self.stream_id} websocket connected")

                async def _run_session():
                    wf = await self._receive_initial_bot_intro(websocket, wf=None)
                    silence_task = asyncio.create_task(self._silence_sender_loop(websocket))
                    try:
                        wf = await self._continuous_audio_loop(websocket, wf)
                    finally:
                        self.silence_running = False
                        self.silence_event.set()
                        silence_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await silence_task
                    if wf is not None:
                        wf.close()

                await asyncio.wait_for(_run_session(), timeout=hard_deadline)
        except TimeoutError:
            error = f"Hard deadline reached ({hard_deadline:.0f}s)"
        except ConnectionClosed:
            error = "WebSocket connection closed"
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__

        if error:
            await self.logger.log(f"{self.stream_id} finished with error: {error}")
        else:
            await self.logger.log(f"{self.stream_id} finished successfully")

        server_metric_average = {key: average_or_none(values) for key, values in self.server_metric_samples.items()}
        server_metric_counts = {key: len(values) for key, values in self.server_metric_samples.items()}

        result = ClientResult(
            stream_id=self.stream_id,
            average_latency=average_or_none(self.latency_values),
            individual_latencies=self.latency_values,
            num_turns=len(self.latency_values),
            glitch_detected=self.glitch_detected,
            reverse_barge_in_threshold=self.reverse_barge_in_threshold,
            metrics_start_time=self.metrics_start_time,
            test_duration=self.test_duration,
            server_metrics={
                "samples": self.server_metric_samples,
                "average": server_metric_average,
                "sample_counts": server_metric_counts,
            },
            rtvi_messages=self.rtvi_messages,
            timestamp=dt.datetime.now().isoformat(),
            error=error,
        )
        await self.logger.log_table(
            f"{self.stream_id} latency breakdown summary",
            [
                ("client_avg_latency", round3(result.average_latency)),
                ("client_turns", str(result.num_turns)),
                ("glitch_detected", str(result.glitch_detected)),
                ("llm_ttft", round3(server_metric_average.get("llm_ttft"))),
                ("tts_ttfb", round3(server_metric_average.get("tts_ttfb"))),
                ("asr_ttfb", round3(server_metric_average.get("asr_ttfb"))),
                ("server_e2e", round3(server_metric_average.get("server_e2e"))),
                ("vad_smart_turn", round3(server_metric_average.get("vad_smart_turn"))),
                ("llm_processing_time", round3(server_metric_average.get("llm_processing_time"))),
                ("llm_tokens_per_sec", round3(server_metric_average.get("llm_tokens_per_sec"))),
            ],
        )
        return result


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path | None]:
    """Compute final result/log/audio paths, falling back to ``--output-dir``."""
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    result_path = Path(args.result_path).resolve() if args.result_path else out / f"result_{args.stream_id}.json"
    logger_path = Path(args.logger_path).resolve() if args.logger_path else out / f"benchmark_{args.stream_id}.log"

    if args.audio_output_path:
        audio_output_path: Path | None = Path(args.audio_output_path).resolve()
    elif args.save_audio:
        audio_output_path = out / f"audio_output_{args.stream_id}.wav"
    else:
        audio_output_path = None
    return result_path, logger_path, audio_output_path


def build_arg_parser() -> argparse.ArgumentParser:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Single-client voice-agent benchmark. Use simulate_concurrency.sh for parallel runs."
    )
    parser.add_argument("--host", default="localhost", help="WebSocket host")
    parser.add_argument("--port", type=int, default=7860, help="WebSocket port")
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=script_dir / "dataset",
        help="Directory containing 16 kHz mono WAV files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=script_dir,
        help="Default parent directory for result/log/audio outputs",
    )
    parser.add_argument("--stream-id", default="", help="Stream id; auto-generated when empty")
    parser.add_argument("--start-delay", type=float, default=0.0, help="Seconds to wait before connecting")
    parser.add_argument(
        "--metrics-start-time",
        type=float,
        help="Unix epoch seconds when metric collection should begin (defaults to now+start_delay)",
    )
    parser.add_argument(
        "--session-end-time",
        type=float,
        help="Unix epoch seconds when this client should stop (defaults to metrics_start+test_duration)",
    )
    parser.add_argument("--test-duration", type=float, default=150.0, help="Metric collection window in seconds")
    parser.add_argument(
        "--reverse-barge-in-threshold",
        type=float,
        default=0.4,
        help="Seconds after input ends before bot audio counts as the real response",
    )
    parser.add_argument("--result-path", type=Path, help="Write client result JSON here")
    parser.add_argument("--logger-path", type=Path, help="Write client log here")
    parser.add_argument("--audio-output-path", type=Path, help="Write client output WAV here")
    parser.set_defaults(save_audio=True)
    parser.add_argument(
        "--no-save-audio",
        dest="save_audio",
        action="store_false",
        help="Disable writing the default per-client output WAV",
    )

    # Aggregation modes — used by simulate_concurrency.sh after a run completes.
    aggregate = parser.add_argument_group("aggregation modes (post-run)")
    aggregate.add_argument(
        "--aggregate-run-dir",
        type=Path,
        help="Fold a directory of client_*/result_*.json into benchmark_summary.json",
    )
    aggregate.add_argument(
        "--aggregate-suite-dir",
        type=Path,
        help="Fold run_*_clients/benchmark_summary.json files into results.{tsv,txt,json}",
    )
    aggregate.add_argument(
        "--num-clients",
        type=int,
        help="Configured client count for --aggregate-run-dir (defaults to file count)",
    )
    return parser


async def async_main(args: argparse.Namespace) -> int:
    args.output_dir = args.output_dir.resolve()
    args.dataset_dir = args.dataset_dir.resolve()

    if not args.dataset_dir.is_dir():
        print(f"Dataset directory not found: {args.dataset_dir}", file=sys.stderr)
        return 2

    audio_files = sorted(p for p in args.dataset_dir.iterdir() if p.suffix.lower() == ".wav")
    if not audio_files:
        print(f"No .wav files found in {args.dataset_dir}", file=sys.stderr)
        return 2

    if not args.stream_id:
        args.stream_id = f"client_1_{str(time.time_ns())[:13]}"

    if args.metrics_start_time is None:
        args.metrics_start_time = time.time() + max(0.0, args.start_delay)
    if args.session_end_time is None:
        args.session_end_time = args.metrics_start_time + args.test_duration

    result_path, logger_path, audio_output_path = _resolve_paths(args)

    logger = RunLogger(logger_path)
    client = PerfClient(
        stream_id=args.stream_id,
        host=args.host,
        port=int(args.port),
        audio_files=audio_files,
        start_delay=float(args.start_delay),
        metrics_start_time=float(args.metrics_start_time),
        session_end_time=float(args.session_end_time),
        test_duration=float(args.test_duration),
        reverse_barge_in_threshold=float(args.reverse_barge_in_threshold),
        audio_output_path=audio_output_path,
        logger=logger,
    )
    result = await client.run()
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    print(
        f"client={args.stream_id} turns={result.num_turns} "
        f"avg_latency={round3(result.average_latency)}s "
        f"glitch={result.glitch_detected} "
        f"result={result_path}"
    )
    return 0


# ---------------------------------------------------------------------------
# Aggregation helpers (used by --aggregate-run-dir / --aggregate-suite-dir)
# ---------------------------------------------------------------------------

_SUITE_HEADERS = (
    "Parallel Streams",
    "Successful",
    "Avg Latency",
    "P95 Latency",
    "Min Latency",
    "Max Latency",
    "LLM TTFT",
    "TTS TTFB",
    "ASR TTFB",
    "Server E2E",
    "VAD+Smart Turn",
    "LLM Proc Time",
    "Glitches",
)


def _calculate_p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = math.ceil(0.95 * len(ordered)) - 1
    return ordered[max(0, min(idx, len(ordered) - 1))]


def _weighted_avg(per_client: list[dict], key: str) -> tuple[float | None, int]:
    weighted = 0.0
    total = 0
    for c in per_client:
        sm = c.get("server_metrics") or {}
        avg = (sm.get("average") or {}).get(key)
        cnt = (sm.get("sample_counts") or {}).get(key, 0)
        if avg is not None and cnt:
            weighted += float(avg) * int(cnt)
            total += int(cnt)
    return ((weighted / total) if total else None), total


def _format_table_lines(headers: Iterable[str], rows: list[list[str]]) -> list[str]:
    """Column-aligned text table; numeric columns right-justified."""
    headers = list(headers)
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(val))

    def is_num(v: str) -> bool:
        v = v.strip()
        if not v:
            return False
        try:
            float(v)
        except ValueError:
            return False
        return True

    right = [bool(rows) and i > 0 and all(is_num(row[i]) for row in rows) for i in range(len(headers))]

    def render(values: list[str]) -> str:
        return "  ".join(
            (values[i].rjust(widths[i]) if right[i] else values[i].ljust(widths[i])) for i in range(len(headers))
        )

    out = [render(headers), "  ".join("-" * w for w in widths)]
    for row in rows:
        out.append(render(row))
    return out


def _aggregate_run_dir(run_dir: Path, num_clients: int | None) -> Path:
    """Collapse all client_*/result_*.json into a benchmark_summary.json."""
    result_files = sorted(run_dir.glob("client_*/result_*.json"))
    clients: list[dict] = [json.loads(p.read_text(encoding="utf-8")) for p in result_files]

    if num_clients is None:
        num_clients = len(clients)

    valid = [c for c in clients if c.get("average_latency") is not None and int(c.get("num_turns", 0)) > 0]
    latencies = [float(c["average_latency"]) for c in valid]

    server_avg: dict[str, float | None] = {}
    server_counts: dict[str, int] = {}
    for key in SERVER_METRIC_KEYS:
        avg, total = _weighted_avg(clients, key)
        server_avg[key] = avg
        server_counts[key] = total

    summary = {
        "timestamp": dt.datetime.now().isoformat(),
        "config": {
            "num_clients": num_clients,
            "test_duration": (clients[0].get("test_duration") if clients else None),
            "metrics_start_time": (clients[0].get("metrics_start_time") if clients else None),
            "concurrency_mode": "process-per-client",
        },
        "results": {
            "configured_clients": num_clients,
            "successful_clients": len(valid),
            "total_turns": sum(int(c.get("num_turns", 0)) for c in valid),
            "aggregate_average_latency": average_or_none(latencies),
            "p95_client_latency": _calculate_p95(latencies),
            "min_client_latency": (min(latencies) if latencies else None),
            "max_client_latency": (max(latencies) if latencies else None),
            "server_metrics": {"average": server_avg, "sample_counts": server_counts},
            "glitch_detection": {
                "clients_with_glitches": sum(1 for c in valid if c.get("glitch_detected")),
                "total_clients": len(valid),
                "affected_client_ids": [c["stream_id"] for c in valid if c.get("glitch_detected")],
            },
            "error_detection": {
                "total_clients": len(clients),
                "clients_with_errors": sum(1 for c in clients if c.get("error")),
                "client_error_counts": {c["stream_id"]: 1 for c in clients if c.get("error")},
            },
        },
        "clients": clients,
    }

    out = run_dir / "benchmark_summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return out


def _row_from_summary(summary: dict[str, Any], num_clients: int) -> dict[str, Any]:
    r = summary["results"]
    sa = r["server_metrics"]["average"]
    return {
        "parallel_streams": num_clients,
        "successful_streams": r["successful_clients"],
        "configured_streams": r["configured_clients"],
        "avg_latency": r["aggregate_average_latency"],
        "p95_latency": r["p95_client_latency"],
        "min_latency": r["min_client_latency"],
        "max_latency": r["max_client_latency"],
        "llm_ttft": sa.get("llm_ttft"),
        "tts_ttfb": sa.get("tts_ttfb"),
        "asr_ttfb": sa.get("asr_ttfb"),
        "server_e2e": sa.get("server_e2e"),
        "vad_smart_turn": sa.get("vad_smart_turn"),
        "llm_processing_time": sa.get("llm_processing_time"),
        "audio_glitches": r["glitch_detection"]["clients_with_glitches"],
    }


def _row_to_strings(row: dict[str, Any]) -> list[str]:
    return [
        str(row["parallel_streams"]),
        f"{row['successful_streams']}/{row['configured_streams']}",
        round3(row["avg_latency"]),
        round3(row["p95_latency"]),
        round3(row["min_latency"]),
        round3(row["max_latency"]),
        round3(row["llm_ttft"]),
        round3(row["tts_ttfb"]),
        round3(row["asr_ttfb"]),
        round3(row["server_e2e"]),
        round3(row["vad_smart_turn"]),
        round3(row["llm_processing_time"]),
        str(row["audio_glitches"]),
    ]


def _aggregate_suite_dir(suite_dir: Path) -> tuple[Path, Path, Path]:
    """Emit results.{tsv,txt,json} for a sweep dir or a single-level run dir.

    Sweep layout (one row per ``run_<N>_clients`` subdir):
        suite_dir/run_<N>_clients/benchmark_summary.json

    Single-level layout (one row, taken from the summary at the top level):
        suite_dir/benchmark_summary.json
    """
    run_dirs = sorted(
        (p for p in suite_dir.iterdir() if p.is_dir() and p.name.startswith("run_")),
        key=lambda p: int(p.name.split("_")[1]) if p.name.split("_")[1].isdigit() else 0,
    )

    rows: list[dict[str, Any]] = []
    if run_dirs:
        for run_dir in run_dirs:
            try:
                num_clients = int(run_dir.name.split("_")[1])
            except (IndexError, ValueError):
                continue
            summary_path = run_dir / "benchmark_summary.json"
            if not summary_path.exists():
                continue
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            rows.append(_row_from_summary(summary, num_clients))
    else:
        summary_path = suite_dir / "benchmark_summary.json"
        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            num_clients = int(summary.get("config", {}).get("num_clients") or summary["results"]["configured_clients"])
            rows.append(_row_from_summary(summary, num_clients))

    tsv = suite_dir / "results.tsv"
    txt = suite_dir / "results.txt"
    js = suite_dir / "results.json"

    str_rows = [_row_to_strings(r) for r in rows]
    with tsv.open("w", encoding="utf-8") as f:
        f.write("\t".join(_SUITE_HEADERS) + "\n")
        for row in str_rows:
            f.write("\t".join(row) + "\n")

    txt.write_text("\n".join(_format_table_lines(_SUITE_HEADERS, str_rows)) + "\n", encoding="utf-8")
    js.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return tsv, txt, js


def _run_aggregate_run(run_dir: Path, num_clients: int | None) -> int:
    run_dir = run_dir.resolve()
    if not run_dir.is_dir():
        print(f"--aggregate-run-dir not found: {run_dir}", file=sys.stderr)
        return 2
    summary_path = _aggregate_run_dir(run_dir, num_clients=num_clients)
    r = json.loads(summary_path.read_text(encoding="utf-8"))["results"]
    print(
        f"run aggregated: {summary_path}  "
        f"successful={r['successful_clients']}/{r['configured_clients']}  "
        f"avg_latency={round3(r['aggregate_average_latency'])}s  "
        f"p95={round3(r['p95_client_latency'])}s"
    )
    return 0


def _run_aggregate_suite(suite_dir: Path) -> int:
    suite_dir = suite_dir.resolve()
    if not suite_dir.is_dir():
        print(f"--aggregate-suite-dir not found: {suite_dir}", file=sys.stderr)
        return 2
    tsv, txt, js = _aggregate_suite_dir(suite_dir)
    print(f"suite aggregated: {suite_dir}")
    print(f"  TXT:  {txt}")
    print(f"  TSV:  {tsv}")
    print(f"  JSON: {js}")
    return 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def main() -> int:
    args = build_arg_parser().parse_args()

    if args.aggregate_run_dir is not None:
        return _run_aggregate_run(args.aggregate_run_dir, args.num_clients)
    if args.aggregate_suite_dir is not None:
        return _run_aggregate_suite(args.aggregate_suite_dir)

    try:
        return asyncio.run(async_main(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
