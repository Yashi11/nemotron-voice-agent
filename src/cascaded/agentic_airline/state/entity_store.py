# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Per-stream canonical entity store for PNRs, flight numbers, and dollar amounts.

On each ASR hit for a high-stakes entity, the store records the canonical
value with its confidence and any heard-spelling variants.  Later tool
calls and the DeepAgent read from the store rather than scanning chat
history, which eliminates the dominant EVA-A failure mode of entity drift
across multi-turn conversations.

Pipecat frames run on a single asyncio loop per stream, so reads and writes
are atomic between ``await`` points — no lock required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

EntityKind = Literal["pnr", "flight_number", "dollar_amount", "confirmation_code", "last4_card"]


@dataclass(slots=True)
class Entity:
    """A canonical entity captured from ASR, with spelling variants and confirmation state."""

    kind: EntityKind
    value: str
    confidence: float
    heard: list[str] = field(default_factory=list)
    confirmed: bool = False


class EntityStore:
    """Canonical entity store keyed by :class:`EntityKind`, scoped to one stream."""

    __slots__ = ("stream_id", "_entities")

    def __init__(self, stream_id: str) -> None:
        """Create an empty store bound to ``stream_id``."""
        self.stream_id = stream_id
        self._entities: dict[EntityKind, Entity] = {}

    def put(self, kind: EntityKind, value: str, confidence: float, heard: str | None = None) -> Entity:
        """Record or refine the canonical value for ``kind``.

        Same-value writes with equal-or-lower confidence are treated as
        refinements — the previous reading is retained in ``heard``.  A
        *different* value always wins (the caller is referring to a new
        entity, not restating the old one), which keeps a second
        ``lookup_pnr`` on a different PNR from silently sticking to the
        first one.
        """
        existing = self._entities.get(kind)
        incoming = [heard] if heard else []
        if existing and existing.value == value and existing.confidence >= confidence:
            existing.heard.extend(incoming)
            return existing
        rolled_forward = [existing.value, *existing.heard, *incoming] if existing else incoming
        entity = Entity(kind=kind, value=value, confidence=confidence, heard=rolled_forward)
        self._entities[kind] = entity
        return entity

    def forget(self, kind: EntityKind) -> bool:
        """Remove the canonical entry for ``kind`` if present."""
        return self._entities.pop(kind, None) is not None

    def get(self, kind: EntityKind) -> Entity | None:
        """Return the canonical entity for ``kind`` or ``None`` if unseen."""
        return self._entities.get(kind)

    def confirm(self, kind: EntityKind) -> Entity | None:
        """Mark ``kind`` as caller-confirmed. Returns the entity, or ``None`` if absent."""
        entity = self._entities.get(kind)
        if entity is not None:
            entity.confirmed = True
        return entity

    def as_dict(self) -> dict[str, dict]:
        """Serialize for prompts, logs, or LangGraph state snapshots."""
        return {
            kind: {
                "value": e.value,
                "confidence": e.confidence,
                "confirmed": e.confirmed,
                "heard": list(e.heard),
            }
            for kind, e in self._entities.items()
        }
