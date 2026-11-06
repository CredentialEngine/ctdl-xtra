import pytest
from conftest import SAMPLE_STEMS, build_run, fixture_url, publish_rules, seed_template
from fastapi.testclient import TestClient

from review_ui import cli
from review_ui.api import create_app
from review_ui.catalogs import cid_of, discover, summarize
from review_ui.extract import run_extraction
from review_ui.review import ReviewSession
from review_ui.runs import find_runs
from review_ui.store import LocalStore

CCSF = "ccsf-curricunet-com-catalog"


@pytest.fixture
def root(tmp_path):
    """A storage root with the template and rulesets published in it, two runs of the CCSF catalog, one run of a catalog that has a broken ruleset,
    and one run of a catalog with no ruleset at all."""
    base = tmp_path / "crawls"
    seed_template(base)
    publish_rules(base)  # the real CCSF ruleset, in <root>/review-ui-index/rulesets/
    LocalStore(base).write_json(
        "review-ui-index/rulesets/broken/rules.json",
        {"catalog_folder": "other-catalog"},
    )
    build_run(base, "ccsf/new", CCSF, "2026-10-01T16:02:34Z")
    build_run(base, "ccsf/old", CCSF, "2026-09-01T10:00:00Z")
    build_run(base, "other/run", "other-catalog", "2026-08-01T10:00:00Z")
    build_run(base, "bare/run", "no-ruleset-catalog", "2026-07-01T10:00:00Z")
    return base


def known(properties):
    return {p.name for p in properties}


def sample(store, run):
    store.write_json(
        f"{run.key}/review-ui/sample.json",
        {
            "pages": [
                {"stem": s, "url": fixture_url(s), "page_type": "x", "reason": ""}
                for s in SAMPLE_STEMS
            ]
        },
    )


def run_of(root, rel):
    return next(r for r in find_runs(root) if r.key == rel)


def test_discover_lists_runs_that_have_a_ruleset_newest_first(root, properties):
    found = discover(LocalStore(root), known(properties))
    assert [(c.run.key, c.ruleset_error is None) for c in found] == [
        ("ccsf/new", True),
        ("ccsf/old", True),
        ("other/run", False),  # its ruleset is invalid: listed, with the error
    ]
    assert "no-ruleset-catalog" not in {c.run.catalog_folder for c in found}
    assert "ruleset_id" in found[2].ruleset_error


def test_a_run_given_with_dash_dash_run_is_added_even_without_a_ruleset(
    root, properties
):
    extra = run_of(root, "bare/run")
    found = discover(LocalStore(root), known(properties), extra)
    assert found[-1].run.key == "bare/run" and found[-1].ruleset is None


def test_cid_is_url_safe_and_stable(root):
    assert (
        cid_of(run_of(root, "ccsf/new"))
        == "ccsf-curricunet-com-catalog-2026-10-01t16-02-34z"
    )


def test_summary_walks_from_nothing_to_ready(root, properties, ruleset):
    store, run = LocalStore(root), run_of(root, "ccsf/new")
    (catalog,) = [
        c
        for c in discover(LocalStore(root), known(properties))
        if c.run.key == "ccsf/new"
    ]

    card = summarize(store, catalog)
    assert (card["pages"], card["ready"], card["extraction"], card["review"]) == (
        5,
        False,
        None,
        None,
    )
    assert f"extract --run {run.key}" in card["hint"]
    assert card["ruleset"] == {"id": CCSF, "version": 2, "rules": 17}

    run_extraction(root, run, ruleset, properties, ts="2026-02-01T00-00-00Z", workers=1)
    assert "sample" in summarize(store, catalog)["hint"]  # extracted without a sample

    sample(store, run)
    run_extraction(root, run, ruleset, properties, ts="2026-02-02T00-00-00Z", workers=1)
    card = summarize(store, catalog)
    assert card["ready"] and card["hint"] is None
    assert card["extraction"] == {
        "id": "2026-02-02T00-00-00Z",
        "records": 17,
        "ruleset_version": 2,
        "stale": False,
        "legacy": False,
    }


def test_an_extraction_from_older_rules_is_marked_stale(root, properties, ruleset):
    store, run = LocalStore(root), run_of(root, "ccsf/new")
    sample(store, run)
    run_extraction(root, run, ruleset, properties, workers=1)
    publish_rules(root, version=3)
    (catalog,) = [
        c
        for c in discover(LocalStore(root), known(properties))
        if c.run.key == "ccsf/new"
    ]
    assert summarize(store, catalog)["extraction"]["stale"] is True


def test_review_progress_comes_from_the_latest_review_of_the_current_extraction(
    root, properties, ruleset
):
    store, run = LocalStore(root), run_of(root, "ccsf/new")
    sample(store, run)
    run_extraction(root, run, ruleset, properties, ts="2026-02-01T00-00-00Z", workers=1)
    (catalog,) = [
        c
        for c in discover(LocalStore(root), known(properties))
        if c.run.key == "ccsf/new"
    ]
    review = ReviewSession.create(store, run.key, "2026-02-01T00-00-00Z")
    url = fixture_url("course_admj")
    review.apply(
        {
            "type": "flag",
            "author": "Jared",
            "scope": "page",
            "target": "page::course_admj",
            "stem": "course_admj",
            "source_url": url,
            "flagged": True,
        }
    )
    card = summarize(store, catalog)["review"]
    assert card["review_id"] == review.review_id
    assert (card["counts"]["flagged_pages"], card["counts"]["accepted"]) == (1, 0)
    # a review of an older extraction is not shown for the new one
    run_extraction(root, run, ruleset, properties, ts="2026-02-02T00-00-00Z", workers=1)
    assert summarize(store, catalog)["review"] is None


@pytest.fixture
def client(root, properties, ruleset):
    store = LocalStore(root)
    for rel in ("ccsf/new", "ccsf/old"):
        run = run_of(root, rel)
        sample(store, run)
        run_extraction(root, run, ruleset, properties, workers=1)
    return TestClient(create_app(root, None))


def test_the_landing_endpoint_lists_every_catalog_with_no_default(client):
    body = client.get("/api/catalogs").json()
    assert body["default"] is None
    ready = {c["run_key"]: c["ready"] for c in body["catalogs"]}
    assert ready == {"ccsf/new": True, "ccsf/old": True, "other/run": False}


def test_dash_dash_run_makes_that_catalog_the_default(root, client):
    app = create_app(root, run_of(root, "ccsf/old"))
    assert (
        TestClient(app).get("/api/catalogs").json()["default"]
        == "ccsf-curricunet-com-catalog-2026-09-01t10-00-00z"
    )


def test_each_catalog_has_its_own_review(client):
    new, old = (
        "/api/c/ccsf-curricunet-com-catalog-2026-10-01t16-02-34z",
        "/api/c/ccsf-curricunet-com-catalog-2026-09-01t10-00-00z",
    )
    state_new, state_old = (
        client.get(f"{new}/state").json(),
        client.get(f"{old}/state").json(),
    )
    assert (
        state_new["run"]["key"] == "ccsf/new" and state_old["run"]["key"] == "ccsf/old"
    )
    url = fixture_url("course_admj")
    event = {
        "type": "flag",
        "author": "Jared",
        "scope": "page",
        "target": "page::course_admj",
        "stem": "course_admj",
        "source_url": url,
        "flagged": True,
    }
    assert client.post(f"{new}/events", json=event).status_code == 200
    assert client.get(f"{new}/state").json()["review"]["counts"]["flagged_pages"] == 1
    assert client.get(f"{old}/state").json()["review"]["counts"]["flagged_pages"] == 0


def test_an_unknown_catalog_is_a_404_and_one_with_no_extraction_a_409(client):
    assert client.get("/api/c/nope/state").status_code == 404
    reply = client.get("/api/c/other-catalog-2026-08-01t10-00-00z/state")
    assert (
        reply.status_code == 409 and "extract --run other/run" in reply.json()["detail"]
    )


def test_serving_a_run_with_no_extraction_is_a_clear_error(crawl_root):
    with pytest.raises(SystemExit, match="extract --run"):
        cli.main(["serve", "--root", str(crawl_root), "--run", "cat"])


def test_an_extraction_from_the_first_app_is_not_ready(root, properties, ruleset):
    store, run = LocalStore(root), run_of(root, "ccsf/new")
    sample(store, run)
    run_extraction(root, run, ruleset, properties, ts="2026-02-01T00-00-00Z", workers=1)
    rules_key = f"{run.key}/extractions/2026-02-01T00-00-00Z/rules.json"
    frozen = store.read_json(rules_key)
    del frozen["content_root"]  # how the first app froze its rules
    store.write_json(rules_key, frozen)
    (catalog,) = [
        c
        for c in discover(LocalStore(root), known(properties))
        if c.run.key == "ccsf/new"
    ]
    card = summarize(store, catalog)
    assert card["extraction"]["legacy"] is True and card["ready"] is False
    assert "older version" in card["hint"] and "--extraction" in card["hint"]


def test_a_ruleset_published_while_the_app_runs_appears_without_a_restart(root, client):
    before = {
        c["catalog_folder"] for c in client.get("/api/catalogs").json()["catalogs"]
    }
    assert "newly-published" not in before
    build_run(root, "new/run", "newly-published", "2026-11-01T10:00:00Z")
    publish_rules(root, catalog_folder="newly-published", ruleset_id="newly-published")
    # The index caches for a few seconds; a request for an unknown catalog re-checks.
    cid = "newly-published-2026-11-01t10-00-00z"
    assert (
        client.get(f"/api/c/{cid}/state").status_code == 409
    )  # found: no extraction yet
    after = {
        c["catalog_folder"] for c in client.get("/api/catalogs").json()["catalogs"]
    }
    assert "newly-published" in after


def test_a_missing_field_template_is_reported_by_the_server_not_a_crash(tmp_path):
    base = tmp_path / "crawls"
    build_run(base, "ccsf/new", CCSF, "2026-10-01T16:02:34Z")
    from review_ui.template import ConfigMissing

    with pytest.raises(ConfigMissing, match="template publish"):
        create_app(base, None)
