# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Ephemeral session-scoped webcam frame store."""

from __future__ import annotations

import base64
import contextlib
import itertools
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from utils import parse_env_float, parse_env_int


@dataclass(frozen=True)
class WebcamFrame:
    """One compressed browser webcam snapshot."""

    id: str
    session_id: str
    sequence: int
    name: str
    content_type: str
    data: bytes
    created_at: str

    def metadata(self) -> dict[str, str | int]:
        """Return public frame metadata without raw bytes."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "sequence": self.sequence,
            "kind": "image",
            "name": self.name,
            "content_type": self.content_type,
            "bytes": len(self.data),
            "created_at": self.created_at,
        }

    def data_url(self) -> str:
        """Return the frame payload as a model-friendly data URL."""
        encoded = base64.b64encode(self.data).decode("ascii")
        return f"data:{self.content_type};base64,{encoded}"


_lock = threading.Lock()
_sequence = itertools.count(1)
_frames_by_session: dict[str, list[WebcamFrame]] = {}
_listeners_by_session: dict[str, list[Callable[[], None]]] = {}


def register_webcam_frame_listener(session_id: str, listener: Callable[[], None]) -> Callable[[], None]:
    """Register a callback invoked whenever a session stores a new webcam frame."""
    cleaned_session_id = session_id.strip()
    if not cleaned_session_id:
        return lambda: None
    with _lock:
        _listeners_by_session.setdefault(cleaned_session_id, []).append(listener)

    def unregister() -> None:
        with _lock:
            listeners = _listeners_by_session.get(cleaned_session_id)
            if not listeners:
                return
            with contextlib.suppress(ValueError):
                listeners.remove(listener)
            if not listeners:
                _listeners_by_session.pop(cleaned_session_id, None)

    return unregister


def webcam_client_config() -> dict[str, float | int | bool]:
    """Return browser-facing webcam capture defaults from local env knobs."""
    return {
        "sample_interval_seconds": parse_env_float("WEBCAM_SAMPLE_INTERVAL_SECONDS", 1, min_value=0.5),
        "frame_max_width": parse_env_int("WEBCAM_FRAME_MAX_WIDTH", 640, min_value=160),
        "jpeg_quality": parse_env_float("WEBCAM_JPEG_QUALITY", 0.7, min_value=0.1),
        "initial_upload_enabled": True,
        "initial_upload_delay_ms": parse_env_int("WEBCAM_INITIAL_UPLOAD_DELAY_MS", 700, min_value=0),
    }


def store_webcam_frame(
    *,
    session_id: str,
    name: str,
    content_type: str,
    data: bytes,
) -> WebcamFrame:
    """Store one ephemeral webcam snapshot for a live session."""
    cleaned_session_id = session_id.strip()
    cleaned_content_type = content_type.strip().lower() or "image/jpeg"
    if not cleaned_session_id:
        raise ValueError("session_id is required")
    if not cleaned_content_type.startswith("image/"):
        raise ValueError("webcam frame must be an image")
    if not data:
        raise ValueError("webcam frame is empty")

    max_bytes = parse_env_int("WEBCAM_FRAME_MAX_BYTES", 5_000_000, min_value=1)
    if len(data) > max_bytes:
        raise ValueError(f"webcam frame exceeds max size ({max_bytes} bytes)")

    limit = parse_env_int("WEBCAM_FRAME_RING_LIMIT", 8, min_value=1)
    with _lock:
        frame = WebcamFrame(
            id=uuid.uuid4().hex,
            session_id=cleaned_session_id,
            sequence=next(_sequence),
            name=name.strip() or "webcam-frame.jpg",
            content_type=cleaned_content_type,
            data=data,
            created_at=datetime.now(UTC).isoformat(),
        )
        frames = _frames_by_session.setdefault(cleaned_session_id, [])
        frames.append(frame)
        del frames[:-limit]
        listeners = list(_listeners_by_session.get(cleaned_session_id, ()))
    for listener in listeners:
        listener()
    return frame


def latest_webcam_frame(session_id: str) -> WebcamFrame | None:
    """Return the latest webcam frame for a session."""
    with _lock:
        frames = list(_frames_by_session.get(session_id.strip(), ()))
    return frames[-1] if frames else None


def get_webcam_frame(session_id: str, frame_id: str) -> WebcamFrame | None:
    """Return a specific webcam frame by id."""
    cleaned_session_id = session_id.strip()
    cleaned_frame_id = frame_id.strip()
    if not cleaned_session_id or not cleaned_frame_id:
        return None
    with _lock:
        frames = list(_frames_by_session.get(cleaned_session_id, ()))
    return next((frame for frame in frames if frame.id == cleaned_frame_id), None)


def clear_session_webcam_frames(session_id: str) -> None:
    """Drop all webcam frames for a session."""
    with _lock:
        _frames_by_session.pop(session_id.strip(), None)
        _listeners_by_session.pop(session_id.strip(), None)


def clear_session_webcam_frame_data(session_id: str) -> None:
    """Drop stored webcam frames but keep live-session listeners registered."""
    with _lock:
        _frames_by_session.pop(session_id.strip(), None)
