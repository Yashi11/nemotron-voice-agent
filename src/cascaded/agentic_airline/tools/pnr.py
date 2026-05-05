# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""PNR and flight-status tools. Read-only, safe for the fast agent.

On each successful lookup, the canonical PNR and flight number are pinned
to the stream's :class:`EntityStore` so later tool calls and the DeepAgent
trust a single source for high-stakes entities across turns.

When a lookup resolves to a *different* PNR than the one currently
stored, the handler also resets orchestrator memory — step markers,
suggested / committed flight, route, prefs, and the prior confirmation
code — so a subsequent cancel / rebook on the new PNR doesn't inherit
state from the previous one.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from cascaded.agentic_airline.tools import _backend, booking_client

if TYPE_CHECKING:
    from pipecat.services.llm_service import FunctionCallParams

    from cascaded.agentic_airline.state.conversation_memory import ConversationMemory
    from cascaded.agentic_airline.state.entity_store import EntityStore


# Memory keys owned by the orchestrators (intent-step markers + attendant
# state).  Listed here because the fast-agent tool layer has to reset
# them when the caller switches PNRs — the orchestrators never see that
# transition.  Keep in sync with the per-intent modules under
# ``cascaded.agentic_airline.orchestrators``.
_INTENT_MEMORY_KEYS: tuple[str, ...] = (
    "rebook_step",
    "cancel_step",
    "booking_step",
    "rebook_ambiguous_count",
    "cancel_ambiguous_count",
    "route",
    "suggested_flight",
    "committed_flight",
    "rebook_alternatives",
    "alternatives_snapshot",
    "new_origin",
    "new_destination",
    "new_pnr",
    "last_confirmation_code",
    "seat_pref",
    "meal_pref",
    "passenger_name",
    "price",
    "currency",
    "booked_cabin",
    "cancel_kind",
    "cancel_policy_ref",
    "cancel_outcome",
    "cancel_penalty",
)


def _reset_for_new_pnr(entity_store: EntityStore, memory: ConversationMemory) -> None:
    """Clear intent memory + stale flight-level entities so a fresh PNR starts clean."""
    reset_intent_scratch(entity_store, memory)
    entity_store.forget("flight_number")


def reset_intent_scratch(entity_store: EntityStore, memory: ConversationMemory) -> None:
    """Clear flow scratch while keeping the currently loaded flight context intact."""
    for key in _INTENT_MEMORY_KEYS:
        memory.forget(key)
    entity_store.forget("confirmation_code")


TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_pnr",
            "description": (
                "Look up a booking by PNR (6-character record locator). "
                "Use this to retrieve passenger, flight, and fare details "
                "before any other action."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pnr": {
                        "type": "string",
                        "description": (
                            "6-character booking reference (3 letters + 3 digits), uppercase. "
                            "Use only a code the caller has actually spoken."
                        ),
                    },
                },
                "required": ["pnr"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_flight_status",
            "description": "Get current status (scheduled, delayed, cancelled) and delay minutes for a flight.",
            "parameters": {
                "type": "object",
                "properties": {
                    "flight_number": {
                        "type": "string",
                        "description": (
                            "Airline flight number (2 letters + 2-4 digits, uppercase). "
                            "Use only a value the caller has actually spoken."
                        ),
                    },
                },
                "required": ["flight_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_routes",
            "description": (
                "List scheduled routes for an airport: destinations "
                "reachable FROM an origin, or origins that fly INTO a "
                "destination. Use this when the caller asks questions "
                "like 'where can I fly from JFK?' or 'what cities fly "
                "into Seattle?'. Pass EXACTLY ONE of origin / destination."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {
                        "type": "string",
                        "description": (
                            "Origin IATA code (e.g. JFK). Use only a code the caller has actually spoken; "
                            "omit when filtering by destination."
                        ),
                    },
                    "destination": {
                        "type": "string",
                        "description": (
                            "Destination IATA code (e.g. SEA). Use only a code the caller has actually spoken; "
                            "omit when filtering by origin."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
]


def build_handlers(entity_store: EntityStore, memory: ConversationMemory) -> dict[str, Callable]:
    """Build per-stream handlers that update ``entity_store`` on every hit."""

    async def handle_lookup_pnr(params: FunctionCallParams) -> None:
        pnr = str(params.arguments.get("pnr", "")).strip().upper()
        record = await _backend.get_pnr(pnr)
        if record is None:
            await params.result_callback({"error": f"PNR {pnr!r} not found"})
            return
        # Use the canonical PNR from the record, not the caller input, so a
        # fuzzy-matched lookup (e.g. ``RABC123 → ABC123``) doesn't leak the
        # mangled ASR string into EntityStore or the tool result.
        canonical_pnr = record["pnr"]
        prior = entity_store.get("pnr")
        if prior is not None and prior.value != canonical_pnr:
            _reset_for_new_pnr(entity_store, memory)
        entity_store.put("pnr", canonical_pnr, confidence=1.0)
        entity_store.put("flight_number", record["flight_number"], confidence=1.0)
        await params.result_callback(
            {
                "pnr": canonical_pnr,
                "passenger": record["passenger"],
                "flight_number": record["flight_number"],
                "origin": record["origin"],
                "destination": record["destination"],
                "departure": record["departure"],
                "cabin": record["cabin"],
                "fare_basis": record["fare_basis"],
                "elite_tier": record["elite_tier"],
                "status": record["status"],
                "delay_minutes": record["delay_minutes"],
                "ancillaries": record["ancillaries"],
            }
        )

    async def handle_get_flight_status(params: FunctionCallParams) -> None:
        flight = str(params.arguments.get("flight_number", "")).strip().upper()
        matches = await _backend.find_by_flight(flight)
        if not matches:
            await params.result_callback({"error": f"flight {flight!r} not found"})
            return
        record = matches[0]
        entity_store.put("flight_number", flight, confidence=1.0)
        await params.result_callback(
            {
                "flight_number": flight,
                "status": record["status"],
                "delay_minutes": record["delay_minutes"],
                "scheduled_departure": record["departure"],
            }
        )

    async def handle_list_routes(params: FunctionCallParams) -> None:
        origin = str(params.arguments.get("origin", "") or "").strip().upper() or None
        destination = str(params.arguments.get("destination", "") or "").strip().upper() or None
        if (origin is None) == (destination is None):
            await params.result_callback({"error": "pass exactly one of origin or destination"})
            return
        try:
            rows = await booking_client.list_routes(origin=origin, destination=destination)
        except Exception as exc:  # noqa: BLE001 — surface error text to the model
            await params.result_callback({"error": f"list_routes failed: {exc}"})
            return
        await params.result_callback(
            {
                "origin": origin,
                "destination": destination,
                "routes": rows,
            }
        )

    return {
        "lookup_pnr": handle_lookup_pnr,
        "get_flight_status": handle_get_flight_status,
        "list_routes": handle_list_routes,
    }
