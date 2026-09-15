from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


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
