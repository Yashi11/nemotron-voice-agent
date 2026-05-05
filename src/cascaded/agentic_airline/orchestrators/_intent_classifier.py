# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Intent-level classifier — Call 1 of the 3-LLM state-runner pipeline.

Given the caller's latest turn, the active flow, and its current state
purpose, this classifier decides ONE of:

* ``stay``   — continue the active flow (orchestrator LLM runs next).
* ``pivot``  — caller clearly wants a different flow.  ``new_intent`` is
               one of ``rebook`` / ``cancel`` / ``booking``.
* ``abandon``— caller wants to stop entirely.

Cross-intent transitions are the classifier's SOLE responsibility.  The
downstream orchestrator LLM sees no cross-intent guidance and cannot
propose a pivot — keeping its reasoning narrow to the flow it's running.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from loguru import logger

from cascaded.agentic_airline.orchestrators._llm import ainvoke_text

_VALID_ACTIONS = {"stay", "pivot", "abandon"}
_VALID_INTENTS = {"rebook", "cancel", "booking"}


@dataclass(slots=True, frozen=True)
class ClassifierDecision:
    """Structured output of the intent classifier."""

    action: str  # "stay" | "pivot" | "abandon"
    new_intent: str | None = None  # only set on pivot
    trigger_phrase: str | None = None  # exact substring the LLM says justifies the pivot


_SYSTEM = (
    "You classify a caller turn in an airline phone call.  The caller "
    "is already inside ONE flow; the default answer is ALWAYS stay.\n\n"
    "The three flows the system supports:\n"
    "  booking — create a BRAND-NEW reservation from scratch.  Caller "
    "has NO existing PNR; the flow collects origin, destination, "
    "flight choice, seat, meal, price, then confirms.  Caller phrases: "
    "'I want to make a reservation', 'book me a new flight', 'I need "
    "to fly somewhere'.\n"
    "  rebook — change the flight on an EXISTING booking.  Caller has "
    "a PNR; the flow asks for the new destination, offers alternatives, "
    "collects seat/meal updates, commits.  Caller phrases: 'rebook my "
    "flight', 'reschedule', 'change my existing flight', 'switch to a "
    "different flight for my booking'.\n"
    "  cancel — cancel an EXISTING booking and get a refund or credit.  "
    "Caller phrases: 'cancel my booking', 'I want a refund', 'call it "
    "off'.\n\n"
    "Output ONE compact JSON object, nothing else:\n"
    "  {\n"
    '    "action": "stay" | "pivot" | "abandon",\n'
    '    "new_intent": "rebook"|"cancel"|"booking"|null,\n'
    '    "trigger_phrase": "<exact substring from the caller\'s words that '
    'justifies a pivot/abandon>" | null\n'
    "  }\n\n"
    "PIVOT rules:\n"
    "  - Only when the caller's words EXPLICITLY match a different "
    "flow's caller phrases above.  An utterance that fits the CURRENT "
    "flow's expected input is NOT a pivot, even if its wording sounds "
    "like another flow.\n"
    "  - Revision words ('actually', 'wait', 'no', 'scratch that', "
    "'on second thought', 'change of mind', 'get out', 'forget "
    "Seattle') followed by a slot value (route, city, seat, meal, "
    "cabin, flight) are the caller REVISING their previous answer in "
    "the SAME flow — STAY.  Do not treat the revision word as evidence "
    "of a different flow on its own.\n"
    "  - Examples of NOT a pivot (all STAY):\n"
    "      • in booking, 'actually go from New York to Chicago' — "
    "caller is revising the destination of the new reservation.\n"
    "      • in booking, 'get out, actually go from New York to "
    "Chicago' — same revision; 'get out' is venting, the slot value "
    "that follows fits booking.\n"
    "      • in booking, 'no wait make it Miami instead' — destination "
    "revision.\n"
    "      • in booking, 'I want to move from X to Y' — new-reservation "
    "route, NOT a rebook (rebook needs an EXISTING booking).\n"
    "      • in rebook, 'actually aisle please' — seat revision.\n"
    "  - Example of PIVOT: in booking, the caller names a DIFFERENT "
    "flow's vocabulary AND that flow's required context — e.g. "
    "'actually cancel my existing booking ABC123' (cancel + existing "
    "PNR) → PIVOT to cancel; 'actually I have a booking already, "
    "reschedule it' (rebook + existing booking) → PIVOT to rebook.\n"
    "  - The trigger_phrase for a PIVOT must contain the OTHER flow's "
    "vocabulary (cancel/refund for cancel; rebook/reschedule/existing "
    "booking for rebook; book/reservation/new flight for booking) — "
    "NOT just a revision word like 'actually' or 'get out'.\n"
    "  - new_intent MUST match what the caller named, NOT what the "
    "current flow is.\n"
    "  - trigger_phrase MUST be copied VERBATIM from the caller's "
    "utterance — the exact text proving the pivot.  If no substring of "
    "the caller's words justifies a pivot, you must NOT pivot.\n\n"
    "STAY in EVERY other case, including:\n"
    "  - Slot-fills and slot REVISIONS that mention routes, cities, "
    "dates, seats, meals, times, cabins — caller ANSWERS or REVISES, "
    "not switches.\n"
    "  - Side questions about the caller's booking.\n"
    "  - Chitchat, greetings, clarifications, repeats.\n"
    "  - Same-flow restarts (in-flow mid-change).\n"
    "  - Ambiguous utterances.\n\n"
    "ABANDON: explicit stop with NO slot value following ('never mind', "
    "'forget it', 'stop', 'cancel this call', 'I'm done').  "
    "trigger_phrase = the stop phrase.  If the stop is followed by a "
    "slot value that fits the CURRENT flow (a route, seat, meal, "
    "cabin), it is a revision — STAY, not abandon.  Only pivot when "
    "the words after the stop match a DIFFERENT flow's vocabulary.\n\n"
    "Never invent a trigger_phrase that isn't literally in the caller's "
    "words."
)


async def classify_turn(
    current_intent: str,
    current_state: str,
    state_purpose: str,  # accepted for backwards-compat; not used in the prompt
    transcript: str,
    history: list[dict] | None = None,
) -> ClassifierDecision:
    """Classify ONE caller turn as stay / pivot / abandon.

    Failures (LLM error, malformed JSON, invalid action) map to a
    conservative ``stay`` so the flow keeps moving.  Pivots are
    validated against the caller's own words: the model is required to
    quote a ``trigger_phrase`` from the utterance, and the parser
    rejects any phrase that isn't actually present — that keeps the
    LLM from fabricating a pivot reason.

    The classifier deliberately does NOT see the current state's full
    purpose text: orchestrator state descriptions carry operational
    details (slot_updates syntax, tool names) that distract the
    classifier and bias it toward pivots.  Knowing the active flow's
    name is sufficient — the classifier only decides whether the
    caller's words match a DIFFERENT flow's caller phrasing.
    """
    if not transcript:
        return ClassifierDecision(action="stay")

    history_block = (
        "\n".join(f"  {turn.get('role', '?')}: {turn.get('content', '')}" for turn in (history or [])[-4:])
        or "  (no prior dialogue)"
    )

    user = (
        f"Active flow: {current_intent}\n\n"
        f"Recent dialogue:\n{history_block}\n\n"
        f"Caller just said: {transcript!r}\n\n"
        "JSON:"
    )
    try:
        raw = await ainvoke_text(_SYSTEM, user)
    except Exception as exc:
        logger.warning(f"intent classifier failed ({type(exc).__name__}): {exc}")
        return ClassifierDecision(action="stay")

    decision = _parse(raw, current_intent, transcript)
    logger.debug(f"intent classifier raw={raw!r} → {decision}")
    return decision


def _parse(raw: str, current_intent: str, transcript: str) -> ClassifierDecision:
    """Parse the classifier's JSON and validate pivot/abandon evidence.

    A pivot is only honored when the model quotes a ``trigger_phrase``
    that is actually a substring of the caller's words.  This prevents
    hallucinated pivots (e.g. classifying ``new reservation`` as
    ``pivot → cancel`` — the word ``cancel`` isn't in the utterance).
    """
    if not raw:
        return ClassifierDecision(action="stay")
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    if start == -1:
        return ClassifierDecision(action="stay")
    depth = 0
    end = -1
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        return ClassifierDecision(action="stay")
    try:
        payload = json.loads(text[start:end])
    except json.JSONDecodeError:
        return ClassifierDecision(action="stay")
    if not isinstance(payload, dict):
        return ClassifierDecision(action="stay")

    action = str(payload.get("action") or "").strip().lower()
    if action not in _VALID_ACTIONS:
        return ClassifierDecision(action="stay")

    new_intent_raw = payload.get("new_intent")
    new_intent: str | None = None
    if isinstance(new_intent_raw, str):
        cand = new_intent_raw.strip().lower()
        if cand in _VALID_INTENTS:
            new_intent = cand

    trigger_raw = payload.get("trigger_phrase")
    trigger: str | None = trigger_raw.strip() if isinstance(trigger_raw, str) and trigger_raw.strip() else None

    # Same-intent "pivot" is really a same-flow restart — treat as stay
    # so the orchestrator handles it.
    if action == "pivot" and (new_intent is None or new_intent == current_intent.lower()):
        return ClassifierDecision(action="stay")

    transcript_low = transcript.lower()
    if action == "pivot":
        # Self-verification: the quoted trigger phrase must actually
        # appear in the caller's words.  This blocks hallucinated
        # pivots where the model picks a flow the caller never named.
        if trigger is None or trigger.lower() not in transcript_low:
            logger.info(
                f"intent classifier: rejecting pivot→{new_intent!r} because "
                f"trigger_phrase {trigger!r} is not in transcript {transcript!r}; "
                "staying"
            )
            return ClassifierDecision(action="stay")
        return ClassifierDecision(action="pivot", new_intent=new_intent, trigger_phrase=trigger)
    if action == "abandon":
        # Abandon also benefits from evidence, but is less risky — just
        # log if missing; don't block.
        if trigger is None or trigger.lower() not in transcript_low:
            logger.info(
                f"intent classifier: abandon without verifiable trigger "
                f"({trigger!r} not in {transcript!r}); honoring anyway"
            )
        return ClassifierDecision(action="abandon", trigger_phrase=trigger)
    return ClassifierDecision(action="stay")
