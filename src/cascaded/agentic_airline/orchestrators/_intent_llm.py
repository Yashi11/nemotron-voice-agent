# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""LLM intent classifier + entity extractor (regex-router fallback).

Runs only when the regex router returns ``simple`` on a substantive
utterance.  One Llama-8B call returns a strict JSON object carrying the
detected intent plus any travel entities the caller spoke.  The router
stamps each field into ``frame.metadata`` so the bridge can pre-populate
memory / entity_store *before* the orchestrator spawns — the caller
doesn't have to re-provide info the LLM already heard.

Entities extracted (all nullable):

- ``destination`` / ``origin`` — IATA codes
- ``flight_number`` — carrier + digits
- ``pnr`` — 6-character record locator
- ``seat_preference`` / ``meal_preference`` — free-form or code

Values the LLM returns that don't validate against local helpers
(:mod:`cascaded.agentic_airline.orchestrators._parse`) are dropped so a
hallucinated IATA or malformed PNR can't silently drift into state.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from loguru import logger

from cascaded.agentic_airline.orchestrators._llm import ainvoke_text
from cascaded.agentic_airline.orchestrators._parse import (
    extract_flight_number,
    extract_iata,
    extract_pnr,
)

INTENTS = frozenset({"rebook", "cancel", "booking", "simple"})

# Skip the LLM for very short turns — pure confirmations / greetings
# that can never carry a meaningful intent or entity.
_MIN_TOKENS_FOR_LLM = 3


@dataclass(slots=True, frozen=True)
class IntentAndEntities:
    """Structured result from :func:`classify`.

    ``intent`` is always one of :data:`INTENTS`.  All entity fields are
    cleaned / validated and set to ``None`` when the LLM didn't produce
    a usable value.
    """

    intent: str
    destination: str | None = None
    origin: str | None = None
    flight_number: str | None = None
    pnr: str | None = None
    seat_preference: str | None = None
    meal_preference: str | None = None


_SYSTEM = (
    "You classify a traveler's airline-call utterance and extract any travel "
    "entities they mention. Reply with ONE JSON object, no prose, no code fences.\n\n"
    "Fields (use null if not explicitly stated):\n"
    '- intent: one of "rebook", "cancel", "booking", "simple"\n'
    "- destination: IATA code (3 uppercase letters) or null\n"
    "- origin: IATA code or null\n"
    "- flight_number: carrier letters + digits (e.g. AA123) or null\n"
    "- pnr: 6-character booking reference (3 letters + 3 digits) or null\n"
    "- seat_preference: specific seat (22B) or area (aisle/window/exit row) or null\n"
    "- meal_preference: meal code or description or null\n\n"
    "Intent rules:\n"
    "- rebook = change an EXISTING booking's flight / switch flights. "
    "The traveler must refer to an existing booking, current flight, "
    "reservation, or PNR.\n"
    "- cancel = cancel an existing booking / get a refund\n"
    "- booking = create a NEW reservation from scratch (no existing PNR). "
    "Plain travel requests like 'I want to go from X to Y' are booking "
    "unless the traveler mentions an existing booking.\n"
    "- simple = greetings, yes/no confirmations, chit-chat, mid-flow replies "
    "like 'the earlier one', and anything not in the above three categories.\n\n"
    "Rules:\n"
    "- Only include entities the traveler explicitly spoke. Never invent.\n"
    "- Never use example values from this prompt as a fallback.\n\n"
    "Examples:\n"
    '"Hi there" -> {"intent":"simple"}\n'
    '"I want to reb it to Miami" -> {"intent":"rebook","destination":"MIA"}\n'
    '"reschedule from JFK to Seattle please" -> {"intent":"rebook","origin":"JFK","destination":"SEA"}\n'
    '"cancel my booking" -> {"intent":"cancel"}\n'
    '"I want to book a new flight" -> {"intent":"booking"}\n'
    '"make me a reservation from LAX to SFO" -> {"intent":"booking","origin":"LAX","destination":"SFO"}\n'
    '"I want to go from Agra to Jodhpur" -> {"intent":"booking"}\n'
    '"I don\'t have a PNR, I need a new reservation from SFO to JFK" -> '
    '{"intent":"booking","origin":"SFO","destination":"JFK"}\n'
    '"yes the earlier one" -> {"intent":"simple"}\n'
    '"I want an aisle seat" -> {"intent":"simple","seat_preference":"aisle"}\n'
)


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_IATA_RE = re.compile(r"^[A-Z]{3}$")


async def classify(transcript: str) -> IntentAndEntities:
    """Return intent + any entities extracted from ``transcript``.

    Skips the LLM call (returns ``simple``) for short turns below
    :data:`_MIN_TOKENS_FOR_LLM` words and on any LLM / parse failure.
    """
    if not transcript or len(transcript.split()) < _MIN_TOKENS_FOR_LLM:
        return IntentAndEntities(intent="simple")
    try:
        raw = await ainvoke_text(_SYSTEM, f"Traveler said: {transcript!r}\n\nJSON:")
    except Exception as exc:
        logger.warning(f"intent LLM failed ({type(exc).__name__}): {exc}")
        return IntentAndEntities(intent="simple")
    result = _parse(raw, transcript)
    logger.debug(f"intent LLM raw={raw!r} → {result}")
    return result


def _parse(raw: str, transcript: str) -> IntentAndEntities:
    match = _JSON_RE.search(raw)
    if not match:
        return IntentAndEntities(intent="simple")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return IntentAndEntities(intent="simple")
    if not isinstance(data, dict):
        return IntentAndEntities(intent="simple")

    intent = str(data.get("intent") or "simple").strip().lower()
    if intent not in INTENTS:
        intent = "simple"

    return IntentAndEntities(
        intent=intent,
        destination=_clean_iata(data.get("destination")),
        origin=_clean_iata(data.get("origin")),
        flight_number=_clean_flight(data.get("flight_number")),
        pnr=_clean_pnr(data.get("pnr")),
        seat_preference=_clean_str(data.get("seat_preference")),
        meal_preference=_clean_str(data.get("meal_preference")),
    )


def _clean_str(value) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    return s or None


def _clean_iata(value) -> str | None:
    """Only return an IATA we actually serve; else drop.

    Prevents the LLM hallucinating DXB / SIN etc. from leaking into
    memory when the backend doesn't know that route.
    """
    if not isinstance(value, str):
        return None
    val = value.strip().upper()
    if not _IATA_RE.match(val):
        return None
    return extract_iata(val)


def _clean_flight(value) -> str | None:
    if not isinstance(value, str):
        return None
    return extract_flight_number(value)


def _clean_pnr(value) -> str | None:
    if not isinstance(value, str):
        return None
    return extract_pnr(value)
