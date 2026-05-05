# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Python orchestrator package: declarative state runner + per-intent state tables.

Each intent has its own ``orchestrate_*`` coroutine that builds a
:class:`TurnContext` and hands it to :mod:`_state_runner`.  The runner
does one fused LLM call per turn to decide action + tool + params, runs
the tool, and composes the reply via the responder.

Three intents today: ``rebook``, ``cancel``, ``booking`` (new
reservation).  Branch-point decisions (confirm / deny / pick /
change_X) live inside the runner; every spoken sentence is composed by
the responder — no canned strings.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from cascaded.agentic_airline.orchestrators.booking import orchestrate_booking
from cascaded.agentic_airline.orchestrators.cancel import orchestrate_cancel
from cascaded.agentic_airline.orchestrators.errors import OrchestratorFallback
from cascaded.agentic_airline.orchestrators.rebook import orchestrate_rebook

if TYPE_CHECKING:
    from cascaded.agentic_airline.state.conversation_memory import ConversationMemory
    from cascaded.agentic_airline.state.entity_store import EntityStore


Orchestrator = Callable[
    [str, str, "EntityStore", "ConversationMemory", str | None],
    Awaitable[str],
]


ORCHESTRATORS: dict[str, Orchestrator] = {
    "rebook": orchestrate_rebook,
    "cancel": orchestrate_cancel,
    "booking": orchestrate_booking,
}


async def run_orchestrator(
    intent: str,
    transcript: str,
    summary: str,
    entity_store: EntityStore,
    memory: ConversationMemory,
    session_id: str | None = None,
) -> str:
    """Dispatch to the intent orchestrator or raise :class:`OrchestratorFallback`.

    Returns the spoken sentence the bridge should emit to TTS.
    Unrecognized intents raise so the bridge emits its graceful
    fallback sentence.  ``session_id`` is the pipeline stream_id; the
    runner stamps it on backend mutations for activity_log correlation.
    """
    fn = ORCHESTRATORS.get((intent or "").lower())
    if fn is None:
        raise OrchestratorFallback(f"no orchestrator for intent {intent!r}")
    return await fn(transcript, summary, entity_store, memory, session_id)


__all__ = ["ORCHESTRATORS", "OrchestratorFallback", "run_orchestrator"]
