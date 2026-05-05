# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Seed data for a fresh booking database.

Mirrors the prior in-memory fixtures (``tools/_backend._PNRS`` /
``_ALTERNATIVES``) and the IRROPS policy table from ``policy/irrops.py``.
Idempotent only in the sense that ``db.init_db`` calls this at most
once per database lifecycle (gated on empty ``pnrs``); the individual
INSERTs themselves rely on UNIQUE constraints and will raise on repeat.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# Alternative routes — each entry is (origin, destination, flight_number,
# departure, arrival, cabin).  Loaded into ``flights`` verbatim with
# status='scheduled' and delay=0.
_ALTERNATIVES: list[tuple[str, str, str, str, str, str]] = [
    ("JFK", "LAX", "AA124", "2026-05-01T10:00:00", "2026-05-01T13:30:00", "economy"),
    ("JFK", "LAX", "AA126", "2026-05-01T14:00:00", "2026-05-01T17:45:00", "economy"),
    ("LAX", "JFK", "AA201", "2026-05-01T09:00:00", "2026-05-01T17:30:00", "economy"),
    ("LAX", "JFK", "AA205", "2026-05-01T13:30:00", "2026-05-01T22:00:00", "economy"),
    ("JFK", "SEA", "AA311", "2026-05-01T07:30:00", "2026-05-01T11:15:00", "economy"),
    ("JFK", "SEA", "AA315", "2026-05-01T15:00:00", "2026-05-01T18:50:00", "economy"),
    ("SEA", "JFK", "AA316", "2026-05-01T08:00:00", "2026-05-01T16:30:00", "economy"),
    ("SEA", "JFK", "AA320", "2026-05-01T14:00:00", "2026-05-01T22:20:00", "economy"),
    ("JFK", "SFO", "AA501", "2026-05-01T08:30:00", "2026-05-01T12:15:00", "economy"),
    ("JFK", "SFO", "AA507", "2026-05-01T17:00:00", "2026-05-01T20:50:00", "business"),
    ("SFO", "JFK", "AA502", "2026-05-01T09:30:00", "2026-05-01T18:05:00", "economy"),
    ("SFO", "JFK", "AA506", "2026-04-30T22:00:00", "2026-05-01T06:30:00", "business"),
    ("JFK", "LHR", "AA100", "2026-05-03T21:00:00", "2026-05-04T09:00:00", "business"),
    ("JFK", "LHR", "AA108", "2026-05-04T17:30:00", "2026-05-05T05:45:00", "business"),
    ("LHR", "JFK", "AA109", "2026-05-04T11:00:00", "2026-05-04T14:15:00", "business"),
    ("BOS", "ORD", "AA236", "2026-04-26T09:00:00", "2026-04-26T10:45:00", "economy"),
    ("BOS", "ORD", "AA238", "2026-04-26T13:00:00", "2026-04-26T14:50:00", "economy"),
    ("BOS", "ORD", "AA240", "2026-04-26T18:30:00", "2026-04-26T20:20:00", "economy"),
    ("ORD", "BOS", "AA237", "2026-04-26T11:15:00", "2026-04-26T14:45:00", "economy"),
    ("BOS", "MIA", "AA733", "2026-05-04T14:45:00", "2026-05-04T18:15:00", "economy"),
    ("MIA", "BOS", "AA734", "2026-05-04T10:00:00", "2026-05-04T13:15:00", "economy"),
    ("MIA", "BOS", "AA738", "2026-05-04T17:00:00", "2026-05-04T20:15:00", "economy"),
    ("LAX", "SEA", "AA614", "2026-05-02T17:00:00", "2026-05-02T19:45:00", "economy"),
    ("LAX", "SEA", "AA618", "2026-05-02T20:30:00", "2026-05-02T23:15:00", "economy"),
    ("SEA", "LAX", "AA615", "2026-05-02T08:00:00", "2026-05-02T10:50:00", "economy"),
    ("ORD", "SFO", "AA458", "2026-04-25T18:00:00", "2026-04-25T20:30:00", "business"),
    ("ORD", "MIA", "AA883", "2026-04-27T14:00:00", "2026-04-27T18:15:00", "premium_economy"),
    ("ORD", "MIA", "AA885", "2026-04-27T19:30:00", "2026-04-27T23:45:00", "economy"),
    ("DFW", "ATL", "AA447", "2026-04-28T15:00:00", "2026-04-28T18:30:00", "economy"),
    ("DFW", "ATL", "AA449", "2026-04-28T19:30:00", "2026-04-28T22:45:00", "economy"),
    ("ATL", "DFW", "AA446", "2026-04-28T11:00:00", "2026-04-28T12:30:00", "economy"),
    ("DEN", "LAX", "AA1301", "2026-04-29T12:00:00", "2026-04-29T13:45:00", "economy"),
    ("DEN", "LAX", "AA1305", "2026-04-29T16:30:00", "2026-04-29T18:15:00", "economy"),
    ("LAX", "DEN", "AA1302", "2026-04-29T09:00:00", "2026-04-29T12:15:00", "economy"),
    ("ATL", "MIA", "AA791", "2026-04-22T22:00:00", "2026-04-23T00:15:00", "economy"),
    ("ATL", "ORD", "AA550", "2026-04-26T15:00:00", "2026-04-26T16:30:00", "economy"),
    ("ORD", "ATL", "AA551", "2026-04-26T09:30:00", "2026-04-26T12:45:00", "economy"),
    ("LAX", "LAS", "AA830", "2026-05-01T11:00:00", "2026-05-01T12:10:00", "economy"),
    ("LAX", "LAS", "AA834", "2026-05-01T15:30:00", "2026-05-01T16:45:00", "economy"),
    ("PHX", "LAX", "AA960", "2026-05-02T08:30:00", "2026-05-02T09:45:00", "economy"),
]


# PNR fixtures — each entry is a dict the seeder unpacks into ``flights``
# (for the originally-booked flight) + ``pnrs`` + ``ancillaries``.
_PNRS: list[dict] = [
    {
        "pnr": "ABC123",
        "passenger": "Jane Doe",
        "flight_number": "AA123",
        "origin": "JFK",
        "destination": "LAX",
        "departure": "2026-05-01T08:00:00",
        "arrival": "2026-05-01T11:30:00",
        "cabin": "economy",
        "fare_basis": "nonrefundable",
        "elite_tier": "gold",
        "status": "scheduled",
        "delay_minutes": 0,
        "seat": "14A",
        "bag_count": 1,
        "meal": "VGML",
    },
    {
        "pnr": "DEF456",
        "passenger": "John Smith",
        "flight_number": "AA456",
        "origin": "ORD",
        "destination": "SFO",
        "departure": "2026-04-25T14:30:00",
        "arrival": "2026-04-25T17:00:00",
        "cabin": "business",
        "fare_basis": "refundable",
        "elite_tier": "platinum",
        "status": "delayed",
        "delay_minutes": 240,
        "seat": "3B",
        "bag_count": 2,
        "meal": None,
    },
    {
        "pnr": "GHI789",
        "passenger": "Maria Garcia",
        "flight_number": "AA789",
        "origin": "ATL",
        "destination": "MIA",
        "departure": "2026-04-22T19:00:00",
        "arrival": "2026-04-22T21:15:00",
        "cabin": "economy",
        "fare_basis": "basic_economy",
        "elite_tier": "none",
        "status": "cancelled_weather",
        "delay_minutes": 0,
        "seat": "28F",
        "bag_count": 0,
        "meal": None,
    },
    {
        "pnr": "JKL234",
        "passenger": "Ahmed Khan",
        "flight_number": "AA106",
        "origin": "JFK",
        "destination": "LHR",
        "departure": "2026-05-03T19:30:00",
        "arrival": "2026-05-04T07:30:00",
        "cabin": "business",
        "fare_basis": "refundable",
        "elite_tier": "gold",
        "status": "delayed",
        "delay_minutes": 90,
        "seat": "5A",
        "bag_count": 2,
        "meal": "KSML",
    },
    {
        "pnr": "MNO567",
        "passenger": "Priya Patel",
        "flight_number": "AA234",
        "origin": "BOS",
        "destination": "ORD",
        "departure": "2026-04-26T06:45:00",
        "arrival": "2026-04-26T08:30:00",
        "cabin": "economy",
        "fare_basis": "nonrefundable",
        "elite_tier": "silver",
        "status": "misconnect",
        "delay_minutes": 150,
        "seat": "22C",
        "bag_count": 1,
        "meal": None,
    },
    {
        "pnr": "PQR890",
        "passenger": "Carlos Rodriguez",
        "flight_number": "AA612",
        "origin": "LAX",
        "destination": "SEA",
        "departure": "2026-05-02T15:00:00",
        "arrival": "2026-05-02T17:50:00",
        "cabin": "economy",
        "fare_basis": "basic_economy",
        "elite_tier": "none",
        "status": "scheduled",
        "delay_minutes": 0,
        "seat": "31F",
        "bag_count": 0,
        "meal": None,
    },
    {
        "pnr": "STU345",
        "passenger": "Linda Williams",
        "flight_number": "AA881",
        "origin": "ORD",
        "destination": "MIA",
        "departure": "2026-04-27T10:15:00",
        "arrival": "2026-04-27T14:30:00",
        "cabin": "premium_economy",
        "fare_basis": "refundable",
        "elite_tier": "platinum",
        "status": "cancelled_airline",
        "delay_minutes": 0,
        "seat": "8B",
        "bag_count": 1,
        "meal": "VGML",
    },
    {
        "pnr": "VWX678",
        "passenger": "Robert Chen",
        "flight_number": "AA445",
        "origin": "DFW",
        "destination": "ATL",
        "departure": "2026-04-28T13:30:00",
        "arrival": "2026-04-28T16:30:00",
        "cabin": "economy",
        "fare_basis": "nonrefundable",
        "elite_tier": "silver",
        "status": "delayed",
        "delay_minutes": 45,
        "seat": "16A",
        "bag_count": 2,
        "meal": None,
    },
    {
        "pnr": "YZA901",
        "passenger": "Sarah Thompson",
        "flight_number": "AA1299",
        "origin": "DEN",
        "destination": "LAX",
        "departure": "2026-04-29T09:00:00",
        "arrival": "2026-04-29T10:45:00",
        "cabin": "economy",
        "fare_basis": "nonrefundable",
        "elite_tier": "none",
        "status": "diversion",
        "delay_minutes": 180,
        "seat": "14D",
        "bag_count": 1,
        "meal": None,
    },
    {
        "pnr": "BCD234",
        "passenger": "Michael O'Brien",
        "flight_number": "AA189",
        "origin": "SFO",
        "destination": "JFK",
        "departure": "2026-04-30T22:15:00",
        "arrival": "2026-05-01T06:45:00",
        "cabin": "business",
        "fare_basis": "refundable",
        "elite_tier": "platinum",
        "status": "scheduled",
        "delay_minutes": 0,
        "seat": "2D",
        "bag_count": 3,
        "meal": "SPML",
    },
    {
        "pnr": "EFG567",
        "passenger": "Emma Davis",
        "flight_number": "AA732",
        "origin": "MIA",
        "destination": "BOS",
        "departure": "2026-05-04T07:30:00",
        "arrival": "2026-05-04T10:45:00",
        "cabin": "economy",
        "fare_basis": "basic_economy",
        "elite_tier": "none",
        "status": "delayed",
        "delay_minutes": 120,
        "seat": "29A",
        "bag_count": 1,
        "meal": None,
    },
]


def seed_all(conn: sqlite3.Connection) -> None:
    """Insert all fixture rows into an empty database (single transaction)."""
    now = _now()
    with conn:
        for origin, destination, flight_number, departure, arrival, cabin in _ALTERNATIVES:
            conn.execute(
                "INSERT OR IGNORE INTO flights "
                "(flight_number, origin, destination, departure, arrival, cabin) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (flight_number, origin, destination, departure, arrival, cabin),
            )
        for pnr_row in _PNRS:
            conn.execute(
                "INSERT OR IGNORE INTO flights "
                "(flight_number, origin, destination, departure, arrival, cabin, status, delay_minutes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    pnr_row["flight_number"],
                    pnr_row["origin"],
                    pnr_row["destination"],
                    pnr_row["departure"],
                    pnr_row["arrival"],
                    pnr_row["cabin"],
                    pnr_row["status"],
                    pnr_row["delay_minutes"],
                ),
            )

        flight_key_to_id: dict[tuple[str, str], int] = {
            (row["flight_number"], row["departure"]): row["id"]
            for row in conn.execute("SELECT id, flight_number, departure FROM flights")
        }

        for pnr_row in _PNRS:
            flight_id = flight_key_to_id[(pnr_row["flight_number"], pnr_row["departure"])]
            conn.execute(
                "INSERT INTO pnrs (pnr, passenger, flight_id, fare_basis, elite_tier, "
                "                  status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
                (
                    pnr_row["pnr"],
                    pnr_row["passenger"],
                    flight_id,
                    pnr_row["fare_basis"],
                    pnr_row["elite_tier"],
                    now,
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO ancillaries (pnr, seat, bag_count, meal) VALUES (?, ?, ?, ?)",
                (pnr_row["pnr"], pnr_row["seat"], pnr_row["bag_count"], pnr_row["meal"]),
            )
