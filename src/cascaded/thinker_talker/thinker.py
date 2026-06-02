# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Thinker implementation for the independent Thinker/Talker example."""

from __future__ import annotations

import asyncio
import random
import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

from loguru import logger

from cascaded.thinker_talker.airports import (
    airport_display_name,
    iata_code,
    spoken_time,
)
from cascaded.thinker_talker.backend import BookingBackend
from cascaded.thinker_talker.planner import ThinkerPlanner
from cascaded.thinker_talker.protocol import ThinkerLifecycleEvent, response_hint, tool_result
from cascaded.thinker_talker.state import BookingDraft, ThinkerSessionState

USER_FACING_AIRLINE = "G Force Airlines"
USER_FACING_FLIGHT_PREFIX = "G Force Airline's"
INTERNAL_BACKEND_CARRIER = "Booking Server"

# Thinker tools that only read session state (or are pure). These are safe to
# run concurrently with each other and with the serialized mutating-tool chain.
# Everything else (flight_search, booking) writes shared session state and must
# be sequenced — see _dispatch_parallel_tool_calls.
_READ_ONLY_TOOLS = frozenset({"pnr_status", "response_hint"})


class ThinkerBackend:
    """Pluggable Thinker boundary behind Talker's ``call_thinker`` tool.

    Talker provides a detailed natural-language query with conversation context.
    The Thinker planner LLM owns intent detection and parameter extraction from
    that query plus session state. This class validates the plan and executes
    the internal Python tools/backends.
    """

    def __init__(
        self,
        *,
        state: ThinkerSessionState | None = None,
        backend: BookingBackend | None = None,
        planner: ThinkerPlanner | None = None,
        today_provider: Any | None = None,
        tool_delay_seconds: float = 0.0,
        tool_delay_min_seconds: float | None = None,
    ) -> None:
        """Create a Thinker backend for one voice session."""
        if planner is None:
            raise ValueError("ThinkerBackend requires a ThinkerPlanner")
        if backend is None:
            raise ValueError("ThinkerBackend requires a BookingBackend")
        self.state = state or ThinkerSessionState()
        self._today_provider = today_provider or date.today
        self._backend = backend
        self._planner = planner
        self._tool_delay_seconds = tool_delay_seconds
        self._tool_delay_min_seconds = tool_delay_min_seconds

    async def call(
        self,
        query: str,
        slots: dict[str, Any] | None = None,
        *,
        on_started: Callable[[ThinkerLifecycleEvent], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """Run one Thinker invocation and return a speakable protocol payload."""
        clean_query = query.strip()
        clean_slots = dict(slots or {})
        call_id = uuid.uuid4().hex[:12]
        if self.state.active_task and not self.state.active_task.done():
            self.cancel_active("new_thinker_call")
        self.state.active_call_id = call_id
        started_event = ThinkerLifecycleEvent(marker="ThinkerStarted", call_id=call_id, query=clean_query)
        self.state.add_event(started_event)
        if on_started:
            await on_started(started_event)
        task = asyncio.create_task(self._run_call(call_id, clean_query, clean_slots))
        self.state.active_task = task
        try:
            payload = await task
        except asyncio.CancelledError:
            self.state.add_event(
                ThinkerLifecycleEvent(
                    marker="ThinkerAborted",
                    call_id=call_id,
                    query=clean_query,
                    reason="new_user_query",
                )
            )
            raise
        finally:
            if self.state.active_task is task:
                self.state.active_task = None
                self.state.active_call_id = None
        return payload

    def cancel_active(self, reason: str = "new_user_query") -> bool:
        """Abort the active Thinker task if one is running."""
        task = self.state.active_task
        if task is None or task.done():
            return False
        logger.info(f"Thinker call {self.state.active_call_id or '(unknown)'} aborted: {reason}")
        task.cancel()
        return True

    def cancel_pending_booking(self) -> bool:
        """Clear a pending booking draft or confirmation if one exists."""
        has_pending_booking = (
            self.state.booking_draft is not None
            or self.state.waiting_for_preferences
            or self.state.waiting_for_confirmation
        )
        if has_pending_booking:
            self.state.reset_booking()
        return has_pending_booking

    async def _run_call(self, call_id: str, query: str, slots: dict[str, Any]) -> dict[str, Any]:
        """Dispatch the query to internal Thinker tools."""
        delay_seconds = self._next_tool_delay_seconds()
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

        payload = await self._dispatch(query, slots)
        self.state.add_event(
            ThinkerLifecycleEvent(marker="IntermediateResponse", call_id=call_id, query=query, payload=payload)
        )
        self.state.add_event(
            ThinkerLifecycleEvent(marker="ThinkerCompleted", call_id=call_id, query=query, payload=payload)
        )
        return payload

    def _next_tool_delay_seconds(self) -> float:
        """Return the synthetic tool delay for this call."""
        max_delay = max(0.0, self._tool_delay_seconds)
        if max_delay <= 0:
            return 0.0
        if self._tool_delay_min_seconds is None:
            return max_delay
        min_delay = max(0.0, min(self._tool_delay_min_seconds, max_delay))
        return random.uniform(min_delay, max_delay)

    async def _dispatch(self, query: str, slots: dict[str, Any]) -> dict[str, Any]:
        try:
            plan = await self._planner.plan(query=query, slots=slots, state=self._planner_state())
        except Exception as exc:
            logger.warning(f"Thinker planner failed: {exc}")
            return response_hint(
                reason="planner_error",
                action="retry",
                response_text="I could not plan that request. Could you say it again?",
                context="general",
                error=str(exc),
            )

        tool_calls = _plan_tool_calls(plan)
        if len(tool_calls) > 1:
            return await self._dispatch_parallel_tool_calls(query, slots, plan, tool_calls)
        if not tool_calls:
            return response_hint(
                reason="unsupported_request",
                action="answer_directly",
                response_text="I can help search flights, book a selected flight, or check a PNR status.",
                context="general",
            )
        return await self._dispatch_tool_call(query, slots, tool_calls[0])

    async def _dispatch_parallel_tool_calls(
        self,
        query: str,
        slots: dict[str, Any],
        plan: dict[str, Any],
        tool_calls: list[dict[str, Any]],
    ) -> dict[str, Any]:
        # State-mutating tools (flight_search, booking) write shared session
        # state (search_results / search_context / booking_draft). Running them
        # in a bare asyncio.gather() would interleave those writes
        # (last-writer-wins), so we serialize the mutating tools in planner order
        # while still running read-only tools concurrently with that chain. The
        # result list stays in planner order so _combine_parallel_payloads is
        # unaffected.
        payloads: list[dict[str, Any] | None] = [None] * len(tool_calls)

        async def run_one(index: int, tool_call: dict[str, Any]) -> None:
            payloads[index] = await self._dispatch_tool_call(query, slots, tool_call)

        async def run_mutating_chain(items: list[tuple[int, dict[str, Any]]]) -> None:
            for index, tool_call in items:
                await run_one(index, tool_call)

        mutating: list[tuple[int, dict[str, Any]]] = []
        coros: list[Awaitable[None]] = []
        for index, tool_call in enumerate(tool_calls):
            tool_name = str(tool_call.get("tool", "") or "").strip()
            if tool_name in _READ_ONLY_TOOLS:
                coros.append(run_one(index, tool_call))
            else:
                mutating.append((index, tool_call))
        if mutating:
            coros.append(run_mutating_chain(mutating))

        await asyncio.gather(*coros)
        return _combine_parallel_payloads(plan, [payload for payload in payloads if payload is not None])

    async def _dispatch_tool_call(self, query: str, slots: dict[str, Any], tool_call: dict[str, Any]) -> dict[str, Any]:
        tool_name = str(tool_call.get("tool", "") or "").strip()
        planned_params = tool_call.get("params") if isinstance(tool_call.get("params"), dict) else {}
        planned_slots = {**slots, **planned_params}
        if tool_name == "booking":
            return await self._continue_booking(planned_slots)
        if tool_name == "pnr_status":
            return await self._pnr_status(planned_slots)
        if tool_name == "flight_search":
            return await self._flight_search(query, planned_slots)
        if tool_name == "response_hint":
            return self._planner_response_hint(tool_call)
        return response_hint(
            reason="unsupported_request",
            action="answer_directly",
            response_text="I can help search flights, book a selected flight, or check a PNR status.",
            context="general",
        )

    def _planner_state(self) -> dict[str, Any]:
        draft = self.state.booking_draft
        return {
            "search_context": self.state.search_context,
            "search_results": self.state.search_results,
            "booking_draft": {
                "flight": draft.flight,
                "seat_pref": draft.seat_pref,
                "meal_pref": draft.meal_pref,
                "passenger_name": draft.passenger_name,
            }
            if draft
            else None,
            "waiting_for_preferences": self.state.waiting_for_preferences,
            "waiting_for_confirmation": self.state.waiting_for_confirmation,
        }

    def _planner_response_hint(self, plan: dict[str, Any]) -> dict[str, Any]:
        return response_hint(
            reason=str(plan.get("reason") or "params_missing"),
            action=str(plan.get("action") or "req_params"),
            response_text=str(plan.get("response_text") or "Could you share the missing details?"),
            context=str(plan.get("context") or "general"),
            params_needed=_string_list(plan.get("params_needed")),
            params_resolved=plan.get("params_resolved") if isinstance(plan.get("params_resolved"), dict) else None,
            error=str(plan.get("error")) if plan.get("error") is not None else None,
        )

    async def _flight_search(self, query: str, slots: dict[str, Any]) -> dict[str, Any]:
        origin, destination = _extract_route(query, slots)
        travel_date = _slot(slots, "date")
        sorting = _slot(slots, "sorting")
        params_resolved: dict[str, Any] = {}
        params_needed: list[str] = []
        if origin:
            params_resolved["origin_city"] = airport_display_name(origin)
        else:
            params_needed.append("origin_city")
        if destination:
            params_resolved["dest_city"] = airport_display_name(destination)
        else:
            params_needed.append("dest_city")
        if travel_date:
            params_resolved["date"] = travel_date
        else:
            params_needed.append("date")

        if params_needed:
            return response_hint(
                reason="params_missing",
                action="req_params",
                params_needed=params_needed,
                params_resolved=params_resolved,
                response_text="Where are you flying from, where to, and when?",
                context="flight_search",
            )

        try:
            flights = await self._backend.search_flights(
                origin=origin,
                destination=destination,
                travel_date=travel_date,
                sorting=sorting,
            )
        except Exception as exc:
            logger.warning(f"flight_search backend failed: {exc}")
            flights = []
        if not flights:
            self.state.reset_search_and_booking()
            return response_hint(
                reason="tool_error",
                action="req_params",
                params_needed=["origin_city", "dest_city", "date"],
                params_resolved=params_resolved,
                error="No flights found for the requested route.",
                response_text="I could not find flights for that route. Would you like to try different cities?",
                context="flight_search",
            )

        self.state.search_context = {
            "origin_city": airport_display_name(origin),
            "dest_city": airport_display_name(destination),
            "origin_airport": origin,
            "dest_airport": destination,
            "date": travel_date,
            "sorting": sorting or "price",
        }
        self.state.search_results = flights
        self.state.reset_booking()
        options = ", ".join(_format_flight_option(flight) for flight in flights[:5])
        response_text = f"I found {len(flights)} flights: {options}. Which flight would you like to book?"
        return tool_result(
            tool="flight_search",
            status="success",
            data={
                "flights": [_user_facing_flight(flight) for flight in flights],
                "search_context": self.state.search_context,
            },
            response_text=response_text,
            context="flight_search",
        )

    async def _continue_booking(self, slots: dict[str, Any]) -> dict[str, Any]:
        if not self.state.search_results:
            return response_hint(
                reason="missing_search_context",
                action="req_flight_search",
                params_needed=["origin_city", "dest_city", "date"],
                response_text="I need to search flights before booking. Where are you flying from, where to, and when?",
                context="booking",
            )

        selected_value = _slot(slots, "flight_selected")
        selected = _extract_selected_flight(selected_value, self.state.search_results)
        if selected_value is not None and selected is None:
            if self.state.booking_draft is not None:
                self.state.booking_draft = None
                self.state.waiting_for_preferences = False
                self.state.waiting_for_confirmation = False
            return response_hint(
                reason="params_missing",
                action="req_params",
                params_needed=["flight_selected"],
                response_text=(
                    "I could not match that flight selection. "
                    "Which flight from the search results would you like to book?"
                ),
                context="booking",
            )

        if selected is not None and self.state.booking_draft is not None:
            draft = self.state.booking_draft
            if _flight_identity(selected) != _flight_identity(draft.flight):
                draft.flight = selected
                self._merge_preferences(slots)
                self.state.waiting_for_preferences = False
                self.state.waiting_for_confirmation = True
                return self._confirmation_hint()

        if self.state.waiting_for_confirmation:
            self._merge_preferences(slots)
            confirmed = _bool_slot(slots, "confirmed")
            if confirmed is True:
                return await self._finalize_booking()
            if confirmed is False:
                self.state.reset_booking()
                return response_hint(
                    reason="booking_cancelled",
                    action="cancelled",
                    response_text="No problem, I have not booked it.",
                    context="booking",
                )
            return response_hint(
                reason="confirm_required",
                action="confirm_booking",
                response_text="Should I confirm this booking?",
                context="booking",
            )

        if self.state.booking_draft is None:
            if selected is None:
                return response_hint(
                    reason="params_missing",
                    action="req_params",
                    params_needed=["flight_selected"],
                    response_text="Which flight from the search results would you like to book?",
                    context="booking",
                )
            passenger_name = _slot(slots, "passenger_name")
            self.state.booking_draft = BookingDraft(flight=selected, passenger_name=passenger_name)

        self._merge_preferences(slots)
        use_defaults = _bool_slot(slots, "use_defaults") is True
        has_preferences = _slot(slots, "seat_pref") is not None or _slot(slots, "meal_pref") is not None
        if self.state.waiting_for_preferences or use_defaults or has_preferences:
            self.state.waiting_for_preferences = False
            self.state.waiting_for_confirmation = True
            return self._confirmation_hint()

        self.state.waiting_for_preferences = True
        return response_hint(
            reason="params_optional",
            action="req_params",
            params_needed=["seat_pref", "meal_pref"],
            defaults_available=True,
            response_text="Do you have a seat or meal preference? Otherwise I will use the defaults.",
            context="booking",
        )

    def _confirmation_hint(self) -> dict[str, Any]:
        draft = self.state.booking_draft
        if draft is None:
            raise RuntimeError("booking draft missing while building confirmation")
        flight = draft.flight
        seat = draft.seat_pref or "default seat"
        meal = draft.meal_pref or "default meal"
        price = flight.get("price_usd")
        price_text = f", for ${price}" if price is not None else ""
        summary = {
            "route": f"{flight['origin_city']} to {flight['dest_city']}",
            "date": flight["date"],
            "flight_id": flight["flight_id"],
            "carrier": _user_facing_carrier(flight),
            "seat_pref": draft.seat_pref,
            "meal_pref": draft.meal_pref,
            "price_usd": price,
        }
        return response_hint(
            reason="confirm_required",
            action="confirm_booking",
            summary=summary,
            response_text=(
                f"Here is the booking summary: {_flight_label(flight)} from "
                f"{flight['origin_city']} to {flight['dest_city']} on {flight['date']}, "
                f"{seat}, {meal}{price_text}. Shall I confirm?"
            ),
            context="booking",
        )

    async def _finalize_booking(self) -> dict[str, Any]:
        draft = self.state.booking_draft
        if draft is None:
            return response_hint(
                reason="params_missing",
                action="req_params",
                params_needed=["flight_selected"],
                response_text="Which flight should I book?",
                context="booking",
            )
        record = await self._backend.create_booking(
            passenger_name=draft.passenger_name,
            flight=draft.flight,
            seat_pref=draft.seat_pref,
            meal_pref=draft.meal_pref,
        )
        if record is None:
            return response_hint(
                reason="tool_error",
                action="req_params",
                params_needed=["flight_selected"],
                error="Booking backend could not create the PNR.",
                response_text="I could not complete that booking. Please choose another flight.",
                context="booking",
            )
        self.state.reset_booking()
        return tool_result(
            tool="booking",
            status="success",
            data={"booking": _user_facing_record(record), "pnr": record.get("pnr")},
            response_text=f"Your booking is confirmed. Your PNR is {record.get('pnr')}.",
            context="booking",
        )

    def _merge_preferences(self, slots: dict[str, Any]) -> None:
        draft = self.state.booking_draft
        if draft is None:
            return
        seat = _slot(slots, "seat_pref")
        meal = _slot(slots, "meal_pref")
        passenger = _slot(slots, "passenger_name")
        if seat:
            draft.seat_pref = seat
        if meal:
            draft.meal_pref = meal
        if passenger:
            draft.passenger_name = passenger

    async def _pnr_status(self, slots: dict[str, Any]) -> dict[str, Any]:
        pnr = _slot(slots, "pnr_code")
        if pnr is None:
            return response_hint(
                reason="params_missing",
                action="req_params",
                params_needed=["pnr_code"],
                response_text="Sure, could you tell me your PNR number?",
                context="pnr_status",
            )
        pnr = _canonical_pnr(pnr)
        record = await self._backend.get_pnr(pnr)
        if record is None:
            return response_hint(
                reason="tool_error",
                action="req_params",
                params_needed=["pnr_code"],
                error=f"PNR {pnr.upper()} was not found.",
                response_text=f"I could not find PNR {pnr.upper()}. Could you check the code?",
                context="pnr_status",
            )
        return tool_result(
            tool="pnr_status",
            status="success",
            data={"booking": _user_facing_record(record)},
            response_text=(
                f"PNR {record['pnr']} is {record['status']} for {record['origin_city']} to "
                f"{record['dest_city']} on {record['date']}."
            ),
            context="pnr_status",
        )


def _canonical_pnr(value: str) -> str:
    """Return canonical alphanumeric PNR text as planned by the Thinker LLM."""
    compact = "".join(ch for ch in value.upper() if ch.isalnum())
    return compact or value.strip().upper()


def _format_flight_option(flight: dict[str, Any]) -> str:
    price = flight.get("price_usd")
    price_text = f" at ${price}" if price is not None else ""
    departure = spoken_time(str(flight.get("departure_time") or ""))
    return f"{_flight_label(flight)} at {departure}{price_text}"


def _flight_label(flight: dict[str, Any]) -> str:
    return f"{_user_facing_carrier(flight)} {flight['flight_id']}"


def _user_facing_carrier(flight: dict[str, Any]) -> str:
    carrier = str(flight.get("carrier") or "").strip()
    if not carrier or carrier == INTERNAL_BACKEND_CARRIER:
        return USER_FACING_FLIGHT_PREFIX
    return carrier


def _user_facing_flight(flight: dict[str, Any]) -> dict[str, Any]:
    display = dict(flight)
    display["carrier"] = _user_facing_carrier(flight)
    display["airline_brand"] = USER_FACING_AIRLINE
    return display


def _user_facing_record(record: dict[str, Any]) -> dict[str, Any]:
    display = dict(record)
    display["carrier"] = _user_facing_carrier(record)
    display["airline_brand"] = USER_FACING_AIRLINE
    return display


def _flight_identity(flight: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(flight.get("flight_id") or ""),
        str(flight.get("origin_airport") or ""),
        str(flight.get("dest_airport") or ""),
        str(flight.get("departure_time") or ""),
    )


def _slot(slots: dict[str, Any], key: str) -> str | None:
    value = slots.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value).lower()
    text = str(value).strip()
    return text or None


def _bool_slot(slots: dict[str, Any], key: str) -> bool | None:
    value = slots.get(key)
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "yes", "confirm", "confirmed"}:
        return True
    if text in {"false", "no", "cancel", "cancelled"}:
        return False
    return None


def _extract_route(query: str, slots: dict[str, Any]) -> tuple[str | None, str | None]:
    origin = _slot_airport(slots, "origin_city") or _slot_airport(slots, "origin_airport")
    destination = _slot_airport(slots, "dest_city") or _slot_airport(slots, "dest_airport")
    return origin, destination


def _slot_airport(slots: dict[str, Any], key: str) -> str | None:
    value = _slot(slots, key)
    return iata_code(value) if value else None


def _plan_tool_calls(plan: dict[str, Any]) -> list[dict[str, Any]]:
    base_params = plan.get("params") if isinstance(plan.get("params"), dict) else {}
    raw_calls = plan.get("tool_calls")
    if raw_calls is None:
        raw_calls = plan.get("tools")
    if isinstance(raw_calls, list):
        tool_calls: list[dict[str, Any]] = []
        for raw_call in raw_calls:
            if isinstance(raw_call, str):
                tool_calls.append({"tool": raw_call, "params": dict(base_params)})
                continue
            if not isinstance(raw_call, dict):
                continue
            call = dict(raw_call)
            call_params = call.get("params") if isinstance(call.get("params"), dict) else {}
            call["params"] = {**base_params, **call_params}
            tool_calls.append(call)
        return tool_calls
    if plan.get("tool"):
        return [plan]
    return []


def _combine_parallel_payloads(plan: dict[str, Any], payloads: list[dict[str, Any]]) -> dict[str, Any]:
    response_text = str(plan.get("response_text") or "").strip()
    if not response_text:
        response_text = " ".join(str(payload.get("response_text") or "").strip() for payload in payloads).strip()
    response_text = response_text or "I finished checking those items."
    contexts = [str(payload.get("context") or "") for payload in payloads if payload.get("context")]
    context = "multi_tool" if len(set(contexts)) != 1 else contexts[0]
    data = {"results": payloads}
    if any(payload.get("type") == "response_hint" for payload in payloads):
        return response_hint(
            reason="multi_tool_followup",
            action="review_results",
            response_text=response_text,
            context=context,
            data=data,
        )
    status = "success" if all(payload.get("status") == "success" for payload in payloads) else "partial"
    return tool_result(
        tool="multi_tool",
        status=status,
        data=data,
        response_text=response_text,
        context=context,
    )


def _string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    result = [str(item).strip() for item in value if str(item).strip()]
    return result or None


def _extract_selected_flight(selection: str | None, search_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if selection is None:
        return None
    lowered = selection.lower()
    ordinal = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
    if lowered in ordinal and ordinal[lowered] <= len(search_results):
        return search_results[ordinal[lowered] - 1]
    if lowered.isdigit():
        index = int(lowered) - 1
        if 0 <= index < len(search_results):
            return search_results[index]
    for flight in search_results:
        if str(flight["flight_id"]).lower() == lowered:
            return flight
    return None
