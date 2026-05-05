# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""LLM response generator that composes a single spoken sentence.

The orchestrator never hardcodes caller-facing text.  Every confirmation,
clarification, and progress utterance is generated here from a role
instruction plus a dict of pre-formatted facts.  :func:`sanitize_response`
strips markdown / bullet prose the 8B model sometimes leaks, picks the
first line, and caps length so TTS doesn't read multi-paragraph planning.
"""

from __future__ import annotations

import re

from loguru import logger

from cascaded.agentic_airline.orchestrators._llm import ainvoke_text

_MAX_CHARS = 240

_SYSTEM = (
    "You speak for an airline voice agent on a live phone call. "
    "Produce exactly one short spoken sentence (≤ 25 words). "
    "Plain prose only — no markdown, no bullets, no asterisks, no lists, "
    "no numbered steps. Use ONLY the facts you are given; NEVER invent "
    "flight numbers, times, amounts, codes, cities, or airport names. "
    "When a fact like new_origin or new_destination is provided, use "
    "its exact value — do not substitute a different city. Sound natural "
    "and helpful, like a human agent; do not narrate what you are doing."
)


async def generate_response(instruction: str, facts: dict) -> str:
    """Compose one spoken sentence from ``instruction`` + ``facts``.

    Facts are embedded verbatim in the sentence — they're already in
    spoken form (NATO phonetics, digit words, time words) so the model
    just needs to glue them into natural phrasing.  Empty / None fact
    values are skipped so the prompt doesn't carry dead slots.
    """
    fact_lines = "\n".join(f"- {k}: {v}" for k, v in facts.items() if v not in (None, ""))
    user = f"Task: {instruction}\n\nFacts:\n{fact_lines or '(none)'}"
    try:
        raw = await ainvoke_text(_SYSTEM, user)
    except Exception as exc:
        logger.warning(f"orchestrator responder failed ({type(exc).__name__}): {exc}")
        raise
    return sanitize_response(raw)


_MARKDOWN_RE = re.compile(r"[*_`#>]+|^\s*[-+]\s+", re.MULTILINE)
_TRAILING_QUOTE_RE = re.compile(r"^[\"'\s]+|[\"'\s]+$")


def sanitize_response(text: str) -> str:
    """Trim to one TTS-safe sentence.

    Drops markdown markers, strips wrapping quotes, picks the first
    non-empty line, and caps the result at :data:`_MAX_CHARS` (truncated
    on a word boundary with a trailing period).
    """
    if not text:
        return ""
    cleaned = _MARKDOWN_RE.sub("", text)
    first = ""
    for line in cleaned.splitlines():
        stripped = _TRAILING_QUOTE_RE.sub("", line).strip()
        if stripped:
            first = stripped
            break
    if not first:
        return ""
    if len(first) > _MAX_CHARS:
        first = first[:_MAX_CHARS].rsplit(" ", 1)[0].rstrip(",;: ") + "."
    return first
