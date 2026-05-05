# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Injects ``Current PNR details`` into the fast LLM's system context.

Sits between the bridge and the fast LLM, reads the stream's
:class:`EntityStore` on each downstream :class:`LLMContextFrame`, and
appends a compact one-line summary of the currently loaded PNR to the
context's first system message.  When no PNR is loaded yet, appends the
literal ``Current PNR details: None`` so the fast LLM can tell the
state apart from *"PNR unknown because lookup failed."*.

Why here and not in the system prompt yaml:

* The yaml prompt is static; it can't reflect per-turn state.
* The bridge swallows deep-intent turns, so any prompt mutation has to
  happen AFTER the bridge decides this turn is fast-path.
* The injection is idempotent — each call rewrites the block marker in
  place so stale details from a previous turn never accumulate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from pipecat.frames.frames import Frame, LLMContextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from cascaded.agentic_airline.tools import _backend

if TYPE_CHECKING:
    from cascaded.agentic_airline.state.entity_store import EntityStore


_BLOCK_OPEN = "<pnr_state>"
_BLOCK_CLOSE = "</pnr_state>"


class CurrentPnrInjector(FrameProcessor):
    """Rewrites the system message's PNR block on every fast-LLM turn."""

    def __init__(self, entity_store: EntityStore) -> None:
        """Bind the injector to ``entity_store`` (read-only access)."""
        super().__init__()
        self._entity_store = entity_store

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Rewrite the system PNR block on each downstream LLM context frame."""
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM and isinstance(frame, LLMContextFrame):
            await self._inject(frame)
        await self.push_frame(frame, direction)

    async def _inject(self, frame: LLMContextFrame) -> None:
        """Replace (or append) the ``<pnr_state>…</pnr_state>`` block in the system message."""
        block = await self._render_block()
        messages = frame.context.get_messages()
        for msg in messages:
            if msg.get("role") == "system":
                msg["content"] = _rewrite_system(msg.get("content", ""), block)
                return
        # No system message? Add one.
        messages.insert(0, {"role": "system", "content": block})

    async def _render_block(self) -> str:
        """Build the compact PNR summary from entity_store + backend."""
        entity = self._entity_store.get("pnr")
        if entity is None:
            # Phrased to describe the LOOKUP state only — do not say
            # "no booking" or similar, which has been observed to mislead
            # the fast LLM into triggering the booking intent.
            body = "Current PNR details: not loaded (caller hasn't shared a booking reference)."
            return f"{_BLOCK_OPEN}\n{body}\n{_BLOCK_CLOSE}"
        try:
            record = await _backend.get_pnr(entity.value)
        except Exception as exc:  # noqa: BLE001 — never block the LLM on state injection
            logger.warning(f"pnr_injector: backend lookup failed for {entity.value!r}: {exc}")
            record = None
        if record is None:
            body = f"Current PNR details: {entity.value} (record unavailable right now)."
            return f"{_BLOCK_OPEN}\n{body}\n{_BLOCK_CLOSE}"
        body = _format_record(record)
        return f"{_BLOCK_OPEN}\n{body}\n{_BLOCK_CLOSE}"


_MEAL_SPOKEN_FOR_INJECTOR = {
    "VGML": "vegetarian",
    "VLML": "vegetarian",
    "NVML": "non-vegetarian",
    "KSML": "kosher",
    "MOML": "halal",
    "GFML": "gluten-free",
    "DBML": "diabetic",
    "CHML": "child meal",
}


def _format_record(record: dict) -> str:
    """One-line spoken-friendly summary of a PNR record."""
    ancillaries = record.get("ancillaries") or {}
    parts: list[str] = [f"Current PNR details: {record.get('pnr', '?')}"]
    if record.get("passenger"):
        parts.append(f"passenger {record['passenger']}")
    if record.get("flight_number"):
        parts.append(f"flight {record['flight_number']}")
    if record.get("origin") and record.get("destination"):
        parts.append(f"{record['origin']}→{record['destination']}")
    if record.get("departure"):
        parts.append(f"departs {record['departure']}")
    if record.get("status"):
        parts.append(f"status {record['status']}")
    if record.get("delay_minutes"):
        parts.append(f"delay {record['delay_minutes']}m")
    if record.get("cabin"):
        parts.append(f"cabin {record['cabin']}")
    if record.get("fare_basis"):
        parts.append(f"fare {record['fare_basis']}")
    if record.get("elite_tier"):
        parts.append(f"elite {record['elite_tier']}")
    if ancillaries.get("seat"):
        parts.append(f"seat {ancillaries['seat']}")
    if ancillaries.get("bag_count") is not None:
        parts.append(f"bags {ancillaries['bag_count']}")
    meal_code = ancillaries.get("meal")
    if meal_code:
        meal_spoken = _MEAL_SPOKEN_FOR_INJECTOR.get(str(meal_code).upper(), meal_code)
        parts.append(f"meal {meal_spoken} ({meal_code})")
    return " | ".join(parts) + "."


def _rewrite_system(content: str, block: str) -> str:
    """Replace the first existing ``<pnr_state>`` block, else append."""
    start = content.find(_BLOCK_OPEN)
    if start == -1:
        separator = "\n\n" if content else ""
        return f"{content}{separator}{block}"
    end = content.find(_BLOCK_CLOSE, start)
    if end == -1:
        return content[:start].rstrip() + "\n\n" + block
    end += len(_BLOCK_CLOSE)
    return content[:start].rstrip() + "\n\n" + block + content[end:].lstrip()
