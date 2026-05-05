# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Cascaded voice pipeline with Python state-machine orchestrators.

Tier-1 (fast): Nemotron-3-Nano handles greetings, PNR/flight lookups,
and dispatches multi-step intents via ``ask_deep_agent``.

Tier-2 (orchestrator): deterministic Python state machines
(booking / rebook / cancel) drive branch-point decisions through a
small Llama-8B classifier and compose every spoken reply via the
shared responder.  See ``orchestrators/`` for details.
"""
