# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Shared helpers for Omni subagents."""

from __future__ import annotations

from typing import Any

_USER_INTENT_VALUES = frozenset({"idle", "showing_object", "stop_signal", "engaged", "leaving"})


def normalize_user_intent(value: Any) -> str:
    """Coerce user intent to a supported enum value."""
    candidate = str(value or "idle").strip().lower().replace("-", "_").replace(" ", "_")
    return candidate if candidate in _USER_INTENT_VALUES else "idle"


def normalize_visual_control(payload: Any) -> dict[str, Any]:
    """Normalize model-scored visual-control intent into a stable schema."""
    record = payload if isinstance(payload, dict) else {}
    intent = str(record.get("intent") or "none").strip().lower()
    if intent not in {"none", "stop", "continue"}:
        intent = "none"
    try:
        confidence = float(record.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    reason = str(record.get("reason") or "").strip()
    return {
        "intent": intent,
        "confidence": min(1.0, max(0.0, confidence)),
        "reason": reason,
    }
