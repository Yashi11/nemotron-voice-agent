# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Declarative state + tool catalog for the booking (new reservation) intent.

Flow:

* ``start`` → collect origin (ask if missing) → ``awaiting_destination``
* ``awaiting_destination`` → collect destination → call list_alternatives →
  ``offered_alternative``
* ``offered_alternative`` → caller picks flight → ``awaiting_seat_pref``
* ``awaiting_seat_pref`` → ``awaiting_meal_pref``
* ``awaiting_meal_pref`` → compute price (via collected) → ``showed_price``
* ``showed_price`` → caller confirms → ``create_booking`` → ``booked``
* ``booked`` — terminal, confirmation + PNR read back.

Payment question is handled as a side-answer: the ``payment_instructions``
fact is always available, and the per-state response_hint tells the
responder to repeat *"Payment details will be shared via email after
confirmation"* on demand.
"""

from __future__ import annotations

from cascaded.agentic_airline.orchestrators._state_runner import (
    IntentSpec,
    StateSpec,
    ToolSpec,
)
from cascaded.agentic_airline.tools import booking_client

_IATA_PROPERTY = {"type": "string", "description": "3-letter IATA airport code, uppercase"}
_FLIGHT_PROPERTY = {"type": "string", "description": "Carrier + digits, e.g. 'AA311', uppercase"}
_VALID_CABINS = frozenset({"economy", "premium_economy", "business", "first"})


def _normalized_cabin(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cabin = value.strip().lower()
    return cabin if cabin in _VALID_CABINS else None


def _selected_snapshot_alternative(collected: dict, flight_number: object) -> dict | None:
    snapshot = collected.get("alternatives_snapshot")
    if not isinstance(snapshot, list):
        return None
    selected = str(flight_number or "").upper()
    if not selected:
        return None
    for alt in snapshot:
        if not isinstance(alt, dict):
            continue
        if str(alt.get("flight_number") or "").upper() == selected:
            return alt
    return None


def _proposal_alt(ctx, decision) -> dict | None:
    updates = decision.slot_updates or {}
    chosen = updates.get("suggested_flight")
    if chosen:
        return _selected_snapshot_alternative(ctx.collected, chosen)
    existing = ctx.collected.get("suggested_flight")
    if existing:
        return _selected_snapshot_alternative(ctx.collected, existing)
    return None


def _proposal_route(ctx, decision) -> tuple[str | None, str | None]:
    updates = decision.slot_updates or {}
    alt = _proposal_alt(ctx, decision)
    origin = updates.get("new_origin") or ctx.collected.get("new_origin")
    destination = updates.get("new_destination") or ctx.collected.get("new_destination")
    if alt is not None:
        origin = alt.get("origin") or origin
        destination = alt.get("destination") or destination
    origin_u = str(origin).strip().upper() if origin else None
    destination_u = str(destination).strip().upper() if destination else None
    return origin_u, destination_u


def _proposal_flight_number(ctx, decision) -> str | None:
    alt = _proposal_alt(ctx, decision)
    if alt is not None and alt.get("flight_number"):
        return str(alt["flight_number"]).upper()
    return None


def _proposal_cabin(ctx, decision) -> str:
    updates = decision.slot_updates or {}
    requested = _normalized_cabin(updates.get("requested_cabin"))
    if requested:
        return requested
    collected_requested = _normalized_cabin(ctx.collected.get("requested_cabin"))
    if collected_requested:
        return collected_requested
    alt = _proposal_alt(ctx, decision)
    if alt is not None:
        alt_cabin = _normalized_cabin(alt.get("cabin"))
        if alt_cabin:
            return alt_cabin
    collected_cabin = _normalized_cabin(ctx.collected.get("booked_cabin"))
    if collected_cabin:
        return collected_cabin
    return "economy"


def _proposal_passenger(ctx, decision) -> str:
    updates = decision.slot_updates or {}
    passenger = updates.get("passenger_name") or ctx.collected.get("passenger_name")
    return str(passenger).strip() if passenger else "Guest"


def _proposal_optional_value(ctx, decision, key: str) -> str | None:
    updates = decision.slot_updates or {}
    value = updates.get(key) or ctx.collected.get(key)
    if value in (None, ""):
        return None
    return str(value)


def _resolve_list_alternatives_params(ctx, decision) -> dict[str, str]:
    origin, destination = _proposal_route(ctx, decision)
    if not origin or not destination:
        return {}
    return {"origin": origin, "destination": destination}


def _resolve_price_quote_params(ctx, decision) -> dict[str, str]:
    origin, destination = _proposal_route(ctx, decision)
    if not origin or not destination:
        return {}
    return {
        "origin": origin,
        "destination": destination,
        "cabin": _proposal_cabin(ctx, decision),
    }


def _resolve_create_booking_params(ctx, decision) -> dict[str, str]:
    origin, destination = _proposal_route(ctx, decision)
    flight_number = _proposal_flight_number(ctx, decision)
    if not origin or not destination or not flight_number:
        return {}
    params: dict[str, str] = {
        "passenger": _proposal_passenger(ctx, decision),
        "origin": origin,
        "destination": destination,
        "flight_number": flight_number,
        "cabin": _proposal_cabin(ctx, decision),
    }
    seat = _proposal_optional_value(ctx, decision, "seat_pref")
    if seat:
        params["seat"] = seat
    meal = _proposal_optional_value(ctx, decision, "meal_pref")
    if meal:
        params["meal"] = meal
    return params


async def _tool_list_alternatives(origin: str, destination: str) -> list[dict]:
    return await booking_client.list_alternatives(origin, destination)


async def _tool_price_quote(origin: str, destination: str, cabin: str = "economy") -> dict | None:
    return await booking_client.price_quote(origin, destination, cabin)


async def _tool_create_booking(
    passenger: str,
    origin: str,
    destination: str,
    flight_number: str,
    seat: str | None = None,
    meal: str | None = None,
    cabin: str | None = None,
    session_id: str | None = None,
) -> dict | None:
    return await booking_client.create_booking(
        passenger=passenger,
        origin=origin,
        destination=destination,
        flight_number=flight_number,
        seat=seat,
        meal=meal,
        cabin=cabin,
        session_id=session_id,
    )


async def _tool_list_routes(origin: str | None = None, destination: str | None = None) -> list[dict]:
    return await booking_client.list_routes(origin=origin, destination=destination)


_TOOLS: dict[str, ToolSpec] = {
    "list_alternatives": ToolSpec(
        name="list_alternatives",
        description=(
            "List scheduled flights on a specific route so the caller "
            "can pick one for their new booking. Requires BOTH origin "
            "and destination — call this once both airports are known."
        ),
        params={
            "type": "object",
            "properties": {"origin": _IATA_PROPERTY, "destination": _IATA_PROPERTY},
            "required": ["origin", "destination"],
        },
        execute=_tool_list_alternatives,
        param_resolver=_resolve_list_alternatives_params,
    ),
    "price_quote": ToolSpec(
        name="price_quote",
        description=(
            "Return a fare estimate for a prospective booking. Call "
            "this at the awaiting_meal_pref → showed_price transition "
            "so the caller hears a concrete price before confirming. "
            "Pass origin, destination, and cabin (from Collected."
            "requested_cabin or Collected.booked_cabin or 'economy')."
        ),
        params={
            "type": "object",
            "properties": {
                "origin": _IATA_PROPERTY,
                "destination": _IATA_PROPERTY,
                "cabin": {
                    "type": "string",
                    "description": ("Cabin class — economy / premium_economy / business / first"),
                },
            },
            "required": ["origin", "destination"],
        },
        execute=_tool_price_quote,
        param_resolver=_resolve_price_quote_params,
    ),
    "create_booking": ToolSpec(
        name="create_booking",
        description=(
            "Create a brand-new PNR on the chosen flight. Pass "
            "passenger_name, origin, destination, flight_number, seat, "
            "meal, and cabin from Collected. Only call AFTER the caller "
            "has confirmed the price at the showed_price state."
        ),
        params={
            "type": "object",
            "properties": {
                "passenger": {
                    "type": "string",
                    "description": ("Caller's name (from Collected.passenger_name or 'Guest' if not gathered)"),
                },
                "origin": _IATA_PROPERTY,
                "destination": _IATA_PROPERTY,
                "flight_number": _FLIGHT_PROPERTY,
                "seat": {"type": "string", "description": "Seat preference or omit"},
                "meal": {"type": "string", "description": "Meal preference (free-form, canonicalised server-side)"},
                "cabin": {
                    "type": "string",
                    "description": "Cabin class — economy / premium_economy / business / first",
                },
            },
            "required": ["passenger", "origin", "destination", "flight_number"],
        },
        execute=_tool_create_booking,
        param_resolver=_resolve_create_booking_params,
    ),
    "list_routes": ToolSpec(
        name="list_routes",
        description=(
            "List destinations reachable FROM an origin OR origins that "
            "fly INTO a destination. Pass EXACTLY ONE of origin / "
            "destination. Useful when the caller is unsure where to fly."
        ),
        params={
            "type": "object",
            "properties": {"origin": _IATA_PROPERTY, "destination": _IATA_PROPERTY},
            "required": [],
        },
        execute=_tool_list_routes,
    ),
}


STATE_START = "start"
STATE_AWAITING_DESTINATION = "awaiting_destination"
STATE_OFFERED = "offered_alternative"
STATE_SEAT = "awaiting_seat_pref"
STATE_MEAL = "awaiting_meal_pref"
STATE_PRICE = "showed_price"
STATE_BOOKED = "booked"


_STATES: dict[str, StateSpec] = {
    STATE_START: StateSpec(
        name=STATE_START,
        purpose=(
            "Collect the origin city/airport the caller wants to depart "
            "from for their NEW booking.\n"
            "- If the caller names ONLY an origin → slot_updates="
            '{"new_origin": <IATA>}, next_state=awaiting_destination, '
            "no tool.\n"
            "- If the caller names BOTH origin AND destination in the "
            "same utterance (e.g. 'from JFK to SFO', 'book me a flight "
            'from JFK to San Francisco\') → slot_updates={"new_origin": '
            '<origin IATA>, "new_destination": <destination IATA>}, '
            "next_state=offered_alternative, tool=list_alternatives"
            "(origin=<origin>, destination=<destination>). Destination "
            "and origin MUST be DIFFERENT codes parsed from different "
            "parts of the utterance — never set both to the same IATA.\n"
            "- If the caller hasn't named either → stay at start."
        ),
        allowed_next=(STATE_AWAITING_DESTINATION, STATE_OFFERED, STATE_START),
        preferred_tools=("list_alternatives",),
        response_hint=(
            "Ask warmly which city or airport the caller wants to "
            "depart from. Use spoken city names (e.g. 'New York JFK'), "
            "not bare IATA codes."
        ),
    ),
    STATE_AWAITING_DESTINATION: StateSpec(
        name=STATE_AWAITING_DESTINATION,
        purpose=(
            "Origin is captured in Collected.new_origin. Collect the "
            "destination.\n"
            "- When the caller NAMES a destination city/airport → CALL "
            "list_alternatives(origin=new_origin, destination=<spoken>) "
            "and move to offered_alternative.\n"
            "- When the caller CHANGES the origin mid-flow ('from San "
            "Francisco instead', 'not Agra, make it San Francisco') → "
            "same-intent restart. Use reset_scope=intent_flow so the old "
            "proposal is dropped. If they ALSO provide a destination in "
            "the same utterance, stash BOTH fresh slots and CALL "
            "list_alternatives on the NEW route. Otherwise stash the NEW "
            "origin and stay in awaiting_destination so you can ask for "
            "the new destination.\n"
            "- When the caller ASKS for suggestions ('where can I fly "
            "from SFO', 'what cities can I reach from here', 'list the "
            "destinations available') → CALL list_routes(origin="
            "new_origin). Stay in this state; the responder will read "
            "back the list.\n"
            "- NEVER call list_alternatives with origin == destination. "
            "Destination MUST come from the caller's current utterance."
        ),
        allowed_next=(STATE_OFFERED, STATE_START, STATE_AWAITING_DESTINATION),
        preferred_tools=("list_alternatives", "list_routes"),
        response_hint=(
            "Ask the caller which city or airport they want to fly TO. "
            "Mention the origin they gave using its actual value from "
            "Collected.new_origin — never substitute a different city."
        ),
    ),
    STATE_OFFERED: StateSpec(
        name=STATE_OFFERED,
        purpose=(
            "Alternatives are in offered_alternatives (runner-supplied). "
            "Let the caller pick one — stash the chosen flight number "
            "in slot_updates.suggested_flight and move to "
            "awaiting_seat_pref. If the caller names a cabin preference, "
            "stash slot_updates.requested_cabin too. If the caller wants "
            "a different route, same-intent restart: use "
            "reset_scope=intent_flow and move to an earlier booking "
            "state with the fresh route slots."
        ),
        allowed_next=(STATE_SEAT, STATE_OFFERED, STATE_START),
        preferred_tools=(),
        response_hint=(
            "Offer the flights in offered_alternatives by number AND "
            "departure time (read airport names from airport_names when "
            "present). Ask which one works best."
        ),
    ),
    STATE_SEAT: StateSpec(
        name=STATE_SEAT,
        purpose=(
            "Collect the caller's seat preference: aisle, window, or a "
            "specific code (e.g. 14A). If the caller has NO seat "
            "preference ('any seat', 'you choose', 'no specific seat'), "
            "do NOT stash a seat slot — just move to awaiting_meal_pref. "
            "Otherwise stash into slot_updates.seat_pref. Move to "
            "awaiting_meal_pref."
        ),
        allowed_next=(STATE_MEAL, STATE_SEAT),
        preferred_tools=(),
        response_hint=(
            "Ask whether they'd prefer an aisle, a window, a specific "
            "seat, or no seat preference. Keep it one sentence."
        ),
    ),
    STATE_MEAL: StateSpec(
        name=STATE_MEAL,
        purpose=(
            "Collect the caller's meal preference: vegetarian, "
            "non_vegetarian, vegan, kosher, halal, gluten_free, or none. "
            "Stash into slot_updates.meal_pref AND CALL price_quote"
            "(origin=new_origin, destination=new_destination, cabin="
            "requested_cabin or booked_cabin) so the next state can read "
            "Collected.price. Move to showed_price."
        ),
        allowed_next=(STATE_PRICE, STATE_MEAL),
        preferred_tools=("price_quote",),
        response_hint=(
            "Ask about meal preference and list 2-3 common options "
            "(vegetarian / non-vegetarian / vegan). Keep it one sentence."
        ),
    ),
    STATE_PRICE: StateSpec(
        name=STATE_PRICE,
        purpose=(
            "Summarise the proposed booking (route, flight, seat, meal) "
            "and cabin, then read the price from Collected.price with "
            "Collected.currency. Ask the caller to confirm. On YES, "
            "CALL create_booking(passenger, origin, destination, "
            "flight_number, seat, meal, cabin) and move to booked. If "
            "caller asks about payment, answer from "
            "payment_instructions. If "
            "the caller wants to change the seat AND gives the NEW seat "
            "value in the same utterance (e.g. 'make that 3A', 'window "
            "seat instead'), stash slot_updates.seat_pref and stay at "
            "showed_price so you can re-summarise immediately. If they "
            "just ask to change the seat without saying to what, go back "
            "to awaiting_seat_pref. If they want to change the meal AND "
            "give the NEW meal in the same utterance (e.g. 'make that "
            "non-vegetarian'), stash slot_updates.meal_pref, CALL "
            "price_quote(origin=new_origin, destination=new_destination, "
            "cabin=requested_cabin or booked_cabin), and stay at "
            "showed_price so the updated proposal is read back "
            "immediately. If they just ask to change the meal without "
            "naming the new meal, go back to awaiting_meal_pref. If they "
            "name a NEW cabin value (e.g. 'economy class', 'business "
            "instead'), stash slot_updates.requested_cabin, CALL "
            "price_quote(origin=new_origin, destination=new_destination, "
            "cabin=<new cabin>), and stay at showed_price. If they ask "
            "to change cabin without naming it, stay at showed_price and "
            "ask which cabin they prefer. If they want a different route "
            "or flight search, use reset_scope=intent_flow so the old "
            "proposal is dropped."
        ),
        allowed_next=(STATE_BOOKED, STATE_SEAT, STATE_MEAL, STATE_PRICE, STATE_START),
        preferred_tools=("create_booking", "price_quote"),
        response_hint=(
            "Summarise the PROPOSED booking: new_origin → "
            "new_destination on suggested_flight, cabin, seat_pref, "
            "meal_pref_spoken, and the total price (include currency). "
            "Ask for confirmation. If the caller asks HOW to pay, use "
            "Collected.payment_instructions verbatim: 'Payment details "
            "will be shared via email after confirmation.'"
        ),
    ),
    STATE_BOOKED: StateSpec(
        name=STATE_BOOKED,
        purpose=(
            "Booking is live in the database. Read back the new PNR "
            "(Collected.new_pnr), confirmation_code, flight, and route. "
            "Mention that payment details will be emailed shortly."
        ),
        allowed_next=(STATE_BOOKED,),
        preferred_tools=(),
        response_hint=(
            "Announce the booking is confirmed. Read back the new_pnr, "
            "confirmation_code, and flight details. Say payment "
            "instructions will be sent to the caller's email on file."
        ),
    ),
}


BOOKING_INTENT = IntentSpec(
    name="booking",
    entry_state=STATE_START,
    terminal_states=frozenset({STATE_BOOKED}),
    states=_STATES,
    tools=_TOOLS,
    always_available=("list_routes",),
    tool_transitions={
        "list_alternatives": (STATE_OFFERED, STATE_AWAITING_DESTINATION),
        "price_quote": (STATE_PRICE, STATE_PRICE),
        "create_booking": (STATE_BOOKED, None),
    },
    prompt_examples=(
        "- Caller says where they want to FLY FROM (e.g. 'Los Angeles', "
        "'S F O') at state=start → slot_updates={\"new_origin\": <IATA>}, "
        "next_state=awaiting_destination, no tool yet (we still need the "
        "destination).\n"
        "- Caller says where they want to FLY TO at state="
        'awaiting_destination → slot_updates={"new_destination": '
        "<IATA>}, next_state=offered_alternative, tool=list_alternatives"
        "(origin=new_origin_from_collected, destination=<just-heard>). "
        "NEVER pass origin twice — destination comes from THIS turn's "
        "words, not from Collected.new_origin.\n"
        "- Caller changes the ORIGIN while at awaiting_destination "
        "('from San Francisco instead', 'not Agra, San Francisco') → "
        "reset_scope=intent_flow, next_state=awaiting_destination with "
        'slot_updates={"new_origin": <new IATA>} so the stale route is '
        "cleared but you do NOT re-ask for origin. If the same utterance "
        "also contains the new destination, set BOTH slots and call "
        "list_alternatives on the new route.\n"
        "- Caller asks for SUGGESTIONS at state=awaiting_destination "
        "('where can I fly from SFO', 'what cities from here', 'list "
        "the destinations available') → tool=list_routes(origin="
        "new_origin_from_collected), stay on awaiting_destination. Do "
        "NOT call list_alternatives and do NOT invent a destination.\n"
        "- Caller picks 'the 3 PM one' / 'the earlier' / by flight "
        "number at state=offered_alternative → slot_updates="
        '{"suggested_flight": <flight_number from '
        "offered_alternatives>}, next_state=awaiting_seat_pref, no "
        "tool.\n"
        "- Caller says 'the first option' / 'the first one' at state="
        'offered_alternative → slot_updates={"suggested_flight": '
        '"<first flight number from offered_alternatives>"}, '
        "next_state=awaiting_seat_pref.\n"
        "- Caller picks a flight AND says a cabin ('the 9:30 one in "
        'economy\') → slot_updates={"suggested_flight": <flight>, '
        '"requested_cabin": "economy"}, next_state=awaiting_seat_pref.\n'
        "- Caller confirms at state=showed_price → tool=create_booking"
        "(passenger=Collected.passenger_name or 'Guest', origin="
        "new_origin, destination=new_destination, flight_number="
        "suggested_flight, seat=seat_pref, meal=meal_pref, cabin="
        "requested_cabin_or_booked_cabin), "
        "next_state=booked.\n"
        "- Caller says 'make that non-vegetarian' / 'change meal to vegan' "
        'at state=showed_price → slot_updates={"meal_pref": <meal>}, '
        "tool=price_quote(origin=new_origin, destination=new_destination, "
        "cabin=requested_cabin_or_booked_cabin), next_state=showed_price.\n"
        "- Caller says only 'change the meal' at state=showed_price → "
        "next_state=awaiting_meal_pref, no tool.\n"
        "- Caller says 'make that 3A' / 'window seat instead' at "
        'state=showed_price → slot_updates={"seat_pref": <seat>}, '
        "next_state=showed_price, no tool.\n"
        "- Caller says 'any seat is fine' / 'you choose the seat' at "
        "state=awaiting_seat_pref → no seat slot needed, "
        "next_state=awaiting_meal_pref.\n"
        "- Caller says only 'change the seat' at state=showed_price → "
        "next_state=awaiting_seat_pref, no tool.\n"
        "- Caller says 'make that economy class' / 'business instead' at "
        'state=showed_price → slot_updates={"requested_cabin": <cabin>}, '
        "tool=price_quote(origin=new_origin, destination=new_destination, "
        "cabin=<cabin>), next_state=showed_price.\n"
        "- Caller says 'different flight entirely' / 'start over with a "
        "new route' → use reset_scope=intent_flow and move to the "
        "appropriate earlier booking state."
    ),
    state_ranks={
        STATE_START: 0,
        STATE_AWAITING_DESTINATION: 1,
        STATE_OFFERED: 2,
        STATE_SEAT: 3,
        STATE_MEAL: 4,
        STATE_PRICE: 5,
        STATE_BOOKED: 6,
    },
    state_slot_ownership={
        STATE_START: ("new_origin", "passenger_name"),
        STATE_AWAITING_DESTINATION: ("new_destination",),
        STATE_OFFERED: ("suggested_flight", "alternatives_snapshot", "booked_cabin", "requested_cabin"),
        STATE_SEAT: ("seat_pref",),
        STATE_MEAL: ("meal_pref",),
        STATE_PRICE: ("price", "currency"),
        STATE_BOOKED: ("new_pnr", "last_confirmation_code"),
    },
    flow_scoped_entities=("confirmation_code",),
)
