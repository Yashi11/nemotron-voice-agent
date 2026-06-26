# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

# ruff: noqa: D100, D101, D102, D105

import asyncio
import unittest
from collections.abc import Callable
from unittest.mock import AsyncMock

from examples.omni_assistant.nvidia_omni_multimodal_service import NvidiaOmniMultimodalService


class _FakeTurn:
    """Stand-in for one in-flight Omni turn that can be released or cancelled."""

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.cancelled = False
        self.completed = False


class OmniTurnPreemptionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.service = NvidiaOmniMultimodalService(api_key="not-needed", base_url="http://localhost:8000/v1")

        # Run turns as plain asyncio tasks and bypass the pipecat task-manager /
        # metrics machinery, which would otherwise require a full pipeline setup.
        self.service.create_task = lambda coro, name=None: asyncio.create_task(coro, name=name)
        self.service.stop_all_metrics = AsyncMock()

        # Replace the real LLM/TTS turn with a controllable fake that stays
        # "in flight" until released, and records whether it was cancelled.
        self.turns: list[_FakeTurn] = []

        async def fake_run_omni_turn(**_kwargs) -> None:
            turn = _FakeTurn()
            self.turns.append(turn)
            try:
                await turn.release.wait()
                turn.completed = True
            except asyncio.CancelledError:
                turn.cancelled = True
                raise

        self.service._run_omni_turn = fake_run_omni_turn

    async def asyncTearDown(self) -> None:
        # Release/cancel anything still pending so no task is left dangling.
        for turn in self.turns:
            turn.release.set()
        await self.service._cancel_pending_request()

    async def _wait_for(self, predicate: Callable[[], bool], timeout: float = 1.0) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not predicate():
            if loop.time() > deadline:
                self.fail("condition was not met within the timeout")
            await asyncio.sleep(0.005)

    def _fill_audio(self, seconds: float = 1.0) -> None:
        # PCM16 mono payload comfortably above the min_user_audio_secs gate (0.3s).
        nbytes = int(self.service._sample_rate * self.service._channels * 2 * seconds)
        self.service._audio_buffer = [b"\x00" * nbytes]

    async def test_audio_turn_preempts_in_flight_turn(self) -> None:
        # First (slow) turn goes in flight and blocks.
        self._fill_audio()
        await self.service._maybe_run_audio_turn()
        first_task = self.service._pending_request
        self.assertIsNotNone(first_task)
        await self._wait_for(lambda: len(self.turns) == 1)
        self.assertFalse(first_task.done())

        # A new user turn arrives while the first is still running.
        self._fill_audio()
        await self.service._maybe_run_audio_turn()
        second_task = self.service._pending_request

        # The previous turn must be preempted (cancelled), not skipped...
        self.assertTrue(first_task.cancelled())
        self.assertTrue(self.turns[0].cancelled)
        self.service.stop_all_metrics.assert_awaited()

        # ...and a brand-new turn must have started in its place.
        self.assertIsNotNone(second_task)
        self.assertIsNot(second_task, first_task)
        await self._wait_for(lambda: len(self.turns) == 2)
        self.assertFalse(second_task.done())

    async def test_text_turn_preempts_in_flight_turn(self) -> None:
        self.service._pending_content_parts = [{"type": "text", "text": "first"}]
        await self.service._maybe_run_text_or_multimodal_turn(None)
        first_task = self.service._pending_request
        self.assertIsNotNone(first_task)
        await self._wait_for(lambda: len(self.turns) == 1)
        self.assertFalse(first_task.done())

        self.service._pending_content_parts = [{"type": "text", "text": "second"}]
        await self.service._maybe_run_text_or_multimodal_turn(None)
        second_task = self.service._pending_request

        self.assertTrue(first_task.cancelled())
        self.assertTrue(self.turns[0].cancelled)
        self.assertIsNot(second_task, first_task)
        await self._wait_for(lambda: len(self.turns) == 2)
        self.assertFalse(second_task.done())

    async def test_context_turn_yields_to_in_flight_audio_turn(self) -> None:
        self._fill_audio()
        await self.service._maybe_run_audio_turn()
        audio_task = self.service._pending_request
        self.assertIsNotNone(audio_task)
        await self._wait_for(lambda: len(self.turns) == 1)
        self.assertFalse(audio_task.done())

        # Context/run echo for the same spoken turn must yield, not preempt.
        self.service._pending_content_parts = [{"type": "text", "text": "echo"}]
        await self.service._maybe_run_text_or_multimodal_turn(None)

        self.assertIs(self.service._pending_request, audio_task)
        self.assertFalse(audio_task.cancelled())
        self.assertFalse(self.turns[0].cancelled)
        self.assertEqual(len(self.turns), 1)
        self.service.stop_all_metrics.assert_not_awaited()

    async def test_audio_turn_below_min_duration_does_not_preempt(self) -> None:
        # A valid turn is running.
        self._fill_audio()
        await self.service._maybe_run_audio_turn()
        first_task = self.service._pending_request
        await self._wait_for(lambda: len(self.turns) == 1)

        # A sub-threshold blip must NOT cancel the in-flight turn.
        self._fill_audio(seconds=0.05)
        await self.service._maybe_run_audio_turn()

        self.assertIs(self.service._pending_request, first_task)
        self.assertFalse(first_task.cancelled())
        self.assertFalse(self.turns[0].cancelled)
        self.assertEqual(len(self.turns), 1)


if __name__ == "__main__":
    unittest.main()
