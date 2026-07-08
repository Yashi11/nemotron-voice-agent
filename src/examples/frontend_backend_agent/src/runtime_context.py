# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Runtime context helpers for the Frontend/Backend Agent."""

from __future__ import annotations

import os
from datetime import date


def runtime_today() -> date:
    """Return today's date, with an explicit override for deterministic evals."""
    override = os.getenv("FRONTEND_BACKEND_AGENT_TODAY", "").strip()
    if not override:
        return date.today()
    try:
        return date.fromisoformat(override)
    except ValueError as exc:
        raise ValueError("FRONTEND_BACKEND_AGENT_TODAY must use YYYY-MM-DD format") from exc
