# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Cancel orchestrator — thin shim over the declarative state runner.

Cancellation terms are classified here (pure Python from PNR status /
fare / delay) and pushed into ``collected`` so the LLM reads them as
facts.  Airline-initiated disruptions (``cancelled_*``, ``misconnect``,
long delays ≥ 6 h) always get a full cash refund.  Voluntary cancels
follow the fare table: refundable → cash, nonrefundable → travel credit,
basic_economy → nothing.  The policy reference is cite-able by the
responder.
"""

from __future__ import annotations

from cascaded.agentic_airline.orchestrators._common import (
    STEP_AWAITING_PNR,
    enter_awaiting_pnr,
    handle_awaiting_pnr,
    sync_explicit_pnr,
    try_pnr_record,
)
from cascaded.agentic_airline.orchestrators._state_runner import (
    TurnContext,
    apply_cleanup_plan,
    reset_intent_flow,
    run_state,
)
from cascaded.agentic_airline.orchestrators.cancel_states import (
    CANCEL_INTENT,
    STATE_START,
)
from cascaded.agentic_airline.orchestrators.errors import OrchestratorFallback
from cascaded.agentic_airline.state.conversation_memory import ConversationMemory
from cascaded.agentic_airline.state.entity_store import EntityStore

_POLICY_REF_VOLUNTARY = "CXL-VOL-2024-02"
_POLICY_REF_IRROPS = "IRR-2024-03"


async def orchestrate_cancel(
    transcript: str,
    summary: str,
    entity_store: EntityStore,
    memory: ConversationMemory,
    session_id: str | None = None,
) -> str:
    """Run one cancel step via the declarative state runner."""
    entry_step = memory.get("cancel_step") or STATE_START
    if entry_step in CANCEL_INTENT.terminal_states:
        reset_intent_flow(CANCEL_INTENT, memory, entity_store)
        entry_step = STATE_START
    pnr, record = await try_pnr_record(entity_store)
    inline_pnr, inline_record, explicit_pnr, switched_pnr = await sync_explicit_pnr(transcript, entity_store, memory)
    if explicit_pnr:
        pnr, record = inline_pnr, inline_record
        if switched_pnr:
            memory.put("cancel_step", STATE_START)
            entry_step = STATE_START

    if record is None:
        if entry_step in (STATE_START, STEP_AWAITING_PNR):
            if entry_step == STEP_AWAITING_PNR:
                spoken, resolved = await handle_awaiting_pnr("cancel", transcript, entity_store, memory)
                if not resolved:
                    return spoken
                memory.put("cancel_step", STATE_START)
                pnr, record = await try_pnr_record(entity_store)
                if record is None:
                    raise OrchestratorFallback("awaiting_pnr resolved but record missing")
                entry_step = STATE_START
            else:
                return await enter_awaiting_pnr("cancel", memory)
        else:
            raise OrchestratorFallback(f"no PNR in entity store at step {entry_step!r}")

    # Classify terms deterministically and push into memory so the fused
    # LLM reads them as facts on every turn.
    _stash_terms(record, memory)

    ctx = TurnContext(
        intent=CANCEL_INTENT,
        current_state=entry_step if entry_step in CANCEL_INTENT.states else STATE_START,
        transcript=transcript,
        collected=_collect_state(record, memory, entity_store),
        history=[],
        record=record,
        session_id=session_id,
    )
    result = await run_state(ctx)
    apply_cleanup_plan(result.cleanup_plan, memory, entity_store)
    await _apply_tool_side_effects(result, entity_store, memory)
    memory.put("cancel_step", result.next_state)
    return result.sentence


def _collect_state(
    record: dict,
    memory: ConversationMemory,
    entity_store: EntityStore,
) -> dict:
    """Flatten PNR + stashed cancel terms for the fused LLM."""
    ancillaries = record.get("ancillaries") or {}
    collected: dict = {
        "pnr": record.get("pnr"),
        "passenger": record.get("passenger"),
        "current_flight": record.get("flight_number"),
        "current_origin": record.get("origin"),
        "current_destination": record.get("destination"),
        "current_departure": record.get("departure"),
        "current_cabin": record.get("cabin"),
        "current_fare_basis": record.get("fare_basis"),
        "current_elite_tier": record.get("elite_tier"),
        "current_status": record.get("status"),
        "current_delay_minutes": record.get("delay_minutes"),
    }
    if ancillaries.get("seat"):
        collected["current_seat"] = ancillaries["seat"]
    if ancillaries.get("meal"):
        collected["current_meal"] = ancillaries["meal"]
    for key in ("cancel_kind", "cancel_policy_ref", "cancel_outcome", "cancel_penalty"):
        value = memory.get(key)
        if value:
            collected[key] = value
    code_entity = entity_store.get("confirmation_code")
    if code_entity:
        collected["last_confirmation_code"] = code_entity.value
    return {k: v for k, v in collected.items() if v not in (None, "")}


def _stash_terms(record: dict, memory: ConversationMemory) -> None:
    """Write the classified cancel terms to memory so the LLM sees them."""
    terms = _classify_terms(record)
    memory.put("cancel_kind", terms["kind"])
    memory.put("cancel_policy_ref", terms["policy_ref"])
    memory.put("cancel_outcome", terms["outcome"])
    if terms.get("penalty"):
        memory.put("cancel_penalty", terms["penalty"])


async def _apply_tool_side_effects(result, entity_store: EntityStore, memory: ConversationMemory) -> None:
    """Persist cross-turn state from the cancel_booking tool result."""
    if result.tool_name == "cancel_booking" and isinstance(result.tool_result, dict):
        code = result.tool_result.get("confirmation_code")
        if code:
            entity_store.put("confirmation_code", code, confidence=1.0)
            memory.put("last_confirmation_code", code)


def _classify_terms(record: dict) -> dict:
    """Classify what the caller is entitled to on cancellation.

    Airline-caused disruptions override the fare table.  Delays ≥ 6 h
    match the IRROPS refund threshold so callers don't get stranded.
    """
    status = record["status"]
    fare = record["fare_basis"]
    delay = int(record["delay_minutes"] or 0)

    if status in ("cancelled_airline", "cancelled_weather", "misconnect"):
        return {
            "kind": "airline_refund",
            "outcome": "full cash refund to the original form of payment",
            "policy_ref": _POLICY_REF_IRROPS,
        }
    if status == "delayed" and delay >= 360:
        return {
            "kind": "long_delay_refund",
            "outcome": "full cash refund due to a delay over six hours",
            "policy_ref": _POLICY_REF_IRROPS,
        }
    if status == "diversion":
        return {
            "kind": "diversion_limited",
            "outcome": "rebook on a later flight is available but no cash refund on a diversion",
            "policy_ref": _POLICY_REF_IRROPS,
            "penalty": "contract of carriage limits refunds on diversion events",
        }
    if fare == "refundable":
        return {
            "kind": "voluntary_refundable",
            "outcome": "full cash refund to the original form of payment",
            "policy_ref": _POLICY_REF_VOLUNTARY,
        }
    if fare == "nonrefundable":
        return {
            "kind": "voluntary_nonrefundable",
            "outcome": "full travel credit, no cash refund",
            "policy_ref": _POLICY_REF_VOLUNTARY,
        }
    if fare == "basic_economy":
        return {
            "kind": "voluntary_basic",
            "outcome": "no refund or travel credit under basic economy terms",
            "policy_ref": _POLICY_REF_VOLUNTARY,
            "penalty": "basic economy fares are fully non-refundable",
        }
    return {
        "kind": "unknown_fare",
        "outcome": "standard cancellation terms apply",
        "policy_ref": _POLICY_REF_VOLUNTARY,
    }
