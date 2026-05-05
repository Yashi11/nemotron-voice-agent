# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Airline-specific TTS text filter.

Extends :class:`cascaded.shared.nemotron_speech_text_filter.NemotronSpeechTextFilter`
with substitutions that fix common TTS pronunciation failures in an
airline domain:

* **Flight numbers** (``AA123``, ``UA4567``) → ``A A 1 2 3`` so the TTS
  reads the carrier as two letters and the flight number digit-by-digit
  instead of "one hundred twenty three".
* **PNRs** (``ABC123``) → ``A B C 1 2 3``.
* **IATA airport codes** → always expanded to a full spoken form
  (``MIA`` → ``Miami``, ``JFK`` → ``John F Kennedy``) — "full forms for
  destinations" is friendlier than letter-by-letter and avoids TTS
  treating three-letter tokens as common-word homophones (``BOS`` →
  "boss", ``ATL`` → "at-el").
* **Clock times** (``2:30 PM``) → ``2 30 PM`` so the TTS doesn't voice
  the colon.
* **Dollar amounts** (``$30``) → ``30 dollars``.

Applied *before* the generic Nemotron cleanup so downstream whitespace /
punctuation normalization still runs on the substituted output.
"""

from __future__ import annotations

import re

from cascaded.shared.nemotron_speech_text_filter import NemotronSpeechTextFilter

# Every recognized IATA code resolves to a full spoken form — no
# letter-by-letter fallback, because the TTS is much less predictable on
# three-letter acronyms than it is on real words.  Unknown codes fall
# through to per-letter spelling via :func:`_spell_letters`.
_IATA_CITY: dict[str, str] = {
    # Domestic US hubs and common destinations
    "MIA": "Miami",
    "SEA": "Seattle",
    "SFO": "San Francisco",
    "LAX": "Los Angeles",
    "ORD": "Chicago O'Hare",
    "ATL": "Atlanta",
    "DFW": "Dallas Fort Worth",
    "DEN": "Denver",
    "BOS": "Boston Logan",
    "PHX": "Phoenix",
    "LAS": "Las Vegas",
    "EWR": "Newark Liberty",
    "MSP": "Minneapolis Saint Paul",
    "IAH": "Houston Intercontinental",
    "DCA": "Washington Reagan",
    "IAD": "Washington Dulles",
    "CLT": "Charlotte",
    "JFK": "John F Kennedy",
    "LGA": "LaGuardia",
    "SJC": "San Jose",
    "BWI": "Baltimore Washington",
    "HOU": "Houston Hobby",
    # International gateways
    "LHR": "London Heathrow",
    "CDG": "Paris Charles de Gaulle",
    "FRA": "Frankfurt",
    "NRT": "Tokyo Narita",
    "HND": "Tokyo Haneda",
    "YYZ": "Toronto Pearson",
    "MEX": "Mexico City",
}

# 2-letter carrier + 3-4 digit flight number.  Real airlines use 2 letters
# (AA, UA, DL, BA, LH ...) exclusively for IATA-registered carriers.
_FLIGHT_RE = re.compile(r"\b([A-Z]{2})(\d{2,4})\b")

# 3-letter + 3-digit PNR (matches our fixture shape).  Real PNRs vary; this
# covers the common case without over-matching acronyms like ``USA`` or
# sequences like ``ABC 123`` (which wouldn't match because of the space).
_PNR_RE = re.compile(r"\b([A-Z]{3})(\d{3})\b")

# Clock time: H:MM or HH:MM, not part of an HH:MM:SS timestamp.
_TIME_RE = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!:?\d)")

# 3 uppercase letters, standalone — the IATA airport-code pattern.
# Must run *after* the flight and PNR substitutions so that their letter
# portions aren't later re-expanded into airport names.
_IATA_RE = re.compile(r"\b([A-Z]{3})\b")

# Dollar amount: ``$30``, ``$30.50``.
_DOLLAR_RE = re.compile(r"\$(\d+(?:\.\d+)?)")


def _space_digits(digits: str) -> str:
    """Insert spaces between digits so the TTS voices each one individually."""
    return " ".join(digits)


def _spell_letters(letters: str) -> str:
    """Insert spaces between letters so the TTS reads each letter individually."""
    return " ".join(letters)


def _sub_flight(match: re.Match) -> str:
    return f"{_spell_letters(match.group(1))} {_space_digits(match.group(2))}"


def _sub_pnr(match: re.Match) -> str:
    return f"{_spell_letters(match.group(1))} {_space_digits(match.group(2))}"


def _sub_time(match: re.Match) -> str:
    return f"{match.group(1)} {match.group(2)}"


def _sub_iata(match: re.Match) -> str:
    code = match.group(1)
    return _IATA_CITY.get(code, _spell_letters(code))


def _sub_dollar(match: re.Match) -> str:
    return f"{match.group(1)} dollars"


def _apply_airline_substitutions(text: str) -> str:
    """Apply the airline-specific regex substitutions in dependency order."""
    text = _FLIGHT_RE.sub(_sub_flight, text)
    text = _PNR_RE.sub(_sub_pnr, text)
    text = _TIME_RE.sub(_sub_time, text)
    text = _IATA_RE.sub(_sub_iata, text)
    text = _DOLLAR_RE.sub(_sub_dollar, text)
    return text


class AirlineSpeechTextFilter(NemotronSpeechTextFilter):
    """Airline domain-aware TTS text filter.

    Applies airline-specific substitutions (flight numbers, PNRs, airport
    codes, times, dollar amounts) first, then delegates to the parent
    Nemotron filter for generic cleanup.
    """

    async def filter(self, text: str) -> str:
        """Return ``text`` with airline entities re-spelled for Nemotron TTS."""
        return await super().filter(_apply_airline_substitutions(text))
