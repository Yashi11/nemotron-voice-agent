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

Applied *before* the generic Nemotron cleanup so downstream whitespace /
punctuation normalization still runs on the substituted output.
"""

from __future__ import annotations

import re

from cascaded.shared.nemotron_speech_text_filter import NemotronSpeechTextFilter

# Every recognized IATA code resolves to a full spoken form — no
# letter-by-letter fallback, because the TTS is much less predictable on
# three-letter acronyms than it is on real words.  Unknown codes fall
# through to per-letter spelling via :func:`_insert_spaces`.
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

# 3 uppercase letters, standalone — the IATA airport-code pattern.
# Must run *after* the flight and PNR substitutions so that their letter
# portions aren't later re-expanded into airport names.
_IATA_RE = re.compile(r"\b([A-Z]{3})\b")


def _insert_spaces(s: str) -> str:
    """Insert a space between every character so TTS reads each one individually."""
    return " ".join(s)


def _sub_alphanumeric_code(match: re.Match) -> str:
    """Spell every capture group character-by-character, separated by spaces.

    Each group is spaced out individually and groups are joined with a space,
    so ``AA123`` (groups: ``'AA'``, ``'123'``) becomes ``'A A 1 2 3'``.
    Works for any number of capture groups.
    """
    return " ".join(_insert_spaces(g) for g in match.groups())


def _sub_iata(match: re.Match) -> str:
    code = match.group(1)
    return _IATA_CITY.get(code, _insert_spaces(code))


def _apply_airline_substitutions(text: str) -> str:
    """Apply the airline-specific regex substitutions in dependency order."""
    text = _FLIGHT_RE.sub(_sub_alphanumeric_code, text)
    text = _PNR_RE.sub(_sub_alphanumeric_code, text)
    text = _IATA_RE.sub(_sub_iata, text)
    return text


class AirlineSpeechTextFilter(NemotronSpeechTextFilter):
    """Airline domain-aware TTS text filter.

    Applies airline-specific substitutions (flight numbers, PNRs, airport
    codes) first, then delegates to the parent Nemotron filter for generic
    cleanup.
    """

    async def filter(self, text: str) -> str:
        """Return ``text`` with airline entities re-spelled for Nemotron TTS."""
        return await super().filter(_apply_airline_substitutions(text))
