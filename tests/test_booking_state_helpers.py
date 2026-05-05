# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

# ruff: noqa: D100, D101, D102, D107

"""Regression tests for booking, bridge, and state-runner helpers."""

import json
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

if "loguru" not in sys.modules:
    loguru = types.ModuleType("loguru")
    loguru.logger = types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    sys.modules["loguru"] = loguru

if "langchain_core.language_models.chat_models" not in sys.modules:
    langchain_core = types.ModuleType("langchain_core")
    language_models = types.ModuleType("langchain_core.language_models")
    chat_models = types.ModuleType("langchain_core.language_models.chat_models")

    class BaseChatModel:  # pragma: no cover - test import shim
        pass

    chat_models.BaseChatModel = BaseChatModel
    sys.modules["langchain_core"] = langchain_core
    sys.modules["langchain_core.language_models"] = language_models
    sys.modules["langchain_core.language_models.chat_models"] = chat_models

if "langchain_nvidia_ai_endpoints" not in sys.modules:
    langchain_nvidia = types.ModuleType("langchain_nvidia_ai_endpoints")

    class ChatNVIDIA:  # pragma: no cover - test import shim
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def ainvoke(self, messages):
            raise RuntimeError("ChatNVIDIA should not be used in unit tests")

    langchain_nvidia.ChatNVIDIA = ChatNVIDIA
    sys.modules["langchain_nvidia_ai_endpoints"] = langchain_nvidia

if "pipecat.adapters.schemas.tools_schema" not in sys.modules:
    pipecat = types.ModuleType("pipecat")
    adapters = types.ModuleType("pipecat.adapters")
    schemas = types.ModuleType("pipecat.adapters.schemas")
    tools_schema = types.ModuleType("pipecat.adapters.schemas.tools_schema")
    frames = types.ModuleType("pipecat.frames")
    frames_frames = types.ModuleType("pipecat.frames.frames")
    processors = types.ModuleType("pipecat.processors")
    frame_processor = types.ModuleType("pipecat.processors.frame_processor")
    services = types.ModuleType("pipecat.services")
    llm_service = types.ModuleType("pipecat.services.llm_service")

    class AdapterType:  # pragma: no cover - test import shim
        OPENAI = "openai"

    class ToolsSchema:  # pragma: no cover - test import shim
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

    class FunctionCallResultProperties:  # pragma: no cover - test import shim
        def __init__(self, run_llm: bool = True) -> None:
            self.run_llm = run_llm

    class Frame:  # pragma: no cover - test import shim
        pass

    class InterruptionFrame(Frame):  # pragma: no cover - test import shim
        pass

    class LLMContextFrame(Frame):  # pragma: no cover - test import shim
        def __init__(self) -> None:
            self.metadata = {}
            self.context = types.SimpleNamespace(get_messages=lambda: [])

    class LLMFullResponseEndFrame(Frame):  # pragma: no cover - test import shim
        pass

    class LLMFullResponseStartFrame(Frame):  # pragma: no cover - test import shim
        pass

    class LLMTextFrame(Frame):  # pragma: no cover - test import shim
        def __init__(self, text: str = "") -> None:
            self.text = text

    class UserStartedSpeakingFrame(Frame):  # pragma: no cover - test import shim
        pass

    class FrameDirection:  # pragma: no cover - test import shim
        DOWNSTREAM = "downstream"
        UPSTREAM = "upstream"

    class FrameProcessor:  # pragma: no cover - test import shim
        async def process_frame(self, *args, **kwargs) -> None:
            return None

        async def push_frame(self, *args, **kwargs) -> None:
            return None

    tools_schema.AdapterType = AdapterType
    tools_schema.ToolsSchema = ToolsSchema
    frames_frames.Frame = Frame
    frames_frames.InterruptionFrame = InterruptionFrame
    frames_frames.LLMContextFrame = LLMContextFrame
    frames_frames.LLMFullResponseEndFrame = LLMFullResponseEndFrame
    frames_frames.LLMFullResponseStartFrame = LLMFullResponseStartFrame
    frames_frames.LLMTextFrame = LLMTextFrame
    frames_frames.UserStartedSpeakingFrame = UserStartedSpeakingFrame
    frame_processor.FrameDirection = FrameDirection
    frame_processor.FrameProcessor = FrameProcessor
    llm_service.FunctionCallResultProperties = FunctionCallResultProperties

    sys.modules["pipecat"] = pipecat
    sys.modules["pipecat.adapters"] = adapters
    sys.modules["pipecat.adapters.schemas"] = schemas
    sys.modules["pipecat.adapters.schemas.tools_schema"] = tools_schema
    sys.modules["pipecat.frames"] = frames
    sys.modules["pipecat.frames.frames"] = frames_frames
    sys.modules["pipecat.processors"] = processors
    sys.modules["pipecat.processors.frame_processor"] = frame_processor
    sys.modules["pipecat.services"] = services
    sys.modules["pipecat.services.llm_service"] = llm_service

if "httpx" not in sys.modules:
    httpx = types.ModuleType("httpx")

    class AsyncClient:  # pragma: no cover - test import shim
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def aclose(self) -> None:
            return None

    httpx.AsyncClient = AsyncClient
    sys.modules["httpx"] = httpx

from cascaded.agentic_airline.agent.bridge import (
    DeepAgentBridgeService,
    _should_preserve_record_context,
)
from cascaded.agentic_airline.orchestrators._common import sync_explicit_pnr
from cascaded.agentic_airline.orchestrators._state_runner import (
    CleanupPlan,
    IntentSpec,
    StateDecision,
    StateRunResult,
    StateSpec,
    TurnContext,
    _build_cleanup_plan,
    _build_response_facts,
    _parse_orchestrator,
    _resolve_tool_params,
    apply_cleanup_plan,
    run_state,
)
from cascaded.agentic_airline.orchestrators.booking import (
    _clear_booking_flow,
    _collect_state,
    _normalized_meal,
    _persist_slot_updates,
    _sync_selected_flight_details,
    orchestrate_booking,
)
from cascaded.agentic_airline.orchestrators.booking_states import (
    BOOKING_INTENT,
    STATE_AWAITING_DESTINATION,
    STATE_MEAL,
    STATE_PRICE,
    STATE_START,
)
from cascaded.agentic_airline.state.conversation_memory import ConversationMemory
from cascaded.agentic_airline.state.entity_store import EntityStore
from cascaded.agentic_airline.tools.pnr import reset_intent_scratch


def _snapshot() -> list[dict]:
    return [
        {
            "flight_number": "AA506",
            "departure": "2026-04-30T22:00:00",
            "origin": "SFO",
            "destination": "JFK",
            "cabin": "business",
        },
        {
            "flight_number": "AA502",
            "departure": "2026-05-01T09:30:00",
            "origin": "SFO",
            "destination": "JFK",
            "cabin": "economy",
        },
    ]


class BookingStateHelperTests(unittest.TestCase):
    def test_preserve_record_context_only_for_active_or_explicit_same_pnr(self) -> None:
        self.assertFalse(
            _should_preserve_record_context(
                prev_intent="rebook",
                new_intent="cancel",
                flow_in_progress=False,
                current_pnr="ABC123",
                explicit_pnr=None,
            )
        )
        self.assertTrue(
            _should_preserve_record_context(
                prev_intent="rebook",
                new_intent="cancel",
                flow_in_progress=True,
                current_pnr="ABC123",
                explicit_pnr=None,
            )
        )
        self.assertTrue(
            _should_preserve_record_context(
                prev_intent="rebook",
                new_intent="cancel",
                flow_in_progress=False,
                current_pnr="ABC123",
                explicit_pnr="ABC123",
            )
        )
        self.assertFalse(
            _should_preserve_record_context(
                prev_intent="rebook",
                new_intent="cancel",
                flow_in_progress=False,
                current_pnr="ABC123",
                explicit_pnr="DEF456",
            )
        )

    def test_clear_booking_flow_drops_stale_slots(self) -> None:
        memory = ConversationMemory("stream-1")
        memory.put("new_origin", "AGR")
        memory.put("new_destination", "JFK")
        memory.put("suggested_flight", "AA506")
        memory.put("seat_pref", "aisle")
        memory.put("meal_pref", "vegetarian")
        memory.put("booked_cabin", "business")
        memory.put("price", "600.00")

        _clear_booking_flow(memory)

        self.assertIsNone(memory.get("new_origin"))
        self.assertIsNone(memory.get("new_destination"))
        self.assertIsNone(memory.get("suggested_flight"))
        self.assertIsNone(memory.get("seat_pref"))
        self.assertIsNone(memory.get("meal_pref"))
        self.assertIsNone(memory.get("booked_cabin"))
        self.assertIsNone(memory.get("price"))

    def test_sync_selected_flight_details_uses_actual_choice(self) -> None:
        memory = ConversationMemory("stream-2")
        memory.put("alternatives_snapshot", json.dumps(_snapshot()))
        memory.put("suggested_flight", "AA502")
        memory.put("new_origin", "AGR")
        memory.put("booked_cabin", "business")

        _sync_selected_flight_details(memory)

        self.assertEqual(memory.get("new_origin"), "SFO")
        self.assertEqual(memory.get("new_destination"), "JFK")
        self.assertEqual(memory.get("booked_cabin"), "economy")

    def test_collect_state_derives_cabin_from_selected_flight(self) -> None:
        memory = ConversationMemory("stream-3")
        entity_store = EntityStore("stream-3")
        memory.put("alternatives_snapshot", json.dumps(_snapshot()))
        memory.put("suggested_flight", "AA502")
        memory.put("new_origin", "SFO")
        memory.put("new_destination", "JFK")
        memory.put("booked_cabin", "business")

        collected = _collect_state(memory, entity_store)

        self.assertEqual(collected["suggested_flight"], "AA502")
        self.assertEqual(collected["booked_cabin"], "economy")
        self.assertEqual(collected["new_origin_spoken"], "San Francisco")
        self.assertEqual(collected["new_destination_spoken"], "New York JFK")

    def test_collect_state_prefers_requested_cabin_over_selected_flight_cabin(self) -> None:
        memory = ConversationMemory("stream-3b")
        entity_store = EntityStore("stream-3b")
        memory.put("alternatives_snapshot", json.dumps(_snapshot()))
        memory.put("suggested_flight", "AA506")
        memory.put("new_origin", "SFO")
        memory.put("new_destination", "JFK")
        memory.put("requested_cabin", "economy")

        collected = _collect_state(memory, entity_store)

        self.assertEqual(collected["requested_cabin"], "economy")
        self.assertEqual(collected["booked_cabin"], "economy")

    def test_build_cleanup_plan_for_backward_booking_transition(self) -> None:
        plan = _build_cleanup_plan(BOOKING_INTENT, STATE_PRICE, STATE_MEAL)

        self.assertEqual(plan.forget_keys, ("meal_pref", "price", "currency"))
        self.assertEqual(plan.forget_entities, ("confirmation_code",))

    def test_build_cleanup_plan_for_intent_flow_reset(self) -> None:
        plan = _build_cleanup_plan(
            BOOKING_INTENT,
            STATE_AWAITING_DESTINATION,
            STATE_AWAITING_DESTINATION,
            "intent_flow",
        )

        self.assertIn("new_origin", plan.forget_keys)
        self.assertIn("new_destination", plan.forget_keys)
        self.assertIn("suggested_flight", plan.forget_keys)
        self.assertIn("requested_cabin", plan.forget_keys)
        self.assertIn("price", plan.forget_keys)
        self.assertEqual(plan.forget_entities, ("confirmation_code",))

    def test_apply_cleanup_plan_forgets_memory_and_transient_entity(self) -> None:
        memory = ConversationMemory("stream-cleanup")
        entity_store = EntityStore("stream-cleanup")
        memory.put("meal_pref", "vegetarian")
        memory.put("price", "600.00")
        memory.put("currency", "USD")
        entity_store.put("confirmation_code", "CNF123", confidence=1.0)

        apply_cleanup_plan(
            CleanupPlan(
                forget_keys=("meal_pref", "price", "currency"),
                forget_entities=("confirmation_code",),
            ),
            memory,
            entity_store,
        )

        self.assertIsNone(memory.get("meal_pref"))
        self.assertIsNone(memory.get("price"))
        self.assertIsNone(memory.get("currency"))
        self.assertIsNone(entity_store.get("confirmation_code"))

    def test_reset_intent_scratch_keeps_flight_but_drops_confirmation(self) -> None:
        memory = ConversationMemory("stream-reset")
        entity_store = EntityStore("stream-reset")
        memory.put("booking_step", STATE_PRICE)
        memory.put("new_origin", "SFO")
        entity_store.put("confirmation_code", "CNF123", confidence=1.0)
        entity_store.put("flight_number", "AA506", confidence=1.0)

        reset_intent_scratch(entity_store, memory)

        self.assertIsNone(memory.get("booking_step"))
        self.assertIsNone(memory.get("new_origin"))
        self.assertIsNone(entity_store.get("confirmation_code"))
        self.assertEqual(entity_store.get("flight_number").value, "AA506")

    def test_normalized_meal_rejects_invalid_value(self) -> None:
        self.assertEqual(_normalized_meal("non vegetarian"), "non_vegetarian")
        self.assertIsNone(_normalized_meal("AA506"))

    def test_persist_slot_updates_rejects_invalid_meal(self) -> None:
        memory = ConversationMemory("stream-meal")

        _persist_slot_updates({"meal_pref": "AA506"}, memory)

        self.assertIsNone(memory.get("meal_pref"))

    def test_build_response_facts_ignores_invalid_meal_slot_update(self) -> None:
        ctx = TurnContext(
            intent=BOOKING_INTENT,
            current_state=STATE_PRICE,
            transcript="whatever",
            collected={
                "new_origin": "SFO",
                "new_destination": "JFK",
                "suggested_flight": "AA506",
            },
            history=[],
            record=None,
        )
        decision = StateDecision(
            action="stay",
            next_state=STATE_PRICE,
            tool_name=None,
            tool_params={},
            response_instruction="",
            response_facts={},
            slot_updates={"meal_pref": "AA506"},
        )

        facts = _build_response_facts(ctx, decision, None)

        self.assertNotIn("proposed_meal", facts)
        self.assertNotIn("meal_pref_spoken", facts)

    def test_bridge_reset_on_fresh_intent_change_drops_loaded_record(self) -> None:
        memory = ConversationMemory("stream-bridge")
        entity_store = EntityStore("stream-bridge")
        bridge = DeepAgentBridgeService(entity_store, memory)
        bridge._last_intent = "rebook"
        memory.put("rebook_step", "committed")
        memory.put("new_destination", "SFO")
        entity_store.put("pnr", "ABC123", confidence=1.0)
        entity_store.put("flight_number", "AA501", confidence=1.0)
        entity_store.put("confirmation_code", "CNF123", confidence=1.0)

        bridge._reset_on_intent_change("cancel", preserve_record_context=False)

        self.assertIsNone(memory.get("new_destination"))
        self.assertIsNone(entity_store.get("pnr"))
        self.assertIsNone(entity_store.get("flight_number"))
        self.assertIsNone(entity_store.get("confirmation_code"))
        self.assertEqual(bridge._last_intent, "cancel")

    def test_bridge_reset_on_mid_flow_pivot_keeps_loaded_record(self) -> None:
        memory = ConversationMemory("stream-bridge-pivot")
        entity_store = EntityStore("stream-bridge-pivot")
        bridge = DeepAgentBridgeService(entity_store, memory)
        bridge._last_intent = "rebook"
        memory.put("rebook_step", "offered_alternative")
        memory.put("new_destination", "SFO")
        entity_store.put("pnr", "ABC123", confidence=1.0)
        entity_store.put("flight_number", "AA501", confidence=1.0)

        bridge._reset_on_intent_change("cancel", preserve_record_context=True)

        self.assertIsNone(memory.get("new_destination"))
        self.assertEqual(entity_store.get("pnr").value, "ABC123")
        self.assertEqual(entity_store.get("flight_number").value, "AA501")
        self.assertEqual(bridge._last_intent, "cancel")

    def test_parse_orchestrator_ignores_unavailable_tool_for_seat_state(self) -> None:
        ctx = TurnContext(
            intent=BOOKING_INTENT,
            current_state="awaiting_seat_pref",
            transcript="I will take seat 3A.",
            collected={},
            history=[],
            record=None,
        )
        raw = (
            '{"next_state":"awaiting_meal_pref","tool_name":"price_quote",'
            '"tool_params":{"origin":"JFK","destination":"SFO","cabin":"economy"},'
            '"response_instruction":"Summarise the updated proposal.",'
            '"response_facts":{},"slot_updates":{"seat_pref":"3A"}}'
        )

        decision = _parse_orchestrator(raw, ctx)

        self.assertEqual(decision.next_state, "awaiting_meal_pref")
        self.assertIsNone(decision.tool_name)
        self.assertEqual(decision.tool_params, {})
        self.assertEqual(decision.response_instruction, "")

    def test_parse_orchestrator_accepts_intent_flow_reset_scope(self) -> None:
        ctx = TurnContext(
            intent=BOOKING_INTENT,
            current_state=STATE_AWAITING_DESTINATION,
            transcript="Can we do from San Francisco then?",
            collected={
                "new_origin": "AGR",
                "new_destination": "JDH",
            },
            history=[],
            record=None,
        )
        raw = (
            '{"next_state":"awaiting_destination","tool_name":null,'
            '"tool_params":{},'
            '"response_instruction":"Ask for the new destination.",'
            '"response_facts":{},"slot_updates":{"new_origin":"SFO"},'
            '"reset_scope":"intent_flow"}'
        )

        decision = _parse_orchestrator(raw, ctx)

        self.assertEqual(decision.next_state, STATE_AWAITING_DESTINATION)
        self.assertEqual(decision.reset_scope, "intent_flow")
        self.assertEqual(decision.slot_updates, {"new_origin": "SFO"})

    def test_build_response_facts_reflects_fresh_meal_slot_update(self) -> None:
        ctx = TurnContext(
            intent=BOOKING_INTENT,
            current_state=STATE_PRICE,
            transcript="I want a non vegetarian meal.",
            collected={
                "new_origin": "JFK",
                "new_destination": "SFO",
                "suggested_flight": "AA501",
                "seat_pref": "3A",
                "meal_pref": "vegetarian",
                "price": "150.00",
                "currency": "USD",
            },
            history=[],
            record=None,
        )
        decision = StateDecision(
            action="stay",
            next_state=STATE_PRICE,
            tool_name=None,
            tool_params={},
            response_instruction="",
            response_facts={},
            slot_updates={"meal_pref": "non_vegetarian"},
        )

        facts = _build_response_facts(ctx, decision, None)

        self.assertEqual(facts["meal_pref"], "non_vegetarian")
        self.assertEqual(facts["meal_pref_spoken"], "non-vegetarian")
        self.assertEqual(facts["proposed_meal"], "non_vegetarian")
        self.assertEqual(facts["proposed_meal_spoken"], "non-vegetarian")

    def test_resolve_tool_params_for_price_quote_uses_canonical_cabin(self) -> None:
        ctx = TurnContext(
            intent=BOOKING_INTENT,
            current_state=STATE_PRICE,
            transcript="Make that economy class.",
            collected={
                "new_origin": "SFO",
                "new_destination": "JFK",
                "suggested_flight": "AA502",
                "alternatives_snapshot": _snapshot(),
                "booked_cabin": "business",
            },
            history=[],
            record=None,
        )
        decision = StateDecision(
            action="stay",
            next_state=STATE_PRICE,
            tool_name="price_quote",
            tool_params={"origin": "AGR", "destination": "JDH", "cabin": "business"},
            response_instruction="",
            response_facts={},
            slot_updates={"requested_cabin": "economy"},
        )

        resolved = _resolve_tool_params(ctx, decision)

        self.assertEqual(
            resolved.tool_params,
            {"origin": "SFO", "destination": "JFK", "cabin": "economy"},
        )

    def test_resolve_tool_params_for_create_booking_uses_selected_snapshot_flight(self) -> None:
        ctx = TurnContext(
            intent=BOOKING_INTENT,
            current_state=STATE_PRICE,
            transcript="Yes, book it.",
            collected={
                "new_origin": "SFO",
                "new_destination": "JFK",
                "suggested_flight": "AA502",
                "requested_cabin": "economy",
                "seat_pref": "window",
                "meal_pref": "non_vegetarian",
                "passenger_name": "Alex Doe",
                "alternatives_snapshot": _snapshot(),
            },
            history=[],
            record=None,
        )
        decision = StateDecision(
            action="stay",
            next_state="booked",
            tool_name="create_booking",
            tool_params={
                "passenger": "Guest",
                "origin": "AGR",
                "destination": "JDH",
                "flight_number": "AA506",
                "cabin": "business",
            },
            response_instruction="",
            response_facts={},
            slot_updates={},
        )

        resolved = _resolve_tool_params(ctx, decision)

        self.assertEqual(
            resolved.tool_params,
            {
                "passenger": "Alex Doe",
                "origin": "SFO",
                "destination": "JFK",
                "flight_number": "AA502",
                "seat": "window",
                "meal": "non_vegetarian",
                "cabin": "economy",
            },
        )

    def test_persist_slot_updates_rejects_invalid_flight_and_cabin(self) -> None:
        memory = ConversationMemory("stream-persist")
        memory.put("alternatives_snapshot", json.dumps(_snapshot()))

        _persist_slot_updates(
            {"suggested_flight": "AA999", "requested_cabin": "space_class"},
            memory,
        )

        self.assertIsNone(memory.get("suggested_flight"))
        self.assertIsNone(memory.get("requested_cabin"))


class BookingOrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_explicit_pnr_switches_active_record(self) -> None:
        memory = ConversationMemory("stream-sync")
        entity_store = EntityStore("stream-sync")
        memory.put("cancel_step", "showed_terms")
        memory.put("cancel_outcome", "travel credit")
        entity_store.put("pnr", "OLD999", confidence=1.0)
        entity_store.put("flight_number", "AA999", confidence=1.0)

        with patch(
            "cascaded.agentic_airline.orchestrators._common._backend.get_pnr",
            new=AsyncMock(
                return_value={
                    "pnr": "ABC123",
                    "flight_number": "AA501",
                    "passenger": "Jane Doe",
                }
            ),
        ):
            pnr, record, explicit, switched = await sync_explicit_pnr(
                "cancel PNR A B C 1 2 3",
                entity_store,
                memory,
            )

        self.assertTrue(explicit)
        self.assertTrue(switched)
        self.assertEqual(pnr, "ABC123")
        self.assertEqual(record["flight_number"], "AA501")
        self.assertEqual(entity_store.get("pnr").value, "ABC123")
        self.assertEqual(entity_store.get("flight_number").value, "AA501")
        self.assertIsNone(memory.get("cancel_outcome"))

    async def test_sync_explicit_pnr_not_found_drops_stale_record(self) -> None:
        memory = ConversationMemory("stream-sync-miss")
        entity_store = EntityStore("stream-sync-miss")
        entity_store.put("pnr", "OLD999", confidence=1.0)
        entity_store.put("flight_number", "AA999", confidence=1.0)

        with patch(
            "cascaded.agentic_airline.orchestrators._common._backend.get_pnr",
            new=AsyncMock(return_value=None),
        ):
            pnr, record, explicit, switched = await sync_explicit_pnr(
                "cancel PNR D E F 4 5 6",
                entity_store,
                memory,
            )

        self.assertTrue(explicit)
        self.assertTrue(switched)
        self.assertIsNone(pnr)
        self.assertIsNone(record)
        self.assertIsNone(entity_store.get("pnr"))
        self.assertIsNone(entity_store.get("flight_number"))

    async def test_run_state_uses_current_state_hint_after_illegal_transition(self) -> None:
        intent = IntentSpec(
            name="booking",
            entry_state="awaiting_seat_pref",
            terminal_states=frozenset(),
            states={
                "awaiting_seat_pref": StateSpec(
                    name="awaiting_seat_pref",
                    purpose="Collect seat preference.",
                    allowed_next=("awaiting_meal_pref", "awaiting_seat_pref"),
                    response_hint="Ask about seat preference.",
                ),
                "awaiting_meal_pref": StateSpec(
                    name="awaiting_meal_pref",
                    purpose="Collect meal preference.",
                    allowed_next=("showed_price", "awaiting_meal_pref"),
                    response_hint="Ask about meal preference.",
                ),
                "showed_price": StateSpec(
                    name="showed_price",
                    purpose="Summarise price.",
                    allowed_next=("showed_price",),
                    response_hint="Summarise the proposal.",
                ),
            },
            tools={},
        )
        ctx = TurnContext(
            intent=intent,
            current_state="awaiting_seat_pref",
            transcript="No specific seat, you choose.",
            collected={},
            history=[],
            record=None,
        )
        decision = StateDecision(
            action="stay",
            next_state="showed_price",
            tool_name=None,
            tool_params={},
            response_instruction="Summarise the proposed booking.",
            response_facts={},
            slot_updates={},
            reset_scope=None,
        )

        with (
            patch(
                "cascaded.agentic_airline.orchestrators._intent_classifier.classify_turn",
                new=AsyncMock(return_value=types.SimpleNamespace(action="stay", new_intent=None)),
            ),
            patch(
                "cascaded.agentic_airline.orchestrators._state_runner._orchestrator_call",
                new=AsyncMock(return_value=decision),
            ),
            patch(
                "cascaded.agentic_airline.orchestrators._state_runner.generate_response",
                new=AsyncMock(return_value="Ask about seat preference."),
            ) as responder_mock,
        ):
            result = await run_state(ctx)

        self.assertEqual(result.next_state, "awaiting_seat_pref")
        self.assertEqual(result.sentence, "Ask about seat preference.")
        self.assertEqual(
            responder_mock.await_args.args[0],
            "Ask about seat preference.",
        )

    async def test_new_booking_after_terminal_state_restarts_clean(self) -> None:
        memory = ConversationMemory("stream-4")
        entity_store = EntityStore("stream-4")
        memory.put("booking_step", "booked")
        memory.put("meal_pref", "vegetarian")
        memory.put("booked_cabin", "business")
        entity_store.put("confirmation_code", "OLD999", confidence=1.0)

        fake_result = StateRunResult(
            sentence="Which city or airport would you like to depart from?",
            next_state=STATE_START,
            tool_name=None,
            tool_result=None,
            decision=StateDecision(
                action="stay",
                next_state=STATE_START,
                tool_name=None,
                tool_params={},
                response_instruction="",
                response_facts={},
                slot_updates={},
                reset_scope=None,
            ),
        )

        with patch(
            "cascaded.agentic_airline.orchestrators.booking.run_state",
            new=AsyncMock(return_value=fake_result),
        ) as run_state_mock:
            await orchestrate_booking("book me a new flight", "book me a new flight", entity_store, memory)

        ctx = run_state_mock.await_args.args[0]
        self.assertEqual(ctx.current_state, STATE_START)
        self.assertNotIn("meal_pref", ctx.collected)
        self.assertNotIn("booked_cabin", ctx.collected)
        self.assertNotIn("last_confirmation_code", ctx.collected)
        self.assertIsNone(memory.get("meal_pref"))
        self.assertIsNone(memory.get("booked_cabin"))
        self.assertIsNone(entity_store.get("confirmation_code"))

    async def test_route_turn_is_handled_by_run_state_without_booking_shortcut(self) -> None:
        memory = ConversationMemory("stream-5")
        entity_store = EntityStore("stream-5")
        memory.put("booking_step", STATE_AWAITING_DESTINATION)
        memory.put("new_origin", "AGR")
        memory.put("new_destination", "JDH")
        fake_result = StateRunResult(
            sentence="Which city or airport would you like to fly to from Agra?",
            next_state=STATE_AWAITING_DESTINATION,
            tool_name=None,
            tool_result=None,
            decision=StateDecision(
                action="stay",
                next_state=STATE_AWAITING_DESTINATION,
                tool_name=None,
                tool_params={},
                response_instruction="",
                response_facts={},
                slot_updates={},
                reset_scope=None,
            ),
        )

        with patch(
            "cascaded.agentic_airline.orchestrators.booking.run_state",
            new=AsyncMock(return_value=fake_result),
        ) as run_state_mock:
            spoken = await orchestrate_booking(
                "Okay, can do from San Francisco.",
                "Okay, can do from San Francisco.",
                entity_store,
                memory,
            )

        self.assertEqual(spoken, "Which city or airport would you like to fly to from Agra?")
        run_state_mock.assert_awaited_once()

    async def test_intent_flow_cleanup_applies_before_new_slot_updates(self) -> None:
        memory = ConversationMemory("stream-6")
        entity_store = EntityStore("stream-6")
        memory.put("booking_step", STATE_AWAITING_DESTINATION)
        memory.put("new_origin", "AGR")
        memory.put("new_destination", "JDH")
        memory.put("requested_cabin", "business")
        memory.put("suggested_flight", "AA999")
        memory.put("seat_pref", "aisle")
        memory.put("meal_pref", "vegetarian")
        memory.put("price", "999.00")
        entity_store.put("confirmation_code", "OLD123", confidence=1.0)

        fake_result = StateRunResult(
            sentence="Which city or airport would you like to fly to from San Francisco?",
            next_state=STATE_AWAITING_DESTINATION,
            tool_name=None,
            tool_result=None,
            decision=StateDecision(
                action="stay",
                next_state=STATE_AWAITING_DESTINATION,
                tool_name=None,
                tool_params={},
                response_instruction="",
                response_facts={},
                slot_updates={"new_origin": "SFO"},
                reset_scope="intent_flow",
            ),
            cleanup_plan=CleanupPlan(
                forget_keys=(
                    "new_origin",
                    "new_destination",
                    "suggested_flight",
                    "requested_cabin",
                    "seat_pref",
                    "meal_pref",
                    "price",
                    "currency",
                    "booked_cabin",
                ),
                forget_entities=("confirmation_code",),
            ),
        )

        with patch(
            "cascaded.agentic_airline.orchestrators.booking.run_state",
            new=AsyncMock(return_value=fake_result),
        ) as run_state_mock:
            spoken = await orchestrate_booking(
                "San Francisco to New York, please.",
                "San Francisco to New York, please.",
                entity_store,
                memory,
            )

        self.assertEqual(spoken, "Which city or airport would you like to fly to from San Francisco?")
        run_state_mock.assert_awaited_once()
        self.assertEqual(memory.get("booking_step"), STATE_AWAITING_DESTINATION)
        self.assertEqual(memory.get("new_origin"), "SFO")
        self.assertIsNone(memory.get("new_destination"))
        self.assertIsNone(memory.get("suggested_flight"))
        self.assertIsNone(memory.get("requested_cabin"))
        self.assertIsNone(memory.get("seat_pref"))
        self.assertIsNone(memory.get("meal_pref"))
        self.assertIsNone(memory.get("price"))
        self.assertIsNone(entity_store.get("confirmation_code"))


if __name__ == "__main__":
    unittest.main()
