# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Nemotron Voice Chat ↔ Pipecat OpenAI Realtime compatibility shim.

Monkey-patches ``pipecat.services.openai.realtime.events.parse_server_event``
to:
  1. Drop duplicate ``response.output_text.*`` events (Nemotron sends the same
     transcript via both "text" and "audio_transcript" — Pipecat handles both,
     causing double words).
  2. Fill missing fields that Pipecat's Pydantic models require but Nemotron
     may omit.
  3. Accumulate incremental user-transcription deltas into a running transcript
     (Pipecat's client displays each delta as a *replacement*).

Usage — import once before the pipeline runs::

    import speech_to_speech.nemotron_compat  # noqa: F401

Safe when talking to OpenAI: only fills defaults for fields already absent.
"""

import json
import uuid

from loguru import logger
from pipecat.services.openai.realtime import events as _events

_DROP_EVENT_TYPES = {
    "response.output_text.delta",
    "response.output_text.done",
}

_RESPONSE_STREAM_EVENTS = {
    "response.output_audio.delta",
    "response.output_audio.done",
    "response.output_audio_transcript.delta",
    "response.output_audio_transcript.done",
}


def _ensure(d: dict, key: str, default):
    """Set *d[key]* to *default* only if the key is missing or ``None``."""
    if key not in d or d[key] is None:
        d[key] = default


def _nemo_id() -> str:
    return f"nemo_{uuid.uuid4().hex[:12]}"


class _ResponseTracker:
    """Keeps a single response_id / item_id pair stable across audio-delta events."""

    def __init__(self):
        self.response_id: str | None = None
        self.item_id: str | None = None

    def get_or_create(self):
        if self.response_id is None:
            self.response_id = f"nemo_resp_{uuid.uuid4().hex[:12]}"
            self.item_id = f"nemo_item_{uuid.uuid4().hex[:12]}"
        return self.response_id, self.item_id

    def reset(self):
        self.response_id = None
        self.item_id = None


_tracker = _ResponseTracker()


class _UserTranscriptAccumulator:
    """Accumulates incremental transcription deltas into a running transcript."""

    def __init__(self):
        self._text = ""

    def append(self, delta: str) -> str:
        self._text += delta
        return self._text

    def reset(self):
        self._text = ""


_user_transcript = _UserTranscriptAccumulator()


def _fill_response_fields(data: dict):
    rid, iid = _tracker.get_or_create()
    _ensure(data, "response_id", rid)
    _ensure(data, "item_id", iid)
    _ensure(data, "output_index", 0)
    _ensure(data, "content_index", 0)


def _normalise(raw: str) -> str:
    data = json.loads(raw)
    evt_type = data.get("type", "")

    _ensure(data, "event_id", str(uuid.uuid4()))

    if evt_type in ("session.created", "session.updated"):
        session = data.setdefault("session", {})
        if "modalities" in session and "output_modalities" not in session:
            session["output_modalities"] = session.pop("modalities")

    elif evt_type in _RESPONSE_STREAM_EVENTS:
        _fill_response_fields(data)

    elif evt_type == "conversation.item.input_audio_transcription.delta":
        _ensure(data, "item_id", _nemo_id())
        _ensure(data, "content_index", 0)
        if "delta" in data:
            data["delta"] = _user_transcript.append(data["delta"])

    elif evt_type == "conversation.item.input_audio_transcription.completed":
        _ensure(data, "item_id", _nemo_id())
        _ensure(data, "content_index", 0)
        _user_transcript.reset()

    elif evt_type == "input_audio_buffer.speech_started":
        _ensure(data, "audio_start_ms", 0)
        _ensure(data, "item_id", _nemo_id())
        _tracker.reset()
        _user_transcript.reset()

    elif evt_type == "input_audio_buffer.speech_stopped":
        _ensure(data, "audio_end_ms", 0)
        _ensure(data, "item_id", _nemo_id())

    elif evt_type == "input_audio_buffer.committed":
        _ensure(data, "item_id", _nemo_id())

    elif evt_type in ("response.created", "response.done"):
        resp = data.setdefault("response", {})
        _ensure(resp, "id", _nemo_id())
        _ensure(resp, "object", "realtime.response")
        _ensure(resp, "status", "completed" if evt_type == "response.done" else "in_progress")
        _ensure(resp, "status_details", None)
        _ensure(resp, "output", [])
        if evt_type == "response.done":
            _tracker.reset()

    elif evt_type in ("response.output_item.added", "response.output_item.done"):
        rid, _ = _tracker.get_or_create()
        _ensure(data, "response_id", rid)
        _ensure(data, "output_index", 0)
        item = data.setdefault("item", {})
        _ensure(item, "type", "message")
        _ensure(item, "id", uuid.uuid4().hex)

    elif evt_type in ("response.content_part.added", "response.content_part.done"):
        _fill_response_fields(data)
        part = data.setdefault("part", {})
        _ensure(part, "type", "output_audio")

    elif evt_type in ("conversation.item.added", "conversation.item.done"):
        item = data.setdefault("item", {})
        _ensure(item, "type", "message")
        _ensure(item, "id", uuid.uuid4().hex)

    elif evt_type == "conversation.created":
        conv = data.setdefault("conversation", {})
        _ensure(conv, "id", _nemo_id())
        _ensure(conv, "object", "realtime.conversation")

    elif evt_type in (
        "response.function_call_arguments.delta",
        "response.function_call_arguments.done",
    ):
        _fill_response_fields(data)
        _ensure(data, "call_id", _nemo_id())

    return json.dumps(data)


# Monkey-patch: intercept Pipecat's event parser

_original_parse = _events.parse_server_event


def _patched_parse_server_event(raw: str):
    try:
        peek = json.loads(raw)
    except json.JSONDecodeError:
        return _original_parse(raw)

    evt_type = peek.get("type", "")

    if evt_type in _DROP_EVENT_TYPES:
        logger.debug(f"Nemotron compat: dropping duplicate '{evt_type}'")
        _ensure(peek, "event_id", str(uuid.uuid4()))
        return _events.ServerEvent(event_id=peek["event_id"], type="nemotron_compat.dropped")

    if evt_type not in _events._server_event_types:
        logger.debug(f"Nemotron compat: skipping unknown '{evt_type}'")
        _ensure(peek, "event_id", str(uuid.uuid4()))
        return _events.ServerEvent(event_id=peek["event_id"], type=evt_type)

    return _original_parse(_normalise(raw))


_events.parse_server_event = _patched_parse_server_event
logger.info("Nemotron Voice Chat compatibility shim applied")
