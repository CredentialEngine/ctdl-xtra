import json

import pytest
from conftest import RULES, fixture_url

from review_ui import cli


def test_sample_then_extract_through_the_command_line(crawl_root, store, run, capsys):
    assert (
        cli.main(
            [
                "sample",
                "--root",
                str(crawl_root),
                "--run",
                "cat",
                "--rules",
                str(RULES),
                "--size",
                "4",
            ]
        )
        == 0
    )
    sample = store.read_json(f"{run.key}/review-ui/sample.json")
    assert sample["size"] == 4
    assert (
        cli.main(
            [
                "extract",
                "--root",
                str(crawl_root),
                "--run",
                "cat",
                "--rules",
                str(RULES),
                "--workers",
                "1",
            ]
        )
        == 0
    )
    assert '"records": 17' in capsys.readouterr().out


def test_sample_refuses_to_replace_an_existing_sample(crawl_root):
    args = [
        "sample",
        "--root",
        str(crawl_root),
        "--run",
        "cat",
        "--rules",
        str(RULES),
        "--size",
        "3",
    ]
    assert cli.main(args) == 0
    with pytest.raises(SystemExit, match="already exists"):
        cli.main(args)
    assert cli.main(args + ["--force"]) == 0


def test_extract_exits_nonzero_when_an_accepted_value_changed(
    crawl_root, store, run, capsys
):
    store.write_json(f"{run.key}/review-ui/s1/session.json", {})
    store.write_json(
        f"{run.key}/review-ui/s1/decisions.json",
        {
            f"ADMJ51::Language::{fixture_url('course_admj')}::0": {
                "kind": "field",
                "status": "accepted",
                "value": "French",
            }
        },
    )
    code = cli.main(
        [
            "extract",
            "--root",
            str(crawl_root),
            "--run",
            "cat",
            "--rules",
            str(RULES),
            "--workers",
            "1",
        ]
    )
    assert code == 1 and "REGRESSION" in capsys.readouterr().out


def test_run_must_match_exactly_one(crawl_root):
    with pytest.raises(SystemExit, match="matched 0"):
        cli.main(["sample", "--root", str(crawl_root), "--run", "zzz"])


def test_check_rules_passes_for_the_shipped_ruleset_and_fails_a_bad_example(
    crawl_root, tmp_path, capsys
):
    assert (
        cli.main(["check-rules", "--root", str(crawl_root), "--rules", str(RULES)]) == 0
    )
    rules = json.loads(RULES.read_text())
    rules["field_rules"][0]["example_output"] = "wrong"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(rules))
    assert (
        cli.main(["check-rules", "--root", str(crawl_root), "--rules", str(bad)]) == 1
    )
    assert "FAIL course-name" in capsys.readouterr().out


def test_invalid_ruleset_is_reported_not_run(crawl_root, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"ruleset_id": "x"}))
    with pytest.raises(SystemExit, match="invalid ruleset"):
        cli.main(["check-rules", "--root", str(crawl_root), "--rules", str(bad)])


def test_export_feedback_writes_next_to_the_review(crawl_root, store, run, extraction):
    from review_ui.review import ReviewSession

    review = ReviewSession.create(store, run.key, "2026-02-01T00-00-00Z")
    assert cli.main(["export-feedback", "--root", str(crawl_root), "--run", "cat"]) == 0
    assert store.exists(f"{review.base}/feedback.md")


# -- rulesets and the template live in the storage root ----------------------
def test_sample_and_extract_use_the_ruleset_published_in_the_root(
    crawl_root, store, run, capsys
):
    from conftest import publish_rules

    publish_rules(crawl_root, catalog_folder="cat")  # the run's catalog is "cat"
    assert (
        cli.main(["sample", "--root", str(crawl_root), "--run", "cat", "--size", "4"])
        == 0
    )
    assert (
        cli.main(
            ["extract", "--root", str(crawl_root), "--run", "cat", "--workers", "1"]
        )
        == 0
    )
    assert '"records": 17' in capsys.readouterr().out


def test_a_catalog_with_no_published_ruleset_says_how_to_publish_one(crawl_root):
    with pytest.raises(SystemExit, match="rules publish"):
        cli.main(["extract", "--root", str(crawl_root), "--run", "cat"])


def test_a_missing_field_template_is_a_clear_error(tmp_path):
    with pytest.raises(SystemExit, match="template publish"):
        cli.main(["rules", "list", "--root", str(tmp_path)])


def test_rules_publish_then_list_then_pull(crawl_root, tmp_path, capsys):
    assert cli.main(["rules", "publish", "--root", str(crawl_root), str(RULES)]) == 0
    assert "published ccsf-curricunet-com-catalog v2" in capsys.readouterr().out
    assert cli.main(["rules", "list", "--root", str(crawl_root)]) == 0
    assert "ccsf-curricunet-com-catalog  v2" in capsys.readouterr().out
    out = tmp_path / "pulled.json"
    assert (
        cli.main(
            [
                "rules",
                "pull",
                "--root",
                str(crawl_root),
                "ccsf-curricunet-com-catalog",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    assert json.loads(out.read_text()) == json.loads(RULES.read_text())


def test_rules_publish_refuses_an_unchanged_version_unless_forced(crawl_root):
    args = ["rules", "publish", "--root", str(crawl_root), str(RULES)]
    assert cli.main(args) == 0
    with pytest.raises(SystemExit, match="already at version 2"):
        cli.main(args)
    assert cli.main(args + ["--force"]) == 0


def test_rules_publish_refuses_a_ruleset_whose_examples_fail(crawl_root, tmp_path):
    rules = json.loads(RULES.read_text())
    rules["field_rules"][0]["example_output"] = "wrong"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(rules))
    with pytest.raises(SystemExit, match="examples fail"):
        cli.main(["rules", "publish", "--root", str(crawl_root), str(bad)])


def test_rules_pull_of_an_unknown_catalog(crawl_root):
    with pytest.raises(SystemExit, match="No ruleset"):
        cli.main(["rules", "pull", "--root", str(crawl_root), "nope"])


def test_template_publish_validates_the_shape(tmp_path, crawl_root):
    from conftest import PROPERTIES

    empty = tmp_path / "fresh"
    assert cli.main(["template", "publish", "--root", str(empty), str(PROPERTIES)]) == 0
    assert (empty / "review-ui-index" / "templates" / "course.properties.json").exists()
    junk = tmp_path / "junk.json"
    junk.write_text(json.dumps([{"nope": 1}]))
    with pytest.raises(SystemExit, match="not a field template"):
        cli.main(["template", "publish", "--root", str(empty), str(junk)])


# -- host and port for a container --------------------------------------------------
def serve_defaults(monkeypatch, **env):
    """The --host/--port the serve command would use, given environment variables."""
    import argparse

    for name in ("REVIEW_UI_HOST", "REVIEW_UI_PORT", "PORT"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    captured = {}

    def fake_serve(args):
        captured["host"], captured["port"] = args.host, args.port
        return 0

    monkeypatch.setattr(cli, "cmd_serve", fake_serve)
    cli.main(["serve"])
    assert isinstance(captured["port"], int) and argparse
    return captured


def test_serve_defaults_to_localhost_8001(monkeypatch):
    assert serve_defaults(monkeypatch) == {"host": "127.0.0.1", "port": 8001}


def test_a_container_sets_the_host_and_port_through_the_environment(monkeypatch):
    got = serve_defaults(monkeypatch, REVIEW_UI_HOST="0.0.0.0", REVIEW_UI_PORT="9000")
    assert got == {"host": "0.0.0.0", "port": 9000}


def test_a_platform_port_variable_is_used_when_ours_is_not_set(monkeypatch):
    assert serve_defaults(monkeypatch, PORT="8080")["port"] == 8080
    assert (
        serve_defaults(monkeypatch, PORT="8080", REVIEW_UI_PORT="9000")["port"] == 9000
    )
