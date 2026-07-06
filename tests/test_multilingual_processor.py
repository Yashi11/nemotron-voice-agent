# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

# ruff: noqa: D100, D101, D102

import unittest

from examples.multilingual.multilingual_processor import (
    LANG_TYPE,
    META_TYPE,
    MultilingualTextAggregator,
    fixed_session_language_addon_key,
)


async def _collect_aggregations(chunks: list[str]):
    aggregator = MultilingualTextAggregator()
    aggregations = []
    for chunk in chunks:
        async for aggregation in aggregator.aggregate(chunk):
            aggregations.append(aggregation)
    while tail := await aggregator.flush():
        aggregations.append(tail)
    return aggregations


def _spoken_texts(aggregations) -> list[str]:
    return [aggregation.text for aggregation in aggregations if aggregation.type not in {LANG_TYPE, META_TYPE}]


def _metadata_texts(aggregations) -> list[str]:
    return [aggregation.text for aggregation in aggregations if aggregation.type == META_TYPE]


class MultilingualTextAggregatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_newline_metadata_is_not_spoken(self) -> None:
        aggregations = await _collect_aggregations(
            [
                "Language: en-US Text: Hello there.",
                "\nMetaData: internal note. This must not be spoken.",
            ]
        )

        self.assertEqual(_spoken_texts(aggregations), ["Hello there."])
        self.assertTrue(any(aggregation.type == META_TYPE for aggregation in aggregations))

    async def test_split_metadata_marker_is_not_spoken(self) -> None:
        aggregations = await _collect_aggregations(
            [
                "Language: en-US Text: Hello there. Me",
                "taData: hidden note.",
            ]
        )

        self.assertEqual(_spoken_texts(aggregations), ["Hello there."])
        self.assertTrue(
            any(
                aggregation.type == META_TYPE and aggregation.text == "MetaData: hidden note."
                for aggregation in aggregations
            )
        )

    async def test_only_text_field_is_spoken(self) -> None:
        aggregations = await _collect_aggregations(
            [
                "Language: en-US Text: Hello there.MetaData: user intent. Extra reasoning after metadata.",
            ]
        )

        self.assertEqual(_spoken_texts(aggregations), ["Hello there."])
        self.assertEqual(
            _metadata_texts(aggregations),
            ["MetaData: user intent. Extra reasoning after metadata."],
        )

    async def test_missing_text_marker_drops_raw_output(self) -> None:
        aggregations = await _collect_aggregations(
            [
                "Language: en-US Hello there. MetaData: hidden note.",
            ]
        )

        self.assertEqual(aggregations, [])

    async def test_flush_preserves_metadata_after_spoken_text(self) -> None:
        aggregator = MultilingualTextAggregator()
        async for _ in aggregator.aggregate("Language: en-US Text:"):
            pass
        aggregator._buf = "Hello there. MetaData: hidden note."

        first = await aggregator.flush()
        second = await aggregator.flush()

        self.assertEqual(first.text if first else "", "Hello there.")
        self.assertEqual(second.text if second else "", "MetaData: hidden note.")
        self.assertEqual(second.type if second else "", META_TYPE)


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
