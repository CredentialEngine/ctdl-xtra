from conftest import fixture_url

from review_ui.extract import (
    baseline_decisions,
    check_regressions,
    latest_extraction,
    run_extraction,
)


def test_extraction_writes_records_pages_labels_and_report(store, run, extraction):
    base = f"{run.key}/extractions/2026-02-01T00-00-00Z"
    assert extraction["pages_total"] == 5
    assert extraction["labels_per_rule"] == {
        "label-course-page": 2,
        "label-program-page": 1,
        "label-course-on-program-page": 1,
    }
    assert extraction["records"] == 7 + 10
    assert store.exists(f"{base}/records/ADMJ51.json")
    assert store.exists(f"{base}/rules.json") and store.exists(f"{base}/sample.json")
    pages = {row["stem"]: row for row in store.read_jsonl(f"{base}/pages.jsonl")}
    assert pages["course_admj"]["record_ids"] == ["ADMJ51", "ADMJ52", "ADMJ53"]
    assert pages["course_admj"]["title"] == "ADMJ - Administration of Justice"
    assert pages["index_courses"]["labels"] == []
    labels = store.read_json(f"{run.key}/discovery/2026-02-01T00-00-00Z/labels.json")
    assert {
        "label": "Course",
        "source_url": fixture_url("course_admj"),
        "rule_id": "label-course-page",
        "stem": "course_admj",
    } in labels


def test_fill_rates_count_present_and_absent_per_rule_and_property(extraction):
    credit = extraction["fill"]["label-course-page"]["Credit Value"]
    assert credit == {
        "total": 7,
        "present": 6,
        "absent": 1,
    }  # the range course has none


def test_parallel_workers_give_the_same_result(
    crawl_root, run, ruleset, properties, extraction
):
    again = run_extraction(
        crawl_root, run, ruleset, properties, ts="2026-02-02T00-00-00Z", workers=2
    )
    assert {k: v for k, v in again.items() if k != "extraction_id"} == {
        k: v for k, v in extraction.items() if k != "extraction_id"
    }


def test_latest_extraction_ignores_unfinished_folders(store, run, extraction):
    store.write_text(f"{run.key}/extractions/2099-01-01T00-00-00Z/partial.txt", "x")
    assert latest_extraction(store, run.key) == "2026-02-01T00-00-00Z"


def records_with(value):
    return {"R": {"source_expected": {"fields": [{"field_id": "k", "value": value}]}}}


def decision(status, **extra):
    return {"kind": "field", "status": status, "value": "old", **extra}


def test_changed_accepted_value_is_a_regression():
    result = check_regressions({"k": decision("accepted")}, records_with("new"), set())
    assert result["regressions"] == [{"key": "k", "was": "old", "now": "new"}]


def test_accepted_value_that_only_differs_in_whitespace_is_not():
    result = check_regressions(
        {"k": decision("accepted", value="A  b")}, records_with(" a b "), set()
    )
    assert result["regressions"] == [] and result["accepted_checked"] == 1


def test_accepted_value_that_disappears_is_a_regression():
    assert (
        len(check_regressions({"k": decision("accepted")}, {}, set())["regressions"])
        == 1
    )


def test_rejected_value_now_matching_the_expected_one_counts_as_fixed():
    fixed = check_regressions(
        {"k": decision("rejected", expected_value="NEW")}, records_with("new"), set()
    )
    assert (fixed["fixed"], fixed["still_wrong"]) == (1, 0)
    wrong = check_regressions(
        {"k": decision("rejected", expected_value="x")}, records_with("new"), set()
    )
    assert (wrong["fixed"], wrong["still_wrong"]) == (0, 1)


def test_accepted_label_that_is_no_longer_produced_is_a_regression():
    decisions = {
        "label::u::Course::r": {
            "kind": "label",
            "status": "accepted",
            "value": "Course",
        }
    }
    assert len(check_regressions(decisions, {}, set())["regressions"]) == 1
    assert (
        check_regressions(decisions, {}, {"label::u::Course::r"})["regressions"] == []
    )


def test_baseline_takes_the_latest_decision_across_sessions(store, run):
    store.write_json(f"{run.key}/review-ui/s1/session.json", {})
    store.write_json(
        f"{run.key}/review-ui/s1/decisions.json",
        {"k": {"status": "rejected"}, "j": {"status": "accepted"}},
    )
    store.write_json(f"{run.key}/review-ui/s2/session.json", {})
    store.write_json(
        f"{run.key}/review-ui/s2/decisions.json", {"k": {"status": "accepted"}}
    )
    merged = baseline_decisions(store, run.key)
    assert merged["k"]["status"] == "accepted" and merged["j"]["status"] == "accepted"


def test_extraction_reports_regressions_against_earlier_reviews(
    crawl_root, store, run, ruleset, properties, extraction
):
    key = f"ADMJ51::Learning Opportunity Name::{fixture_url('course_admj')}::0"
    store.write_json(f"{run.key}/review-ui/s1/session.json", {})
    store.write_json(
        f"{run.key}/review-ui/s1/decisions.json",
        {key: {"kind": "field", "status": "accepted", "value": "Something Else"}},
    )
    report = run_extraction(
        crawl_root, run, ruleset, properties, ts="2026-02-03T00-00-00Z", workers=1
    )
    assert report["regression"]["regressions"][0]["now"] == "Juvenile Procedures"


def test_records_are_written_in_parallel_and_all_arrive(
    crawl_root, run, ruleset, properties, monkeypatch
):
    import threading

    from review_ui import extract as extract_module
    from review_ui.store import LocalStore

    writers = set()
    original = LocalStore.write_json

    def spy(self, key, value):
        if "/records/" in key:
            writers.add(threading.get_ident())
        return original(self, key, value)

    monkeypatch.setattr(LocalStore, "write_json", spy)
    monkeypatch.setattr(extract_module, "WRITE_THREADS", 4)
    report = extract_module.run_extraction(
        crawl_root, run, ruleset, properties, ts="2026-03-01T00-00-00Z", workers=1
    )
    folder = crawl_root / run.key / "extractions" / "2026-03-01T00-00-00Z" / "records"
    assert len(list(folder.glob("*.json"))) == report["records"] == 17
    assert len(writers) > 1  # more than one thread did the writing


def test_run_extraction_accepts_a_ready_made_store(
    crawl_root, run, ruleset, properties
):
    from review_ui.extract import run_extraction
    from review_ui.store import LocalStore

    # a Store object cannot be sent to worker processes, so it is used in this process
    report = run_extraction(
        LocalStore(crawl_root),
        run,
        ruleset,
        properties,
        ts="2026-03-02T00-00-00Z",
        workers=4,
    )
    assert report["records"] == 17
