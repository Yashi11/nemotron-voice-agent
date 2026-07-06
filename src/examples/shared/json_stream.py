# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

r"""Streaming JSON helpers shared by cascaded pipelines.

Two utilities live here:

* :class:`JsonStringFieldStreamer` — incrementally extracts a single string
  field from a JSON object as it streams in, unescaping standard JSON escape
  sequences (including ``\\uXXXX``) so non-Latin scripts survive intact.
* :func:`extract_json_payload` — a best-effort, non-streaming parse of raw or
  fenced JSON model output, used as a fallback when streaming parsing fails.
"""

from __future__ import annotations

import json
from typing import Any


def extract_json_payload(text: str) -> dict[str, Any]:
    """Parse raw or fenced JSON from model output, returning ``{}`` on failure."""
    if not text:
        return {}
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.startswith("json"):
            candidate = candidate[4:].strip()
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            parsed = json.loads(candidate[start : end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}


class JsonStringFieldStreamer:
    """Incrementally extract a string field's value from streamed JSON text.

    Feed streamed chunks via :meth:`feed`; it returns the (unescaped) portion of
    the target field's string value contained in that chunk. Once the closing
    quote of the value is seen, :attr:`done` is set and further ``feed`` calls
    return ``""``.
    """

    def __init__(self, field_name: str) -> None:
        """Build a streamer that watches for ``"<field_name>": "..."``."""
        self._needle = f'"{field_name}"'
        self._state = "search"
        self._buffer = ""
        self._escaped = False
        self._unicode_remaining = 0
        self._unicode_buffer = ""
        self.done = False

    def feed(self, text: str) -> str:
        """Consume a streamed chunk and return any decoded field content in it."""
        if self.done or not text:
            return ""
        if self._state != "in_string":
            self._buffer += text
            emitted = self._advance_to_string()
            if self._state != "in_string":
                return ""
            text = emitted
        return self._consume_string_chars(text)

    def _advance_to_string(self) -> str:
        while True:
            if self._state == "search":
                idx = self._buffer.find(self._needle)
                if idx < 0:
                    self._buffer = self._buffer[-len(self._needle) :]
                    return ""
                self._buffer = self._buffer[idx + len(self._needle) :]
                self._state = "colon"
            if self._state == "colon":
                stripped = self._buffer.lstrip()
                if not stripped:
                    self._buffer = ""
                    return ""
                if stripped[0] != ":":
                    self._state = "search"
                    self._buffer = stripped
                    continue
                self._buffer = stripped[1:]
                self._state = "quote"
            if self._state == "quote":
                stripped = self._buffer.lstrip()
                if not stripped:
                    self._buffer = ""
                    return ""
                if stripped[0] != '"':
                    self._state = "search"
                    self._buffer = stripped
                    continue
                self._state = "in_string"
                emitted = stripped[1:]
                self._buffer = ""
                return emitted

    def _consume_string_chars(self, text: str) -> str:
        out: list[str] = []
        for ch in text:
            if self._unicode_remaining:
                self._unicode_buffer += ch
                self._unicode_remaining -= 1
                if self._unicode_remaining == 0:
                    try:
                        out.append(chr(int(self._unicode_buffer, 16)))
                    except ValueError:
                        out.append(f"\\u{self._unicode_buffer}")
                    self._unicode_buffer = ""
                continue
            if self._escaped:
                self._escaped = False
                if ch == "u":
                    self._unicode_remaining = 4
                    self._unicode_buffer = ""
                else:
                    out.append(
                        {
                            '"': '"',
                            "\\": "\\",
                            "/": "/",
                            "b": "\b",
                            "f": "\f",
                            "n": "\n",
                            "r": "\r",
                            "t": "\t",
                        }.get(ch, ch)
                    )
                continue
            if ch == "\\":
                self._escaped = True
                continue
            if ch == '"':
                self.done = True
                break
            out.append(ch)
        return "".join(out)
