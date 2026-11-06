import pytest
from conftest import fixture_url

from review_ui.review import INDEX_KEY, EventError, ReviewSession
from review_ui.views import ExtractionView

EID = "2026-02-01T00-00-00Z"
URL = fixture_url("course_admj")
NAME_KEY = f"ADMJ51::Learning Opportunity Name::{URL}::0"


def decision(status="accepted", **extra):
    return {
        "type": "decision",
        "author": "Seth",
        "kind": "field",
        "key": NAME_KEY,
        "status": status,
        "canonical_label": "Learning Opportunity Name",
        "source_url": URL,
        "record_id": "ADMJ51",
        "value": "Juvenile Procedures",
        **extra,
    }


@pytest.fixture
def session(store, run, extraction):
    return ReviewSession.create(store, run.key, EID)


def test_new_session_counts_every_item_as_pending(session, store, run, extraction):
    keys = ExtractionView(store, run.key, EID).item_keys(
        ["course_admj", "course_mixed", "index_courses"]
    )
    assert session.counts() == {
        "total": len(keys),
        "accepted": 0,
        "rejected": 0,
        "missing": 0,
        "pending": len(keys),
        "flagged_pages": 0,
        "flagged_items": 0,
    }


def test_decisions_are_saved_to_events_decisions_and_index(session, store):
    session.apply(decision())
    assert len(store.read_jsonl(f"{session.base}/events.jsonl")) == 1
    assert (
        store.read_json(f"{session.base}/decisions.json")[NAME_KEY]["status"]
        == "accepted"
    )
    (entry,) = store.read_json(INDEX_KEY)
    assert entry["accepted"] == 1 and entry["review_id"] == session.review_id


def test_setting_a_decision_back_to_pending_removes_it(session):
    session.apply(decision())
    session.apply(decision("pending"))
    assert session.decisions == {}


def test_state_is_rebuilt_from_the_event_log(session, store, run):
    session.apply(decision("rejected", expected_value="x", reasons=["wrong_format"]))
    session.apply(
        {
            "type": "note",
            "author": "Jared",
            "scope": "general",
            "target": None,
            "text": "hello",
        }
    )
    reopened = ReviewSession.open(store, run.key, session.review_id)
    assert reopened.decisions[NAME_KEY]["expected_value"] == "x"
    assert [n["text"] for n in reopened.notes.values()] == ["hello"]
    reopened.apply(decision("accepted"))
    assert [e["seq"] for e in store.read_jsonl(f"{session.base}/events.jsonl")] == [
        1,
        2,
        3,
    ]


def test_a_note_is_replaced_by_id_and_removed_when_emptied(session):
    saved = session.apply(
        {
            "type": "note",
            "author": "Seth",
            "scope": "rule",
            "target": "course-name",
            "text": "a",
        }
    )
    session.apply(
        {
            "type": "note",
            "author": "Seth",
            "scope": "rule",
            "target": "course-name",
            "text": "b",
            "id": saved["id"],
        }
    )
    assert [n["text"] for n in session.notes.values()] == ["b"]
    session.apply(
        {
            "type": "note",
            "author": "Seth",
            "scope": "rule",
            "target": "course-name",
            "text": "",
            "id": saved["id"],
        }
    )
    assert session.notes == {}


@pytest.mark.parametrize(
    "event,message",
    [
        ({**decision(), "author": ""}, "author"),
        ({**decision(), "status": "maybe"}, "status"),
        ({**decision(), "kind": "x"}, "kind"),
        ({**decision(), "reasons": ["bad"]}, "reasons"),
        ({**decision("missing")}, "expected_value"),
        (
            {
                "type": "note",
                "author": "S",
                "scope": "rule",
                "target": None,
                "text": "t",
            },
            "target",
        ),
        ({"type": "note", "author": "S", "scope": "nope", "text": "t"}, "scope"),
        ({"type": "other", "author": "S"}, "unknown event"),
    ],
)
def test_invalid_events_are_rejected_and_not_saved(session, store, event, message):
    with pytest.raises(EventError, match=message):
        session.apply(event)
    assert store.read_jsonl(f"{session.base}/events.jsonl") == []


def test_missing_counts_separately_and_never_hides_pending_items(session):
    before = session.counts()["pending"]
    session.apply(decision("missing", key="k2", expected_value="GIS"))
    counts = session.counts()
    assert counts["missing"] == 1 and counts["pending"] == before


def test_new_session_carries_over_unchanged_accepted_values_only(store, run, session):
    session.apply(decision())
    other = f"ADMJ51::Coded Notation::{URL}::0"
    session.apply(
        decision(
            "rejected", key=other, canonical_label="Coded Notation", value="ADMJ 51"
        )
    )
    session.apply(decision(key="gone::key", value="x"))
    from review_ui.extract import baseline_decisions

    fresh = ReviewSession.create(
        store, run.key, EID, carry_over=baseline_decisions(store, run.key)
    )
    assert list(fresh.decisions) == [NAME_KEY]
    assert fresh.decisions[NAME_KEY]["carried_from"] == session.review_id


def test_changed_value_is_not_carried_over(store, run, session):
    session.apply(decision(value="An Older Name"))
    from review_ui.extract import baseline_decisions

    fresh = ReviewSession.create(
        store, run.key, EID, carry_over=baseline_decisions(store, run.key)
    )
    assert fresh.decisions == {}


def test_two_sessions_started_in_the_same_second_get_different_folders(
    store, run, session
):
    other = ReviewSession.create(store, run.key, EID)
    assert other.review_id != session.review_id


# -- flag for review ---------------------------------------------------------
STEM = "course_admj"
CODE_KEY = f"ADMJ51::Coded Notation::{URL}::0"
LABEL_KEY = f"label::{URL}::Course::label-course-page"


def flag(target=NAME_KEY, scope="field", flagged=True, **extra):
    return {
        "type": "flag",
        "author": "Jared",
        "scope": scope,
        "target": target,
        "stem": STEM,
        "source_url": URL,
        "canonical_label": "Learning Opportunity Name",
        "record_id": "ADMJ51",
        "flagged": flagged,
        **extra,
    }


def test_a_flag_is_saved_to_events_flags_json_and_the_index(session, store):
    session.apply(flag(note="  Is this the official title?  "))
    assert store.read_json(f"{session.base}/flags.json")[NAME_KEY]["note"] == (
        "Is this the official title?"
    )
    assert len(store.read_jsonl(f"{session.base}/events.jsonl")) == 1
    (entry,) = store.read_json(INDEX_KEY)
    assert entry["flagged_items"] == 1 and entry["flagged_pages"] == 0


def test_a_page_and_several_of_its_properties_can_all_be_flagged(session):
    session.apply(flag(f"page::{STEM}", scope="page", note="ask the dean"))
    session.apply(flag(NAME_KEY))
    session.apply(flag(CODE_KEY, canonical_label="Coded Notation"))
    session.apply(flag(LABEL_KEY, scope="label", canonical_label="Course"))
    counts = session.counts()
    assert (counts["flagged_pages"], counts["flagged_items"]) == (1, 3)


def test_flagging_does_not_change_the_pending_count_or_any_decision(session):
    before = session.counts()["pending"]
    session.apply(flag())
    assert session.counts()["pending"] == before and session.decisions == {}
    session.apply(decision())
    assert session.counts()["pending"] == before - 1
    assert NAME_KEY in session.flags and NAME_KEY in session.decisions


def test_unflagging_removes_the_flag(session):
    session.apply(flag())
    session.apply(flag(flagged=False))
    assert session.flags == {} and session.counts()["flagged_items"] == 0


def test_flags_are_rebuilt_from_the_event_log(session, store, run):
    session.apply(flag(note="ask Registrar"))
    session.apply(flag(CODE_KEY, canonical_label="Coded Notation"))
    session.apply(flag(CODE_KEY, flagged=False))
    reopened = ReviewSession.open(store, run.key, session.review_id)
    assert list(reopened.flags) == [NAME_KEY]
    assert reopened.flags[NAME_KEY]["note"] == "ask Registrar"
    assert reopened.state()["flags"] == reopened.flags


@pytest.mark.parametrize(
    "event,message",
    [
        (flag(scope="nope"), "scope"),
        (flag(target=""), "target"),
        ({**flag(), "stem": ""}, "stem"),
        ({**flag(), "source_url": ""}, "source_url"),
        (flag(flagged="yes"), "flagged"),
        (flag("page::other", scope="page"), "page::<stem>"),
        ({**flag(), "author": ""}, "author"),
    ],
)
def test_invalid_flags_are_rejected_and_not_saved(session, store, event, message):
    with pytest.raises(EventError, match=message):
        session.apply(event)
    assert store.read_jsonl(f"{session.base}/events.jsonl") == []


def test_new_session_carries_open_flags_whose_target_still_exists(store, run, session):
    session.apply(flag(note="still unsure"))
    session.apply(flag(f"page::{STEM}", scope="page"))
    session.apply(flag("gone::key", note="vanished item"))
    session.apply({**flag("page::nowhere", scope="page"), "stem": "nowhere"})
    from review_ui.extract import latest_flags

    fresh = ReviewSession.create(
        store, run.key, EID, carry_flags=latest_flags(store, run.key)
    )
    assert sorted(fresh.flags) == sorted([NAME_KEY, f"page::{STEM}"])
    assert fresh.flags[NAME_KEY]["carried_from"] == session.review_id
    assert fresh.flags[NAME_KEY]["note"] == "still unsure"


def test_a_flag_cleared_in_the_latest_session_is_not_resurrected(store, run, session):
    session.apply(flag())
    from review_ui.extract import latest_flags

    second = ReviewSession.create(
        store, run.key, EID, carry_flags=latest_flags(store, run.key)
    )
    second.apply(flag(flagged=False))
    third = ReviewSession.create(
        store, run.key, EID, carry_flags=latest_flags(store, run.key)
    )
    assert third.flags == {}
