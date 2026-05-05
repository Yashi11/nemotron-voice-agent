# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Pipecat ``FrameProcessor`` that classifies intent + extracts entities.

First-turn intent is decided by
:mod:`cascaded.agentic_airline.orchestrators._intent_llm` — an LLM that returns
the intent label alongside any travel entities the caller spoke.  The
previous regex fast-path was removed: it missed natural paraphrases
("I'd like to change my booking to Thursday") and over-triggered on
domain nouns, so we now pay one classifier call on no-pending turns
for a more faithful read.

While an orchestrator is parked mid-flow, the router skips the LLM
call entirely: slot-shaped replies ("the earlier one", "aisle please")
drive the state machine forward.  Only one keyword carve-out — at the
awaiting-PNR step — bails out without an LLM round-trip:

- ``_ABANDON_RE`` — "never mind" / "forget it" → clear pending, let
  the fast LLM close gracefully.

Past the PNR gate the 3-LLM pipeline (classifier → orchestrator →
responder) owns abandon / side-query / pivot decisions.

Outputs stamped on ``frame.metadata``:

- ``intent`` — rebook / cancel / booking / simple
- ``requires_deep`` — True when the bridge should swallow the frame
  and spawn the orchestrator
- ``extracted_destination`` / ``extracted_origin`` — IATA codes
- ``extracted_flight`` / ``extracted_pnr`` — validated identifiers
- ``extracted_seat`` / ``extracted_meal`` — free-form strings

The bridge reads each ``extracted_*`` field and pre-populates
memory / entity_store before spawning an orchestrator session.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pipecat.frames.frames import Frame, LLMContextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

if TYPE_CHECKING:
    from cascaded.agentic_airline.state.conversation_memory import ConversationMemory


_ABANDON_RE = re.compile(
    r"\b(never\s*mind|forget\s+(it|that)|start\s+over|quit|stop\s+(this|asking)|"
    r"cancel\s+(the|this|that)\s+(request|call|chat|session)|scrap\s+(it|that))\b",
    re.IGNORECASE,
)
# Only used at the awaiting-PNR step — before a record is loaded the
# orchestrator has nothing to reason over, so the router still needs a
# cheap bail-out.  Past the PNR gate the 3-LLM pipeline (classifier →
# orchestrator → responder) owns abandon / side-query / pivot decisions.


@dataclass(slots=True, frozen=True)
class IntentClassification:
    """Router output attached to ``frame.metadata``."""

    intent: str
    requires_deep: bool


_SIMPLE = IntentClassification(intent="simple", requires_deep=False)


class IntentRouterProcessor(FrameProcessor):
    """LLM-first intent router with pending-flow resume, stamps metadata."""

    def __init__(self, memory: ConversationMemory | None = None) -> None:
        """Build the router with optional :class:`ConversationMemory` for flow resume."""
        super().__init__()
        self._memory = memory

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Classify on downstream context frames; pass everything through."""
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM and isinstance(frame, LLMContextFrame):
            transcript = _last_user_text(frame)
            result, extracted = await self._classify(transcript)
            _apply_metadata(frame, result, extracted)
        await self.push_frame(frame, direction)

    async def _classify(self, transcript: str) -> tuple[IntentClassification, dict]:
        """Return (classification, extracted-entities) for ``transcript``."""
        if not transcript:
            return _SIMPLE, {}
        if self._memory is None:
            return await self._llm_classify_with_entities(transcript)

        pending_pnr = _pending_pnr_intent(self._memory)
        pending_any = _pending_intent(self._memory)

        if pending_any is not None:
            # Awaiting-PNR-only safety hatch: caller bails before giving a
            # PNR.  Past this step the orchestrator's turn analyzer owns
            # abandon / side-query / pivot decisions.
            if pending_pnr and _ABANDON_RE.search(transcript):
                _clear_pending(self._memory)
                return _SIMPLE, {}
            if pending_pnr:
                from cascaded.agentic_airline.orchestrators._parse import extract_pnr

                if extract_pnr(transcript) is None:
                    result, extracted = await self._llm_classify_with_entities(transcript)
                    if result.intent not in ("simple", pending_any):
                        _clear_pending(self._memory)
                        return result, extracted
            # Anything else mid-flow → orchestrator decides.
            return IntentClassification(intent=pending_any, requires_deep=True), {}

        # No pending flow — LLM classifier drives first-turn routing.
        return await self._llm_classify_with_entities(transcript)

    async def _llm_classify_with_entities(self, transcript: str) -> tuple[IntentClassification, dict]:
        llm_out = await _llm_classify(transcript)
        extracted = {
            "extracted_destination": llm_out.destination,
            "extracted_origin": llm_out.origin,
            "extracted_flight": llm_out.flight_number,
            "extracted_pnr": llm_out.pnr,
            "extracted_seat": llm_out.seat_preference,
            "extracted_meal": llm_out.meal_preference,
        }
        if llm_out.intent != "simple":
            return (
                IntentClassification(intent=llm_out.intent, requires_deep=True),
                extracted,
            )
        return _SIMPLE, extracted


async def _llm_classify(transcript: str):
    """Lazy import so the router module has no hard dependency on the orchestrators."""
    from cascaded.agentic_airline.orchestrators._intent_llm import classify as _classify

    return await _classify(transcript)


def _pending_pnr_intent(memory: ConversationMemory) -> str | None:
    from cascaded.agentic_airline.orchestrators._common import pending_pnr_intent

    return pending_pnr_intent(memory)


def _pending_intent(memory: ConversationMemory) -> str | None:
    from cascaded.agentic_airline.orchestrators._common import pending_intent

    return pending_intent(memory)


def _clear_pending(memory: ConversationMemory) -> None:
    from cascaded.agentic_airline.orchestrators._common import clear_awaiting_pnr

    clear_awaiting_pnr(memory)


def _apply_metadata(frame: LLMContextFrame, result: IntentClassification, extracted: dict) -> None:
    """Stamp classification + entity extractions on the frame."""
    frame.metadata["intent"] = result.intent
    frame.metadata["requires_deep"] = result.requires_deep
    for key, value in extracted.items():
        if value is not None:
            frame.metadata[key] = value


def _last_user_text(frame: LLMContextFrame) -> str:
    """Extract the most recent user message text from the LLM context."""
    for msg in reversed(frame.context.get_messages()):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text"
            )
    return ""
