# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Shared small-LLM client for the orchestrator package.

One module-level :class:`ChatNVIDIA` client — no tools bound — reused
across every orchestrator call in a stream.  Sized for narrow tasks:
single-label classification and one-sentence response generation.

Defaults to the same Nemotron-3-Nano-30B model as the Tier-1 Fast LLM
with ``enable_thinking=false``, so one warm NIM worker serves both layers
and no reasoning tokens leak into classifier / responder completions.

Configuration:
- Uses ``orchestrator-llm.nemotron-nano`` from the active service catalog.
- ``NVIDIA_API_KEY`` — required; raises on first ``get_llm`` call if unset
"""

from __future__ import annotations

import asyncio
import os

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from loguru import logger

from utils import load_service_entry, parse_json_dict

ORCHESTRATOR_LLM_CATALOG_CATEGORY = "orchestrator-llm"
_DEFAULT_TIMEOUT_SECS = 15.0

_client: BaseChatModel | None = None
_timeout_secs = _DEFAULT_TIMEOUT_SECS


def _parse_extra_params(raw: object) -> dict:
    """Parse catalog ``extra_params`` into ``ChatNVIDIA.model_kwargs``."""
    if not raw:
        return {}
    parsed = raw if isinstance(raw, dict) else parse_json_dict(str(raw), label="orchestrator extra_params")
    extra_body = parsed.get("extra_body")
    return extra_body if isinstance(extra_body, dict) else parsed


def get_llm() -> BaseChatModel:
    """Return the lazily constructed shared orchestrator LLM client.

    Raises :class:`RuntimeError` if ``NVIDIA_API_KEY`` is not set.
    """
    global _client, _timeout_secs
    if _client is not None:
        return _client
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY is not set; orchestrators cannot run")
    llm_config = load_service_entry(ORCHESTRATOR_LLM_CATALOG_CATEGORY, "")
    model = llm_config.get("model_id", "")
    base_url = llm_config.get("base_url", "")
    if not model or not base_url:
        raise RuntimeError(
            f"Service catalog category '{ORCHESTRATOR_LLM_CATALOG_CATEGORY}' must define model_id and base_url"
        )
    extra_params = _parse_extra_params(llm_config.get("extra_params", ""))
    _timeout_secs = _parse_timeout_secs(llm_config.get("timeout_secs", _DEFAULT_TIMEOUT_SECS))
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
    logger.info(
        f"Orchestrator LLM: model={model}, base_url={base_url}, "
        f"timeout={_timeout_secs}s, extra={extra_params or '(none)'}"
    )
    return _client


def _parse_timeout_secs(raw: object) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning(f"Invalid orchestrator timeout_secs={raw!r}; using {_DEFAULT_TIMEOUT_SECS}s")
        return _DEFAULT_TIMEOUT_SECS


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
    resp = await asyncio.wait_for(llm.ainvoke(messages), timeout=_timeout_secs)
    return (getattr(resp, "content", None) or "").strip()
