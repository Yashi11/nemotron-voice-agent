# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Declarative state + tool catalog for the cancel intent.

Paired with :mod:`cascaded.agentic_airline.orchestrators._state_runner` — the
runner consumes these specs on each caller turn without knowing anything
cancel-specific.  Cancellation terms (refund / travel credit / no
recovery) are classified in pure Python inside ``cancel.py`` and pushed
into ``collected`` so the LLM reads them as facts rather than computing
them itself.
"""

from __future__ import annotations

from cascaded.agentic_airline.orchestrators._state_runner import IntentSpec, StateSpec, ToolSpec
from cascaded.agentic_airline.tools import _backend, booking_client

_PNR_PROPERTY = {
    "type": "string",
    "description": "6-character record locator, uppercase",
}


async def _tool_cancel_booking(
    pnr: str,
    kind: str,
    policy_ref: str,
    session_id: str | None = None,
) -> dict | None:
    return await booking_client.cancel_booking(pnr, kind=kind, policy_ref=policy_ref, session_id=session_id)


async def _tool_lookup_pnr(pnr: str) -> dict | None:
    return await _backend.get_pnr(pnr)


async def _tool_get_flight_status(flight_number: str) -> dict | None:
    return await _backend.get_flight_status(flight_number)


async def _tool_list_routes(origin: str | None = None, destination: str | None = None) -> list[dict]:
    return await booking_client.list_routes(origin=origin, destination=destination)


_TOOLS: dict[str, ToolSpec] = {
    "cancel_booking": ToolSpec(
        name="cancel_booking",
        description=(
            "Commit the cancellation for this PNR. Pass the cancel kind "
            "and policy_ref from Collected (cancel_kind / "
            "cancel_policy_ref) — they're already classified. Mints a "
            "confirmation code."
        ),
        params={
            "type": "object",
            "properties": {
                "pnr": _PNR_PROPERTY,
                "kind": {
                    "type": "string",
                    "description": (
                        "Classification from Collected.cancel_kind "
                        "(airline_refund / voluntary_refundable / voluntary_nonrefundable / "
                        "voluntary_basic / long_delay_refund / diversion_limited)."
                    ),
                },
                "policy_ref": {
                    "type": "string",
                    "description": "Policy identifier from Collected.cancel_policy_ref (e.g. CXL-VOL-2024-02).",
                },
            },
            "required": ["pnr", "kind", "policy_ref"],
        },
        execute=_tool_cancel_booking,
    ),
    "lookup_pnr": ToolSpec(
        name="lookup_pnr",
        description="Fetch booking details. Rarely needed — Collected already has them.",
        params={
            "type": "object",
            "properties": {"pnr": _PNR_PROPERTY},
            "required": ["pnr"],
        },
        execute=_tool_lookup_pnr,
    ),
    "get_flight_status": ToolSpec(
        name="get_flight_status",
        description="Return status and delay minutes for a flight.",
        params={
            "type": "object",
            "properties": {
                "flight_number": {
                    "type": "string",
                    "description": "Carrier + digits, uppercase.",
                }
            },
            "required": ["flight_number"],
        },
        execute=_tool_get_flight_status,
    ),
    "list_routes": ToolSpec(
        name="list_routes",
        description="List destinations from an origin OR origins into a destination — pass exactly one.",
        params={
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "3-letter IATA, uppercase"},
                "destination": {"type": "string", "description": "3-letter IATA, uppercase"},
            },
            "required": [],
        },
        execute=_tool_list_routes,
    ),
}


STATE_START = "start"
STATE_SHOWED = "showed_terms"
STATE_CANCELLED = "cancelled"


_STATES: dict[str, StateSpec] = {
    STATE_START: StateSpec(
        name=STATE_START,
        purpose=(
            "Read the cancellation terms back to the caller (use "
            "Collected.cancel_outcome, Collected.cancel_policy_ref, and "
            "Collected.cancel_penalty if present) and ask them to "
            "confirm cancelling. Do NOT call cancel_booking yet — wait "
            "for an explicit yes. Move to showed_terms."
        ),
        allowed_next=(STATE_SHOWED, STATE_START),
        preferred_tools=(),
        response_hint=(
            "Read the cancellation terms: cancel_outcome, cite "
            "cancel_policy_ref, mention cancel_penalty if present. Ask "
            "the caller to confirm the cancellation. Do NOT describe "
            "the current booking as a status update."
        ),
    ),
    STATE_SHOWED: StateSpec(
        name=STATE_SHOWED,
        purpose=(
            "Terms have been presented; waiting for yes/no. On YES, CALL "
            "cancel_booking(pnr, kind=cancel_kind, policy_ref="
            "cancel_policy_ref) and move to cancelled. On NO, tell the "
            "caller the booking is kept and move to cancelled without "
            "calling any tool."
        ),
        allowed_next=(STATE_CANCELLED, STATE_SHOWED),
        preferred_tools=("cancel_booking",),
        response_hint=(
            "Waiting for yes/no. If unclear, re-ask briefly whether the "
            "caller wants to proceed with cancelling under the terms."
        ),
    ),
    STATE_CANCELLED: StateSpec(
        name=STATE_CANCELLED,
        purpose=(
            "Terminal state. Reached after the caller either confirmed "
            "cancellation (cancel_booking fired, confirmation_code in "
            "facts) OR declined cancellation (no tool ran, no code). "
            "No further tools — just acknowledge the outcome."
        ),
        allowed_next=(STATE_CANCELLED,),
        preferred_tools=(),
        response_hint=(
            "If confirmation_code is in facts, announce the "
            "cancellation is complete and read the code back. "
            "Otherwise — no code present — acknowledge the caller "
            "decided to KEEP their booking unchanged and ask how else "
            "you can help. Never say rebooked."
        ),
    ),
}


CANCEL_INTENT = IntentSpec(
    name="cancel",
    entry_state=STATE_START,
    terminal_states=frozenset({STATE_CANCELLED}),
    states=_STATES,
    tools=_TOOLS,
    always_available=("list_routes", "lookup_pnr", "get_flight_status"),
    tool_transitions={
        "cancel_booking": (STATE_CANCELLED, None),
    },
    prompt_examples=(
        "- Caller confirms cancellation at state=showed_terms → "
        "tool=cancel_booking(pnr, kind=cancel_kind, policy_ref="
        "cancel_policy_ref), next_state=cancelled.\n"
        "- Caller declines at state=showed_terms → no tool, move to "
        "cancelled, acknowledge the booking is kept."
    ),
    state_ranks={
        STATE_START: 0,
        STATE_SHOWED: 1,
        STATE_CANCELLED: 2,
    },
    state_slot_ownership={
        STATE_START: (
            "cancel_kind",
            "cancel_policy_ref",
            "cancel_outcome",
            "cancel_penalty",
        ),
        STATE_SHOWED: (),
        STATE_CANCELLED: ("last_confirmation_code",),
    },
    flow_scoped_entities=("confirmation_code",),
)
