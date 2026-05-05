# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Declarative state + tool catalog for the rebook intent.

Paired with :mod:`cascaded.agentic_airline.orchestrators._state_runner` — the
runner consumes these specs on each caller turn without knowing anything
rebook-specific.  Porting another intent (cancel / standby) is
just declaring the states + tools here and wiring a thin entry point.

Contract:

* Each state's ``allowed_next`` lists the transitions the fused LLM may
  pick.  The runner rejects anything outside the list and stays on the
  current state (keeps the agent from skipping seat / meal steps on its
  way to a commit).
* Tool ``execute`` callbacks return the backend result verbatim — the
  runner drops it into the responder's facts under ``tool_result``.
  Post-processing that touches EntityStore / ConversationMemory (e.g.
  stashing a confirmation code on commit) happens in
  :func:`cascaded.agentic_airline.orchestrators.rebook.orchestrate_rebook`.
"""

from __future__ import annotations

from cascaded.agentic_airline.orchestrators._state_runner import IntentSpec, StateSpec, ToolSpec
from cascaded.agentic_airline.tools import _backend, booking_client

# ----------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------

# Each ``params`` block is a JSON schema dropped verbatim into the fused
# LLM's tool catalogue.  Keep them minimal and unambiguous — the schema
# is the only instruction the LLM sees about parameter shape.
_IATA_PROPERTY = {"type": "string", "description": "3-letter IATA airport code, uppercase"}
_FLIGHT_PROPERTY = {
    "type": "string",
    "description": "Carrier + digits, e.g. 'AA311'. Uppercase, no spaces.",
}
_PNR_PROPERTY = {
    "type": "string",
    "description": "6-character record locator (3 letters + 3 digits), uppercase",
}


async def _tool_list_alternatives(origin: str, destination: str) -> list[dict]:
    return await booking_client.list_alternatives(origin, destination)


async def _tool_ancillaries_diff(pnr: str, new_flight_number: str) -> dict | None:
    return await booking_client.ancillaries_diff(pnr, new_flight_number)


async def _tool_commit_rebook(
    pnr: str,
    new_flight_number: str,
    session_id: str | None = None,
    seat: str | None = None,
    meal: str | None = None,
    departure: str | None = None,
) -> dict | None:
    return await booking_client.commit_rebook(
        pnr, new_flight_number, session_id=session_id, seat=seat, meal=meal, departure=departure
    )


def _resolve_commit_rebook_params(ctx, decision) -> dict | None:
    """Inject ``departure`` from alternatives_snapshot for the chosen flight.

    The LLM only picks a flight_number; without departure, the backend
    resolves it as "earliest scheduled" — wrong when flight numbers
    recur across dates.  We look up the chosen alternative in the
    snapshot the orchestrator already has and pin the exact row.
    """
    params = dict(decision.tool_params or {})
    chosen = params.get("new_flight_number") or ctx.collected.get("suggested_flight")
    if not chosen:
        return None
    snapshot = ctx.collected.get("alternatives_snapshot")
    if not isinstance(snapshot, list):
        return None
    needle = str(chosen).strip().upper()
    for alt in snapshot:
        if not isinstance(alt, dict):
            continue
        if str(alt.get("flight_number") or "").upper() == needle:
            departure = alt.get("departure")
            if departure:
                params["departure"] = departure
                return params
            break
    return None


async def _tool_list_routes(origin: str | None = None, destination: str | None = None) -> list[dict]:
    return await booking_client.list_routes(origin=origin, destination=destination)


async def _tool_lookup_pnr(pnr: str) -> dict | None:
    return await _backend.get_pnr(pnr)


async def _tool_get_flight_status(flight_number: str) -> dict | None:
    return await _backend.get_flight_status(flight_number)


_TOOLS: dict[str, ToolSpec] = {
    "list_alternatives": ToolSpec(
        name="list_alternatives",
        description=(
            "List scheduled flights on a specific route. Use when the caller "
            "named both an origin and a destination and wants to see actual "
            "flight options."
        ),
        params={
            "type": "object",
            "properties": {"origin": _IATA_PROPERTY, "destination": _IATA_PROPERTY},
            "required": ["origin", "destination"],
        },
        execute=_tool_list_alternatives,
    ),
    "ancillaries_diff": ToolSpec(
        name="ancillaries_diff",
        description=(
            "Preview how seat, bags, and meal carry over to a new flight "
            "before committing the rebook. Requires the PNR and the chosen "
            "replacement flight number."
        ),
        params={
            "type": "object",
            "properties": {"pnr": _PNR_PROPERTY, "new_flight_number": _FLIGHT_PROPERTY},
            "required": ["pnr", "new_flight_number"],
        },
        execute=_tool_ancillaries_diff,
    ),
    "commit_rebook": ToolSpec(
        name="commit_rebook",
        description=(
            "Atomically swap the PNR's flight to new_flight_number AND "
            "persist seat / meal changes the caller requested this flow. "
            "Only call AFTER the caller has explicitly confirmed the new "
            "flight, seat, and meal at the preview state. Pass seat and "
            "meal from Collected (seat_pref / meal_pref) — they'll be "
            "saved to the database in the same transaction."
        ),
        params={
            "type": "object",
            "properties": {
                "pnr": _PNR_PROPERTY,
                "new_flight_number": _FLIGHT_PROPERTY,
                "seat": {
                    "type": "string",
                    "description": (
                        "Seat update: a seat code (e.g. '14D', '21A'), an aisle/window "
                        "preference, or 'keep' to leave unchanged."
                    ),
                },
                "meal": {
                    "type": "string",
                    "description": (
                        "Meal update: 'vegetarian', 'non_vegetarian', 'vegan', 'kosher', "
                        "'halal', or 'keep' to leave unchanged."
                    ),
                },
            },
            "required": ["pnr", "new_flight_number"],
        },
        execute=_tool_commit_rebook,
        param_resolver=_resolve_commit_rebook_params,
    ),
    "list_routes": ToolSpec(
        name="list_routes",
        description=(
            "List scheduled routes for ONE airport: destinations reachable "
            "FROM an origin, OR origins that fly INTO a destination. Pass "
            "exactly one of origin / destination. This lists airports, NOT "
            "individual flights — use list_alternatives when the caller "
            "names both an origin and a destination."
        ),
        params={
            "type": "object",
            "properties": {"origin": _IATA_PROPERTY, "destination": _IATA_PROPERTY},
            "required": [],
        },
        execute=_tool_list_routes,
    ),
    "lookup_pnr": ToolSpec(
        name="lookup_pnr",
        description="Fetch passenger, flight, fare, and ancillary details for a PNR.",
        params={
            "type": "object",
            "properties": {"pnr": _PNR_PROPERTY},
            "required": ["pnr"],
        },
        execute=_tool_lookup_pnr,
    ),
    "get_flight_status": ToolSpec(
        name="get_flight_status",
        description="Return status (scheduled / delayed / cancelled) and delay minutes for a flight.",
        params={
            "type": "object",
            "properties": {"flight_number": _FLIGHT_PROPERTY},
            "required": ["flight_number"],
        },
        execute=_tool_get_flight_status,
    ),
}


# ----------------------------------------------------------------------
# States
# ----------------------------------------------------------------------

STATE_START = "start"
STATE_OFFERED = "offered_alternative"
STATE_SEAT = "awaiting_seat_pref"
STATE_MEAL = "awaiting_meal_pref"
STATE_PREVIEW = "showed_ancillaries"
STATE_COMMITTED = "committed"
STATE_NO_ALT = "no_alternatives"


_STATES: dict[str, StateSpec] = {
    STATE_START: StateSpec(
        name=STATE_START,
        purpose=(
            "PNR is loaded; need the destination the caller wants to "
            "rebook to.\n"
            "- Caller names a destination → CALL list_alternatives"
            "(origin=current_origin, destination=<spoken>). Next state: "
            "offered_alternative.\n"
            "- Caller asks ABOUT THEIR booking (status, current flight, "
            "destination, seat, meal, departure, elite_tier) → NO tool, "
            "stay at start, answer from Collected (current_flight, "
            "current_origin, current_destination, current_status, "
            "current_seat, current_meal_spoken, etc.). Re-ask the "
            "destination briefly at the end.\n"
            "- Caller asks 'where can I fly from X' → CALL list_routes"
            "(origin=X), stay.\n"
            "- No destination named and no side query → stay and ask "
            "briefly."
        ),
        allowed_next=(STATE_OFFERED, STATE_NO_ALT, STATE_START),
        preferred_tools=("list_alternatives", "list_routes"),
        # No default hint — the state's purpose has multiple branches,
        # and supplying a hint here caused the LLM to copy the destination
        # re-ask verbatim even when the caller asked a side query.
        response_hint="",
    ),
    STATE_OFFERED: StateSpec(
        name=STATE_OFFERED,
        purpose=(
            "Alternatives have been presented; caller picks one (by "
            "position, time, or flight number). Once picked, move to "
            "awaiting_seat_pref. If the caller changes destination here, "
            "transition back to start."
        ),
        allowed_next=(STATE_SEAT, STATE_START, STATE_OFFERED),
        preferred_tools=(),
        response_hint=(
            "Offer the flights in offered_alternatives by flight number and departure time; ask which one works."
        ),
    ),
    STATE_SEAT: StateSpec(
        name=STATE_SEAT,
        purpose=(
            "Collect seat preference for the new flight. On entry, ASK the "
            "caller whether they want to KEEP their existing seat "
            "(Collected.current_seat — e.g. '14A') or CHANGE to a different "
            "seat; surface the existing seat number in the question so the "
            "caller knows what they're keeping. Valid answers: keep / "
            "aisle / window / a specific seat code (e.g. 12C). Once the "
            "caller has chosen, move to awaiting_meal_pref."
        ),
        allowed_next=(STATE_MEAL, STATE_SEAT),
        preferred_tools=(),
        response_hint=("Ask whether to keep current_seat (name the code, e.g. 14A) or pick a different seat."),
    ),
    STATE_MEAL: StateSpec(
        name=STATE_MEAL,
        purpose=(
            "Collect meal preference for the new flight. On entry, ASK "
            "the caller whether they want to KEEP their existing meal "
            "(Collected.current_meal — e.g. 'VGML' / 'vegetarian') or "
            "CHANGE to another option (vegetarian, non_vegetarian, vegan, "
            "kosher, halal); surface the existing meal in the question. "
            "Once captured, call ancillaries_diff to compute the carry-over "
            "and move to showed_ancillaries."
        ),
        allowed_next=(STATE_PREVIEW, STATE_MEAL),
        preferred_tools=("ancillaries_diff",),
        response_hint=(
            "Ask whether to keep current_meal_spoken or pick another "
            "option (vegetarian / non-vegetarian / vegan / kosher / halal)."
        ),
    ),
    STATE_PREVIEW: StateSpec(
        name=STATE_PREVIEW,
        purpose=(
            "Preview the PROPOSED rebook to the caller: describe the NEW "
            "flight (suggested_flight), NEW route (new_origin → "
            "new_destination), and the NEW ancillaries — use "
            "Collected.proposed_seat and Collected.proposed_meal_spoken "
            "(e.g. 'non-vegetarian'), NOT the current_* values. Ask for "
            "a final yes/no. On YES, call commit_rebook(pnr, "
            "new_flight_number=suggested_flight, seat=seat_pref, "
            "meal=meal_pref) and move to committed. On NO or destination "
            "change, go back to start."
        ),
        allowed_next=(STATE_COMMITTED, STATE_START, STATE_PREVIEW),
        preferred_tools=("commit_rebook",),
        response_hint=(
            "Summarise the PROPOSED rebook using suggested_flight, "
            "new_destination, proposed_seat, and proposed_meal_spoken. "
            "Ask the caller to confirm. Describe the NEW booking, not "
            "the current one."
        ),
    ),
    STATE_COMMITTED: StateSpec(
        name=STATE_COMMITTED,
        purpose=(
            "Rebook is complete. Confirm with confirmation_code, the "
            "new flight (suggested_flight), new route, and proposed "
            "seat/meal (use proposed_meal_spoken, not current_meal). "
            "Do not call any tools here."
        ),
        allowed_next=(STATE_COMMITTED,),
        preferred_tools=(),
        response_hint=("Announce the rebook completed; read back confirmation_code and committed_flight."),
    ),
    STATE_NO_ALT: StateSpec(
        name=STATE_NO_ALT,
        purpose=(
            "No scheduled flights on the route the caller asked for. Offer "
            "to try a different destination — transition back to start "
            "once they name one."
        ),
        allowed_next=(STATE_START, STATE_NO_ALT),
        preferred_tools=("list_routes",),
        response_hint=(
            "Tell the caller there aren't alternatives on that route; "
            "ask if they'd like to try a different destination or origin."
        ),
    ),
}


REBOOK_INTENT = IntentSpec(
    name="rebook",
    entry_state=STATE_START,
    terminal_states=frozenset({STATE_COMMITTED}),
    states=_STATES,
    tools=_TOOLS,
    always_available=("list_routes", "lookup_pnr", "get_flight_status"),
    tool_transitions={
        "list_alternatives": (STATE_OFFERED, STATE_NO_ALT),
        "commit_rebook": (STATE_COMMITTED, None),
    },
    prompt_examples=(
        "- Caller names a destination at state=start (origin in "
        "Collected.current_origin) → tool=list_alternatives"
        "(origin=current_origin, destination=spoken), next_state="
        "offered_alternative.\n"
        "- Caller picks an option at state=offered_alternative → "
        'slot_updates={"suggested_flight": <flight_number>}, '
        "next_state=awaiting_seat_pref, no tool.\n"
        "- Caller affirms at state=showed_ancillaries → tool="
        "commit_rebook(pnr, new_flight_number=suggested_flight, seat="
        "seat_pref, meal=meal_pref), next_state=committed.\n"
        "- Caller names a different destination after "
        "showed_ancillaries → same-intent restart: next_state=start, "
        "tool=list_alternatives(origin=current_origin, destination="
        "<new>)."
    ),
    state_ranks={
        STATE_START: 0,
        STATE_OFFERED: 1,
        STATE_NO_ALT: 1,
        STATE_SEAT: 2,
        STATE_MEAL: 3,
        STATE_PREVIEW: 4,
        STATE_COMMITTED: 5,
    },
    state_slot_ownership={
        STATE_START: ("new_destination",),
        STATE_OFFERED: (
            "suggested_flight",
            "alternatives_snapshot",
            "rebook_alternatives",
            "new_origin",
        ),
        STATE_NO_ALT: (),
        STATE_SEAT: ("seat_pref",),
        STATE_MEAL: ("meal_pref",),
        STATE_PREVIEW: (),
        STATE_COMMITTED: ("committed_flight", "last_confirmation_code"),
    },
    flow_scoped_entities=("confirmation_code",),
)
