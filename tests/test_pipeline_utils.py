# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

# ruff: noqa: D100, D101, D102

import os
import unittest
from unittest.mock import patch

from pipecat.turns.user_start.transcription_user_turn_start_strategy import TranscriptionUserTurnStartStrategy
from pipecat.turns.user_start.vad_user_turn_start_strategy import VADUserTurnStartStrategy
from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy, TurnAnalyzerUserTurnStopStrategy

from examples.shared.pipeline_utils import build_user_aggregator_params


class _FakeTurnAnalyzer:
    pass


class PipelineUtilsTurnStrategyTests(unittest.TestCase):
    def test_default_turn_strategies_use_only_vad_for_turn_start(self) -> None:
        with (
            patch.dict(os.environ, {"USE_SILERO_VAD_TURN_DETECTION": "false"}),
            patch(
                "pipecat.audio.turn.smart_turn.local_smart_turn_v3.LocalSmartTurnAnalyzerV3",
                return_value=_FakeTurnAnalyzer(),
            ),
        ):
            params = build_user_aggregator_params()

        strategies = params.user_turn_strategies
        self.assertIsNotNone(strategies)
        assert strategies is not None

        self.assertEqual(len(strategies.start), 1)
        self.assertIsInstance(strategies.start[0], VADUserTurnStartStrategy)
        self.assertFalse(any(isinstance(strategy, TranscriptionUserTurnStartStrategy) for strategy in strategies.start))
        self.assertEqual(len(strategies.stop), 1)
        self.assertIsInstance(strategies.stop[0], TurnAnalyzerUserTurnStopStrategy)

    def test_silero_timeout_turn_strategies_use_only_vad_for_turn_start(self) -> None:
        with patch.dict(
            os.environ,
            {
                "USE_SILERO_VAD_TURN_DETECTION": "true",
                "SILERO_VAD_STOP_SECS": "0.5",
            },
        ):
            params = build_user_aggregator_params()

        strategies = params.user_turn_strategies
        self.assertIsNotNone(strategies)
        assert strategies is not None

        self.assertEqual(len(strategies.start), 1)
        self.assertIsInstance(strategies.start[0], VADUserTurnStartStrategy)
        self.assertFalse(any(isinstance(strategy, TranscriptionUserTurnStartStrategy) for strategy in strategies.start))
        self.assertEqual(len(strategies.stop), 1)
        self.assertIsInstance(strategies.stop[0], SpeechTimeoutUserTurnStopStrategy)
