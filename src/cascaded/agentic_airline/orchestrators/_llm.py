# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Shared small-LLM client for the orchestrator package.

One module-level :class:`ChatNVIDIA` client — no tools bound — reused
across every orchestrator call in a stream.  Sized for narrow tasks:
single-label classification and one-sentence response generation.

Defaults to the same Nemotron-3-Nano-30B model as the Tier-1 Fast LLM
with ``enable_thinking=false``, so one warm NIM worker serves both layers
and no reasoning tokens leak into classifier / responder completions.

Configuration knobs (env vars):
- ``ORCHESTRATOR_LLM_MODEL`` — model name (default: Nemotron-3-Nano-30B)
- ``ORCHESTRATOR_LLM_BASE_URL`` — NIM endpoint override
- ``ORCHESTRATOR_LLM_EXTRA_PARAMS`` — JSON for ``model_kwargs`` (e.g. ``extra_body``)
- ``ORCHESTRATOR_LLM_TIMEOUT`` — per-call seconds (default 15)
- ``NVIDIA_API_KEY`` — required; raises on first ``get_llm`` call if unset
"""

from __future__ import annotations

import asyncio
import json
import os

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from loguru import logger

_DEFAULT_MODEL = "nvidia/nemotron-3-nano-30b-a3b"
_DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
# ChatNVIDIA merges ``model_kwargs`` into the top-level request body, so the
# chat-template hook is passed flat — NOT wrapped in ``extra_body`` like the
# Fast LLM path, which uses the OpenAI SDK's own ``extra_body`` merging.
_DEFAULT_EXTRA_PARAMS = '{"chat_template_kwargs":{"enable_thinking":false}}'
_DEFAULT_TIMEOUT_SECS = 15.0

_client: BaseChatModel | None = None


def _parse_extra_params(raw: str) -> dict:
    """Parse the JSON env var into a dict forwarded as ``model_kwargs``."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(f"ORCHESTRATOR_LLM_EXTRA_PARAMS not valid JSON ({exc}); ignoring")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def get_llm() -> BaseChatModel:
    """Return the lazily constructed shared orchestrator LLM client.

    Raises :class:`RuntimeError` if ``NVIDIA_API_KEY`` is not set.
    """
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY is not set; orchestrators cannot run")
    model = os.environ.get("ORCHESTRATOR_LLM_MODEL", _DEFAULT_MODEL)
    base_url = os.environ.get("ORCHESTRATOR_LLM_BASE_URL", _DEFAULT_BASE_URL)
    extra_params = _parse_extra_params(os.environ.get("ORCHESTRATOR_LLM_EXTRA_PARAMS", _DEFAULT_EXTRA_PARAMS))
    _client = ChatNVIDIA(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=0.0,
        # Sized for the turn analyzer's JSON envelope (~150 tokens) while
        # still capping the one-sentence responder at a safe ceiling.
        max_completion_tokens=240,
        model_kwargs=extra_params or {},
    )
    logger.info(f"Orchestrator LLM: model={model}, extra={extra_params or '(none)'}")
    return _client


def _timeout_secs() -> float:
    return float(os.environ.get("ORCHESTRATOR_LLM_TIMEOUT", _DEFAULT_TIMEOUT_SECS))


async def ainvoke_text(system: str, user: str) -> str:
    """Run one chat completion with a per-call timeout.

    NIM endpoints occasionally stall (cold starts, worker scheduling).
    Wrapping :func:`asyncio.wait_for` converts a hang into a
    ``TimeoutError`` the orchestrator turns into its graceful fallback
    apology instead of leaving the caller in silence.
    """
    llm = get_llm()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    resp = await asyncio.wait_for(llm.ainvoke(messages), timeout=_timeout_secs())
    return (getattr(resp, "content", None) or "").strip()
