# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Rebook orchestrator — thin shim over the declarative state runner.

Resolves the PNR (from entity store, inline transcript, or an
awaiting-PNR sub-state) and hands the turn to
:func:`cascaded.agentic_airline.orchestrators._state_runner.run_state` with the
``REBOOK_INTENT`` spec.  Intent-specific post-processing (persisting
slot updates the LLM returned, stashing alternatives / confirmation
codes) lives here so the runner stays intent-agnostic.
"""

from __future__ import annotations

import json
from contextlib import suppress

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
from cascaded.agentic_airline.orchestrators.errors import OrchestratorFallback
from cascaded.agentic_airline.orchestrators.rebook_states import REBOOK_INTENT, STATE_START
from cascaded.agentic_airline.state.conversation_memory import ConversationMemory
from cascaded.agentic_airline.state.entity_store import EntityStore


async def orchestrate_rebook(
    transcript: str,
    summary: str,
    entity_store: EntityStore,
    memory: ConversationMemory,
    session_id: str | None = None,
) -> str:
    """Run one rebook step via the declarative state runner."""
    entry_step = memory.get("rebook_step") or STATE_START
    if entry_step in REBOOK_INTENT.terminal_states:
        reset_intent_flow(REBOOK_INTENT, memory, entity_store)
        entry_step = STATE_START
    pnr, record = await try_pnr_record(entity_store)
    inline_pnr, inline_record, explicit_pnr, switched_pnr = await sync_explicit_pnr(transcript, entity_store, memory)
    if explicit_pnr:
        pnr, record = inline_pnr, inline_record
        if switched_pnr:
            memory.put("rebook_step", STATE_START)
            entry_step = STATE_START

    if record is None:
        if entry_step in (STATE_START, STEP_AWAITING_PNR):
            if entry_step == STEP_AWAITING_PNR:
                spoken, resolved = await handle_awaiting_pnr("rebook", transcript, entity_store, memory)
                if not resolved:
                    return spoken
                memory.put("rebook_step", STATE_START)
                pnr, record = await try_pnr_record(entity_store)
                if record is None:
                    raise OrchestratorFallback("awaiting_pnr resolved but record missing")
                entry_step = STATE_START
            else:
                return await enter_awaiting_pnr("rebook", memory)
        else:
            raise OrchestratorFallback(f"no PNR in entity store at step {entry_step!r}")

    ctx = TurnContext(
        intent=REBOOK_INTENT,
        current_state=entry_step if entry_step in REBOOK_INTENT.states else STATE_START,
        transcript=transcript,
        collected=_collect_state(record, memory, entity_store),
        history=[],
        record=record,
        session_id=session_id,
    )
    result = await run_state(ctx)
    apply_cleanup_plan(result.cleanup_plan, memory, entity_store)
    _persist_slot_updates(result.decision.slot_updates or {}, memory)
    await _apply_tool_side_effects(result, record, entity_store, memory)
    memory.put("rebook_step", result.next_state)
    return result.sentence


_PERSISTED_SLOTS = frozenset(
    {
        "seat_pref",
        "meal_pref",
        "suggested_flight",
        "new_origin",
        "new_destination",
    }
)


def _persist_slot_updates(updates: dict, memory: ConversationMemory) -> None:
    """Stash the LLM's slot updates into memory for later turns.

    Only known slots are persisted — prevents the LLM from writing
    arbitrary keys into the stream's scratch space.  Empty / None
    values are treated as 'no change' and skipped.
    """
    for key, value in updates.items():
        if key not in _PERSISTED_SLOTS:
            continue
        if value is None or value == "":
            continue
        memory.put(key, str(value))


_KEEP_TOKENS = frozenset({"keep", "same", "no_change", "existing", "unchanged"})

_MEAL_SPOKEN = {
    "VGML": "vegetarian",
    "VLML": "vegetarian",
    "NVML": "non-vegetarian",
    "KSML": "kosher",
    "MOML": "halal",
    "GFML": "gluten-free",
    "DBML": "diabetic",
    "CHML": "child meal",
}


def _collect_state(
    record: dict,
    memory: ConversationMemory,
    entity_store: EntityStore,
) -> dict:
    """Build the ``collected`` dict the fused LLM sees alongside the transcript.

    Includes every field of the PNR record the runner might need to
    answer a status question or decide which slot is still missing.
    Also derives ``proposed_seat`` / ``proposed_meal`` by merging the
    caller's just-stated pref on top of the existing value so the
    preview/commit responder can speak the NEW booking verbatim without
    conflating it with the old one.  Flat dict; the responder consumes
    it as facts.
    """
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
    # Ancillaries live under record["ancillaries"] in the backend
    # response; flatten so the LLM sees them without nested lookup.
    ancillaries = record.get("ancillaries") or {}
    if isinstance(ancillaries, dict):
        if ancillaries.get("seat"):
            collected["current_seat"] = ancillaries["seat"]
        if ancillaries.get("bag_count") is not None:
            collected["current_bag_count"] = ancillaries["bag_count"]
        if ancillaries.get("meal"):
            collected["current_meal"] = ancillaries["meal"]
    # Per-stream scratch the caller already answered.
    for key in (
        "suggested_flight",
        "committed_flight",
        "route",
        "rebook_alternatives",
        "seat_pref",
        "meal_pref",
        "new_origin",
        "new_destination",
    ):
        value = memory.get(key)
        if value:
            collected[key] = value
    # Full alternatives snapshot (flight + departure) so the LLM can
    # reason about what was offered without re-calling list_alternatives.
    snapshot_raw = memory.get("alternatives_snapshot")
    if snapshot_raw:
        with suppress(json.JSONDecodeError):
            collected["alternatives_snapshot"] = json.loads(snapshot_raw)
    code_entity = entity_store.get("confirmation_code")
    if code_entity:
        collected["last_confirmation_code"] = code_entity.value

    # Derive the PROPOSED seat / meal the responder should describe at
    # preview / commit time.  Caller's pref wins unless it's "keep"
    # (then we carry over the existing).  Meal codes are also expanded
    # into a short spoken form so the responder reads "non-vegetarian"
    # rather than "NVML".
    current_seat = collected.get("current_seat")
    current_meal = collected.get("current_meal")
    seat_pref = collected.get("seat_pref")
    meal_pref = collected.get("meal_pref")
    proposed_seat = current_seat
    if seat_pref and str(seat_pref).lower() not in _KEEP_TOKENS:
        proposed_seat = seat_pref
    proposed_meal = current_meal
    if meal_pref and str(meal_pref).lower() not in _KEEP_TOKENS:
        proposed_meal = meal_pref
    if proposed_seat:
        collected["proposed_seat"] = proposed_seat
    if proposed_meal:
        collected["proposed_meal"] = proposed_meal
        collected["proposed_meal_spoken"] = _MEAL_SPOKEN.get(str(proposed_meal).upper(), proposed_meal)
    if current_meal:
        collected["current_meal_spoken"] = _MEAL_SPOKEN.get(str(current_meal).upper(), current_meal)

    return {k: v for k, v in collected.items() if v not in (None, "")}


async def _apply_tool_side_effects(
    result,  # StateRunResult
    record: dict,
    entity_store: EntityStore,
    memory: ConversationMemory,
) -> None:
    """Persist cross-turn state the runner doesn't own directly.

    Stashes the full alternatives list (flight + departure) so later
    turns don't re-fetch list_alternatives or hallucinate times.
    Commit-tool results land in EntityStore so the fast-LLM layer and
    the caller-facing responder both see the same confirmation code.
    """
    tool_name = result.tool_name
    tool_result = result.tool_result
    if tool_name == "list_alternatives" and isinstance(tool_result, list) and tool_result:
        snapshot = [
            {
                "flight_number": alt.get("flight_number"),
                "departure": alt.get("departure"),
                "origin": alt.get("origin"),
                "destination": alt.get("destination"),
            }
            for alt in tool_result[:4]
            if alt.get("flight_number")
        ]
        if snapshot:
            memory.put("alternatives_snapshot", json.dumps(snapshot))
            memory.put(
                "rebook_alternatives",
                ",".join(a["flight_number"] for a in snapshot),
            )
            memory.put("suggested_flight", snapshot[0]["flight_number"])
            memory.put("new_origin", snapshot[0].get("origin") or "")
            memory.put("new_destination", snapshot[0].get("destination") or "")
    elif tool_name == "commit_rebook" and isinstance(tool_result, dict):
        code = tool_result.get("confirmation_code")
        if code:
            entity_store.put("confirmation_code", code, confidence=1.0)
            memory.put("last_confirmation_code", code)
        new_fn = tool_result.get("new_flight_number") or tool_result.get("flight_number")
        if new_fn:
            memory.put("committed_flight", new_fn)
