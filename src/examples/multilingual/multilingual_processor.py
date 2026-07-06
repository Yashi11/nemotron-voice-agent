# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Multilingual support for the cascaded pipeline.

The LLM answers with a single strict JSON object,
``{"lang_id": "<code>", "response": "<spoken reply>"}``. A streaming aggregator
extracts ``lang_id`` early (to switch the TTS voice the moment it is known) and
streams ``response`` sentence-by-sentence to TTS. Only the spoken ``response``
lands in chat history — ``lang_id`` is a side-channel that never pollutes the
conversation context.

``PerTurnReminderProcessor`` re-states the JSON contract on every user turn at
request time only, so the stored context stays clean.
"""

import copy
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping

from loguru import logger
from pipecat.frames.frames import (
    AggregatedTextFrame,
    Frame,
    LLMContextFrame,
    LLMTextFrame,
    TTSUpdateSettingsFrame,
)
from pipecat.pipeline.worker import PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.nvidia.tts import NvidiaTTSService, NvidiaTTSSettings
from pipecat.utils.text.base_text_aggregator import (
    Aggregation,
    AggregationType,
    BaseTextAggregator,
)
from pipecat.utils.text.simple_text_aggregator import SimpleTextAggregator

import config_store
from examples.shared.json_stream import JsonStringFieldStreamer, extract_json_payload
from examples.shared.prewarm import build_session_languages, load_voice_map
from utils import normalize_lang_code

LANG_FIELD = "lang_id"
RESPONSE_FIELD = "response"

# No aggregation types are hidden from TTS anymore: only the spoken ``response``
# is ever emitted as an aggregation. Kept for pipeline wiring compatibility.
SKIP_TTS_AGGREGATIONS: list[str] = []

_LanguageHandler = Callable[[str], Awaitable[None]]
_LanguageSwitchNotifier = Callable[[str, str], Awaitable[None]]


class MultilingualTextAggregator(BaseTextAggregator):
    """Streaming aggregator for ``{"lang_id": "<code>", "response": "<reply>"}``.

    Yields only ``"sentence"`` aggregations for the spoken ``response`` field.
    ``on_language`` fires as soon as the ``lang_id`` string closes, which — since
    the model is instructed to emit ``lang_id`` first — happens before any spoken
    text streams, preserving early TTS voice switching.
    """

    def __init__(self, *, on_language: _LanguageHandler | None = None):
        """Build the aggregator with an optional language-switch callback."""
        super().__init__(aggregation_type=AggregationType.SENTENCE)
        self._on_language = on_language
        self._sentence_aggregator = SimpleTextAggregator()
        self._reset_stream_state()

    def _reset_stream_state(self) -> None:
        self._lang_streamer = JsonStringFieldStreamer(LANG_FIELD)
        self._response_streamer = JsonStringFieldStreamer(RESPONSE_FIELD)
        self._lang_buf = ""
        self._raw = ""
        self._lang_handler_fired = False
        self._got_response_chars = False

    @property
    def text(self) -> Aggregation:
        """Return the currently buffered spoken text as a sentence aggregation."""
        return Aggregation(text=self._sentence_aggregator.text.text, type=AggregationType.SENTENCE.value)

    async def aggregate(self, text: str) -> AsyncIterator[Aggregation]:
        """Consume streaming LLM JSON and yield spoken-response sentences."""
        self._raw += text

        if not self._lang_streamer.done:
            self._lang_buf += self._lang_streamer.feed(text)
            if self._lang_streamer.done:
                await self._maybe_fire_language_handler()

        response_chunk = self._response_streamer.feed(text)
        if response_chunk:
            self._got_response_chars = True
            async for agg in self._sentence_aggregator.aggregate(response_chunk):
                yield agg

    async def flush(self) -> Aggregation | None:
        """Yield any pending spoken text once the LLM response ends."""
        if not self._lang_handler_fired:
            if not self._lang_buf:
                code = str(extract_json_payload(self._raw).get(LANG_FIELD, "")).strip()
                if code:
                    self._lang_buf = code
            await self._maybe_fire_language_handler()

        trailing = await self._sentence_aggregator.flush()
        if trailing and trailing.text.strip():
            return trailing

        if not self._got_response_chars:
            raw = self._raw.strip()
            response = str(extract_json_payload(raw).get(RESPONSE_FIELD, "")).strip()
            if not response and raw and not raw.lstrip().startswith("{"):
                # The model ignored the JSON contract and returned plain prose
                # (common with small models when server-side guided decoding is
                # unavailable). Speak it as-is instead of dropping the whole turn.
                logger.warning(f"Multilingual: LLM response not JSON; speaking raw text: {raw[:200]!r}")
                response = raw
            if response:
                return Aggregation(text=response, type=AggregationType.SENTENCE.value)
            if raw:
                logger.warning(f"Multilingual: empty/invalid LLM response; dropping: {raw[:200]!r}")
        return None

    def set_on_language(self, handler: _LanguageHandler | None) -> None:
        """Wire (or rewire) the language-switch handler post-construction."""
        self._on_language = handler

    async def handle_interruption(self):
        """Drop all buffered state when the user interrupts the bot."""
        await self.reset()

    async def reset(self):
        """Clear buffered state and reset the streaming parse."""
        self._reset_stream_state()
        await self._sentence_aggregator.reset()

    async def _maybe_fire_language_handler(self) -> None:
        if self._lang_handler_fired or self._on_language is None:
            return
        code = self._lang_buf.strip()
        if not code:
            return
        self._lang_handler_fired = True
        try:
            await self._on_language(code)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Multilingual: language handler failed: {exc}")


class PerTurnReminderProcessor(FrameProcessor):
    """Append a format reminder to the last user message at request time only.

    Sits between the user aggregator and the LLM. When an ``LLMContextFrame``
    passes through, it forwards a *copy* of the context whose last user message
    carries the reminder, leaving the shared/stored context untouched so chat
    history (and summaries) never contain the reminder text.
    """

    def __init__(self, reminder: str):
        """Build the processor with the reminder text to inject per turn."""
        super().__init__()
        self._reminder = (reminder or "").strip()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Forward frames; inject the reminder into outbound context frames."""
        await super().process_frame(frame, direction)
        if self._reminder and isinstance(frame, LLMContextFrame):
            await self.push_frame(self._reminded_frame(frame), direction)
            return
        await self.push_frame(frame, direction)

    def _reminded_frame(self, frame: LLMContextFrame) -> LLMContextFrame:
        source = frame.context
        messages = self._append_reminder(list(source.get_messages()))
        new_context = LLMContext(messages, tools=source.tools, tool_choice=source.tool_choice)
        return LLMContextFrame(context=new_context)

    def _append_reminder(self, messages: list) -> list:
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if isinstance(msg, dict) and msg.get("role") == "user":
                messages[i] = self._augment(msg)
                return messages
        messages.append({"role": "user", "content": self._reminder})
        return messages

    def _augment(self, msg: dict) -> dict:
        content = msg.get("content")
        if isinstance(content, str):
            return {**msg, "content": f"{content}\n\n{self._reminder}"}
        if isinstance(content, list):
            return {**msg, "content": [*content, {"type": "text", "text": self._reminder}]}
        return {**msg, "content": self._reminder}


def build_response_schema(lang_codes: list[str]) -> dict:
    """Build the JSON schema for ``{"lang_id": ..., "response": ...}`` output."""
    lang_schema: dict = {"type": "string"}
    codes = [code for code in (lang_codes or []) if code]
    if codes:
        lang_schema["enum"] = codes
    return {
        "type": "object",
        "properties": {
            LANG_FIELD: lang_schema,
            RESPONSE_FIELD: {"type": "string"},
        },
        "required": [LANG_FIELD, RESPONSE_FIELD],
        "additionalProperties": False,
    }


def with_reasoning(extra: dict, enabled: bool) -> dict:
    """Return a copy of OpenAI extra params with reasoning toggled.

    Sets ``extra_body.chat_template_kwargs.enable_thinking``. Used to enable
    reasoning for the out-of-band summarizer (better summary faithfulness)
    while spoken turns stay reasoning-off for low latency.
    """
    merged = copy.deepcopy(extra) if extra else {}
    extra_body = merged.setdefault("extra_body", {})
    if not isinstance(extra_body, dict):
        return merged
    ctk = extra_body.setdefault("chat_template_kwargs", {})
    if isinstance(ctk, dict):
        ctk["enable_thinking"] = enabled
    return merged


def apply_guided_json(extra: dict, lang_codes: list[str]) -> dict:
    """Enable server-side JSON enforcement in OpenAI-style extra params.

    Sets ``response_format={"type": "json_object"}`` — the OpenAI-standard JSON
    mode honored by both vLLM and NIM — which reliably forces the model to emit
    a valid JSON object (this is what makes the omni_assistant example
    consistent). Additionally attaches an ``nvext.guided_json`` schema with the
    allowed ``lang_id`` enum for servers that support NVIDIA guided decoding
    (e.g. NIM); vanilla vLLM ignores ``nvext`` harmlessly. Existing
    ``extra_body`` keys (e.g. ``chat_template_kwargs``, ``repetition_penalty``)
    are preserved.
    """
    merged = copy.deepcopy(extra) if extra else {}

    # Primary enforcement: OpenAI JSON mode (honored by vLLM and NIM).
    merged["response_format"] = {"type": "json_object"}

    # Optional schema/enum enforcement for NIM-style guided decoding.
    extra_body = merged.setdefault("extra_body", {})
    if not isinstance(extra_body, dict):
        logger.warning("Multilingual: extra_params 'extra_body' is not a dict; skipping nvext.guided_json")
        return merged
    nvext = extra_body.get("nvext")
    if not isinstance(nvext, dict):
        nvext = {}
        extra_body["nvext"] = nvext
    nvext["guided_json"] = build_response_schema(lang_codes)
    return merged


# Human-readable names (with endonym for non-Latin scripts) keyed by the base
# language subtag. Naming the language explicitly — plus a "do not mix other
# languages" hint — steers small models far better than a bare BCP-47 code,
# especially across languages that share a script (e.g. Devanagari is used by
# Hindi, Marathi, and Nepali). Falls back to the raw code for unknown subtags.
#
# Scoped to the languages supported by both the ASR and TTS services (the
# Magpie TTS voice set is the limiting factor). Extend as more voices/languages
# become available.
_LANGUAGE_NAMES: dict[str, str] = {
    "de": "German (Deutsch)",
    "en": "English",
    "es": "Spanish (español)",
    "fr": "French (français)",
    "hi": "Hindi (हिन्दी)",
    "it": "Italian (italiano)",
    "ja": "Japanese (日本語)",
    "vi": "Vietnamese (Tiếng Việt)",
    "zh": "Chinese (中文)",
}


def describe_language(code: str) -> str:
    """Return a human-readable language name for a BCP-47 code (falls back to the code)."""
    if not code:
        return ""
    base = code.split("-")[0].strip().lower()
    return _LANGUAGE_NAMES.get(base, code)


_ONE_LANGUAGE_RULE = (
    "Your ENTIRE response must be in ONE single language only — never mix two languages "
    "and never switch language mid-sentence."
)


def build_reminder(lang_codes: str = "", fixed_language: str = "") -> str:
    """Build the concise per-turn JSON/language reminder string."""
    if fixed_language:
        name = describe_language(fixed_language)
        return (
            "Reminder: reply with ONE strict JSON object only, nothing before or after: "
            f'{{"lang_id": "{fixed_language}", "response": "<spoken reply>"}}. '
            f"Write response only in {name} using its standard native script. {_ONE_LANGUAGE_RULE}"
        )
    allowed = f" Allowed lang_id values: {lang_codes}." if lang_codes else ""
    return (
        "Reminder: reply with ONE strict JSON object only, nothing before or after: "
        '{"lang_id": "<code>", "response": "<spoken reply>"}. '
        "Detect the dominant language of the user's latest transcript, set lang_id to the matching "
        f"allowed code, and write response in that language's standard native script. {_ONE_LANGUAGE_RULE}" + allowed
    )


def get_lang_codes(
    *,
    asr_server: str = "",
    asr_model: str = "",
    asr_function_id: str = "",
    tts_server: str = "",
    tts_voice_id: str = "",
) -> str:
    """Comma-separated language codes for prompt ``{lang_codes}`` injection."""
    if asr_server or tts_server:
        languages = build_session_languages(
            asr_server,
            asr_model,
            asr_function_id,
            tts_server,
            tts_voice_id,
        ).get("languages", [])
        if languages:
            return ", ".join(languages)
        return ""

    tts_config = config_store.get("tts", {})
    languages = tts_config.get("languages", []) if isinstance(tts_config, dict) else []
    if languages:
        return ", ".join(languages)
    return ", ".join(sorted(load_voice_map()))


def split_lang_codes(lang_codes: str) -> list[str]:
    """Split a comma-separated ``{lang_codes}`` string into a clean list."""
    return [code.strip() for code in lang_codes.split(",") if code.strip()]


FIXED_SESSION_LANGUAGE_ADDON_KEY = "fixed_session_language_addon"
AUTO_DETECT_LANGUAGE_ADDON_KEY = "auto_detect_language_addon"
FIXED_SESSION_GREETING_TRIGGER = "[session_start]"


def fixed_session_language_addon_key(catalog: Mapping[str, object], fixed_language: str) -> str:
    """Return the best fixed-session prompt add-on key for ``fixed_language``.

    Lookup order is exact locale, language family, then the English fallback.
    For example, ``fr-FR`` checks ``fixed_session_language_addon_fr_fr`` and
    ``fixed_session_language_addon_fr`` before using ``fixed_session_language_addon``.
    """
    normalized = normalize_lang_code(fixed_language.strip()) if fixed_language else ""
    suffix = normalized.replace("-", "_").lower()
    language = suffix.split("_", 1)[0] if suffix else ""
    candidates = [
        f"{FIXED_SESSION_LANGUAGE_ADDON_KEY}_{suffix}" if suffix else "",
        f"{FIXED_SESSION_LANGUAGE_ADDON_KEY}_{language}" if language else "",
        FIXED_SESSION_LANGUAGE_ADDON_KEY,
    ]
    seen: set[str] = set()
    for key in candidates:
        if not key or key in seen:
            continue
        seen.add(key)
        entry = catalog.get(key)
        content = entry.get("content") if isinstance(entry, Mapping) else ""
        if isinstance(content, str) and content.strip():
            return key
    return FIXED_SESSION_LANGUAGE_ADDON_KEY


def make_language_handler(
    tts: NvidiaTTSService,
    task: PipelineWorker,
    *,
    on_language_switched: _LanguageSwitchNotifier | None = None,
    fixed_language: str = "",
) -> _LanguageHandler:
    """Build the language handler that queues a TTSUpdateSettingsFrame on language change."""
    locked = normalize_lang_code(fixed_language) if fixed_language else ""
    current = ""

    async def handle(code: str) -> None:
        nonlocal current
        normalized = normalize_lang_code(locked or code)
        if not normalized:
            logger.warning(f"Multilingual: empty language code in LLM response: {code!r}")
            return
        if current.lower() == normalized.lower():
            return
        voice_map = load_voice_map()
        voice_id = voice_map.get(normalized.lower())
        if not voice_id:
            logger.warning(f"Multilingual: language '{normalized}' not in voice catalog ({sorted(voice_map.keys())})")
            return
        current = normalized.lower()
        try:
            await task.queue_frame(
                TTSUpdateSettingsFrame(
                    delta=NvidiaTTSSettings(voice=voice_id, language=normalized),
                    service=tts,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Multilingual: TTS settings update failed: {exc}")
            return
        logger.info(f"Multilingual: TTS → language={normalized}, voice={voice_id}")
        if on_language_switched:
            try:
                await on_language_switched(normalized, voice_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Multilingual: RTVI language notification failed: {exc}")

    return handle


class RTVISpokenTextEmitter(FrameProcessor):
    """Mirror spoken-sentence aggregations as ``LLMTextFrame``s for RTVI.

    Sits between ``LLMTextProcessor`` and TTS so RTVI's ``BotLlmText`` event
    sees clean spoken text from a non-llm source. Mirrored frames carry
    ``skip_tts=True`` (TTS already speaks via the AggregatedTextFrame path)
    and ``append_to_context=False`` (the assistant aggregator already captures
    the AggregatedTextFrame, so we must not double-add).
    """

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Forward each frame; mirror spoken aggregations as ``LLMTextFrame``."""
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if not isinstance(frame, AggregatedTextFrame):
            return
        if frame.aggregated_by in SKIP_TTS_AGGREGATIONS:
            return
        text = (frame.text or "").strip()
        if not text:
            return
        mirror = LLMTextFrame(text=text)
        mirror.skip_tts = True
        mirror.append_to_context = False
        await self.push_frame(mirror, direction)
