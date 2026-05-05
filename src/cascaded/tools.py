# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Tool definitions, schemas, and handlers for the cascaded pipeline."""

from pipecat.adapters.schemas.tools_schema import AdapterType, ToolsSchema

from utils import TOOL_HANDLERS as TOOL_HANDLERS  # noqa: F401

# ---------------------------------------------------------------------------
# Tool definitions  (OpenAI function-calling schema)
# ---------------------------------------------------------------------------

_NO_PARAMS: dict = {"type": "object", "properties": {}, "required": []}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": ("Returns the exact current local time. Use this whenever the user asks what time it is."),
            "parameters": _NO_PARAMS,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_date",
            "description": (
                "Returns today's exact date and day of the week. "
                "Use this whenever the user asks what date or day it is."
            ),
            "parameters": _NO_PARAMS,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_timezone",
            "description": (
                "Returns the system timezone. Use this whenever the user asks about their timezone or location."
            ),
            "parameters": _NO_PARAMS,
        },
    },
]

# AdapterType.OPENAI passes the list through to NvidiaLLMService (OpenAI-compatible).
_TOOLS_SCHEMA = ToolsSchema(standard_tools=[], custom_tools={AdapterType.OPENAI: TOOLS})
