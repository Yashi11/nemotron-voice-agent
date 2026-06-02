# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Booking backend clients for the independent Thinker/Talker example."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any, Protocol

import httpx

from cascaded.thinker_talker.airports import airport_display_name


class BookingBackend(Protocol):
    """Backend interface used by the Thinker internal tools."""

    async def search_flights(
        self,
        *,
        origin: str,
        destination: str,
        travel_date: str,
        sorting: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return matching flight options."""

    async def create_booking(
        self,
        *,
        passenger_name: str | None,
        flight: dict[str, Any],
        seat_pref: str | None = None,
        meal_pref: str | None = None,
    ) -> dict[str, Any] | None:
        """Create a booking for ``flight``."""

    async def get_pnr(self, pnr_code: str) -> dict[str, Any] | None:
        """Return a booking record by PNR."""


class HTTPBookingBackend:
    """HTTP client for the shared booking-server sidecar."""

    def __init__(self, base_url: str, *, timeout: float = 10.0) -> None:
        """Create a backend client for ``base_url``."""
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def search_flights(
        self,
        *,
        origin: str,
        destination: str,
        travel_date: str,
        sorting: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return flights from the booking server."""
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            response = await client.get(
                "/flights",
                params={"origin": origin, "destination": destination, "date": travel_date},
            )
        response.raise_for_status()
        rows = response.json()
        flights = [_server_flight_to_option(row, fallback_date=travel_date) for row in rows if isinstance(row, dict)]
        return _sort_flights(_unique_flights(flights), sorting)[:5]

    async def create_booking(
        self,
        *,
        passenger_name: str | None,
        flight: dict[str, Any],
        seat_pref: str | None = None,
        meal_pref: str | None = None,
    ) -> dict[str, Any] | None:
        """Create a PNR through the booking server."""
        payload = {
            "passenger": passenger_name or "Guest",
            "origin": flight["origin_airport"],
            "destination": flight["dest_airport"],
            "flight_number": flight["flight_id"],
            "departure": flight.get("departure_time"),
            "seat": seat_pref,
            "meal": meal_pref,
        }
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            response = await client.post("/pnrs", json={key: value for key, value in payload.items() if value})
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return _server_booking_to_record(
            response.json(),
            flight=flight,
            passenger_name=passenger_name,
            seat_pref=seat_pref,
            meal_pref=meal_pref,
        )

    async def get_pnr(self, pnr_code: str) -> dict[str, Any] | None:
        """Look up PNR status through the booking server."""
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            response = await client.get(f"/pnrs/{pnr_code.strip().upper()}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return _server_pnr_to_record(response.json())


def _server_flight_to_option(row: dict[str, Any], *, fallback_date: str) -> dict[str, Any]:
    departure, arrival = _materialize_timestamps(
        str(row.get("departure") or ""),
        str(row.get("arrival") or ""),
        fallback_date,
    )
    origin = str(row.get("origin") or "").upper()
    destination = str(row.get("destination") or "").upper()
    return {
        "flight_id": str(row.get("flight_number") or "").upper(),
        "carrier": "Booking Server",
        "origin_city": airport_display_name(origin),
        "dest_city": airport_display_name(destination),
        "origin_airport": origin,
        "dest_airport": destination,
        "date": departure[:10] or fallback_date,
        "departure_time": departure,
        "arrival_time": arrival,
        "duration_minutes": 0,
        "price_usd": None,
        "cabin": row.get("cabin"),
    }


def _materialize_timestamps(departure: str, arrival: str, travel_date: str) -> tuple[str, str]:
    """Move seed timestamps onto ``travel_date`` while preserving duration."""
    if not departure or "T" not in departure:
        return departure, arrival
    try:
        departure_dt = datetime.fromisoformat(departure)
        arrival_dt = datetime.fromisoformat(arrival or departure)
        target_date = date.fromisoformat(travel_date)
        materialized_departure = departure_dt.replace(
            year=target_date.year,
            month=target_date.month,
            day=target_date.day,
        )
        duration = arrival_dt - departure_dt
        if duration.total_seconds() < 0:
            duration += timedelta(days=1)
        return materialized_departure.isoformat(), (materialized_departure + duration).isoformat()
    except ValueError:
        materialized_departure = f"{travel_date}{departure[10:]}"
        materialized_arrival = f"{travel_date}{arrival[10:]}" if arrival and "T" in arrival else arrival
        return materialized_departure, materialized_arrival


def _unique_flights(flights: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeated daily seed rows into one option per flight/time."""
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for flight in flights:
        key = (
            str(flight.get("flight_id") or ""),
            str(flight.get("origin_airport") or ""),
            str(flight.get("dest_airport") or ""),
            str(flight.get("departure_time") or "")[11:],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(flight)
    return unique


def _server_booking_to_record(
    data: dict[str, Any],
    *,
    flight: dict[str, Any],
    passenger_name: str | None = None,
    seat_pref: str | None,
    meal_pref: str | None,
) -> dict[str, Any]:
    pnr = str(data.get("pnr") or "").upper()
    response_passenger = str(data.get("passenger") or "").strip()
    provided_passenger = str(passenger_name or "").strip()
    return {
        "pnr": pnr,
        "confirmation_code": data.get("confirmation_code"),
        "passenger_name": response_passenger or provided_passenger or "Guest",
        "status": "confirmed",
        "flight_id": str(data.get("flight_number") or flight["flight_id"]).upper(),
        "carrier": flight.get("carrier", ""),
        "origin_city": flight["origin_city"],
        "dest_city": flight["dest_city"],
        "date": str(data.get("departure") or flight["departure_time"])[:10],
        "departure_time": data.get("departure") or flight["departure_time"],
        "seat_pref": seat_pref,
        "meal_pref": meal_pref,
        "price_usd": data.get("price") or flight.get("price_usd"),
        "currency": data.get("currency", "USD"),
    }


def _server_pnr_to_record(data: dict[str, Any]) -> dict[str, Any]:
    origin = str(data.get("origin") or "").upper()
    destination = str(data.get("destination") or "").upper()
    ancillaries = data.get("ancillaries") if isinstance(data.get("ancillaries"), dict) else {}
    return {
        "pnr": str(data.get("pnr") or "").upper(),
        "passenger_name": data.get("passenger") or "Guest",
        "status": data.get("booking_status") or data.get("status") or "unknown",
        "flight_id": str(data.get("flight_number") or "").upper(),
        "carrier": "Booking Server",
        "origin_city": airport_display_name(origin),
        "dest_city": airport_display_name(destination),
        "date": str(data.get("departure") or "")[:10],
        "departure_time": data.get("departure"),
        "seat_pref": ancillaries.get("seat"),
        "meal_pref": ancillaries.get("meal"),
    }


def _sort_flights(flights: Sequence[dict[str, Any]], sorting: str | None) -> list[dict[str, Any]]:
    if sorting == "departure_time":
        return sorted(flights, key=lambda item: str(item.get("departure_time") or ""))
    if sorting == "duration":
        return sorted(flights, key=lambda item: int(item.get("duration_minutes") or 0))
    return sorted(flights, key=lambda item: int(item.get("price_usd") or 0))
