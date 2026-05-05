# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Per-stream key/value memory for the DeepAgent planner.

Persists loose semantic notes across turns so the DeepAgent can receive a
compact input (intent + summary + memory + canonical entities) instead of
the full fast-agent chat history.  Cuts NIM token usage per deep turn from
~1200 to ~300-500 tokens and saves a non-trivial round-trip latency.

Populated by the DeepAgent via the ``remember`` tool (see
:mod:`cascaded.agentic_airline.agent._lc_tools`).  Read by the bridge when
composing the compact input for the next deep invocation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ConversationMemory:
    """Simple string key/value notes scoped to one stream.

    Keys are free-form semantic labels (``route``, ``suggested_flight``,
    ``seat_preference``, ``confirmed_decision``, ...).  Values are strings;
    the DeepAgent formats structured data as JSON or ``a=b`` pairs if it
    wants richer shapes.
    """

    stream_id: str
    _store: dict[str, str] = field(default_factory=dict)

    def put(self, key: str, value: str) -> None:
        """Set or overwrite ``key`` → ``value``. Keys are trimmed; empty keys are ignored."""
        k = key.strip()
        if k:
            self._store[k] = value

    def get(self, key: str) -> str | None:
        """Return the value for ``key`` or ``None`` if absent."""
        return self._store.get(key.strip())

    def forget(self, key: str) -> bool:
        """Remove ``key`` if present. Returns True if something was removed."""
        return self._store.pop(key.strip(), None) is not None

    def all(self) -> dict[str, str]:
        """Snapshot of all stored pairs. Safe to embed in prompts or logs."""
        return dict(self._store)

    def is_empty(self) -> bool:
        """True when no facts have been remembered yet."""
        return not self._store
