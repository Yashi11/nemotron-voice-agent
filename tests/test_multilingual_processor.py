# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

# ruff: noqa: D100, D101, D102

import unittest

from pipecat.utils.text.base_text_aggregator import AggregationType

from examples.multilingual.multilingual_processor import (
    MultilingualTextAggregator,
    fixed_session_language_addon_key,
)


async def _collect_aggregations(chunks: list[str]):
    aggregator = MultilingualTextAggregator()
    aggregations = []
    for chunk in chunks:
        async for aggregation in aggregator.aggregate(chunk):
            aggregations.append(aggregation)
    if tail := await aggregator.flush():
        aggregations.append(tail)
    return aggregations


def _spoken_texts(aggregations) -> list[str]:
    return [aggregation.text for aggregation in aggregations if aggregation.type == AggregationType.SENTENCE.value]


class MultilingualTextAggregatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_json_response_field_is_spoken(self) -> None:
        aggregations = await _collect_aggregations(
            [
                '{"lang_id":"fr-FR","response":"Bonjour. ',
                'Comment puis-je aider ?"}',
            ]
        )

        self.assertEqual(" ".join(_spoken_texts(aggregations)), "Bonjour. Comment puis-je aider ?")

    async def test_language_handler_fires_when_lang_id_is_complete(self) -> None:
        languages: list[str] = []

        async def on_language(code: str) -> None:
            languages.append(code)

        aggregator = MultilingualTextAggregator(on_language=on_language)
        async for _ in aggregator.aggregate('{"lang_id":"es-ES","response":"Ho'):
            pass

        self.assertEqual(languages, ["es-ES"])

    async def test_plain_text_fallback_is_spoken_when_json_is_missing(self) -> None:
        aggregations = await _collect_aggregations(
            [
                "Bonjour tout le monde.",
            ]
        )

        self.assertEqual(_spoken_texts(aggregations), ["Bonjour tout le monde."])


class FixedSessionLanguageAddonKeyTests(unittest.TestCase):
    def test_exact_locale_prompt_wins(self) -> None:
        catalog = {
            "fixed_session_language_addon": {"content": "english"},
            "fixed_session_language_addon_es": {"content": "spanish"},
            "fixed_session_language_addon_es_us": {"content": "spanish us"},
        }

        self.assertEqual(fixed_session_language_addon_key(catalog, "es-US"), "fixed_session_language_addon_es_us")

    def test_language_family_prompt_wins_before_fallback(self) -> None:
        catalog = {
            "fixed_session_language_addon": {"content": "english"},
            "fixed_session_language_addon_fr": {"content": "french"},
        }

        self.assertEqual(fixed_session_language_addon_key(catalog, "fr-FR"), "fixed_session_language_addon_fr")

    def test_missing_language_prompt_uses_english_fallback(self) -> None:
        catalog = {
            "fixed_session_language_addon": {"content": "english"},
            "fixed_session_language_addon_fr": {"content": "french"},
        }

        self.assertEqual(fixed_session_language_addon_key(catalog, "de-DE"), "fixed_session_language_addon")


if __name__ == "__main__":
    unittest.main()
