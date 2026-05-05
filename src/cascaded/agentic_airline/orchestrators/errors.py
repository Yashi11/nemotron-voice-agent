# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Exceptions raised by the orchestrators package."""

from __future__ import annotations


class OrchestratorFallback(Exception):
    """Raised when the state machine can't confidently handle a turn.

    The bridge catches this and emits a graceful LLM-composed apology
    to the caller.  Reasons include: an unknown step name, two
    consecutive ambiguous classifications, or a backend return value
    the orchestrator didn't plan for.

    Optionally carries a ``new_intent`` set by the turn analyzer when
    the caller has pivoted (e.g. mid-rebook → cancel).  The bridge
    catches the fallback and re-spawns an orchestrator for the new
    intent in the same turn instead of speaking the apology.
    """

    def __init__(self, message: str = "", *, new_intent: str | None = None) -> None:
        """Build a fallback carrying optional pivot target ``new_intent``."""
        super().__init__(message)
        self.new_intent = new_intent
