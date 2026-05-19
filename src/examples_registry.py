# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Built-in voice-agent examples — single source of truth.

Two-level dict: outer key is the ``family`` (``cascaded`` /
``speech-to-speech``), inner key is the example ``id``. Each entry is plain
data (``label`` / ``slots`` / ``bot``). To add a new built-in, append an entry;
nothing else needs to change.
"""

import os
from collections.abc import Callable, Iterator
from typing import Any, TypedDict

from cascaded.agentic_airline.pipeline import bot as agentic_airline_bot
from cascaded.generic.pipeline import bot as cascaded_bot
from speech_to_speech.generic.pipeline import bot as s2s_bot


class ExampleEntry(TypedDict):
    """Raw registry entry for one example."""

    label: str
    slots: list[str]
    bot: Callable[..., Any]


class EnrichedExample(ExampleEntry):
    """Registry entry plus derived family/id/key fields."""

    family: str
    id: str
    key: str


class PipelineFamily(TypedDict):
    """Pipeline family metadata exposed to the client."""

    id: str
    label: str


_DEFAULT_FAMILY = "cascaded"
_DEFAULT_EXAMPLES = {
    "cascaded": "generic",
    "speech-to-speech": "generic",
}
PIPELINE_FAMILIES: tuple[PipelineFamily, ...] = (
    {"id": "cascaded", "label": "Cascaded"},
    {"id": "speech-to-speech", "label": "Speech-to-Speech"},
)

EXAMPLES: dict[str, dict[str, ExampleEntry]] = {
    "cascaded": {
        "generic": {
            "label": "Generic Cascaded",
            "slots": ["llm", "asr", "tts"],
            "bot": cascaded_bot,
        },
        "agentic-airline": {
            "label": "Agentic Airline",
            "slots": ["fast-llm", "orchestrator-llm", "booking-server", "asr", "tts"],
            "bot": agentic_airline_bot,
        },
    },
    "speech-to-speech": {
        "generic": {
            "label": "Speech to Speech",
            "slots": ["s2s"],
            "bot": s2s_bot,
        },
    },
}


def pipeline_family_ids() -> tuple[str, ...]:
    """Return valid pipeline family ids."""
    return tuple(family["id"] for family in PIPELINE_FAMILIES)


def pipeline_options(families: tuple[str, ...] | None = None) -> list[PipelineFamily]:
    """Return client-facing pipeline family metadata."""
    allowed = set(pipeline_family_ids() if families is None else families)
    return [family for family in PIPELINE_FAMILIES if family["id"] in allowed]


def _effective_key(value: str = "") -> str:
    """Resolve the requested example key; ``DEFAULT_PIPELINE_MODE`` env wins over args."""
    return os.getenv("DEFAULT_PIPELINE_MODE", "").lower() or (value or _DEFAULT_FAMILY).lower()


def _enrich(family: str, example_id: str, entry: ExampleEntry) -> EnrichedExample:
    """Project a registry entry into a flat dict with family/id and a wire ``key``.

    ``key`` is always ``"<family>/<id>"`` — unambiguous by construction, since
    the nested dict structure makes (family, id) tuples unique.
    """
    return {**entry, "family": family, "id": example_id, "key": f"{family}/{example_id}"}


def iter_all(families: tuple[str, ...] | None = None) -> Iterator[EnrichedExample]:
    """Yield every registered example as an enriched flat dict."""
    allowed = set(pipeline_family_ids() if families is None else families)
    for family, group in EXAMPLES.items():
        if family not in allowed:
            continue
        for example_id, entry in group.items():
            yield _enrich(family, example_id, entry)


def iter_family_defaults(families: tuple[str, ...] | None = None) -> Iterator[EnrichedExample]:
    """Yield the configured default example for each family."""
    allowed = set(pipeline_family_ids() if families is None else families)
    for family, group in EXAMPLES.items():
        if family not in allowed:
            continue
        example_id = _DEFAULT_EXAMPLES[family]
        yield _enrich(family, example_id, group[example_id])


def find(value: str = "") -> EnrichedExample:
    """Look up an example by ``family/id``, or by ``family`` (returns its first example).

    Falls back to the default example when the value matches neither.
    """
    key = _effective_key(value)
    if "/" in key:
        family, example_id = key.split("/", 1)
        if family in EXAMPLES and example_id in EXAMPLES[family]:
            return _enrich(family, example_id, EXAMPLES[family][example_id])
    if EXAMPLES.get(key):
        example_id = _DEFAULT_EXAMPLES[key]
        return _enrich(key, example_id, EXAMPLES[key][example_id])
    example_id = _DEFAULT_EXAMPLES[_DEFAULT_FAMILY]
    return _enrich(_DEFAULT_FAMILY, example_id, EXAMPLES[_DEFAULT_FAMILY][example_id])


def metadata(example: EnrichedExample) -> dict:
    """Strip non-serialisable fields (``bot``) for client payloads."""
    return {
        "family": example["family"],
        "id": example["id"],
        "key": example["key"],
        "label": example["label"],
        "slots": example["slots"],
    }


def selector_options(families: tuple[str, ...] | None = None) -> list[dict]:
    """Return metadata for the default example in each family."""
    return [metadata(e) for e in iter_family_defaults(families)]


def all_selector_options(families: tuple[str, ...] | None = None) -> list[dict]:
    """Return metadata for every registered example."""
    return [metadata(e) for e in iter_all(families)]
