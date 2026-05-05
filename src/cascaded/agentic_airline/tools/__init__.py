# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Fast-agent tool registry (OpenAI function-calling schema).

Only tools the fast LLM is allowed to call live here: read-only lookups
(``lookup_pnr`` / ``get_flight_status``) and the multi-step hand-off
(``ask_deep_agent``).  Deep-only mutations (rebook / cancel) happen
inside the Python orchestrators via
:mod:`cascaded.agentic_airline.tools.booking_client`, not as fast-LLM tools.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from pipecat.adapters.schemas.tools_schema import AdapterType, ToolsSchema

from cascaded.agentic_airline.tools import ask_deep_agent, pnr

if TYPE_CHECKING:
    from cascaded.agentic_airline.state.conversation_memory import ConversationMemory
    from cascaded.agentic_airline.state.entity_store import EntityStore


FAST_TOOLS: list[dict] = [
    *pnr.TOOLS,
    *ask_deep_agent.TOOLS,
]

FAST_TOOLS_SCHEMA = ToolsSchema(standard_tools=[], custom_tools={AdapterType.OPENAI: FAST_TOOLS})


def build_handlers(
    entity_store: EntityStore,
    memory: ConversationMemory,
    deep_trigger: Callable[..., Awaitable[None]],
) -> dict[str, Callable]:
    """Bind the fast-LLM handler set (read-only lookups + deep-agent hand-off).

    ``memory`` is forwarded to :mod:`cascaded.agentic_airline.tools.pnr` so a
    PNR change on ``lookup_pnr`` can reset stale orchestrator state.
    """
    return {
        **pnr.build_handlers(entity_store, memory),
        **ask_deep_agent.build_handlers(deep_trigger),
    }
