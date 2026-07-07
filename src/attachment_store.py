# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""In-memory session-scoped store for uploaded media attachments."""

from __future__ import annotations

import base64
import contextlib
import itertools
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class Attachment:
    """Session-scoped uploaded media metadata and payload."""

    id: str
    session_id: str
    sequence: int
    kind: str
    name: str
    content_type: str
    data: bytes
    created_at: str

    def metadata(self) -> dict[str, str | int]:
        """Return public metadata without raw bytes."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "sequence": self.sequence,
            "kind": self.kind,
            "name": self.name,
            "content_type": self.content_type,
            "bytes": len(self.data),
            "created_at": self.created_at,
        }

    def data_url(self) -> str:
        """Return the attachment payload as a browser/model-friendly data URL."""
        encoded = base64.b64encode(self.data).decode("ascii")
        return f"data:{self.content_type};base64,{encoded}"


_lock = threading.Lock()
_sequence = itertools.count(1)
_attachments_by_session: dict[str, list[Attachment]] = {}
_listeners_by_session: dict[str, list[Callable[[], None]]] = {}


def register_attachment_listener(session_id: str, listener: Callable[[], None]) -> Callable[[], None]:
    """Register a callback invoked whenever a session stores a new attachment."""
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


def store_attachment(
    *,
    session_id: str,
    kind: str,
    name: str,
    content_type: str,
    data: bytes,
) -> Attachment:
    """Store one attachment for a live session."""
    cleaned_session_id = session_id.strip()
    cleaned_kind = kind.strip().lower()
    if not cleaned_session_id:
        raise ValueError("session_id is required")
    if cleaned_kind not in {"image", "audio", "video"}:
        raise ValueError("kind must be image, audio, or video")
    if not data:
        raise ValueError("attachment is empty")

    with _lock:
        attachment = Attachment(
            id=uuid.uuid4().hex,
            session_id=cleaned_session_id,
            sequence=next(_sequence),
            kind=cleaned_kind,
            name=name.strip() or "attachment",
            content_type=content_type.strip() or f"{cleaned_kind}/*",
            data=data,
            created_at=datetime.now(UTC).isoformat(),
        )
        _attachments_by_session.setdefault(cleaned_session_id, []).append(attachment)
        listeners = list(_listeners_by_session.get(cleaned_session_id, ()))
    for listener in listeners:
        listener()
    return attachment


def latest_attachment(session_id: str) -> Attachment | None:
    """Return the latest uploaded attachment for a session."""
    with _lock:
        attachments = list(_attachments_by_session.get(session_id.strip(), ()))
    return attachments[-1] if attachments else None


def get_attachment(session_id: str, attachment_id: str) -> Attachment | None:
    """Return a session attachment by id."""
    cleaned_session_id = session_id.strip()
    cleaned_attachment_id = attachment_id.strip()
    if not cleaned_session_id or not cleaned_attachment_id:
        return None
    with _lock:
        attachments = list(_attachments_by_session.get(cleaned_session_id, ()))
    return next((attachment for attachment in attachments if attachment.id == cleaned_attachment_id), None)


def clear_session_attachments(session_id: str) -> None:
    """Drop all attachments for a session."""
    with _lock:
        _attachments_by_session.pop(session_id.strip(), None)
        _listeners_by_session.pop(session_id.strip(), None)
