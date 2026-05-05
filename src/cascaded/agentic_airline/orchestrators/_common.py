# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Shared helpers for the per-intent orchestrators.

PNR collection (entry / awaiting / inline) and pending-flow bookkeeping
are the only shared surface now — every other branch-point classifier
moved into the 3-LLM state-runner pipeline.
"""

from __future__ import annotations

from cascaded.agentic_airline.orchestrators._parse import extract_pnr
from cascaded.agentic_airline.orchestrators._responder import generate_response
from cascaded.agentic_airline.orchestrators.errors import OrchestratorFallback
from cascaded.agentic_airline.state.conversation_memory import ConversationMemory
from cascaded.agentic_airline.state.entity_store import EntityStore
from cascaded.agentic_airline.tools import _backend

MAX_AMBIGUOUS = 2

# Every intent-specific orchestrator uses the same "collect a PNR first"
# sub-state at step=start when the entity store is empty.  The step
# label and the per-intent step-memory-key pattern are fixed here so
# ``router.py`` and the orchestrators agree.
STEP_AWAITING_PNR = "awaiting_pnr"


def step_key(intent: str) -> str:
    """Memory key holding the current step for ``intent``."""
    return f"{intent}_step"


async def try_pnr_record(entity_store: EntityStore) -> tuple[str | None, dict | None]:
    """Return ``(pnr, record)`` from the entity store, or ``(None, None)``."""
    entity = entity_store.get("pnr")
    if entity is None:
        return None, None
    record = await _backend.get_pnr(entity.value)
    if record is None:
        return None, None
    return record["pnr"], record


async def resolve_pnr_inline(
    transcript: str,
    entity_store: EntityStore,
    memory: ConversationMemory | None = None,
) -> tuple[str | None, dict | None]:
    """Pull a PNR out of ``transcript`` and pin it to the entity store.

    Lets orchestrators handle the one-shot case ("rebook PNR ABC123 to
    Miami") in a single turn without a separate ``awaiting_pnr`` hop.
    """
    pnr, record, explicit, _switched = await sync_explicit_pnr(transcript, entity_store, memory)
    if not explicit:
        return None, None
    return pnr, record


async def sync_explicit_pnr(
    transcript: str,
    entity_store: EntityStore,
    memory: ConversationMemory | None = None,
) -> tuple[str | None, dict | None, bool, bool]:
    """Apply an explicitly spoken PNR from ``transcript`` to the active record.

    Returns ``(pnr, record, explicit, switched)`` where:
    - ``explicit`` means the transcript contained a parseable PNR
    - ``switched`` means the active record changed or was dropped
    """
    parsed = extract_pnr(transcript)
    if parsed is None:
        pnr, record = await try_pnr_record(entity_store)
        return pnr, record, False, False

    current = entity_store.get("pnr")
    current_pnr = current.value if current is not None else None
    record = await _backend.get_pnr(parsed)
    canonical = record["pnr"] if record is not None else None

    if canonical is not None and current_pnr == canonical:
        entity_store.put("pnr", canonical, confidence=1.0)
        if record.get("flight_number"):
            entity_store.put("flight_number", record["flight_number"], confidence=1.0)
        return canonical, record, True, False

    if current_pnr is not None:
        if memory is not None:
            from cascaded.agentic_airline.tools.pnr import _reset_for_new_pnr

            _reset_for_new_pnr(entity_store, memory)
        else:
            entity_store.forget("confirmation_code")
            entity_store.forget("flight_number")
        entity_store.forget("pnr")
        switched = True
    else:
        switched = False

    if record is None:
        return None, None, True, switched

    entity_store.put("pnr", canonical, confidence=1.0)
    if record.get("flight_number"):
        entity_store.put("flight_number", record["flight_number"], confidence=1.0)
    return canonical, record, True, switched


async def enter_awaiting_pnr(
    intent: str,
    memory: ConversationMemory,
) -> str:
    """Ask the caller for their PNR and park the flow at ``awaiting_pnr``.

    Memory is written only after the sentence is composed — if the LLM
    responder is cancelled or fails, the state stays at ``start`` and
    the next turn re-enters the start handler cleanly.
    """
    sentence = await generate_response(
        "Politely ask the traveler for their six-character booking reference so we can "
        "look up their flight before continuing.",
        {"task": intent},
    )
    memory.put(step_key(intent), STEP_AWAITING_PNR)
    memory.put(f"{intent}_ambiguous_count", "0")
    return sentence


async def handle_awaiting_pnr(
    intent: str,
    transcript: str,
    entity_store: EntityStore,
    memory: ConversationMemory,
) -> tuple[str, bool]:
    """Process an ``awaiting_pnr`` turn. Returns ``(spoken, resolved)``.

    ``resolved`` is True when a PNR was successfully pulled from the
    caller's turn *or* found to already be in the entity store (the
    caller went off and ran ``lookup_pnr`` via the fast path in the
    meantime).  In that case ``spoken`` is empty and the orchestrator
    should reset to ``start`` and re-enter the start handler.

    When ``resolved`` is False, ``spoken`` is a caller-facing sentence
    asking again or rejecting an unknown PNR.  After two strikes we
    raise :class:`OrchestratorFallback` so the DeepAgent can take a
    harder look.
    """
    _existing_pnr, existing_record = await try_pnr_record(entity_store)
    if existing_record is not None:
        return "", True

    parsed = extract_pnr(transcript)
    ambiguous_key = f"{intent}_ambiguous_count"
    prospective = int(memory.get(ambiguous_key) or "0") + 1

    if parsed is None:
        if prospective >= MAX_AMBIGUOUS:
            memory.put(ambiguous_key, str(prospective))
            raise OrchestratorFallback(f"awaiting_pnr: couldn't parse after {prospective} tries")
        sentence = await generate_response(
            "You didn't catch a booking reference. Politely ask the traveler to say their "
            "six-character code one letter and digit at a time.",
            {},
        )
        memory.put(ambiguous_key, str(prospective))
        return sentence, False

    record = await _backend.get_pnr(parsed)
    if record is None:
        if prospective >= MAX_AMBIGUOUS:
            memory.put(ambiguous_key, str(prospective))
            raise OrchestratorFallback(f"awaiting_pnr: {parsed!r} not found after {prospective} tries")
        sentence = await generate_response(
            "Tell the traveler the booking reference you heard wasn't found and ask them "
            "to read it back one more time.",
            {"heard": parsed},
        )
        memory.put(ambiguous_key, str(prospective))
        return sentence, False

    # Success — entity-store puts represent a persisted fact the caller
    # provided; keep them before the return so the orchestrator sees the
    # populated store on the (synthetic) start-step recursion.  The caller
    # hasn't been spoken to yet; the orchestrator's start handler will
    # compose the actual prompt.
    canonical = record["pnr"]
    entity_store.put("pnr", canonical, confidence=1.0)
    if record.get("flight_number"):
        entity_store.put("flight_number", record["flight_number"], confidence=1.0)
    memory.put(ambiguous_key, "0")
    return "", True


def clear_awaiting_pnr(memory: ConversationMemory) -> None:
    """Drop any pending ``awaiting_pnr`` marker across all intents.

    Called when a caller pivots to a different intent (e.g. abandoned a
    rebook halfway through PNR collection and started a cancel flow).
    The new flow's orchestrator will set its own step.
    """
    for intent in ("rebook", "cancel", "booking"):
        if memory.get(step_key(intent)) == STEP_AWAITING_PNR:
            memory.forget(step_key(intent))


def pending_pnr_intent(memory: ConversationMemory) -> str | None:
    """Return the intent currently parked at ``awaiting_pnr``, or None."""
    for intent in ("rebook", "cancel", "booking"):
        if memory.get(step_key(intent)) == STEP_AWAITING_PNR:
            return intent
    return None


# Terminal steps that end a flow — once the orchestrator has landed on
# one of these, the caller's next turn is a fresh intent, not a
# continuation.
_TERMINAL_STEPS = frozenset({"committed", "cancelled", "booked"})


def pending_intent(memory: ConversationMemory) -> str | None:
    """Return an intent with a non-terminal step in progress, or None.

    Used by the router so mid-flow turns ("the earlier one", "aisle
    please") route back to their orchestrator instead of bouncing to
    the fast LLM.  Terminal states (``committed`` / ``cancelled`` /
    ``booked``) are ignored — those flows are done.
    """
    for intent in ("rebook", "cancel", "booking"):
        step = memory.get(step_key(intent))
        if step and step not in _TERMINAL_STEPS:
            return intent
    return None
