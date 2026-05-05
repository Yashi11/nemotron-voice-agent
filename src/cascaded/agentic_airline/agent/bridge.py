# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Pipecat ``FrameProcessor`` that routes multi-step intents to the Python orchestrators.

Sits between :class:`IntentRouterProcessor` and the fast ``NvidiaLLMService``.
Two entry points spawn an orchestrator session:

1. **Router-bypass** — downstream ``LLMContextFrame`` with
   ``metadata['requires_deep'] == True``.  Bridge swallows the frame
   (fast LLM never sees the turn), pre-populates memory / entity_store
   with any entities the router extracted, and runs the orchestrator.
2. **Tool-intercept** — fast LLM calls ``ask_deep_agent``; its handler
   invokes :meth:`trigger_from_tool`.

The bridge stays quiet while the orchestrator runs — the 3-LLM pipeline
typically returns in a few seconds and a pre-response filler only
produced double-speak ("one moment" immediately followed by the real
answer).  Pivot fillers still mark intent switches inside
``_run_with_pivot``.  When an orchestrator raises
:class:`OrchestratorFallback` we emit a short LLM-composed apology
instead of routing anywhere else — the previous LangGraph DeepAgent
fallback path was retired.
"""

from __future__ import annotations

import asyncio
import itertools
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    UserStartedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from cascaded.agentic_airline.agent.router import _last_user_text
from cascaded.agentic_airline.orchestrators import OrchestratorFallback, run_orchestrator
from cascaded.agentic_airline.orchestrators._responder import generate_response
from cascaded.agentic_airline.tools import _backend

if TYPE_CHECKING:
    from cascaded.agentic_airline.state.conversation_memory import ConversationMemory
    from cascaded.agentic_airline.state.entity_store import EntityStore


_HOLD_MESSAGE = "I'm still working on this — please give me one more moment."


EmitText = Callable[[str], Awaitable[None]]


def _should_preserve_record_context(
    *,
    prev_intent: str | None,
    new_intent: str,
    flow_in_progress: bool,
    current_pnr: str | None,
    explicit_pnr: str | None,
) -> bool:
    """Return whether a cross-intent handoff should keep the loaded booking record."""
    if not prev_intent or prev_intent == new_intent:
        return True
    if flow_in_progress:
        return True
    if not current_pnr or not explicit_pnr:
        return False
    return current_pnr.strip().upper() == explicit_pnr.strip().upper()


@dataclass(slots=True)
class OrchestratorSession:
    """Per-turn session state for one orchestrator invocation."""

    spawn_order: int
    intent: str
    summary: str
    transcript: str
    task: asyncio.Task | None = None
    cancelled: bool = False


class DeepAgentBridgeService(FrameProcessor):
    """Delegates multi-step intents to the Python orchestrators.

    Retains the historical class name so the pipeline wiring stays
    backwards-compatible.  The LangGraph DeepAgent has been removed;
    the name now refers to the Python state-machine orchestrators.
    """

    def __init__(self, entity_store: EntityStore, memory: ConversationMemory) -> None:
        """Build the bridge for one stream."""
        super().__init__()
        self._entity_store = entity_store
        self._memory = memory
        self._sessions: list[OrchestratorSession] = []
        self._spawn_counter = itertools.count(1)
        # Latest user transcript seen on a downstream LLMContextFrame.
        # ``ask_deep_agent`` tool payloads only carry the fast LLM's
        # paraphrase; the orchestrator needs the caller's actual words
        # to classify mid-flow replies like "the earlier one".
        self._last_user_transcript: str = ""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Intercept router-bypass deep turns and barge-ins; forward everything else."""
        await super().process_frame(frame, direction)

        if isinstance(frame, (UserStartedSpeakingFrame, InterruptionFrame)):
            await self._cancel_all()
            await self.push_frame(frame, direction)
            return

        if direction == FrameDirection.DOWNSTREAM and isinstance(frame, LLMContextFrame):
            latest = _last_user_text(frame)
            if latest:
                self._last_user_transcript = latest
            # Swap PNR-scoped memory BEFORE any downstream layer sees
            # the frame — runs on every router-classified turn, not
            # just deep ones, so "status of another PNR" (simple) also
            # shakes off the prior PNR's scratch.
            await self._maybe_swap_pnr(frame.metadata)
            if frame.metadata.get("requires_deep"):
                await self._dispatch_new_turn(frame)
                return  # swallow — fast LLM does not see this turn

        await self.push_frame(frame, direction)

    async def _maybe_swap_pnr(self, metadata: dict) -> None:
        """Swap a router-extracted PNR into entity_store, clearing prior scratch.

        The fast LLM's ``lookup_pnr`` tool does the same on its end; this
        is a belt-and-suspenders so a status query that stays simple
        (fast-LLM path) still benefits from a PNR-level reset.
        """
        pnr_raw = metadata.get("extracted_pnr")
        if not pnr_raw:
            return
        canonical = pnr_raw.strip().upper()
        if len(canonical) != 6:
            return
        prior = self._entity_store.get("pnr")
        if prior is not None and prior.value == canonical:
            return
        record = await _backend.get_pnr(canonical)
        if record is None:
            return
        if prior is not None:
            from cascaded.agentic_airline.tools.pnr import _reset_for_new_pnr

            logger.info(f"bridge: PNR swap {prior.value!r} → {canonical!r}; clearing prior PNR-scoped memory")
            _reset_for_new_pnr(self._entity_store, self._memory)
        self._entity_store.put("pnr", canonical, confidence=0.9)
        if record.get("flight_number"):
            self._entity_store.put("flight_number", record["flight_number"], confidence=0.9)

    async def _dispatch_new_turn(self, frame: LLMContextFrame) -> None:
        """Router-bypass entry point.  Absorbs extracted entities and spawns orchestrator."""
        await self._cancel_all()
        transcript = _last_user_text(frame)
        intent = str(frame.metadata.get("intent") or "unknown")
        await self._absorb_entities(frame.metadata)
        current = self._entity_store.get("pnr")
        self._reset_on_intent_change(
            intent,
            preserve_record_context=_should_preserve_record_context(
                prev_intent=getattr(self, "_last_intent", None),
                new_intent=intent,
                flow_in_progress=self._flow_in_progress(getattr(self, "_last_intent", None)),
                current_pnr=current.value if current is not None else None,
                explicit_pnr=frame.metadata.get("extracted_pnr"),
            ),
        )
        self._spawn(intent=intent, summary=transcript, transcript=transcript)

    async def trigger_from_tool(self, intent: str, summary: str, transcript: str = "") -> None:
        """Tool-intercept entry point invoked by the ``ask_deep_agent`` handler.

        Deduplicates on in-flight same-intent sessions: the fast LLM sometimes
        emits multiple parallel ``ask_deep_agent`` calls in one completion, and
        without the guard each call would cancel the previous session.
        """
        intent_l = (intent or "unknown").lower()
        for existing in self._sessions:
            if (
                not existing.cancelled
                and existing.task is not None
                and not existing.task.done()
                and existing.intent == intent_l
            ):
                logger.info(
                    f"session {existing.spawn_order} already running for intent "
                    f"{intent_l!r}; ignoring duplicate tool-trigger"
                )
                return
        await self._cancel_all()
        current = self._entity_store.get("pnr")
        self._reset_on_intent_change(
            intent_l,
            preserve_record_context=_should_preserve_record_context(
                prev_intent=getattr(self, "_last_intent", None),
                new_intent=intent_l,
                flow_in_progress=self._flow_in_progress(getattr(self, "_last_intent", None)),
                current_pnr=current.value if current is not None else None,
                explicit_pnr=None,
            ),
        )
        effective_transcript = transcript or self._last_user_transcript
        self._spawn(intent=intent_l, summary=summary, transcript=effective_transcript)

    def _flow_in_progress(self, intent: str | None) -> bool:
        """Return whether ``intent`` still has a non-terminal step in progress."""
        if not intent:
            return False
        from cascaded.agentic_airline.orchestrators._common import pending_intent

        return pending_intent(self._memory) == intent

    def _reset_on_intent_change(self, new_intent: str, preserve_record_context: bool = False) -> None:
        """Clear intent-scoped scratch when a different intent begins.

        Mid-flow pivots may keep the loaded PNR / flight context, but a
        fresh intent after a completed flow should start without carrying
        forward the previous booking record.
        """
        prev = getattr(self, "_last_intent", None)
        if prev and prev != new_intent:
            from cascaded.agentic_airline.tools.pnr import reset_intent_scratch

            logger.info(
                f"intent change {prev!r} → {new_intent!r}; clearing "
                f"intent-scoped memory (preserve_record_context={preserve_record_context})"
            )
            reset_intent_scratch(self._entity_store, self._memory)
            if not preserve_record_context:
                self._entity_store.forget("pnr")
                self._entity_store.forget("flight_number")
        self._last_intent = new_intent

    async def _absorb_entities(self, metadata: dict) -> None:
        """Pre-populate memory / entity_store from router-extracted entities.

        Only validated identifiers land here. Flow-local slots are
        taken from the transcript by the orchestrators themselves, so
        we avoid writing unused ``pending_*`` scratch that can linger
        across turns.
        """
        flight = metadata.get("extracted_flight")
        if flight and await _backend.find_by_flight(flight):
            self._entity_store.put("flight_number", flight, confidence=0.9)

        pnr = metadata.get("extracted_pnr")
        if pnr:
            record = await _backend.get_pnr(pnr)
            if record is not None:
                canonical = record["pnr"]
                prior = self._entity_store.get("pnr")
                if prior is not None and prior.value != canonical:
                    # PNR change mid-stream — shed scratch tied to the
                    # previous PNR so rebook doesn't inherit the last
                    # booking's ``new_origin`` / ``new_destination`` /
                    # ``suggested_flight`` etc.  Same reset the fast
                    # LLM's ``lookup_pnr`` handler runs on PNR swap.
                    from cascaded.agentic_airline.tools.pnr import _reset_for_new_pnr

                    _reset_for_new_pnr(self._entity_store, self._memory)
                self._entity_store.put("pnr", canonical, confidence=0.9)
                self._entity_store.put("flight_number", record["flight_number"], confidence=0.9)

    def _spawn(self, intent: str, summary: str, transcript: str) -> None:
        """Create an orchestrator session and start its runner task."""
        session = OrchestratorSession(
            spawn_order=next(self._spawn_counter),
            intent=intent,
            summary=summary,
            transcript=transcript,
        )
        session.task = asyncio.create_task(self._run(session))
        self._sessions.append(session)

    async def _run(self, session: OrchestratorSession) -> None:
        """Run the orchestrator; emit its sentence or a graceful fallback.

        On :class:`OrchestratorFallback` with ``new_intent`` set (caller
        pivoted to a different deep intent mid-flow), re-runs the
        orchestrator under the new intent in the same turn so the caller
        doesn't hear an apology before the new flow starts.

        No delayed "one moment" filler — the 3-LLM pipeline responds in
        a few seconds, and the filler used to duplicate every turn by
        firing before the real answer.  Pivot filler (spoken inside
        ``_run_with_pivot``) still marks intent switches; the
        ``_HOLD_MESSAGE`` fallback handles an empty orchestrator reply.
        """
        t0 = time.perf_counter()
        spoken: str = ""
        fallback_reason: str | None = None
        try:
            spoken = await self._run_with_pivot(session)
        except OrchestratorFallback as exc:
            fallback_reason = str(exc)
        except asyncio.CancelledError:
            logger.info(
                f"session {session.spawn_order} orchestrator cancelled "
                f"after {time.perf_counter() - t0:.2f}s (intent={session.intent!r})"
            )
            self._drop(session)
            raise
        except Exception as exc:
            logger.exception(f"session {session.spawn_order} orchestrator error: {exc}")
            fallback_reason = f"unexpected error: {exc}"

        elapsed = time.perf_counter() - t0

        if fallback_reason is not None:
            logger.info(f"session {session.spawn_order} orchestrator fallback ({elapsed:.2f}s): {fallback_reason}")
            if not session.cancelled:
                await self._emit_fallback_sentence(session.intent)
            self._drop(session)
            return

        logger.info(
            f"session {session.spawn_order} orchestrator done intent={session.intent!r} "
            f"elapsed={elapsed:.2f}s chars={len(spoken)}"
        )
        if spoken and not session.cancelled:
            await self._emit_llm_response(spoken)
        elif not session.cancelled:
            await self._emit_llm_response(_HOLD_MESSAGE)
        self._drop(session)

    async def _run_with_pivot(self, session: OrchestratorSession) -> str:
        """Run the orchestrator, transparently re-spawning on caller pivot.

        On a cross-intent pivot the bridge:

        1. Clears intent-scoped scratch so the new flow inherits no
           leftover destinations / prefs / alternatives from the old
           one.  The PNR record itself stays — rebook → cancel on the
           same booking should not force the caller to re-state it.
        2. Speaks a pre-templated filler (*"switching to cancellation —
           one moment"*) so the caller hears an acknowledgment while
           the new flow is composing its first real sentence.

        Bounded loop (``max_pivots``) prevents an LLM that keeps
        emitting ``pivot`` from re-spawning forever; the second
        consecutive pivot raises and lets the bridge's fallback path
        take over.
        """
        from cascaded.agentic_airline.orchestrators._state_runner import pivot_filler
        from cascaded.agentic_airline.tools.pnr import _INTENT_MEMORY_KEYS

        max_pivots = 1
        for attempt in range(max_pivots + 1):
            try:
                return await run_orchestrator(
                    intent=session.intent,
                    transcript=session.transcript,
                    summary=session.summary,
                    entity_store=self._entity_store,
                    memory=self._memory,
                    session_id=self._entity_store.stream_id,
                )
            except OrchestratorFallback as exc:
                if exc.new_intent and exc.new_intent != session.intent and attempt < max_pivots:
                    logger.info(
                        f"session {session.spawn_order} pivot "
                        f"{session.intent!r} → {exc.new_intent!r}; "
                        "clearing intent-scoped memory (PNR kept)"
                    )
                    for key in _INTENT_MEMORY_KEYS:
                        self._memory.forget(key)
                    if not session.cancelled:
                        await self._emit_llm_response(pivot_filler(exc.new_intent))
                    session.intent = exc.new_intent
                    continue
                raise
        return ""

    async def _emit_fallback_sentence(self, intent: str) -> None:
        """Compose a graceful apology via the responder LLM when the state machine can't proceed.

        Used in place of the retired DeepAgent fallback.  If the
        responder itself fails we emit the canned hold message so the
        caller never hits dead air.
        """
        try:
            sentence = await generate_response(
                "Apologize briefly for not being able to complete this request right now "
                "and invite the traveler to rephrase or ask for something else.",
                {"intent": intent},
            )
        except Exception as exc:
            logger.warning(f"fallback responder failed: {exc}")
            sentence = _HOLD_MESSAGE
        await self._emit_llm_response(sentence or _HOLD_MESSAGE)

    def _drop(self, session: OrchestratorSession) -> None:
        if session in self._sessions:
            self._sessions.remove(session)

    async def _emit_llm_response(self, text: str) -> None:
        """Emit ``text`` as an ordered LLM response so TTS speaks it."""
        await self.push_frame(LLMFullResponseStartFrame())
        await self.push_frame(LLMTextFrame(text=text))
        await self.push_frame(LLMFullResponseEndFrame())

    async def _cancel_all(self) -> None:
        """Cancel every in-flight orchestrator session (barge-in / new turn)."""
        for session in list(self._sessions):
            session.cancelled = True
            if session.task and not session.task.done():
                session.task.cancel()
