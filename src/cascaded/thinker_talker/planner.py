# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""LLM planner for the internal Thinker."""

from __future__ import annotations

import json
from typing import Any, Protocol

from loguru import logger
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.services.nvidia.llm import NvidiaLLMService


class ThinkerPlanner(Protocol):
    """Planner interface for selecting internal Thinker tool calls."""

    async def plan(self, *, query: str, slots: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        """Return a structured Thinker plan."""


class NvidiaThinkerPlanner:
    """Thinker planner backed by Nemotron reasoning."""

    def __init__(self, *, llm: NvidiaLLMService, system_prompt: str, max_tokens: int = 4096) -> None:
        """Create an NVIDIA-backed Thinker planner."""
        if not system_prompt.strip():
            raise ValueError("Thinker planner requires a non-empty system prompt")
        self._llm = llm
        self._system_prompt = system_prompt
        self._max_tokens = max_tokens

    async def plan(self, *, query: str, slots: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        """Ask the Thinker LLM for internal tool plan JSON."""
        user_payload = {
            "query": query,
            "structured_fields": slots,
            "session_state": state,
        }
        context = LLMContext(
            [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ]
        )
        raw = await self._llm.run_inference(context, max_tokens=self._max_tokens)
        if not raw:
            raise RuntimeError("Thinker LLM returned an empty plan")
        return parse_plan_json(raw)


def parse_plan_json(raw: str) -> dict[str, Any]:
    """Parse a Thinker LLM JSON object response."""
    cleaned = _strip_thinking(raw).strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        decoded = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            logger.warning(f"Thinker LLM returned non-JSON plan: {raw!r}")
            raise
        decoded = json.loads(cleaned[start : end + 1])
    if not isinstance(decoded, dict):
        raise ValueError("Thinker LLM plan must be a JSON object")
    return decoded


def _strip_thinking(text: str) -> str:
    while "<think>" in text and "</think>" in text:
        start = text.find("<think>")
        end = text.find("</think>", start)
        text = text[:start] + text[end + len("</think>") :]
    return text
