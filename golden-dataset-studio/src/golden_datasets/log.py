"""The append-only annotation log, `<catalog>/golden-dataset-studio/annotations.jsonl` (spec §4.1, §4.3).

People only ever append to it; nothing in it is edited. An edit is a new event whose `supersedes` names the old one.
Readers keep the byte offset they have read up to and fetch only what was appended since (spec §10).
"""

from __future__ import annotations

import json
import threading
import uuid

from .storage import Root

EVENT_TYPES = {"verdict", "comment", "approve", "reopen"}
VERDICTS = {"correct", "wrong", "missing", "question"}
TARGET_KINDS = {"match", "occurrence", "page", "rule"}


def new_id(prefix: str = "an") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def validate(event: dict) -> None:
    if event.get("type") not in EVENT_TYPES:
        raise ValueError(f"event type must be one of {sorted(EVENT_TYPES)}")
    if event["type"] == "verdict" and event.get("verdict") not in VERDICTS:
        raise ValueError(f"verdict must be one of {sorted(VERDICTS)}")
    if event["type"] != "verdict" and event.get("verdict") is not None:
        raise ValueError("only verdict events carry a verdict")
    target = event.get("target") or {}
    if target.get("kind") not in TARGET_KINDS:
        raise ValueError(f"target.kind must be one of {sorted(TARGET_KINDS)}")
    if event["type"] == "verdict" and event["verdict"] == "missing" and target["kind"] not in ("occurrence", "page"):
        raise ValueError("'missing' applies only to record locators (occurrence) and page rules (page)")
    for key in ("annotation_id", "at", "author"):
        if not event.get(key):
            raise ValueError(f"event needs {key}")


class AnnotationLog:
    """One catalog's log. `events()` returns every event, reading only the bytes appended since the last call."""

    def __init__(self, root: Root, path: str):
        self.root, self.path = root, path
        self._offset = 0
        self._partial = b""
        self._events: list[dict] = []
        self._lock = threading.Lock()

    def refresh(self) -> int:
        """Read what was appended since the last read. Returns how many new events arrived."""
        with self._lock:
            data = self.root.read_from(self.path, self._offset)
            if not data:
                return 0
            self._offset += len(data)
            buf = self._partial + data
            lines = buf.split(b"\n")
            self._partial = lines.pop()  # an incomplete last line waits for the next read
            new = [json.loads(line) for line in lines if line.strip()]
            self._events.extend(new)
            return len(new)

    def events(self) -> list[dict]:
        self.refresh()
        return list(self._events)

    @property
    def offset(self) -> int:
        return self._offset

    def append(self, event: dict) -> dict:
        validate(event)
        self.root.append(self.path, (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
        return event

    def append_many(self, events: list[dict]) -> None:
        for e in events:
            validate(e)
        if events:
            data = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events).encode("utf-8")
            self.root.append(self.path, data)
