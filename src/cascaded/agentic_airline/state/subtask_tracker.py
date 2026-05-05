# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Typed per-turn subtask progression tracker.

Surfaced in the fast-agent prompt so the LLM never re-asks a field already
marked ``done``.  Drives the EVA-X Conversation Progression score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Status = Literal["pending", "in_progress", "done", "blocked"]

# Intent -> ordered subtask keys. Small table; extend as intents ship.
_CATALOG: dict[str, tuple[str, ...]] = {
    "rebook": (
        "collect_pnr",
        "confirm_flight",
        "offer_alternatives",
        "preserve_ancillaries",
        "confirm_changes",
        "collect_contact",
    ),
    "cancel": ("collect_pnr", "confirm_flight", "confirm_cancel"),
    "standby": ("collect_pnr", "check_eligibility", "confirm_standby"),
    "booking": ("collect_route", "offer_alternatives", "collect_seat", "collect_meal", "confirm_booking"),
}


@dataclass(slots=True)
class SubtaskState:
    """Tracks per-subtask progress for a single active intent."""

    intent: str
    statuses: dict[str, Status] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)

    @classmethod
    def for_intent(cls, intent: str) -> SubtaskState:
        """Build a fresh state with every catalog subtask set to ``pending``."""
        keys = _CATALOG.get(intent, ())
        return cls(intent=intent, statuses={k: "pending" for k in keys})

    def mark(self, subtask: str, status: Status, note: str = "") -> None:
        """Update a subtask's status and optionally record a note."""
        if subtask not in self.statuses:
            raise KeyError(f"Unknown subtask {subtask!r} for intent {self.intent!r}")
        self.statuses[subtask] = status
        if note:
            self.notes[subtask] = note

    def next_pending(self) -> str | None:
        """Return the first ``pending`` subtask in catalog order, else ``None``."""
        for key in _CATALOG.get(self.intent, ()):
            if self.statuses.get(key) == "pending":
                return key
        return None

    def is_done(self) -> bool:
        """True when every catalog subtask is ``done``."""
        keys = _CATALOG.get(self.intent, ())
        return bool(keys) and all(self.statuses.get(k) == "done" for k in keys)

    def prompt_summary(self) -> str:
        """Compact one-line summary for injection into the fast-agent prompt."""
        keys = _CATALOG.get(self.intent, ())
        if not keys:
            return self.intent
        items = " ".join(f"{k}={self.statuses[k]}" for k in keys)
        return f"{self.intent}: {items}"


def supported_intents() -> tuple[str, ...]:
    """Return the intents for which a subtask catalog is registered."""
    return tuple(_CATALOG.keys())
