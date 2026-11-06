"""Review sessions: reviewer decisions, notes and flags, persisted as they happen.

``events.jsonl`` is the append-only source of truth; ``decisions.json``,
``notes.json`` and ``flags.json`` are views of it, rewritten after every event so a
person (or Claude) can read the current state without replaying anything.

A flag marks a page, or a label or field on it, that the reviewer cannot judge and
needs a subject matter expert for. It is independent of accept/reject: a flagged
item is still pending until someone decides it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from .normalize import values_match
from .runs import now_ts
from .store import Store
from .views import ExtractionView

STATUSES = ("accepted", "rejected", "missing", "pending")
NOTE_SCOPES = ("field", "rule", "property", "general")
FLAG_SCOPES = ("page", "field", "label")
REASONS = (
    "wrong_element",
    "truncated",
    "extra_text",
    "wrong_format",
    "should_be_absent",
    "missed",
    "wrong_label",
)
INDEX_KEY = "review-ui-index/index.json"


class EventError(ValueError):
    pass


class ReviewSession:
    def __init__(self, store: Store, run_key: str, review_id: str, session: dict):
        self.store = store
        self.run_key = run_key
        self.review_id = review_id
        self.session = session
        self.base = f"{run_key}/review-ui/{review_id}"
        self.decisions: dict[str, dict] = {}
        self.notes: dict[str, dict] = {}
        self.flags: dict[str, dict] = {}
        self._seq = 0
        self._replay()

    # -- creation -----------------------------------------------------------
    @classmethod
    def create(
        cls,
        store: Store,
        run_key: str,
        extraction_id: str,
        carry_over: dict[str, dict] | None = None,
        carry_flags: dict[str, dict] | None = None,
    ) -> ReviewSession:
        """Start a session; unchanged accepted values are pre-accepted and open flags
        (questions waiting on an expert) are carried forward."""
        view = ExtractionView(store, run_key, extraction_id)
        stems = [p["stem"] for p in view.sample()] or list(view.pages)
        keys = view.item_keys(stems)
        review_id = _unused_review_id(store, run_key)
        session = {
            "review_id": review_id,
            "run": run_key,
            "extraction_id": extraction_id,
            "created_at": review_id,
            "total_items": len(keys),
            "sample_stems": stems,
        }
        base = f"{run_key}/review-ui/{review_id}"
        store.write_json(f"{base}/session.json", session)
        review = cls(store, run_key, review_id, session)

        current = _current_values(view, stems)
        for key, decision in (carry_over or {}).items():
            if (
                decision["status"] == "accepted"
                and key in current
                and _matches_current(decision, current[key])
            ):
                review.apply(
                    {
                        **{
                            k: v
                            for k, v in decision.items()
                            if k not in ("at", "seq", "carried_from", "review_id")
                        },
                        "type": "decision",
                        "carried_from": decision.get("carried_from")
                        or decision.get("review_id"),
                    }
                )
        for target, flag in (carry_flags or {}).items():
            still_there = (
                flag["stem"] in stems if flag["scope"] == "page" else target in current
            )
            if still_there:
                review.apply(
                    {
                        **{
                            k: v
                            for k, v in flag.items()
                            if k not in ("at", "seq", "carried_from", "review_id")
                        },
                        "type": "flag",
                        "carried_from": flag.get("carried_from")
                        or flag.get("review_id"),
                    }
                )
        review._write_index()
        return review

    @classmethod
    def open(cls, store: Store, run_key: str, review_id: str) -> ReviewSession:
        session = store.read_json(f"{run_key}/review-ui/{review_id}/session.json")
        return cls(store, run_key, review_id, session)

    # -- events -------------------------------------------------------------
    def _replay(self) -> None:
        for event in self.store.read_jsonl(f"{self.base}/events.jsonl"):
            self._fold(event)

    def _fold(self, event: dict) -> None:
        self._seq = max(self._seq, event.get("seq", 0))
        if event["type"] == "decision":
            if event["status"] == "pending":
                self.decisions.pop(event["key"], None)
            else:
                self.decisions[event["key"]] = {
                    **{k: v for k, v in event.items() if k != "type"},
                    "review_id": self.review_id,
                }
        elif event["type"] == "flag":
            if event["flagged"]:
                self.flags[event["target"]] = {
                    **{k: v for k, v in event.items() if k != "type"},
                    "review_id": self.review_id,
                }
            else:
                self.flags.pop(event["target"], None)
        elif event["type"] == "note":
            if event["text"].strip():
                self.notes[event["id"]] = {
                    k: v for k, v in event.items() if k != "type"
                }
            else:
                self.notes.pop(event["id"], None)

    def apply(self, event: dict[str, Any]) -> dict:
        event = self._validate(event)
        self._seq += 1
        event = {**event, "seq": self._seq, "at": now_ts()}
        self.store.append_jsonl(f"{self.base}/events.jsonl", event)  # durable first
        self._fold(event)
        self.store.write_json(f"{self.base}/decisions.json", self.decisions)
        self.store.write_json(f"{self.base}/notes.json", list(self.notes.values()))
        self.store.write_json(f"{self.base}/flags.json", self.flags)
        self._write_index()
        return event

    @staticmethod
    def _validate(event: dict) -> dict:
        kind = event.get("type")
        if not event.get("author"):
            raise EventError("author is required")
        if kind == "decision":
            if event.get("status") not in STATUSES:
                raise EventError(f"status must be one of {STATUSES}")
            if event.get("kind") not in ("field", "label"):
                raise EventError("kind must be 'field' or 'label'")
            for required in ("key", "canonical_label", "source_url"):
                if not event.get(required):
                    raise EventError(f"{required} is required")
            reasons = event.get("reasons", [])
            if any(r not in REASONS for r in reasons):
                raise EventError(f"reasons must be among {REASONS}")
            if event["status"] == "missing" and not event.get("expected_value"):
                raise EventError("a missing field needs expected_value")
            return {**event, "reasons": reasons}
        if kind == "note":
            if event.get("scope") not in NOTE_SCOPES:
                raise EventError(f"scope must be one of {NOTE_SCOPES}")
            if event["scope"] != "general" and not event.get("target"):
                raise EventError("target is required for non-general notes")
            if "text" not in event:
                raise EventError("text is required")
            return {**event, "id": event.get("id") or uuid.uuid4().hex}
        if kind == "flag":
            if event.get("scope") not in FLAG_SCOPES:
                raise EventError(f"scope must be one of {FLAG_SCOPES}")
            for required in ("target", "stem", "source_url"):
                if not event.get(required):
                    raise EventError(f"{required} is required")
            if not isinstance(event.get("flagged"), bool):
                raise EventError("flagged must be true or false")
            if event["scope"] == "page" and event["target"] != f"page::{event['stem']}":
                raise EventError("a page flag's target must be 'page::<stem>'")
            return {**event, "note": (event.get("note") or "").strip()}
        raise EventError(f"unknown event type {kind!r}")

    # -- reporting ----------------------------------------------------------
    def counts(self) -> dict:
        statuses = [d["status"] for d in self.decisions.values()]
        accepted, rejected = statuses.count("accepted"), statuses.count("rejected")
        total = self.session["total_items"]
        return {
            "total": total,
            "accepted": accepted,
            "rejected": rejected,
            "missing": statuses.count("missing"),
            "pending": max(0, total - accepted - rejected),
            "flagged_pages": sum(f["scope"] == "page" for f in self.flags.values()),
            "flagged_items": sum(f["scope"] != "page" for f in self.flags.values()),
        }

    def state(self) -> dict:
        return {
            "session": self.session,
            "decisions": self.decisions,
            "notes": list(self.notes.values()),
            "flags": self.flags,
            "counts": self.counts(),
        }

    def _write_index(self) -> None:
        entry = {
            "run": self.run_key,
            "review_id": self.review_id,
            "extraction_id": self.session["extraction_id"],
            "path": self.base,
            **self.counts(),
            "updated_at": now_ts(),
        }

        def upsert(index: list[dict]) -> list[dict]:
            return [
                e
                for e in index
                if not (e["run"] == self.run_key and e["review_id"] == self.review_id)
            ] + [entry]

        # Atomic: the index is shared by every review (and, in Azure, every replica).
        self.store.update_json(INDEX_KEY, upsert, default=[])


def _unused_review_id(store: Store, run_key: str) -> str:
    """Timestamp id that never collides with an existing session folder."""
    moment = datetime.strptime(now_ts(), "%Y-%m-%dT%H-%M-%SZ").replace(tzinfo=UTC)
    while True:
        review_id = moment.strftime("%Y-%m-%dT%H-%M-%SZ")
        if not store.exists(f"{run_key}/review-ui/{review_id}/session.json"):
            return review_id
        moment += timedelta(seconds=1)


def _current_values(view: ExtractionView, stems: list[str]) -> dict[str, str | None]:
    values: dict[str, str | None] = {}
    for stem in stems:
        page = view.page(stem)
        for label in page["labels"]:
            values[label["key"]] = label["label"]
        for record in page["records"]:
            for f in record["fields"]:
                values[f["field_id"]] = f["value"]
    return values


def _matches_current(decision: dict, current: str | None) -> bool:
    if decision["kind"] == "label":
        return True
    return values_match(decision.get("value"), current)
