# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Declarative state-machine runner for the per-intent orchestrators.

Each intent declares:

* :class:`StateSpec` — one per state, with ``allowed_next``, a short
  ``purpose`` the fused-call LLM reads, and the subset of tools that
  make sense from this state.
* :class:`ToolSpec` — a callable backend action with a JSON-schema
  ``params`` definition the LLM fills.

The runner exposes :func:`run_state` which executes exactly one caller
turn:

1. **Fused LLM call** — decides ``stay`` / ``pivot`` / ``abandon`` and,
   when staying, picks ``next_state``, an optional ``tool_name`` +
   ``tool_params``, and a ``response_instruction`` for the responder.
2. **Tool execution** — runs the tool (if any), validates params.
3. **Responder LLM call** — composes the spoken sentence from
   ``response_instruction`` + ``response_facts`` (+ tool result).

State transitions are enforced against ``allowed_next`` so the LLM
can't skip required steps.  Tool params are validated against the
schema so a hallucinated empty value doesn't reach the backend.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any

from loguru import logger

from cascaded.agentic_airline.orchestrators._intent_classifier import classify_turn
from cascaded.agentic_airline.orchestrators._llm import ainvoke_text
from cascaded.agentic_airline.orchestrators._responder import generate_response
from cascaded.agentic_airline.orchestrators.errors import OrchestratorFallback

ToolExecutor = Callable[..., Awaitable[Any]]
ToolParamResolver = Callable[["TurnContext", "StateDecision"], dict[str, Any] | None]


@dataclass(slots=True, frozen=True)
class ToolSpec:
    """Declarative tool definition exposed to the fused LLM."""

    name: str
    description: str
    params: dict  # JSON schema for the tool's input
    execute: ToolExecutor
    # Optional in-process result transformer.  Runs AFTER the tool
    # returns and BEFORE ``_build_response_facts`` sees the value, so
    # intent-specific filtering (e.g. standby dropping later flights
    # from the shared list_alternatives tool) reaches the responder.
    # Receives (raw_result, collected_dict) and returns the shaped
    # result the runner uses from here on.
    post_process: Callable[[Any, dict], Any] | None = None
    # Optional param resolver that derives authoritative tool params
    # from canonical state after the LLM has decided WHAT to do. This
    # lets the LLM own semantics (restart, pick AA502, economy) while
    # the runner owns execution payloads for fragile tools.
    param_resolver: ToolParamResolver | None = None


@dataclass(slots=True, frozen=True)
class StateSpec:
    """Declarative state definition."""

    name: str
    purpose: str
    allowed_next: tuple[str, ...]  # names of legal next states (may include self)
    # Tool names (must match ToolSpec.name in the intent table) that
    # are particularly relevant from this state.  Cross-intent tools
    # come from the intent's ``always_available_tools``.
    preferred_tools: tuple[str, ...] = ()
    # Short directive the fused LLM should USE VERBATIM as
    # ``response_instruction`` when entering/leaving this state.  Lets
    # per-state guidance live next to the state itself instead of in a
    # monolithic system prompt — the LLM only ever sees the hint for
    # the state it's currently in.
    response_hint: str = ""


@dataclass(slots=True, frozen=True)
class IntentSpec:
    """All state + tool declarations for one intent."""

    name: str  # "rebook" / "cancel" / ...
    entry_state: str
    terminal_states: frozenset[str]
    states: dict[str, StateSpec]
    tools: dict[str, ToolSpec]
    # Tools always available from any state (cross-intent reads like
    # list_routes / lookup_pnr / get_flight_status).
    always_available: tuple[str, ...] = ()
    # Per-intent post-tool transition map: tool_name → (success_state,
    # empty_state).  Keeps safety rails intent-aware so the same tool
    # (``list_alternatives`` in rebook vs. booking) can route to
    # different downstream states.  Absent entries = no override; the
    # LLM's ``next_state`` stands.
    tool_transitions: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    # Intent-scoped tool-selection cheat sheet that gets rendered into
    # the fused LLM's user prompt for turns under THIS intent.  Keeps
    # the system prompt generic; only the relevant guidance reaches the
    # model per turn.
    prompt_examples: str = ""
    # What the runner stashes into memory under the step-key after a
    # successful transition.  Defaults to the state name.
    step_key: str | None = None  # None → ``f"{name}_step"``
    # Linear progression rank for rollback-aware flows. When a turn
    # moves from a higher-rank state to an equal-or-lower-rank state,
    # runner-owned cleanup forgets slots owned by the target state and
    # every later state before the orchestrator persists new answers.
    state_ranks: dict[str, int] = field(default_factory=dict)
    # Slots owned by each state. Used only for runner-planned rollback
    # cleanup; the orchestrator still persists the actual slot_updates.
    state_slot_ownership: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Transient entities that belong to the current flow rather than a
    # durable caller identity. Cleared on rollback / restart.
    flow_scoped_entities: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class TurnContext:
    """Everything the runner needs to execute one caller turn."""

    intent: IntentSpec
    current_state: str
    transcript: str
    collected: dict[str, Any]  # already-known data to show the LLM
    history: list[dict[str, str]]  # [{"role": "caller"|"agent", "content": ...}]
    record: dict | None  # PNR record (may be None at entry states)
    # Pipeline stream_id stamped on every backend mutation so
    # ``activity_log.session_id`` correlates the audit trail with the
    # voice session.  Injected into known mutation tool calls inside
    # ``_invoke_tool``; LLM-authored params never see this field.
    session_id: str | None = None


@dataclass(slots=True, frozen=True)
class StateDecision:
    """Parsed output of the fused LLM call."""

    action: str  # "stay" | "abandon"
    next_state: str | None
    tool_name: str | None
    tool_params: dict
    response_instruction: str
    response_facts: dict[str, Any]
    slot_updates: dict[str, Any] = field(default_factory=dict)
    reset_scope: str | None = None


@dataclass(slots=True, frozen=True)
class CleanupPlan:
    """Post-response cleanup the orchestrator should apply atomically."""

    forget_keys: tuple[str, ...] = ()
    forget_entities: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class StateRunResult:
    """Outcome of one :func:`run_state` turn."""

    sentence: str
    next_state: str
    tool_name: str | None
    tool_result: Any
    decision: StateDecision
    cleanup_plan: CleanupPlan = field(default_factory=CleanupPlan)


# One short sentence per pivot target; kept here (not LLM-composed) so
# the filler emits immediately while the new-intent runner spins up.
_PIVOT_FILLER = {
    "rebook": "Let me restart your rebook — one moment.",
    "cancel": "Sure, switching to cancellation — one moment.",
    "booking": "Sure, let's set up a new booking — one moment.",
}

_VALID_RESET_SCOPES = frozenset({"intent_flow"})

# Keys the responder pulls from tool output — never overwrite them with
# LLM-supplied response_facts hints, which can hallucinate a value.
_RESPONSE_FACT_BLOCKED_KEYS = frozenset(
    {
        "flight_number",
        "flight",
        "departure",
        "departure_time",
        "arrival",
        "destination",
        "origin",
        "confirmation_code",
        "alternatives",
        "tool_result",
    }
)


def pivot_filler(new_intent: str) -> str:
    """Return the pre-templated filler spoken when pivoting to ``new_intent``."""
    return _PIVOT_FILLER.get(new_intent, "Switching gears — one moment.")


async def run_state(ctx: TurnContext) -> StateRunResult:
    """Run one caller turn through the 3-LLM pipeline.

    * **Call 1 (classifier)** decides stay / pivot / abandon.  Only the
      classifier knows about other flows; a pivot raises
      :class:`OrchestratorFallback` with ``new_intent`` so the bridge
      re-spawns cleanly under the new flow.
    * **Call 2 (orchestrator)** runs only on stay.  Its prompt sees
      ONLY this flow's states / tools — no cross-intent mentions — so
      it can't mis-pivot on ambiguous utterances.
    * **Call 3 (responder)** is the existing
      :func:`generate_response` — turns the orchestrator's directive +
      live tool output into one spoken sentence.

    Abandon skips the orchestrator and only runs the responder.
    """
    # --- Call 1: intent classifier ---
    state_spec = ctx.intent.states[ctx.current_state]
    classifier = await classify_turn(
        current_intent=ctx.intent.name,
        current_state=ctx.current_state,
        state_purpose=state_spec.purpose,
        transcript=ctx.transcript,
        history=ctx.history,
    )

    if classifier.action == "pivot" and classifier.new_intent and classifier.new_intent != ctx.intent.name:
        logger.info(
            f"state_runner: pivot {ctx.intent.name!r} → {classifier.new_intent!r} "
            f"from state {ctx.current_state!r} (classifier)"
        )
        raise OrchestratorFallback(
            f"caller pivoted from {ctx.intent.name} to {classifier.new_intent}",
            new_intent=classifier.new_intent,
        )

    if classifier.action == "abandon":
        logger.info(f"state_runner: abandon on {ctx.intent.name!r}/{ctx.current_state!r} (classifier)")
        sentence = await generate_response(
            "The caller asked to stop or never mind. Acknowledge briefly "
            "and ask if there is anything else you can help with.",
            {},
        )
        # Build a minimal decision for the result record; callers
        # sometimes read ``result.decision.slot_updates`` for persistence.
        abandon_decision = StateDecision(
            action="abandon",
            next_state=ctx.current_state,
            tool_name=None,
            tool_params={},
            response_instruction="",
            response_facts={},
            slot_updates={},
            reset_scope=None,
        )
        return StateRunResult(
            sentence=sentence,
            next_state=ctx.current_state,
            tool_name=None,
            tool_result=None,
            decision=abandon_decision,
        )

    # --- Call 2: orchestrator (intent-scoped) ---
    decision = await _orchestrator_call(ctx)

    # stay path — validate next_state
    state_spec = ctx.intent.states[ctx.current_state]
    allowed = set(state_spec.allowed_next) | {ctx.current_state}
    next_state = decision.next_state or ctx.current_state
    invalid_next_state = False
    if next_state not in allowed:
        logger.warning(
            f"state_runner: LLM picked illegal next_state {next_state!r} from "
            f"{ctx.current_state!r}; allowed={sorted(allowed)}; staying"
        )
        next_state = ctx.current_state
        invalid_next_state = True

    decision = _resolve_tool_params(ctx, decision)
    if decision.tool_name:
        spec = ctx.intent.tools.get(decision.tool_name)
        if spec is not None and not _has_required_tool_params(spec, decision.tool_params):
            logger.warning(
                f"state_runner: missing required params for tool {decision.tool_name!r} "
                f"after resolution; staying in {ctx.current_state!r}"
            )
            fallback = _fallback_decision(ctx)
            decision = replace(
                fallback,
                slot_updates=decision.slot_updates,
                reset_scope=decision.reset_scope,
            )
            next_state = ctx.current_state

    tool_result: Any = None
    if decision.tool_name:
        tool_result = await _invoke_tool(
            ctx.intent, decision.tool_name, decision.tool_params, ctx.collected, session_id=ctx.session_id
        )
        spec = ctx.intent.tools.get(decision.tool_name)
        if spec is not None and spec.post_process is not None and tool_result is not None:
            try:
                tool_result = spec.post_process(tool_result, ctx.collected)
            except Exception as exc:  # noqa: BLE001 — keep serving the caller
                logger.warning(f"state_runner: post_process for {decision.tool_name!r} failed: {exc}")

    # Deterministic post-tool transitions.  Specific tool outcomes imply
    # a specific next state regardless of what the LLM picked — these
    # are safety rails, not speculative steering.  Kept intent-agnostic
    # so the runner stays reusable; the intent's state graph already
    # names these steps so we look them up by convention.
    next_state = _force_transition_after_tool(
        ctx.intent,
        next_state,
        decision,
        tool_result,
        ctx.collected,
    )
    cleanup_plan = _build_cleanup_plan(
        ctx.intent,
        ctx.current_state,
        next_state,
        decision.reset_scope,
    )

    # Authoritative facts come from the runner, NOT the LLM — the LLM is
    # great at choosing tools but routinely hallucinates flight numbers
    # and times when it invents ``response_facts`` values.  We rebuild
    # facts from Collected (trustworthy state) + the real tool_result.
    facts = _build_response_facts(ctx, decision, tool_result)

    # Harden against confirmation-code / flight-number hallucination when a
    # tool was supposed to produce them but returned nothing.  The
    # responder must acknowledge the failure instead of inventing a value.
    instruction = decision.response_instruction or "Speak the most helpful next sentence based on the facts provided."
    # When we transitioned to a new state AND the LLM didn't supply a
    # response_instruction of its own, fall back to the NEW state's
    # response_hint.  Trust the LLM's instruction when it wrote one —
    # it understands the caller's specific turn better than the static
    # state hint, e.g. a decline at showed_terms should read "acknowledge
    # the caller kept the booking", which the LLM will phrase itself,
    # and we shouldn't clobber that with the state's generic "cancellation
    # complete" hint.
    if next_state != ctx.current_state and not decision.response_instruction:
        target_hint = ctx.intent.states.get(next_state)
        if target_hint and target_hint.response_hint:
            instruction = target_hint.response_hint
    # Read-back for state-preserving side queries: list_routes /
    # get_flight_status / lookup_pnr shouldn't advance state, but they
    # return data the caller asked for.  Override the instruction so
    # the responder actually reads that data back instead of reusing
    # the state's generic prompt.
    if decision.tool_name and not _tool_result_is_empty(tool_result):
        success_override = _tool_success_instruction(decision.tool_name)
        if success_override is not None:
            instruction = success_override
    if decision.tool_name and _tool_result_is_empty(tool_result):
        instruction = _empty_result_instruction(decision.tool_name, decision.tool_params)
    if invalid_next_state and not decision.tool_name and state_spec.response_hint:
        instruction = state_spec.response_hint

    sentence = await generate_response(instruction, facts)

    return StateRunResult(
        sentence=sentence,
        next_state=next_state,
        tool_name=decision.tool_name,
        tool_result=tool_result,
        decision=decision,
        cleanup_plan=cleanup_plan,
    )


def apply_cleanup_plan(plan: CleanupPlan, memory, entity_store) -> None:
    """Apply a runner-computed cleanup plan after the caller heard the turn."""
    for key in plan.forget_keys:
        memory.forget(key)
    for kind in plan.forget_entities:
        entity_store.forget(kind)


def reset_intent_flow(intent: IntentSpec, memory, entity_store) -> None:
    """Forget all flow-owned scratch for one intent, preserving durable entities."""
    for key in _intent_flow_memory_keys(intent):
        memory.forget(key)
    for kind in intent.flow_scoped_entities:
        entity_store.forget(kind)


def _resolve_tool_params(ctx: TurnContext, decision: StateDecision) -> StateDecision:
    """Replace LLM-authored tool params with authoritative runner-derived values."""
    if decision.tool_name is None:
        return decision
    spec = ctx.intent.tools.get(decision.tool_name)
    if spec is None or spec.param_resolver is None:
        return decision
    try:
        resolved = spec.param_resolver(ctx, decision)
    except Exception as exc:  # noqa: BLE001 - keep caller unblocked
        logger.warning(f"state_runner: param_resolver for {decision.tool_name!r} failed: {exc}")
        return replace(decision, tool_params={})
    if not isinstance(resolved, dict):
        resolved = {}
    return replace(decision, tool_params=resolved)


def _has_required_tool_params(spec: ToolSpec, params: dict[str, Any]) -> bool:
    """Return True when every schema-required param has a usable value."""
    required = spec.params.get("required")
    if not isinstance(required, list):
        return True
    for key in required:
        value = params.get(key)
        if value in (None, ""):
            return False
    return True


def _build_cleanup_plan(
    intent: IntentSpec,
    current_state: str,
    next_state: str,
    reset_scope: str | None = None,
) -> CleanupPlan:
    """Plan slot/entity cleanup for backward moves inside one intent."""
    if reset_scope == "intent_flow":
        return CleanupPlan(
            forget_keys=_intent_flow_memory_keys(intent),
            forget_entities=intent.flow_scoped_entities,
        )
    if current_state == next_state:
        return CleanupPlan()
    ranks = intent.state_ranks or {}
    if current_state not in ranks or next_state not in ranks:
        return CleanupPlan()
    current_rank = ranks[current_state]
    next_rank = ranks[next_state]
    if next_rank > current_rank:
        return CleanupPlan()

    forget_keys: list[str] = []
    ownership = intent.state_slot_ownership or {}
    for state_name, rank in sorted(ranks.items(), key=lambda item: item[1]):
        if next_rank <= rank <= current_rank:
            forget_keys.extend(ownership.get(state_name, ()))
    return CleanupPlan(
        forget_keys=tuple(_dedupe_preserve_order(forget_keys)),
        forget_entities=intent.flow_scoped_entities,
    )


def _intent_flow_memory_keys(intent: IntentSpec) -> tuple[str, ...]:
    """Return the union of all flow-owned memory keys for ``intent``."""
    keys: list[str] = []
    for state_name, _rank in sorted(
        (intent.state_ranks or {}).items(),
        key=lambda item: item[1],
    ):
        keys.extend((intent.state_slot_ownership or {}).get(state_name, ()))
    return tuple(_dedupe_preserve_order(keys))


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    """Return ``values`` with duplicates removed, keeping first occurrence."""
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


_MUTATION_TOOLS_TAKING_SESSION_ID = frozenset({"commit_rebook", "cancel_booking", "create_booking", "list_standby"})


async def _invoke_tool(
    intent: IntentSpec,
    name: str,
    params: dict,
    collected: dict | None = None,
    session_id: str | None = None,
) -> Any:
    """Look up + execute a tool, surfacing errors as log warnings + None.

    Applies pre-flight guards that catch LLM mistakes before they hit
    the backend:

    - ``list_alternatives`` with origin == destination → refuse.
    - ``list_routes`` with both or neither of origin/destination → refuse.
    - ``list_alternatives`` with a route already covered by
      ``Collected.alternatives_snapshot`` → return the cached snapshot
      instead of re-fetching.  Stops the LLM from looping on the same
      tool call while ALSO picking a flight in the same turn, which
      would otherwise trigger a backward state-force.
    """
    tool = intent.tools.get(name)
    if tool is None:
        logger.warning(f"state_runner: unknown tool {name!r}; ignoring")
        return None
    p = params or {}
    if name == "list_alternatives":
        origin = (p.get("origin") or "").strip().upper()
        destination = (p.get("destination") or "").strip().upper()
        if origin and destination and origin == destination:
            logger.warning(f"state_runner: list_alternatives called with origin == destination ({origin!r}); refusing")
            return []
        snapshot = (collected or {}).get("alternatives_snapshot")
        if isinstance(snapshot, list) and snapshot:
            snap_origin = str(snapshot[0].get("origin", "")).upper()
            snap_destination = str(snapshot[0].get("destination", "")).upper()
            if snap_origin == origin and snap_destination == destination:
                logger.info(
                    "state_runner: reusing cached alternatives_snapshot "
                    f"for {origin}->{destination}; skipping list_alternatives"
                )
                return snapshot
    if name == "list_routes":
        has_origin = bool((p.get("origin") or "").strip())
        has_destination = bool((p.get("destination") or "").strip())
        if has_origin == has_destination:
            logger.warning(f"state_runner: list_routes requires exactly one of origin / destination; got {p}; refusing")
            return []
    # Inject session_id outside the LLM-authored params so mutations
    # stamp activity_log.session_id with the pipeline stream_id.
    if session_id and name in _MUTATION_TOOLS_TAKING_SESSION_ID:
        p = {**p, "session_id": session_id}
    try:
        return await tool.execute(**p)
    except Exception as exc:  # noqa: BLE001 — surface to responder as 'unavailable'
        logger.warning(f"state_runner: tool {name!r} failed: {exc}")
        return {"error": str(exc)}


def _compact_result(result: Any) -> Any:
    """Best-effort trim so large lists don't blow the responder's prompt."""
    if isinstance(result, list):
        return result[:8]
    return result


# Short speakable names the responder uses when listing airport codes.
# Extend as new markets come online; codes not in this map fall back
# to the code itself (still readable, just less friendly).
_AIRPORT_CITY_NAMES = {
    "JFK": "New York JFK",
    "LGA": "New York LaGuardia",
    "EWR": "Newark Liberty",
    "LAX": "Los Angeles",
    "SFO": "San Francisco",
    "SJC": "San Jose",
    "ORD": "Chicago O'Hare",
    "MDW": "Chicago Midway",
    "ATL": "Atlanta",
    "BOS": "Boston Logan",
    "DFW": "Dallas Fort Worth",
    "DCA": "Washington Reagan",
    "IAD": "Washington Dulles",
    "BWI": "Baltimore Washington",
    "SEA": "Seattle",
    "PDX": "Portland",
    "DEN": "Denver",
    "MIA": "Miami",
    "FLL": "Fort Lauderdale",
    "PHX": "Phoenix",
    "LAS": "Las Vegas",
    "MSP": "Minneapolis Saint Paul",
    "IAH": "Houston Intercontinental",
    "HOU": "Houston Hobby",
    "CLT": "Charlotte",
    "LHR": "London Heathrow",
    "CDG": "Paris Charles de Gaulle",
    "FRA": "Frankfurt",
    "NRT": "Tokyo Narita",
    "HND": "Tokyo Haneda",
    "YYZ": "Toronto Pearson",
    "MEX": "Mexico City",
}


def _force_transition_after_tool(
    intent: IntentSpec,
    requested: str,
    decision: StateDecision,
    tool_result: Any,
    collected: dict,
) -> str:
    """Apply safety rails on tool-outcome → next-state mapping.

    Reads from ``intent.tool_transitions`` so the same tool can route
    to different downstream states depending on the active intent —
    ``list_alternatives`` goes to ``offered_alternative`` in rebook but
    ``offered_standby`` in standby.

    Honors the LLM's choice when progress has ALREADY been made earlier
    in the flow.  ``_FORWARD_PROGRESS_SLOTS`` lists slots (from THIS
    turn's ``slot_updates`` OR from ``Collected``) that mean the tool's
    default target state is stale — e.g. once ``suggested_flight`` is
    picked, re-calling ``list_alternatives`` should NOT rewind the flow
    back to ``offered_alternative``.  This catches the case where the
    LLM unhelpfully re-invokes the same tool on every subsequent turn
    while the caller is answering seat / meal prompts.
    """
    tool_name = decision.tool_name
    if tool_name is None or not intent.tool_transitions:
        return requested
    mapping = intent.tool_transitions.get(tool_name)
    if mapping is None:
        return requested
    success_state, empty_state = mapping
    empty = _tool_result_is_empty(tool_result)
    target = empty_state if empty else success_state
    if target and target in intent.states:
        # Honor LLM forward progress when progress has been made this
        # turn OR earlier in the flow.
        if (
            not empty
            and requested != target
            and requested in intent.states
            and _progress_made(decision, tool_name, collected)
        ):
            logger.info(
                f"state_runner: honoring LLM's forward state {requested!r} "
                f"(tool {tool_name!r} default target {target!r}); progress "
                "already made (slot_updates or Collected)"
            )
            return requested
        if target != requested:
            logger.info(f"state_runner: forcing post-{tool_name} transition → {target!r} (LLM picked {requested!r})")
        return target
    return requested


_FORWARD_PROGRESS_SLOTS = {
    "list_alternatives": ("suggested_flight",),
}

_SLOT_MEAL_SPOKEN = {
    "VGML": "vegetarian",
    "VLML": "vegetarian",
    "NVML": "non-vegetarian",
    "KSML": "kosher",
    "MOML": "halal",
    "GFML": "gluten-free",
    "vegetarian": "vegetarian",
    "non_vegetarian": "non-vegetarian",
    "non-vegetarian": "non-vegetarian",
    "vegan": "vegan",
    "kosher": "kosher",
    "halal": "halal",
    "gluten_free": "gluten-free",
    "gluten-free": "gluten-free",
    "none": "none",
    "keep": "(keep existing)",
}

_KEEP_SLOT_VALUES = frozenset({"keep", "same", "no_change", "existing", "unchanged"})
_NON_SPECIFIC_SEAT_VALUES = frozenset({"any", "no_preference", "no preference", "agent_choice"})
_VALID_CABIN_VALUES = frozenset({"economy", "premium_economy", "business", "first"})
_CANONICAL_MEAL_VALUES = {
    "vgml": "vegetarian",
    "vlml": "vegetarian",
    "nvml": "non_vegetarian",
    "ksml": "kosher",
    "moml": "halal",
    "gfml": "gluten_free",
    "vegetarian": "vegetarian",
    "non_vegetarian": "non_vegetarian",
    "non vegetarian": "non_vegetarian",
    "non-vegetarian": "non_vegetarian",
    "vegan": "vegan",
    "kosher": "kosher",
    "halal": "halal",
    "gluten_free": "gluten_free",
    "gluten free": "gluten_free",
    "gluten-free": "gluten_free",
    "none": "none",
    "keep": "keep",
    "same": "keep",
    "no_change": "keep",
    "existing": "keep",
    "unchanged": "keep",
}


def _normalized_meal_slot(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    key = value.strip().lower()
    return _CANONICAL_MEAL_VALUES.get(key)


def _progress_made(decision: StateDecision, tool_name: str, collected: dict) -> bool:
    """True when a sentinel slot is set — either this turn or already in Collected.

    Checking ``Collected`` catches the case where the LLM picked the
    flight on a prior turn (``suggested_flight`` landed in memory) and
    the caller has moved on to seat / meal; re-firing
    ``list_alternatives`` now would otherwise rewind the state.
    """
    sentinel_slots = _FORWARD_PROGRESS_SLOTS.get(tool_name, ())
    if not sentinel_slots:
        return False
    slots = decision.slot_updates or {}
    coll = collected or {}
    return any(slots.get(k) or coll.get(k) for k in sentinel_slots)


def _build_response_facts(ctx: TurnContext, decision: StateDecision, tool_result: Any) -> dict:
    """Deterministic facts for the responder — never trust LLM-invented values.

    Pulls from:

    * ``tool_result`` for live backend data (verbatim).
    * ``ctx.collected`` for known booking state.
    * ``decision.response_facts`` as *hints only* — we accept scalar
      strings that look like labels/topics but drop any keys that would
      duplicate or conflict with live data (flight numbers, times,
      origins, destinations, codes).

    This is the single biggest lever against voice-agent hallucination:
    the LLM decided a tool + params, it does not get to make up what
    the tool returned.
    """
    facts: dict = {}

    # Start with trustworthy collected data (full PNR, stashed choices).
    for key, value in ctx.collected.items():
        facts[key] = value

    # Overlay live tool output — the freshest ground truth.
    if decision.tool_name == "list_alternatives" and isinstance(tool_result, list):
        alts = [
            {
                "flight_number": a.get("flight_number"),
                "departure": a.get("departure"),
                "origin": a.get("origin"),
                "destination": a.get("destination"),
                "cabin": a.get("cabin"),
            }
            for a in tool_result[:4]
            if a.get("flight_number")
        ]
        if alts:
            facts["offered_alternatives"] = alts
            facts["new_origin"] = alts[0].get("origin")
            facts["new_destination"] = alts[0].get("destination")
    elif decision.tool_name == "list_routes" and isinstance(tool_result, list):
        codes = [r.get("code") for r in tool_result if r.get("code")]
        if codes:
            facts["available_airport_codes"] = codes
            # Emit "City (CODE)" strings so the responder reads recognisable
            # names back to the caller instead of bare IATA codes.
            facts["airport_names"] = [f"{_AIRPORT_CITY_NAMES.get(c, c)} ({c})" for c in codes]
    elif decision.tool_name == "ancillaries_diff" and isinstance(tool_result, dict):
        facts["ancillaries_diff"] = tool_result
    elif decision.tool_name in {
        "commit_rebook",
        "cancel_booking",
        "create_booking",
    } and isinstance(tool_result, dict):
        # All mutation tools mint a confirmation code the caller must
        # hear verbatim — surface it + the action label so the
        # responder doesn't conflate intents ("rebooked" vs "cancelled").
        code = tool_result.get("confirmation_code")
        if code:
            facts["confirmation_code"] = code
        facts["mutation_action"] = {
            "commit_rebook": "rebooked",
            "cancel_booking": "cancelled",
            "create_booking": "booked",
        }[decision.tool_name]
        if decision.tool_name == "commit_rebook" and tool_result.get("new_flight_number"):
            facts["committed_flight"] = tool_result["new_flight_number"]
        if decision.tool_name == "create_booking":
            if tool_result.get("pnr"):
                facts["new_pnr"] = tool_result["pnr"]
            if tool_result.get("price"):
                facts["price"] = tool_result["price"]
            if tool_result.get("currency"):
                facts["currency"] = tool_result["currency"]
    elif decision.tool_name == "price_quote" and isinstance(tool_result, dict):
        if tool_result.get("price"):
            facts["price"] = tool_result["price"]
        if tool_result.get("currency"):
            facts["currency"] = tool_result["currency"]
        if tool_result.get("cabin"):
            facts["booked_cabin"] = tool_result["cabin"]
    elif decision.tool_name == "get_flight_status" and isinstance(tool_result, dict):
        facts["queried_flight_status"] = {
            "flight_number": tool_result.get("flight_number"),
            "status": tool_result.get("status"),
            "delay_minutes": tool_result.get("delay_minutes"),
            "departure": tool_result.get("departure"),
        }
    elif decision.tool_name == "lookup_pnr" and isinstance(tool_result, dict):
        # Mostly overlaps collected; nothing new to merge.
        pass

    # Accept scalar string hints from the LLM (topic labels, slot
    # confirmations) but reject any key the tool layer owns.
    for key, value in (decision.response_facts or {}).items():
        if key in _RESPONSE_FACT_BLOCKED_KEYS:
            continue
        if key in facts:
            continue
        if isinstance(value, (str, int, float, bool)):
            facts[key] = value

    _overlay_slot_updates_into_facts(facts, decision, ctx.collected)

    return facts


def _overlay_slot_updates_into_facts(facts: dict, decision: StateDecision, collected: dict) -> None:
    """Let the responder see caller choices from THIS turn before memory is persisted."""
    updates = decision.slot_updates or {}
    if not updates:
        return

    for key, value in updates.items():
        if value in (None, ""):
            continue
        if key == "meal_pref":
            meal = _normalized_meal_slot(value)
            if meal is None:
                continue
            value = meal
        if key == "requested_cabin":
            cabin = str(value).strip().lower()
            if cabin not in _VALID_CABIN_VALUES:
                continue
            value = cabin
        facts[key] = value

    origin = updates.get("new_origin")
    if origin:
        facts["new_origin_spoken"] = _AIRPORT_CITY_NAMES.get(str(origin).upper(), str(origin))
    destination = updates.get("new_destination")
    if destination:
        facts["new_destination_spoken"] = _AIRPORT_CITY_NAMES.get(str(destination).upper(), str(destination))

    seat_pref = updates.get("seat_pref")
    if seat_pref and str(seat_pref).lower() not in (_KEEP_SLOT_VALUES | _NON_SPECIFIC_SEAT_VALUES):
        facts["proposed_seat"] = seat_pref

    meal_pref = updates.get("meal_pref")
    if meal_pref:
        normalized_meal = _normalized_meal_slot(meal_pref)
        if normalized_meal:
            spoken = _SLOT_MEAL_SPOKEN.get(normalized_meal, normalized_meal)
            facts["meal_pref"] = normalized_meal
            facts["meal_pref_spoken"] = spoken
            if normalized_meal not in _KEEP_SLOT_VALUES:
                facts["proposed_meal"] = normalized_meal
                facts["proposed_meal_spoken"] = spoken

    requested_cabin = updates.get("requested_cabin")
    if requested_cabin:
        lowered = str(requested_cabin).lower()
        if lowered in _VALID_CABIN_VALUES:
            facts["requested_cabin"] = lowered
            facts["booked_cabin"] = lowered
            facts["proposed_cabin"] = lowered

    suggested_flight = updates.get("suggested_flight")
    if suggested_flight:
        alt = _selected_snapshot_alternative(collected, str(suggested_flight))
        if alt is not None:
            if alt.get("origin"):
                facts["new_origin"] = alt["origin"]
                facts["new_origin_spoken"] = _AIRPORT_CITY_NAMES.get(str(alt["origin"]).upper(), str(alt["origin"]))
            if alt.get("destination"):
                facts["new_destination"] = alt["destination"]
                facts["new_destination_spoken"] = _AIRPORT_CITY_NAMES.get(
                    str(alt["destination"]).upper(), str(alt["destination"])
                )
            if alt.get("cabin"):
                facts["booked_cabin"] = alt["cabin"]
            if alt.get("departure"):
                facts["departure"] = alt["departure"]
    if requested_cabin:
        lowered = str(requested_cabin).lower()
        if lowered in _VALID_CABIN_VALUES:
            facts["booked_cabin"] = lowered


def _selected_snapshot_alternative(collected: dict, flight_number: str) -> dict | None:
    """Return the selected alternative from Collected.alternatives_snapshot, if present."""
    snapshot = (collected or {}).get("alternatives_snapshot")
    if not isinstance(snapshot, list):
        return None
    selected_upper = str(flight_number).upper()
    for alt in snapshot:
        if not isinstance(alt, dict):
            continue
        if str(alt.get("flight_number") or "").upper() == selected_upper:
            return alt
    return None


_TOOL_SUCCESS_INSTRUCTION: dict[str, str] = {
    "list_routes": (
        "The tool returned the airports the caller can fly from/to. "
        "Read back the entries in Collected.airport_names as 'City "
        "(CODE)' pairs, separated by commas, and ask which one they "
        "want to book. Do NOT ignore the list — the caller just asked "
        "for it."
    ),
    "get_flight_status": (
        "Read back the flight status from queried_flight_status "
        "(flight_number, status, delay_minutes if >0, scheduled "
        "departure). One short sentence."
    ),
    "lookup_pnr": (
        "Read back the booking details from the tool result: "
        "passenger, flight, route, departure, cabin, seat, meal. One "
        "concise sentence. Ask how to help next."
    ),
}


def _tool_success_instruction(tool_name: str) -> str | None:
    """Return a responder directive for read-back tools, or None for mutations.

    Only registered for pure-read tools that need an explicit read-back
    when called (the caller asked a question; we ran the tool; now we
    must speak the result).  Mutation tools (commit_rebook / cancel /
    create_booking) are already handled by the mutation_action fact +
    the target state's response_hint.
    """
    return _TOOL_SUCCESS_INSTRUCTION.get(tool_name)


def _empty_result_instruction(tool_name: str | None, params: dict | None) -> str:
    """Compose a tool-specific "no result" directive for the responder.

    Generic failure wording leaves the caller confused — each tool has a
    meaningful empty state worth surfacing plainly.  Never invents codes
    or cities; leans on params the runner already knows.
    """
    params = params or {}
    if tool_name == "list_alternatives":
        origin = params.get("origin", "that origin")
        destination = params.get("destination", "that destination")
        return (
            f"No scheduled flights between {origin} and {destination}. "
            "Tell the caller in one short sentence and ask if they'd "
            "like a different destination or origin. Do not invent cities."
        )
    if tool_name == "list_routes":
        return (
            "No scheduled routes for that airport right now. Tell the "
            "caller and ask if they'd like to try a different airport."
        )
    if tool_name == "commit_rebook":
        return (
            "The rebook could not be committed — either the flight is "
            "unavailable or the PNR is not eligible. Apologise briefly "
            "and ask how the caller wants to proceed. Never invent a "
            "confirmation code."
        )
    if tool_name == "lookup_pnr":
        return "The PNR was not found. Ask the caller to re-state the six-character booking reference."
    if tool_name == "get_flight_status":
        return "Flight number not found. Ask the caller to re-state the flight designator (two letters plus digits)."
    return (
        f"The {tool_name} tool returned no usable result. Tell the caller "
        "we couldn't complete that action right now and ask how they'd "
        "like to proceed. Never invent codes or flight numbers."
    )


def _tool_result_is_empty(result: Any) -> bool:
    """True when the backend returned nothing useful.

    Treats ``None``, an empty list/dict, and explicit error envelopes
    ``{"error": ...}`` as failures the responder must not paper over.
    """
    if result is None:
        return True
    if isinstance(result, (list, tuple, dict, str)) and len(result) == 0:
        return True
    return isinstance(result, dict) and "error" in result


async def _orchestrator_call(ctx: TurnContext) -> StateDecision:
    """One LLM call that picks action + next state + tool + tool params.

    Failures map to a conservative ``stay`` with no tool so the caller
    still hears something instead of dead air.
    """
    system = _ORCHESTRATOR_SYSTEM
    user = _build_orchestrator_user_prompt(ctx)
    try:
        raw = await ainvoke_text(system, user)
    except Exception as exc:
        logger.warning(f"state_runner fused call failed ({type(exc).__name__}): {exc}")
        return _fallback_decision(ctx)

    decision = _parse_orchestrator(raw, ctx)
    logger.debug(f"state_runner raw={raw!r} → {decision}")
    return decision


_ORCHESTRATOR_SYSTEM = (
    "You run ONE airline-service flow and advance it this turn.  The "
    "caller has already been classified as wanting to continue this "
    "flow — your only job is to decide the next step inside it. You "
    "cannot abandon, switch flows, or propose anything outside the "
    "state graph you're given.\n\n"
    "Output ONE compact JSON object — nothing else. ALL seven fields "
    "below are REQUIRED in your output, even if empty:\n"
    "{\n"
    '  "next_state": "<allowed state name verbatim, or null>",\n'
    '  "tool_name": "<tool name or null>",\n'
    '  "tool_params": {...} or null,\n'
    '  "response_instruction": "<short directive to the responder>",\n'
    '  "response_facts": {...},\n'
    '  "slot_updates": {...},\n'
    '  "reset_scope": "intent_flow" | null\n'
    "}\n\n"
    "Typical moves:\n"
    "- Answer the state's question: advance next_state, call the state's "
    "tool if its params are known, stash new info in slot_updates.\n"
    "- Same-flow restart (caller gives fresh inputs mid-flow): set "
    "next_state to the FIRST state name in the Allowed next states list "
    "and call the restart tool if appropriate.\n"
    "- Side query (caller is asking rather than answering): no tool, "
    "compose a response that answers from Collected and keeps the flow "
    "at the current state.\n\n"
    "Mutation-tool invariant: IRREVERSIBLE tools (commit_rebook, "
    "cancel_booking, create_booking) may only be called "
    "when the caller's LATEST utterance is an UNAMBIGUOUS YES to a "
    "confirmation prompt.  If the latest utterance contains any denial "
    "or hesitation — words like 'no', 'not', 'don't', 'didn't', 'never', "
    "'hold on', 'wait', 'changed my mind', 'that's okay then', 'forget "
    "it' — DO NOT call the mutation tool; instead move to the declined/"
    "terminal branch the state's Allowed next states permits and "
    "acknowledge the caller kept their booking.  Treat questions about "
    "terms ('explain', 'what does that mean') as side queries, not "
    "confirmations.\n\n"
    "next_state must be one of the state names listed under Allowed "
    "next states — write it VERBATIM. Never invent names like 'entry', "
    "'done', or 'ready'.\n\n"
    "SLOT PERSISTENCE (slot_updates):\n"
    "Every time the caller makes a choice the flow needs to remember — "
    "seat preference, meal preference, chosen flight, destination city, "
    "whatever — put it in slot_updates so the next turn sees it in "
    "Collected. Without this, choices evaporate and the final tool call "
    "(e.g. commit_rebook) can't reflect them.\n"
    "Examples:\n"
    '- Caller \'I\'ll keep the same seat\' → slot_updates={"seat_pref": "keep"}.\n'
    '- Caller \'aisle please\' → slot_updates={"seat_pref": "aisle"}.\n'
    '- Caller \'14D\' → slot_updates={"seat_pref": "14D"}.\n'
    '- Caller \'non-vegetarian\' → slot_updates={"meal_pref": "non_vegetarian"}.\n'
    '- Caller \'keep the meal\' → slot_updates={"meal_pref": "keep"}.\n'
    '- Caller \'economy please\' → slot_updates={"requested_cabin": "economy"}.\n'
    "- Caller 'the earlier one' (after list_alternatives) → "
    'slot_updates={"suggested_flight": "<first flight number from snapshot>"}.\n'
    "- Caller 'the 3 PM one' (after list_alternatives) → "
    'slot_updates={"suggested_flight": "<matching flight number from snapshot>"}.\n\n'
    "RESETS (reset_scope):\n"
    '- Use reset_scope="intent_flow" when the caller is replacing the '
    "current proposal inside the SAME intent and the old scratch must "
    "be dropped before the new slot_updates are persisted.\n"
    "- Examples: fresh route mid-booking, 'start over this booking', "
    "or 'different flight entirely' after a stale proposal.\n"
    "- Use null for ordinary step progression or small edits like seat "
    "or meal changes.\n\n"
    "CORE RULES:\n"
    "1. If every required param for the next logical tool is in Collected "
    "or the caller's words, CALL THE TOOL THIS TURN.\n"
    "2. NEVER invent codes, flight numbers, times, cities, or PNRs. "
    "Every tool_params value comes from the caller's words or Collected.\n"
    "3. DO NOT put flight-owned values (flight_number, departure, "
    "destination, origin, confirmation_code, alternatives) in "
    "response_facts — the runner wires the real tool output in for you. "
    "response_facts is for short scalar labels only (topic, selected_"
    "choice). Leave it empty when a tool is called.\n"
    "4. If alternatives_snapshot is in Collected, DO NOT re-call "
    "list_alternatives. Move forward: caller's choice picks one of the "
    "snapshot's flights.\n"
    "5. NEVER call lookup_pnr when a PNR is already in Collected.\n\n"
    "Canonical values for tool_params:\n"
    "- 'S F O' / 's.f.o' → 'SFO'; 'L H R' → 'LHR'.\n"
    "- 'Seattle'→SEA, 'San Francisco'→SFO, 'Los Angeles'→LAX, "
    "'London'/'Heathrow'→LHR, 'New York'/'JFK'→JFK, 'Miami'→MIA, "
    "'Boston'→BOS, 'Atlanta'→ATL.\n"
    "- Flight 'A A three eleven'→'AA311'. PNR 'A,B,C,1,2,3'→'ABC123'.\n\n"
    "Generic tool-selection rules (intent-specific examples come "
    "through in the user prompt per turn):\n"
    "- Caller asks a one-sided airport question ('where can I fly from "
    "X' / 'what flies into Y') → list_routes with EXACTLY ONE of "
    "origin/destination. Never list_routes with both.\n"
    "- Caller asks about THEIR own booking (status/seat/meal/departure) "
    "→ no tool; answer from Collected.\n"
    "- If alternatives_snapshot is in Collected, DO NOT re-call "
    "list_alternatives — the caller's reply picks one of the snapshot "
    "flights.\n"
    "- NEVER call lookup_pnr when a PNR is already in Collected.\n\n"
    "response_instruction — keep it short AND specific. Use the matching "
    "verb for the mutation_action (cancelled / rebooked / booked); "
    "NEVER combine verbs ('cancelled and rebooked' is a bug). When "
    "reading an airport list, use 'City (CODE)' form with "
    "entries from Collected.airport_names when list_routes was called. "
    "Never pass template placeholders (e.g. '[Collected.x]' or "
    "'{variable}') through to the caller — resolve them to real values "
    "before writing the instruction."
)


_ALL_INTENTS = ("rebook", "cancel", "booking")


def _build_orchestrator_user_prompt(ctx: TurnContext) -> str:
    state = ctx.intent.states[ctx.current_state]
    allowed_block = (
        "\n".join(
            f"  - {name}: {ctx.intent.states[name].purpose}" for name in state.allowed_next if name in ctx.intent.states
        )
        or "  (terminal)"
    )

    tool_names = list(_current_state_tool_names(ctx))
    tool_block = "\n".join(_format_tool(ctx.intent.tools[n]) for n in tool_names) or "(none)"

    collected_block = "\n".join(f"  - {k}: {v}" for k, v in ctx.collected.items() if v) or "  (none)"

    history_block = (
        "\n".join(f"  {turn['role']}: {turn['content']}" for turn in (ctx.history or [])[-4:])
        or "  (no prior dialogue)"
    )

    # Per-state + per-intent guidance, rendered ONLY for the active
    # intent.  The system prompt stays generic; the model only sees the
    # hints relevant to where we are right now — no mention of other
    # flows the caller could switch to.  Cross-intent handoff is the
    # router's job on a fresh turn, not this LLM's.
    hint_block = ""
    if state.response_hint:
        hint_block += (
            "\nDefault response directive — use it ONLY when the "
            "caller's turn is the expected reply to this state's main "
            "question.  If the turn is a side query (caller is asking "
            "for info rather than answering), a pivot, an abandon, or "
            "anything else that doesn't fit the default, write a "
            "DIFFERENT response_instruction that fits — DO NOT copy the "
            "default verbatim in those cases:\n"
            f"  {state.response_hint}\n"
        )
    if ctx.intent.prompt_examples:
        hint_block += f"\nTool-selection examples for this intent:\n{ctx.intent.prompt_examples}\n"

    return (
        f"Flow: {ctx.intent.name}\n"
        f"Current state: {ctx.current_state} — {state.purpose}\n"
        f"Allowed next states:\n{allowed_block}\n\n"
        f"Available tools (call at most ONE):\n{tool_block}\n\n"
        f"Collected data:\n{collected_block}\n\n"
        f"Recent dialogue:\n{history_block}"
        f"{hint_block}\n"
        f"Caller just said: {ctx.transcript!r}\n\n"
        "JSON:"
    )


def _format_tool(tool: ToolSpec) -> str:
    schema = json.dumps(tool.params, separators=(",", ":"))
    return f"  - {tool.name}({schema}): {tool.description}"


def _current_state_tool_names(ctx: TurnContext) -> tuple[str, ...]:
    """Return tool names surfaced to the orchestrator in the current state."""
    state = ctx.intent.states[ctx.current_state]
    tool_names: list[str] = []
    for n in list(state.preferred_tools) + list(ctx.intent.always_available):
        if n not in tool_names and n in ctx.intent.tools:
            tool_names.append(n)
    return tuple(tool_names)


def _parse_orchestrator(raw: str, ctx: TurnContext) -> StateDecision:
    if not raw:
        return _fallback_decision(ctx)
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    if start == -1:
        return _fallback_decision(ctx)
    depth = 0
    end = -1
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        return _fallback_decision(ctx)
    try:
        payload = json.loads(text[start:end])
    except json.JSONDecodeError:
        return _fallback_decision(ctx)
    if not isinstance(payload, dict):
        return _fallback_decision(ctx)

    # The orchestrator's schema has no ``action`` field; the classifier
    # (Call 1) already decided stay.  Ignore any stale action the model
    # emits — we always treat this as stay.
    action = "stay"

    next_state = payload.get("next_state")
    if isinstance(next_state, str):
        low = next_state.lower().strip()
        if low in ("", "null", "none", "entry", "done", "terminal", "ready"):
            next_state = None
    else:
        next_state = None
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name or tool_name.lower() == "null":
        tool_name = None
    tool_params = payload.get("tool_params") if isinstance(payload.get("tool_params"), dict) else {}
    response_instruction = payload.get("response_instruction")
    response_instruction = response_instruction if isinstance(response_instruction, str) else ""
    response_facts = payload.get("response_facts") if isinstance(payload.get("response_facts"), dict) else {}
    slot_updates = payload.get("slot_updates") if isinstance(payload.get("slot_updates"), dict) else {}
    reset_scope_raw = payload.get("reset_scope")
    reset_scope = None
    if isinstance(reset_scope_raw, str):
        candidate = reset_scope_raw.strip().lower()
        if candidate in _VALID_RESET_SCOPES:
            reset_scope = candidate
    available_tools = set(_current_state_tool_names(ctx))
    if tool_name is not None and tool_name not in available_tools:
        logger.warning(
            f"state_runner: LLM picked unavailable tool {tool_name!r} from "
            f"{ctx.current_state!r}; allowed={sorted(available_tools)}; ignoring tool"
        )
        tool_name = None
        tool_params = {}
        response_instruction = ""

    return StateDecision(
        action=action,
        next_state=next_state,
        tool_name=tool_name,
        tool_params=tool_params,
        response_instruction=response_instruction,
        response_facts=response_facts,
        slot_updates=slot_updates,
        reset_scope=reset_scope,
    )


def _fallback_decision(ctx: TurnContext) -> StateDecision:
    """Conservative ``stay`` when the LLM response is unusable."""
    return StateDecision(
        action="stay",
        next_state=ctx.current_state,
        tool_name=None,
        tool_params={},
        response_instruction=(
            "Apologise briefly for not catching that and re-ask the pending question in one short sentence."
        ),
        response_facts={},
        slot_updates={},
        reset_scope=None,
    )
