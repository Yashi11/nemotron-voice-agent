# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Multilingual frame processor for the cascaded pipeline.

Sits between LLM and TTS in the pipeline. Intercepts ``LLMTextFrame`` chunks,
parses the structured ``Language: <code> Text: <response> MetaData: <info>``
format, extracts ONLY the Text block, switches TTS voice/language based on
the detected language code, and forwards clean spoken text downstream.

Everything downstream — TTS, assistant_aggregator, transcripts — only sees
the spoken text.

Reuses the voice/language catalog already cached by prewarm in config_store.
"""

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TTSUpdateSettingsFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame
from pipecat.services.nvidia.tts import NvidiaTTSService, NvidiaTTSSettings

import config_store
from utils import normalize_lang_code

_TEXT_MARKER = "text:"
_META_MARKER = "metadata:"
_HOLDBACK_LEN = len(_META_MARKER) - 1  # 8 chars to detect split marker
_DEFAULT_LANG = "en-US"

_STATE_HEADER = 0  # Buffering before "Text:" marker
_STATE_TEXT = 1  # Forwarding spoken text
_STATE_META = 2  # Dropping metadata


class MultilingualProcessor(FrameProcessor):
    """Pipeline processor that extracts spoken text from structured LLM output.

    Parses streaming ``Language: <code> Text: <spoken> MetaData: <info>``
    chunks and forwards only ``<spoken>`` as ``LLMTextFrame``. Dynamically
    switches TTS voice/language when a new language code is detected.
    """

    def __init__(self, tts: NvidiaTTSService):
        """Initialize the processor with the target TTS service."""
        super().__init__()
        self._tts = tts
        self._current_language: str = _DEFAULT_LANG
        self._voices_by_lang: dict[str, list[str]] | None = None
        self._lang_lookup: dict[str, str] = {}

        self._state: int = _STATE_HEADER
        self._header_buf: str = ""
        self._holdback: str = ""

    # ── FrameProcessor interface ────────────────────────────────────────

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Route frames through the multilingual state machine."""
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMFullResponseStartFrame):
            self._reset_parse_state()
            await self.push_frame(frame, direction)
        elif isinstance(frame, LLMTextFrame):
            await self._on_llm_text(frame.text, direction)
        elif isinstance(frame, LLMFullResponseEndFrame):
            await self._flush(direction)
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)

    # ── Streaming state machine ─────────────────────────────────────────

    def _reset_parse_state(self) -> None:
        self._state = _STATE_HEADER
        self._header_buf = ""
        self._holdback = ""

    async def _on_llm_text(self, text: str, direction: FrameDirection) -> None:
        if self._state == _STATE_HEADER:
            self._header_buf += text
            idx = self._header_buf.lower().find(_TEXT_MARKER)
            if idx >= 0:
                header = self._header_buf[:idx]
                remainder = self._header_buf[idx + len(_TEXT_MARKER) :]
                await self._extract_and_switch_language(header, direction)
                self._header_buf = ""
                self._state = _STATE_TEXT
                if remainder:
                    await self._forward_text_chunk(remainder, direction)

        elif self._state == _STATE_TEXT:
            await self._forward_text_chunk(text, direction)

        # _STATE_META: silently drop

    async def _forward_text_chunk(self, text: str, direction: FrameDirection) -> None:
        combined = self._holdback + text
        meta_idx = combined.lower().find(_META_MARKER)

        if meta_idx >= 0:
            before = combined[:meta_idx]
            if before.strip():
                await self.push_frame(LLMTextFrame(text=before), direction)
            self._holdback = ""
            self._state = _STATE_META
            return

        if len(combined) > _HOLDBACK_LEN:
            to_send = combined[:-_HOLDBACK_LEN]
            self._holdback = combined[-_HOLDBACK_LEN:]
            await self.push_frame(LLMTextFrame(text=to_send), direction)
        else:
            self._holdback = combined

    async def _flush(self, direction: FrameDirection) -> None:
        if self._state == _STATE_HEADER and self._header_buf.strip():
            buf = self._header_buf
            await self._extract_and_switch_language(buf, direction)
            meta_idx = buf.lower().find(_META_MARKER)
            if meta_idx >= 0:
                buf = buf[:meta_idx]
            if buf.strip():
                await self.push_frame(LLMTextFrame(text=buf.strip()), direction)
        elif self._state == _STATE_TEXT and self._holdback.strip():
            await self.push_frame(LLMTextFrame(text=self._holdback), direction)
        self._reset_parse_state()

    # ── Language extraction & switching ──────────────────────────────────

    async def _extract_and_switch_language(self, header: str, direction: FrameDirection) -> None:
        """Extract language code from the header (``Language: xx-XX``)."""
        lower = header.lower().strip()
        if lower.startswith("language"):
            rest = lower.split("language", 1)[1].lstrip(": ")
            code = rest.strip().split()[0] if rest.strip() else ""
            if code:
                await self._switch_language(code, direction)

    async def _switch_language(self, lang_code: str, direction: FrameDirection) -> None:
        if not lang_code or lang_code.lower() == self._current_language.lower():
            return

        voices_by_lang = self._load_voices()
        if not voices_by_lang:
            return

        key = lang_code.lower()
        matched = self._lang_lookup.get(key)
        if not matched and "-" not in key:
            for k in self._lang_lookup:
                if k.startswith(key + "-"):
                    matched = self._lang_lookup[k]
                    break
        if matched and voices_by_lang.get(matched):
            new_voice = voices_by_lang[matched][0]
            normalized = normalize_lang_code(matched)
            self._current_language = normalized
            await self.push_frame(
                TTSUpdateSettingsFrame(
                    delta=NvidiaTTSSettings(voice=new_voice, language=normalized),
                    service=self._tts,
                ),
                direction,
            )
            logger.info(f"Multilingual: TTS → language={normalized}, voice={new_voice}")
            await self._notify_language_switch(normalized, new_voice)
        else:
            logger.warning(f"Language '{lang_code}' not supported. Available: {list(voices_by_lang.keys())}")

    async def _notify_language_switch(self, language: str, voice_id: str) -> None:
        """Push a server message so the client UI reflects the language switch."""
        await self.push_frame(
            RTVIServerMessageFrame(
                data={
                    "type": "language-switched",
                    "language": language,
                    "voice_id": voice_id,
                }
            )
        )

    # ── Voice discovery (from prewarm cache) ────────────────────────────

    def _load_voices(self) -> dict[str, list[str]]:
        """Build lang_code → [voice_id, ...] map from prewarm cache."""
        if self._voices_by_lang is not None:
            return self._voices_by_lang

        tts_config = config_store.get("tts", {})
        voices = tts_config.get("voices", []) if isinstance(tts_config, dict) else []

        result: dict[str, list[str]] = {}
        for v in voices:
            lang = v.get("language", "")
            vid = v.get("id", "")
            if lang and vid:
                result.setdefault(lang, []).append(vid)

        self._voices_by_lang = result
        self._lang_lookup = {lang.lower(): lang for lang in result}
        logger.info(f"Multilingual: {len(result)} languages from prewarm cache — {list(result.keys())}")
        return result

    def get_lang_codes(self) -> str:
        """Comma-separated language codes for prompt ``{lang_codes}`` injection."""
        tts_config = config_store.get("tts", {})
        languages = tts_config.get("languages", []) if isinstance(tts_config, dict) else []
        if languages:
            return ", ".join(languages)
        return ", ".join(self._load_voices().keys())
