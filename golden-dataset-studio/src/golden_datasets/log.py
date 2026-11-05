"""The append-only annotation log, `<catalog>/golden-dataset-studio/annotations.jsonl` (spec §4.1, §4.3).

People only ever append to it; nothing in it is edited. An edit is a new event whose `supersedes` names the old one.
Two optional fields pass through untouched (Evals spec §4.2, §4.3): `author_role` (`sme` | `engineer`: the author's
role when they wrote it) and `compared_with` (what a note on a diff was compared with). A comment may carry `anchor`
{css_path, char_start, char_end, text}: the text on the page it is about (sme-fixes §1).
Readers keep the byte offset they have read up to and fetch only what was appended since (spec §10).
"""

from __future__ import annotations

import json
import threading
import uuid

from .storage import Root

#: `reset` (phase1-followups spec §4): a rule's reviews in this catalog go back to "not reviewed" and its approval ends.
EVENT_TYPES = {"verdict", "comment", "approve", "reopen", "reset"}
VERDICTS = {"correct", "wrong", "missing", "question"}
TARGET_KINDS = {"match", "occurrence", "page", "rule", "ruleset"}
#: What a comment on a whole rule or on the ruleset is about (Rules tab sidebar).
TOPICS = {"new-rule", "approach", "question-rule", "other"}
AUTHOR_ROLES = {"sme", "engineer"}
#: Why a value is wrong, flagged after ✕ (sme-fixes §6): `not_on_page` = the page doesn't state this property anywhere.
REASONS = {"not_on_page"}
#: A piece of a reviewer's expected answer (`expected.segments[].polarity`, sme-fixes §1): `in` the answer, or `out` of
#: it (text the rule's value has but shouldn't). Missing = `in`, so events written before polarity read the same.
POLARITIES = {"in", "out"}
#: The first profiles were first names only (and misspelled Nicolas): events they wrote keep those names as `author`,
#: so whoever reads an author by person (profiles, "Annotated by") maps them to the full names.
FULL_NAMES = {"Jared": "Jared Diener", "Cadence": "Cadence Calixto", "Nicholas": "Nicolas Soto",
              "Rohit": "Rohit Joy", "Eric": "Eric Riddoch", "Seth": "Seth Alt"}


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
    if target["kind"] == "ruleset" and event["type"] != "comment":
        raise ValueError("only comments target the ruleset")
    if event["type"] == "reset" and (target["kind"] != "rule" or not (event.get("note") or "").strip()):
        raise ValueError("a reset targets a rule and says why (note)")
    if event.get("topic") is not None and (event["type"] != "comment" or event["topic"] not in TOPICS):
        raise ValueError(f"topic is for comments, one of {sorted(TOPICS)}")
    if event["type"] == "verdict" and event["verdict"] == "missing" and target["kind"] not in ("occurrence", "page") \
            and not (target["kind"] == "match" and target.get("item")):
        raise ValueError("'missing' applies only to record locators (occurrence), page rules (page) and a list's "
                         "items (match, item)")
    if event.get("author_role") is not None and event["author_role"] not in AUTHOR_ROLES:
        raise ValueError(f"author_role must be one of {sorted(AUTHOR_ROLES)}")
    if event.get("reasons") is not None and (event.get("verdict") != "wrong" or not isinstance(event["reasons"], list)
                                             or not set(event["reasons"]) <= REASONS):
        raise ValueError(f"reasons go on a wrong verdict, a list of {sorted(REASONS)}")
    for seg in (event.get("expected") or {}).get("segments") or []:
        if seg.get("polarity", "in") not in POLARITIES:
            raise ValueError(f"a segment's polarity must be one of {sorted(POLARITIES)}")
    anchor = event.get("anchor")
    if anchor is not None and (event["type"] != "comment" or not isinstance(anchor, dict) or not anchor.get("css_path")):
        raise ValueError("anchor is for comments: {css_path, char_start, char_end, text}")
    if event.get("compared_with") is not None and not isinstance(event["compared_with"], dict):
        raise ValueError("compared_with must be an object")
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
