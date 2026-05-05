# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Booking orchestrator — thin shim over the declarative state runner.

New bookings don't have a PNR to resolve up front; we mint one at the
``create_booking`` step.  The flow collects origin → destination →
alternatives → seat → meal → price-preview → confirm → booked, and
answers payment questions with the emailed-instructions fallback.
"""

from __future__ import annotations

import json

from cascaded.agentic_airline.orchestrators._state_runner import (
    _AIRPORT_CITY_NAMES,
    TurnContext,
    apply_cleanup_plan,
    run_state,
)
from cascaded.agentic_airline.orchestrators.booking_states import (
    BOOKING_INTENT,
    STATE_START,
)
from cascaded.agentic_airline.state.conversation_memory import ConversationMemory
from cascaded.agentic_airline.state.entity_store import EntityStore

# Pre-computed side-answer used when the caller asks about payment.
# Dropped into Collected on every turn so the LLM has a canned answer
# it can quote verbatim — no backend / no billing lookup.
_PAYMENT_INSTRUCTIONS = "Payment details will be shared via email after confirmation."

# Meal-code → spoken word mapping for the preview response.
_MEAL_SPOKEN = {
    "VGML": "vegetarian",
    "NVML": "non-vegetarian",
    "KSML": "kosher",
    "MOML": "halal",
    "GFML": "gluten-free",
    "vegetarian": "vegetarian",
    "non_vegetarian": "non-vegetarian",
    "non-vegetarian": "non-vegetarian",
    "vegan": "vegan",
    "kosher": "kosher",
    "halal": "halal",
    "gluten_free": "gluten-free",
    "gluten-free": "gluten-free",
    "none": "none",
    "keep": "(keep existing)",
}

_VALID_CABINS = frozenset({"economy", "premium_economy", "business", "first"})
_NON_SPECIFIC_SEAT_VALUES = frozenset({"any", "no_preference", "no preference", "agent_choice"})

_CANONICAL_MEALS = {
    "vgml": "vegetarian",
    "vlml": "vegetarian",
    "nvml": "non_vegetarian",
    "ksml": "kosher",
    "moml": "halal",
    "gfml": "gluten_free",
    "vegetarian": "vegetarian",
    "non_vegetarian": "non_vegetarian",
    "non-vegetarian": "non_vegetarian",
    "non vegetarian": "non_vegetarian",
    "vegan": "vegan",
    "kosher": "kosher",
    "halal": "halal",
    "gluten_free": "gluten_free",
    "gluten-free": "gluten_free",
    "gluten free": "gluten_free",
    "none": "none",
    "keep": "keep",
    "same": "keep",
    "no_change": "keep",
    "existing": "keep",
    "unchanged": "keep",
}


def _normalized_meal(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    key = value.strip().lower().replace("-", "_")
    return _CANONICAL_MEALS.get(key)


async def orchestrate_booking(
    transcript: str,
    summary: str,
    entity_store: EntityStore,
    memory: ConversationMemory,
    session_id: str | None = None,
) -> str:
    """Run one booking step via the declarative state runner."""
    entry_step = memory.get("booking_step") or STATE_START
    if entry_step in BOOKING_INTENT.terminal_states:
        _clear_booking_flow(memory, entity_store)
        entry_step = STATE_START

    ctx = TurnContext(
        intent=BOOKING_INTENT,
        current_state=entry_step if entry_step in BOOKING_INTENT.states else STATE_START,
        transcript=transcript,
        collected=_collect_state(memory, entity_store),
        history=[],
        record=None,
        session_id=session_id,
    )
    result = await run_state(ctx)
    apply_cleanup_plan(result.cleanup_plan, memory, entity_store)
    _persist_slot_updates(result.decision.slot_updates or {}, memory)
    _sync_selected_flight_details(memory)
    await _apply_tool_side_effects(result, entity_store, memory)
    _sync_selected_flight_details(memory)
    memory.put("booking_step", result.next_state)
    return result.sentence


_PERSISTED_SLOTS = frozenset(
    {
        "new_origin",
        "new_destination",
        "suggested_flight",
        "requested_cabin",
        "seat_pref",
        "meal_pref",
        "passenger_name",
        "new_pnr",
    }
)

_BOOKING_FLOW_KEYS = frozenset(
    {
        "new_origin",
        "new_destination",
        "suggested_flight",
        "requested_cabin",
        "seat_pref",
        "meal_pref",
        "passenger_name",
        "new_pnr",
        "alternatives_snapshot",
        "price",
        "currency",
        "booked_cabin",
        "last_confirmation_code",
    }
)


def _persist_slot_updates(updates: dict, memory: ConversationMemory) -> None:
    """Stash caller-supplied slot values for the next turn's Collected dict."""
    for key, value in updates.items():
        if key not in _PERSISTED_SLOTS:
            continue
        if value is None or value == "":
            continue
        if key == "requested_cabin":
            cabin = str(value).strip().lower()
            if cabin not in _VALID_CABINS:
                continue
            value = cabin
        if key == "meal_pref":
            meal = _normalized_meal(value)
            if meal is None:
                continue
            value = meal
        if key == "seat_pref":
            seat = str(value).strip().lower()
            if seat in _NON_SPECIFIC_SEAT_VALUES:
                continue
        if key == "suggested_flight" and _snapshot_alternative(memory, value) is None:
            continue
        memory.put(key, str(value))


def _clear_booking_flow(
    memory: ConversationMemory,
    entity_store: EntityStore | None = None,
) -> None:
    """Drop booking-scoped scratch so a restarted booking starts clean."""
    for key in _BOOKING_FLOW_KEYS:
        memory.forget(key)
    if entity_store is not None:
        entity_store.forget("confirmation_code")


def _selected_alternative(memory: ConversationMemory) -> dict | None:
    """Return the chosen alternative from the cached snapshot, if any."""
    selected_flight = memory.get("suggested_flight")
    return _snapshot_alternative(memory, selected_flight)


def _snapshot_alternative(memory: ConversationMemory, flight_number: object) -> dict | None:
    """Return a flight row from alternatives_snapshot by flight number."""
    snapshot_raw = memory.get("alternatives_snapshot")
    if not snapshot_raw or not flight_number:
        return None
    try:
        snapshot = json.loads(snapshot_raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(snapshot, list):
        return None

    selected_upper = str(flight_number).upper()
    for alt in snapshot:
        if not isinstance(alt, dict):
            continue
        if str(alt.get("flight_number") or "").upper() == selected_upper:
            return alt
    return None


def _sync_selected_flight_details(memory: ConversationMemory) -> None:
    """Align route and cabin with the flight the caller actually picked."""
    alt = _selected_alternative(memory)
    if alt is not None and alt.get("origin"):
        memory.put("new_origin", str(alt["origin"]).upper())
    if alt is not None and alt.get("destination"):
        memory.put("new_destination", str(alt["destination"]).upper())
    requested_cabin = memory.get("requested_cabin")
    if requested_cabin:
        memory.put("booked_cabin", str(requested_cabin).lower())
    elif alt is not None and alt.get("cabin"):
        memory.put("booked_cabin", str(alt["cabin"]).lower())


def _collect_state(memory: ConversationMemory, entity_store: EntityStore) -> dict:
    """Assemble the Collected dict for the fused LLM.

    No PNR record at start — everything is built up from caller input.
    Once create_booking fires, the new PNR + confirmation land in
    Collected for the booked-state response.  IATA codes are paired
    with spoken city names (new_origin_spoken / new_destination_spoken)
    so the responder reads back 'San Francisco' instead of 'SFO'.
    """
    collected: dict = {"payment_instructions": _PAYMENT_INSTRUCTIONS}
    for key in (
        "new_origin",
        "new_destination",
        "suggested_flight",
        "requested_cabin",
        "seat_pref",
        "meal_pref",
        "passenger_name",
        "new_pnr",
        "alternatives_snapshot",
        "price",
        "currency",
        "booked_cabin",
    ):
        value = memory.get(key)
        if value:
            collected[key] = value
    snapshot_raw = memory.get("alternatives_snapshot")
    snapshot = None
    if snapshot_raw:
        try:
            snapshot = json.loads(snapshot_raw)
        except json.JSONDecodeError:
            snapshot = None
        else:
            collected["alternatives_snapshot"] = snapshot
    selected_flight = str(collected.get("suggested_flight") or "").upper()
    if isinstance(snapshot, list) and selected_flight:
        for alt in snapshot:
            if not isinstance(alt, dict):
                continue
            if str(alt.get("flight_number") or "").upper() != selected_flight:
                continue
            if alt.get("origin"):
                collected["new_origin"] = alt["origin"]
            if alt.get("destination"):
                collected["new_destination"] = alt["destination"]
            if alt.get("cabin"):
                collected["booked_cabin"] = str(alt["cabin"]).lower()
            break
    requested_cabin = collected.get("requested_cabin")
    if requested_cabin:
        collected["requested_cabin"] = str(requested_cabin).lower()
        collected["booked_cabin"] = str(requested_cabin).lower()
    # Expand IATA codes to spoken city names for the responder.
    if collected.get("new_origin"):
        collected["new_origin_spoken"] = _AIRPORT_CITY_NAMES.get(
            collected["new_origin"].upper(), collected["new_origin"]
        )
    if collected.get("new_destination"):
        collected["new_destination_spoken"] = _AIRPORT_CITY_NAMES.get(
            collected["new_destination"].upper(), collected["new_destination"]
        )
    # Spoken-form meal label so the LLM can announce it readably.
    meal_pref = collected.get("meal_pref")
    if meal_pref:
        collected["meal_pref_spoken"] = _MEAL_SPOKEN.get(str(meal_pref).lower(), str(meal_pref))
    code_entity = entity_store.get("confirmation_code")
    if code_entity:
        collected["last_confirmation_code"] = code_entity.value
    return {k: v for k, v in collected.items() if v not in (None, "")}


async def _apply_tool_side_effects(
    result,
    entity_store: EntityStore,
    memory: ConversationMemory,
) -> None:
    """Persist alternatives, price, new PNR, and confirmation code."""
    if result.tool_name == "list_alternatives" and isinstance(result.tool_result, list) and result.tool_result:
        _store_alternatives_snapshot(memory, result.tool_result)
    elif result.tool_name == "price_quote" and isinstance(result.tool_result, dict):
        if result.tool_result.get("price"):
            memory.put("price", str(result.tool_result["price"]))
        if result.tool_result.get("currency"):
            memory.put("currency", result.tool_result["currency"])
        if result.tool_result.get("cabin"):
            memory.put("booked_cabin", result.tool_result["cabin"])
    elif result.tool_name == "create_booking" and isinstance(result.tool_result, dict):
        new_pnr = result.tool_result.get("pnr")
        if new_pnr:
            memory.put("new_pnr", new_pnr)
            entity_store.put("pnr", new_pnr, confidence=1.0)
        code = result.tool_result.get("confirmation_code")
        if code:
            entity_store.put("confirmation_code", code, confidence=1.0)
            memory.put("last_confirmation_code", code)
        if result.tool_result.get("price"):
            memory.put("price", str(result.tool_result["price"]))
        if result.tool_result.get("currency"):
            memory.put("currency", result.tool_result["currency"])
        if result.tool_result.get("cabin"):
            memory.put("booked_cabin", str(result.tool_result["cabin"]).lower())


def _store_alternatives_snapshot(memory: ConversationMemory, alternatives: list[dict]) -> list[dict]:
    """Cache a compact alternatives snapshot for later flight selection."""
    snapshot = [
        {
            "flight_number": alt.get("flight_number"),
            "departure": alt.get("departure"),
            "origin": alt.get("origin"),
            "destination": alt.get("destination"),
            "cabin": alt.get("cabin"),
        }
        for alt in alternatives[:4]
        if isinstance(alt, dict) and alt.get("flight_number")
    ]
    if not snapshot:
        return []
    memory.put("alternatives_snapshot", json.dumps(snapshot))
    if snapshot[0].get("destination"):
        memory.put("new_destination", str(snapshot[0]["destination"]).upper())
    if snapshot[0].get("origin"):
        memory.put("new_origin", str(snapshot[0]["origin"]).upper())
    return snapshot
