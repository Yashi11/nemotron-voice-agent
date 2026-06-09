# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Transport owner subagent."""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    ClientConnectedFrame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMRunFrame,
    LLMTextFrame,
    SpeechControlParamsFrame,
    TTSUpdateSettingsFrame,
    UserMuteStartedFrame,
    UserMuteStoppedFrame,
)
from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMAssistantAggregator
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame
from pipecat.runner.types import RunnerArguments
from pipecat.services.nvidia.tts import NvidiaTTSService, NvidiaTTSSettings
from pipecat.turns.user_mute.mute_until_first_bot_complete_user_mute_strategy import (
    MuteUntilFirstBotCompleteUserMuteStrategy,
)
from pipecat_subagents.agents import BaseAgent
from pipecat_subagents.bus import AgentBus, BusBridgeProcessor
from pipecat_subagents.bus.messages import BusTaskResponseMessage

from attachment_store import clear_session_attachments, register_attachment_listener
from examples.omni_assistant.pipeline import _build_user_turn_processor
from examples.omni_assistant.user_mute_processor import UserMuteProcessor
from examples.omni_assistant_subagents.media_dispatch_processor import PostAckMediaDispatchProcessor
from examples.omni_assistant_subagents.subagents.transport.media_analysis_controller import MediaAnalysisController
from examples.omni_assistant_subagents.subagents.transport.speaker_context import (
    SpeakerContextManager,
)
from examples.omni_assistant_subagents.subagents.transport.visual_control import (
    VisualControlController,
)
from examples.omni_assistant_subagents.subagents.transport.webcam_controller import (
    WebcamController,
)
from examples.omni_assistant_subagents.subagents.webcam import WebcamAgent
from examples.shared.nemotron_speech_text_filter import NemotronSpeechTextFilter
from tracing import IS_TRACING_ENABLED
from utils import load_ipa_dictionary, parse_env_float, parse_env_int
from webcam_frame_store import clear_session_webcam_frames

# Delay before emitting a follow-up assistant turn from a completed analyzer task.
# ``@pipecat-ai/client-react`` currently finalizes an assistant bubble ~2.5s after
# ``BotStoppedSpeaking``; emitting new text sooner is rendered as a same-turn
# continuation instead of a fresh turn. Remove this delay once the client exposes
# an explicit assistant-turn boundary signal.
_ANALYZER_FOLLOWUP_TURN_DELAY_SECS = 2.6


class OmniTransportAgent(BaseAgent):
    """Owns transport I/O and bridges user frames to Speaker Omni."""

    AGENT_NAME = "omni_transport"

    def __init__(
        self,
        name: str | None = None,
        *,
        bus: AgentBus,
        transport,
        context: LLMContext,
        api_key: str,
        tts_server: str,
        tts_ssl: bool,
        tts_voice: str,
        runner_args: RunnerArguments,
        session_id: str,
    ) -> None:
        """Initialize the transport owner."""
        super().__init__(name or self.AGENT_NAME, bus=bus, active=True)
        self._transport = transport
        self._context = context
        self._api_key = api_key
        self._tts_server = tts_server
        self._tts_ssl = tts_ssl
        self._tts_voice = tts_voice
        self._runner_args = runner_args
        self._session_id = session_id
        self._tts: NvidiaTTSService | None = None
        self._latency_turn_count = 1
        self._unregister_attachment_listener = None
        self._speaker_context = SpeakerContextManager(
            context=self._context,
            session_id=self._session_id,
            recent_turns=parse_env_int("OMNI_SPEAKER_RECENT_TURNS", 4, min_value=1),
        )
        self._visual_control = VisualControlController(
            context=self._context,
            emit_update=self._emit_webcam_control_update,
            interrupt_for_stop=self._interrupt_for_visual_stop,
            ask_stop_confirmation=self._ask_visual_stop_confirmation,
            continue_after_visual_resume=self._continue_after_visual_resume,
            start_pending_media_analysis=self.start_pending_media_analysis,
        )
        self._media_analysis = MediaAnalysisController(
            session_id=self._session_id,
            context=self._context,
            request_task=self.request_task,
            queue_frame=lambda frame: self.pipeline_task.queue_frame(frame),
            is_visual_control_stopped=self._visual_control.is_stopped,
            followup_delay_secs=_ANALYZER_FOLLOWUP_TURN_DELAY_SECS,
        )
        self._webcam_controller = WebcamController(
            session_id=self._session_id,
            speaker_context=self._speaker_context,
            request_task=self.request_task,
            queue_frame=lambda frame: self.pipeline_task.queue_frame(frame),
            is_visual_control_stopped=self._visual_control.is_stopped,
        )

    async def build_pipeline(self) -> Pipeline:
        """Build the transport pipeline with a bus bridge in the LLM slot."""
        self._tts = NvidiaTTSService(
            api_key=self._api_key,
            server=self._tts_server,
            settings=NvidiaTTSSettings(voice=self._tts_voice),
            use_ssl=self._tts_ssl,
            text_filters=[NemotronSpeechTextFilter()],
            custom_dictionary=load_ipa_dictionary(),
            stop_frame_timeout_s=parse_env_float("TTS_STOP_FRAME_TIMEOUT_S", 30.0, min_value=5.0),
        )
        logger.info(
            f"Nemotron Omni subagents TTS: server={self._tts_server}, ssl={self._tts_ssl}, voice={self._tts_voice}"
        )

        assistant_aggregator = LLMAssistantAggregator(self._context)
        return Pipeline(
            [
                self._transport.input(),
                UserMuteProcessor(strategies=[MuteUntilFirstBotCompleteUserMuteStrategy()]),
                VADProcessor(vad_analyzer=SileroVADAnalyzer(params=VADParams())),
                _build_user_turn_processor(),
                BusBridgeProcessor(
                    bus=self.bus,
                    agent_name=self.name,
                    exclude_frames=(
                        ClientConnectedFrame,
                        LLMFullResponseStartFrame,
                        LLMTextFrame,
                        LLMFullResponseEndFrame,
                        RTVIServerMessageFrame,
                        SpeechControlParamsFrame,
                        UserMuteStartedFrame,
                        UserMuteStoppedFrame,
                    ),
                ),
                PostAckMediaDispatchProcessor(handler=self),
                self._tts,
                self._transport.output(),
                assistant_aggregator,
            ]
        )

    def build_pipeline_task(self, pipeline: Pipeline) -> PipelineTask:
        """Create the transport task with RTVI and latency metrics enabled."""
        latency_observer = UserBotLatencyObserver()
        latest_latency_turn_id = ""
        latest_latency_turn_label = ""
        latest_latency_ms: float | None = None

        @latency_observer.event_handler("on_latency_measured")
        async def on_latency(observer, latency):
            nonlocal latest_latency_ms, latest_latency_turn_id, latest_latency_turn_label
            latest_latency_turn_id = f"turn-{self._latency_turn_count}"
            latest_latency_turn_label = f"Turn {self._latency_turn_count}"
            latest_latency_ms = round(latency * 1000, 3)
            logger.info(f"Nemotron Omni subagents User->Bot latency: {latency:.3f}s")

        @latency_observer.event_handler("on_latency_breakdown")
        async def on_latency_breakdown(observer, breakdown):
            nonlocal latest_latency_ms, latest_latency_turn_id, latest_latency_turn_label
            if latest_latency_ms is None:
                return
            metrics = [
                {
                    "key": "total_latency_ms",
                    "label": "Total Latency",
                    "value": latest_latency_ms,
                    "unit": "ms",
                }
            ]
            if breakdown.user_turn_secs is not None:
                metrics.append(
                    {
                        "key": "user_turn_ms",
                        "label": "User Turn",
                        "value": round(breakdown.user_turn_secs * 1000, 3),
                        "unit": "ms",
                    }
                )
            for index, ttfb in enumerate(breakdown.ttfb):
                processor = ttfb.processor.replace("#", "_").replace(" ", "_")
                metrics.append(
                    {
                        "key": f"ttfb_{index}_{processor}",
                        "label": f"{ttfb.processor} TTFB",
                        "value": round(ttfb.duration_secs * 1000, 3),
                        "unit": "ms",
                    }
                )
            if breakdown.text_aggregation is not None:
                metrics.append(
                    {
                        "key": "text_aggregation_ms",
                        "label": f"{breakdown.text_aggregation.processor} Text Aggregation",
                        "value": round(breakdown.text_aggregation.duration_secs * 1000, 3),
                        "unit": "ms",
                    }
                )
            if not metrics:
                return
            await self.pipeline_task.queue_frame(
                RTVIServerMessageFrame(
                    data={
                        "type": "metric-group",
                        "group_id": latest_latency_turn_id,
                        "group_label": latest_latency_turn_label,
                        "category": "latency",
                        "source": "UserBotLatencyObserver",
                        "metrics": metrics,
                    }
                )
            )
            events = breakdown.chronological_events()
            if events:
                logger.info(f"Nemotron Omni subagents latency breakdown: {' | '.join(events)}")
            self._latency_turn_count += 1
            latest_latency_ms = None
            latest_latency_turn_id = ""
            latest_latency_turn_label = ""

        return PipelineTask(
            pipeline,
            params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
            idle_timeout_secs=self._runner_args.pipeline_idle_timeout_secs,
            observers=[latency_observer],
            enable_tracing=IS_TRACING_ENABLED,
            enable_rtvi=True,
        )

    async def create_pipeline_task(self) -> PipelineTask:
        """Create the transport task and register client event handlers."""
        pipeline_task = await super().create_pipeline_task()

        @pipeline_task.rtvi.event_handler("on_client_ready")
        async def on_client_connected(rtvi):
            logger.info("Nemotron Omni subagents client connected")
            self._start_attachment_state_listener()
            self._webcam_controller.refresh_input_state_context()
            self._context.add_message({"role": "user", "content": "Please introduce yourself to the user."})
            self._webcam_controller.start_summary_loop()
            await pipeline_task.queue_frame(LLMRunFrame())

        @self._transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info("Nemotron Omni subagents client disconnected")
            self._webcam_controller.stop_summary_loop()
            self._stop_attachment_state_listener()
            clear_session_attachments(self._session_id)
            clear_session_webcam_frames(self._session_id)
            await self.cancel()

        @pipeline_task.rtvi.event_handler("on_client_message")
        async def on_client_message(rtvi, message):
            payload = message.data if isinstance(message.data, dict) else {}
            if message.type == "set-voice":
                await self._apply_set_voice(payload, pipeline_task)
            elif message.type == "webcam-state":
                await self._webcam_controller.apply_webcam_state(payload)

        return pipeline_task

    async def queue_media_analysis_prompt(
        self,
        transcript: str,
        prompt: str,
        action: str,
        selected_input_source: str,
    ) -> None:
        """Queue Speaker Omni's hidden analyzer prompt after its acknowledgement closes."""
        await self._media_analysis.queue_prompt(transcript, prompt, action, selected_input_source)

    def has_uploaded_attachment(self) -> bool:
        """Return whether this session currently has an uploaded attachment."""
        return self._media_analysis.has_uploaded_attachment()

    async def start_pending_media_analysis(self) -> None:
        """Dispatch the LLM-selected analyzer after the ack turn has completed."""
        await self._media_analysis.start_pending()

    async def on_user_voice_turn_started(self) -> None:
        """Start short-lived webcam memory updates for the active user turn."""
        await self._webcam_controller.on_user_voice_turn_started()
        await self._visual_control.reset_by_user_voice()

    async def on_user_voice_turn_stopped(self) -> None:
        """Update webcam capture policy once the user turn reaches EOU."""
        await self._webcam_controller.on_user_voice_turn_stopped()

    async def on_user_interrupted_assistant(self) -> None:
        """Cancel pending post-ack media work when the ack was interrupted by speech."""
        await self._media_analysis.clear_pending_on_interruption()

    async def on_assistant_speaking_started(self) -> None:
        """Track active assistant speech for webcam visual-control scoring."""
        await self._webcam_controller.on_assistant_speaking_started()

    async def on_assistant_speaking_stopped(self) -> None:
        """Track when assistant speech has stopped."""
        await self._webcam_controller.on_assistant_speaking_stopped()

    async def on_task_response(self, message: BusTaskResponseMessage) -> None:
        """Route analyzer task results back to Speaker Omni for the spoken answer."""
        await super().on_task_response(message)
        response = message.response or {}
        source = str(getattr(message, "source", "") or "")
        mode = str(response.get("mode") or "").strip()
        if source == WebcamAgent.AGENT_NAME:
            if mode == "summary":
                summary_result = await self._webcam_controller.handle_summary_response(message.task_id, response)
                if summary_result is not None:
                    await self._visual_control.handle(summary_result.visual_control, frame=summary_result.frame)
            elif mode:
                logger.debug(f"Ignoring unsupported webcam task response mode: {mode}")
            return
        await self._media_analysis.handle_task_response(message)

    def _start_attachment_state_listener(self) -> None:
        """Refresh Speaker input-state context when browser uploads an attachment."""
        if self._unregister_attachment_listener:
            return
        loop = asyncio.get_running_loop()
        self._unregister_attachment_listener = register_attachment_listener(
            self._session_id,
            lambda: loop.call_soon_threadsafe(self._webcam_controller.refresh_input_state_context),
        )

    def _stop_attachment_state_listener(self) -> None:
        """Stop listening for attachment uploads for this session."""
        if self._unregister_attachment_listener:
            self._unregister_attachment_listener()
        self._unregister_attachment_listener = None

    async def _interrupt_for_visual_stop(self) -> None:
        """Interrupt current assistant audio without speaking a new response."""
        logger.info("Visual barge-in: interrupting assistant because the user signaled stop")
        await self.pipeline_task.queue_frame(InterruptionFrame())

    async def _ask_visual_stop_confirmation(self) -> None:
        """Interrupt and ask a short confirmation for an ambiguous visual stop."""
        confirmation = "Do you want me to stop?"
        logger.info("Visual barge-in: asking stop confirmation")
        await self.pipeline_task.queue_frame(InterruptionFrame())
        self._context.add_message({"role": "assistant", "content": confirmation})
        await self.pipeline_task.queue_frame(LLMFullResponseStartFrame())
        await self.pipeline_task.queue_frame(LLMTextFrame(text=confirmation))
        await self.pipeline_task.queue_frame(LLMFullResponseEndFrame())

    async def _continue_after_visual_resume(self) -> None:
        """Resume Speaker Omni after a visual continue cue."""
        await self.pipeline_task.queue_frame(LLMRunFrame())

    async def _emit_webcam_control_update(
        self,
        *,
        visual_control: dict[str, Any],
        action: str,
        state: str,
        frame: dict,
    ) -> None:
        """Emit a visual barge-in action for UI/debugging."""
        await self.pipeline_task.queue_frame(
            RTVIServerMessageFrame(
                data={
                    "type": "webcam-control-update",
                    "agent": WebcamAgent.AGENT_NAME,
                    "state": state,
                    "action": action,
                    "visual_control": visual_control,
                    "frame": frame,
                }
            )
        )

    async def _apply_set_voice(self, payload: dict[str, Any], pipeline_task: PipelineTask) -> None:
        voice_id = payload.get("voice_id", "")
        language = payload.get("language", "")
        if not voice_id or self._tts is None:
            return
        settings_kwargs: dict[str, Any] = {"voice": voice_id}
        if language:
            settings_kwargs["language"] = language
        await pipeline_task.queue_frame(
            TTSUpdateSettingsFrame(
                delta=NvidiaTTSSettings(**settings_kwargs),
                service=self._tts,
            )
        )
        logger.info(f"Nemotron Omni subagents voice switched -> {voice_id}")
