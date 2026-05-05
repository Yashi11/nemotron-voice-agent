# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Fast-agent escape hatch: hand off a multi-step intent to Tier-2.

Silent hand-off: the fast LLM calls this tool with empty ``content`` per
its prompt; the handler invokes the bridge trigger, returns a bare ack,
and uses ``run_llm=False`` so pipecat does NOT re-invoke the fast LLM
after the tool result lands.  The orchestrator speaks directly to the
caller; the bridge emits a 2-second delayed filler if the orchestrator
stalls.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from pipecat.services.llm_service import FunctionCallResultProperties

if TYPE_CHECKING:
    from pipecat.services.llm_service import FunctionCallParams

DeepTrigger = Callable[..., Awaitable[None]]

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "ask_deep_agent",
            "description": (
                "Hand off a multi-step intent (rebook, cancel, booking) "
                "to the deep agent. Call with empty content; the "
                "orchestrator speaks directly to the caller. 'booking' is "
                "for a brand-new reservation; rebook and cancel operate on "
                "an existing PNR."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string", "enum": ["rebook", "cancel", "booking"]},
                    "summary": {
                        "type": "string",
                        "description": "One-sentence paraphrase of what the caller asked for.",
                    },
                },
                "required": ["intent", "summary"],
            },
        },
    },
]


def build_handlers(deep_trigger: DeepTrigger) -> dict[str, Callable]:
    """Build the ask_deep_agent handler bound to the bridge's trigger coroutine."""

    async def handle_ask_deep_agent(params: FunctionCallParams) -> None:
        intent = str(params.arguments.get("intent", "")).strip().lower()
        summary = str(params.arguments.get("summary", "")).strip()
        await deep_trigger(intent=intent, summary=summary, transcript="")
        # ``run_llm=False`` suppresses the fast LLM's follow-up turn after
        # the tool result lands, which would otherwise invent closing prose
        # on top of the orchestrator's real response.
        await params.result_callback(
            {"acknowledged": True, "intent": intent},
            properties=FunctionCallResultProperties(run_llm=False),
        )

    return {"ask_deep_agent": handle_ask_deep_agent}
