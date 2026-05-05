# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Thin async shim over :mod:`cascaded.agentic_airline.tools.booking_client`.

Historical callers imported ``_backend.get_pnr`` / ``_backend.commit_rebook_record``
from the in-memory mock.  Those calls now forward over HTTP to the
booking server.  Signatures stayed wherever the HTTP client matched
(``get_pnr`` / ``find_by_flight``); two were renamed / adapted:

- ``get_alternatives(origin, destination)``     → ``list_alternatives``
- ``ancillaries_diff(pnr, _unused_record, new_flight)`` → drops the
  ``record`` arg (the server re-fetches its own), accepted positionally
  for backwards source-compat.

``commit_rebook_record`` now returns the full mutation payload including
``confirmation_code`` — callers use that instead of a separate
deterministic code helper.  The old ``confirmation_code`` function was
deleted along with the code-is-deterministic assumption.
"""

from __future__ import annotations

from cascaded.agentic_airline.tools import booking_client


async def get_pnr(pnr: str) -> dict | None:
    return await booking_client.get_pnr(pnr)


async def find_by_flight(flight_number: str) -> list[dict]:
    return await booking_client.find_by_flight(flight_number)


async def get_flight_status(flight_number: str) -> dict | None:
    return await booking_client.get_flight_status(flight_number)


async def get_alternatives(origin: str, destination: str) -> list[dict]:
    return await booking_client.list_alternatives(origin, destination)


async def ancillaries_diff(pnr: str, _record_unused, new_flight_number: str) -> dict | None:
    """Preview seat/bag/meal carry-over.  ``_record_unused`` kept for source-compat."""
    return await booking_client.ancillaries_diff(pnr, new_flight_number)


async def commit_rebook_record(pnr: str, new_flight_number: str) -> dict | None:
    """Swap ``pnr``'s flight. Returns the full mutation payload.

    Shape: ``{booking, confirmation_code, from_flight, to_flight}``.
    Callers must read ``confirmation_code`` from the response instead
    of pre-computing one — the server mints it.
    """
    return await booking_client.commit_rebook(pnr, new_flight_number)
