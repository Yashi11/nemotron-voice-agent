# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Timezone resolution and time tool handlers."""

import os
from datetime import datetime
from pathlib import Path

from pipecat.services.llm_service import FunctionCallParams

# Abbreviation → human-readable display name.  Safe to use here because the
# abbreviation is derived from the system's active TZ (so "IST" in this context
# always means the locally-configured one), not parsed from user input.
_TZ_ABBR_FALLBACK = {
    "IST": "India Standard Time",
    "EST": "Eastern Standard Time",
    "EDT": "Eastern Daylight Time",
    "CST": "Central Standard Time",
    "CDT": "Central Daylight Time",
    "MST": "Mountain Standard Time",
    "MDT": "Mountain Daylight Time",
    "PST": "Pacific Standard Time",
    "PDT": "Pacific Daylight Time",
    "GMT": "Greenwich Mean Time",
    "UTC": "Coordinated Universal Time",
    "BST": "British Summer Time",
    "CET": "Central European Time",
    "JST": "Japan Standard Time",
}


def get_local_tz_name() -> str:
    """Return a human-readable timezone name for the local system.

    Prefers a spoken-form display name (e.g. "Coordinated Universal Time",
    "India Standard Time") from ``_TZ_ABBR_FALLBACK``.  Falls back to the IANA
    identifier from ``TZ`` / ``/etc/timezone`` / ``/etc/localtime`` (e.g.
    "Asia/Kolkata") when no display name is available.
    """
    abbr = datetime.now().astimezone().tzname() or ""
    if abbr in _TZ_ABBR_FALLBACK:
        return _TZ_ABBR_FALLBACK[abbr]

    tz_env = os.environ.get("TZ", "").strip()
    if tz_env:
        return tz_env

    try:
        return Path("/etc/timezone").read_text().strip()
    except OSError:
        pass

    try:
        link = str(Path("/etc/localtime").resolve())
        if "zoneinfo/" in link:
            return link.split("zoneinfo/", 1)[1]
    except OSError:
        pass

    return abbr or "Unknown"


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


async def handle_get_current_time(params: FunctionCallParams) -> None:
    """Return the current local time as a 12-hour AM/PM string."""
    # %I gives zero-padded 12-hour hour; lstrip("0") removes it portably
    # (%-I is a GNU extension that raises ValueError on non-Linux platforms).
    time_str = datetime.now().strftime("%I:%M %p").lstrip("0") or "12:00 AM"
    await params.result_callback({"time": time_str})


async def handle_get_current_date(params: FunctionCallParams) -> None:
    """Return today's date and day of the week."""
    await params.result_callback({"date": datetime.now().strftime("%A, %B %d %Y")})


async def handle_get_timezone(params: FunctionCallParams) -> None:
    """Return the local system timezone as a human-readable name."""
    await params.result_callback({"timezone_full_name": get_local_tz_name()})


TOOL_HANDLERS = {
    "get_current_time": handle_get_current_time,
    "get_current_date": handle_get_current_date,
    "get_timezone": handle_get_timezone,
}
