from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest

from implementations import crawl_browser

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def no_network(request, monkeypatch) -> None:
    """Fail loudly if a unit test reaches the network.

    A crawler is all network calls, so an injected fake that is forgotten in
    one place would quietly start hitting a real college site. Tests marked
    `integration` opt out.
    """
    if request.node.get_closest_marker("integration"):
        return

    def refuse(*args, **kwargs):
        target = args[0] if args else ""
        url = getattr(target, "full_url", target)
        raise AssertionError(
            f"a unit test tried to open {url!r}. Inject a fake instead, or "
            "mark the test with @pytest.mark.integration."
        )

    def refuse_browser(*args, **kwargs):
        raise AssertionError(
            "a unit test tried to start a real browser. Pass a fake "
            "fetcher_factory, or mark the test with @pytest.mark.integration."
        )

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(
        crawl_browser.PlaywrightFetcher, "__init__", refuse_browser
    )


@pytest.fixture(autouse=True)
def isolated_config_dir(tmp_path_factory, monkeypatch) -> Path:
    """Keep tests off the developer's real ~/.xtra/config.json."""
    directory = tmp_path_factory.mktemp("xtra-config")
    monkeypatch.setenv("XTRA_CONFIG_DIR", str(directory))
    monkeypatch.delenv("XTRA_ENV", raising=False)
    return directory


@pytest.fixture
def fixture_html_dir() -> Path:
    return FIXTURES / "html"


@pytest.fixture
def engl101_html(fixture_html_dir: Path) -> str:
    return (fixture_html_dir / "example-engl101.html").read_text(encoding="utf-8")


@pytest.fixture
def catalog_home_html(fixture_html_dir: Path) -> str:
    return (fixture_html_dir / "example-catalog-home.html").read_text(
        encoding="utf-8"
    )


@pytest.fixture
def engl101_slot() -> dict:
    return {
        "record_id": "example-engl101-course",
        "entity_type": "Course",
        "requested_url": "https://catalog.example.edu/english/engl101",
        "institution_name": "Example College",
        "source_family": "custom_html",
        "template_id": "clean_catalog_course_detail",
        "template_version": "1",
        "page_id": "example-engl101",
        "copy_html": None,
        "retrieved_at": "2026-09-14T18:12:00Z",
        "multi_entity_bundle": False,
        "notes": "",
    }
