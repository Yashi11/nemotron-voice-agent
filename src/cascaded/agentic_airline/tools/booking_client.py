# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Async HTTP facade over the booking server.

Mirrors :class:`cascaded.agentic_airline.booking_server.api.BookingAPI` 1:1 so the orchestrators
and fast-agent tool handlers can swap from the in-memory backend to
the networked service with only an ``await``.  Swapping HTTP for MCP
later becomes a transport change inside this module; callers stay put.

All methods return plain dicts / lists.  ``Optional`` returns map
``404`` to ``None``; everything else ``raise_for_status()``es so
programmer errors (malformed body, server bug) surface loudly.

Base URL resolution follows the same dual-mode pattern as the service
catalog rewriter in :mod:`utils`:

* The active service catalog entry wins when present.
* ``APP_RUNTIME=container`` (set by docker-compose) falls back to the in-network
  hostname ``http://booking-server:8001``.
* Otherwise (host / uv direct runs) falls back to ``http://localhost:8001``.

One shared :class:`httpx.AsyncClient` per stream for connection pooling.
"""

from __future__ import annotations

import os

import httpx
from loguru import logger

from utils import load_service_entry

_HOST_DEFAULT_BASE_URL = "http://localhost:8001"
_CONTAINER_DEFAULT_BASE_URL = "http://booking-server:8001"
_DEFAULT_TIMEOUT = 10.0

_client: httpx.AsyncClient | None = None


def _default_base_url() -> str:
    """Pick the default booking-server URL based on ``APP_RUNTIME``."""
    if os.environ.get("APP_RUNTIME", "").strip().lower() == "container":
        return _CONTAINER_DEFAULT_BASE_URL
    return _HOST_DEFAULT_BASE_URL


def _get_client() -> httpx.AsyncClient:
    """Lazily construct the shared async client. Reused across streams."""
    global _client
    if _client is None:
        booking_server = load_service_entry("booking-server", "")
        base_url = booking_server.get("server") or _default_base_url()
        _client = httpx.AsyncClient(base_url=base_url, timeout=_DEFAULT_TIMEOUT)
        logger.info(f"booking_client connected to {base_url}")
    return _client


async def close() -> None:
    """Close the shared client. Call at process shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ----------------------------------------------------------------------
# Reads
# ----------------------------------------------------------------------


async def get_pnr(pnr: str) -> dict | None:
    """Look up a booking by PNR. ``None`` when the PNR is unknown."""
    resp = await _get_client().get(f"/pnrs/{pnr}")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


async def find_by_flight(flight_number: str) -> list[dict]:
    """Return all booking dicts whose current flight matches ``flight_number``."""
    resp = await _get_client().get(f"/flights/{flight_number}/pnrs")
    resp.raise_for_status()
    return resp.json()


async def get_flight_status(flight_number: str) -> dict | None:
    """Return live flight status, or ``None`` when the designator isn't scheduled."""
    resp = await _get_client().get(f"/flights/{flight_number}/status")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


async def list_alternatives(origin: str, destination: str) -> list[dict]:
    """Return candidate replacement flights on the given route."""
    resp = await _get_client().get(
        "/flights",
        params={"origin": origin, "destination": destination},
    )
    resp.raise_for_status()
    return resp.json()


async def list_routes(
    *,
    origin: str | None = None,
    destination: str | None = None,
) -> list[dict]:
    """Return scheduled routes from an origin or into a destination.

    Exactly one of ``origin`` / ``destination`` must be supplied; each
    returned row is ``{"code": <IATA>, "flight_count": <int>}``.
    """
    params: dict[str, str] = {}
    if origin is not None:
        params["origin"] = origin
    if destination is not None:
        params["destination"] = destination
    resp = await _get_client().get("/routes", params=params)
    resp.raise_for_status()
    return resp.json()


async def ancillaries_diff(pnr: str, new_flight_number: str) -> dict | None:
    """Preview seat / bag / meal carry-over for a proposed rebook."""
    resp = await _get_client().get(
        f"/pnrs/{pnr}/ancillaries-diff",
        params={"new_flight_number": new_flight_number},
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


async def get_activity(pnr: str) -> list[dict]:
    """Return the full activity log for ``pnr``, oldest to newest."""
    resp = await _get_client().get(f"/pnrs/{pnr}/activity")
    resp.raise_for_status()
    return resp.json()


# ----------------------------------------------------------------------
# Mutations
# ----------------------------------------------------------------------


def _session_headers(session_id: str | None) -> dict[str, str]:
    """Stamp the pipeline ``stream_id`` on the request so the server logs it."""
    return {"X-Session-Id": session_id} if session_id else {}


async def price_quote(origin: str, destination: str, cabin: str = "economy") -> dict | None:
    """Fetch a fare estimate for a prospective booking without writing to the DB."""
    resp = await _get_client().get(
        "/price",
        params={"origin": origin, "destination": destination, "cabin": cabin},
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


async def create_booking(
    passenger: str,
    origin: str,
    destination: str,
    flight_number: str,
    seat: str | None = None,
    meal: str | None = None,
    cabin: str | None = None,
    session_id: str | None = None,
) -> dict | None:
    """Mint a brand-new PNR on ``flight_number`` for ``passenger``.

    Server returns 404 when the flight isn't scheduled on that route —
    surface as ``None`` so the runner's empty-result path kicks in.
    """
    payload: dict[str, str] = {
        "passenger": passenger,
        "origin": origin,
        "destination": destination,
        "flight_number": flight_number,
    }
    if seat is not None:
        payload["seat"] = seat
    if meal is not None:
        payload["meal"] = meal
    if cabin is not None:
        payload["cabin"] = cabin
    resp = await _get_client().post(
        "/pnrs",
        json=payload,
        headers=_session_headers(session_id),
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


async def commit_rebook(
    pnr: str,
    new_flight_number: str,
    session_id: str | None = None,
    seat: str | None = None,
    meal: str | None = None,
    departure: str | None = None,
) -> dict | None:
    """Swap ``pnr``'s flight to ``new_flight_number`` and mint a confirmation code.

    ``departure`` (ISO 8601) disambiguates the target flight row when the
    flight number recurs across dates; passing it locks the rebook to the
    exact (flight_number, departure) the caller selected.

    Optional ``seat`` / ``meal`` let the rebook commit persist caller-
    stated preferences into the ancillaries row in the same transaction.
    'keep' / the existing value is a no-op on the backend side.
    """
    payload: dict[str, str] = {"new_flight_number": new_flight_number}
    if departure is not None:
        payload["departure"] = departure
    if seat is not None:
        payload["seat"] = seat
    if meal is not None:
        payload["meal"] = meal
    resp = await _get_client().post(
        f"/pnrs/{pnr}/rebook",
        json=payload,
        headers=_session_headers(session_id),
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


async def cancel_booking(
    pnr: str,
    kind: str,
    policy_ref: str,
    session_id: str | None = None,
) -> dict | None:
    """Mark ``pnr`` as cancelled and log the outcome."""
    resp = await _get_client().post(
        f"/pnrs/{pnr}/cancel",
        json={"kind": kind, "policy_ref": policy_ref},
        headers=_session_headers(session_id),
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


async def list_standby(
    pnr: str,
    flight_number: str,
    session_id: str | None = None,
    departure: str | None = None,
) -> dict | None:
    """Queue ``pnr`` for standby on ``flight_number``."""
    payload: dict[str, str] = {"flight_number": flight_number}
    if departure is not None:
        payload["departure"] = departure
    resp = await _get_client().post(
        f"/pnrs/{pnr}/standby",
        json=payload,
        headers=_session_headers(session_id),
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()
