# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Airport code formatting helpers for the Thinker/Talker example."""

from __future__ import annotations

from datetime import datetime

AIRPORT_DISPLAY_NAMES: dict[str, str] = {
    "JFK": "New York",
    "LGA": "New York LaGuardia",
    "EWR": "Newark",
    "SEA": "Seattle",
    "SFO": "San Francisco",
    "LAX": "Los Angeles",
    "SLC": "Salt Lake City",
    "BOS": "Boston",
    "ORD": "Chicago",
    "DFW": "Dallas",
    "DEN": "Denver",
    "MIA": "Miami",
    "PHX": "Phoenix",
    "LAS": "Las Vegas",
}

AIRPORT_SPOKEN_NAMES: dict[str, str] = {
    "JFK": "John F Kennedy",
    "LGA": "LaGuardia",
    "EWR": "Newark Liberty",
    "SEA": "Seattle",
    "SFO": "San Francisco",
    "LAX": "Los Angeles",
    "SLC": "Salt Lake City",
    "BOS": "Boston",
    "ORD": "Chicago O'Hare",
    "DFW": "Dallas Fort Worth",
    "DEN": "Denver",
    "MIA": "Miami",
    "PHX": "Phoenix",
    "LAS": "Las Vegas",
}


def iata_code(value: str) -> str | None:
    """Return a normalized IATA code when ``value`` is already a code."""
    code = value.strip().upper()
    return code if len(code) == 3 and code.isalpha() else None


def airport_display_name(code: str) -> str:
    """Return a short speakable airport/city label."""
    normalized = code.strip().upper()
    return AIRPORT_DISPLAY_NAMES.get(normalized, normalized)


def airport_spoken_name(code: str) -> str:
    """Return the TTS pronunciation for an airport code."""
    normalized = code.strip().upper()
    return AIRPORT_SPOKEN_NAMES.get(normalized, airport_display_name(normalized))


def spoken_time(iso_timestamp: str) -> str:
    """Return a short 12-hour spoken time for a timestamp."""
    try:
        timestamp = datetime.fromisoformat(iso_timestamp)
    except ValueError:
        return iso_timestamp
    hour = timestamp.strftime("%I").lstrip("0") or "12"
    return f"{hour}:{timestamp:%M} {timestamp:%p}"
