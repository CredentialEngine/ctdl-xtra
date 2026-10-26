"""The dated HTML cache: write once, reuse later runs' copies, never
overwrite. Pages are copied from saved freezes or fetched through a fake
browser; uploads go to a fake blob client."""

from __future__ import annotations

import json
import re
import sys
import types
from collections.abc import Callable
from pathlib import Path

import dynamic_slots
import freeze
import pytest
from crawl_doubles import FakePage
from lib_doubles import (
    COURSE_HTML,
    DAY,
    NOW,
    FakeResponse,
    FakeSyncPlaywright,
    example_slot,
    write_freeze,
)
from normalize import sha256_bytes

STEM = "catalog-example-edu-english-engl101"
URL = "https://catalog.example.edu/english/engl101"


def fake_blob_client(
    monkeypatch: pytest.MonkeyPatch, *, fails: bool = False
) -> list[dict]:
    """Install a BlobClient that records each upload instead of sending it."""
    uploads: list[dict] = []

    class FakeBlobClient:
        def __init__(self, url: str) -> None:
            self.url = url

        @classmethod
        def from_blob_url(cls, url: str) -> FakeBlobClient:
            return cls(url)

        def upload_blob(self, data, overwrite: bool) -> None:
            if fails:
                raise RuntimeError("409 BlobAlreadyExists")
            uploads.append(
                {"url": self.url, "body": data.read(), "overwrite": overwrite}
            )

    module = types.ModuleType("azure.storage.blob")
    module.BlobClient = FakeBlobClient
    monkeypatch.setitem(sys.modules, "azure.storage.blob", module)
    return uploads


def test_portable_paths_are_relative_to_the_pack_lib_or_repo(
    pack: Path, lib_dir: Path, tmp_path: Path
) -> None:
    assert freeze.portable_path(pack / "cache" / DAY / "x.html") == (
        f"cache/{DAY}/x.html"
    )
    assert freeze.portable_path(lib_dir / "record.schema.json") == (
        "record.schema.json"
    )
    assert freeze.portable_path(lib_dir.parents[1] / "tests" / "x.html") == (
        "tests/x.html"
    )
    assert freeze.portable_path(tmp_path / "repo" / "handoff" / "x.html") == (
        "handoff/x.html"
    )
    assert freeze.portable_path(tmp_path / "elsewhere" / "x.html") == "x.html"


def test_redirects_are_listed_oldest_first() -> None:
    hops = ["http://catalog.example.edu/a", "https://catalog.example.edu/a"]
    assert freeze.redirect_urls(FakeResponse(url=URL, redirects=hops)) == hops
    assert freeze.redirect_urls(FakeResponse(url=URL)) == []
    assert freeze.redirect_urls(None) == []
    assert freeze.redirect_urls(object()) == []


def test_the_clock_gives_a_utc_day_and_an_rfc3339_second() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", freeze.utc_day())
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", freeze._now())


def test_a_new_snapshot_goes_under_todays_cache_folder(
    pack: Path, fixed_clock: str
) -> None:
    assert (
        freeze.new_snapshot_path(STEM) == pack / "cache" / DAY / f"{STEM}.html"
    )
    assert freeze.new_snapshot_path(STEM, day="2020-01-02") == (
        pack / "cache" / "2020-01-02" / f"{STEM}.html"
    )
    assert freeze.snapshot_path(STEM) == freeze.new_snapshot_path(STEM)


def test_the_newest_dated_copy_wins_and_other_folders_are_ignored(
    pack: Path,
) -> None:
    slot = example_slot()
    write_freeze(pack, slot, "<p>old</p>", day="2026-01-01")
    newest = write_freeze(pack, slot, "<p>new</p>", day="2026-02-01")
    write_freeze(pack, slot, "<p>not a day</p>", day="latest")
    assert freeze.find_cached_html(STEM) == newest
    assert freeze.snapshot_path(STEM) == newest
    assert freeze.meta_path(STEM) == newest.parent / f"{STEM}.meta.json"
    assert freeze.snapshot_rel(STEM) == f"cache/2026-02-01/{STEM}.html"


def test_a_legacy_snapshot_is_used_when_the_cache_has_none(pack: Path) -> None:
    legacy = pack / "snapshots" / f"{STEM}.html"
    legacy.parent.mkdir()
    legacy.write_text("<p>legacy</p>", encoding="utf-8")
    assert freeze.find_cached_html(STEM) == legacy
    assert freeze.find_cached_html("other-stem") is None


def test_a_snapshot_is_written_once_with_its_hash_and_size(
    pack: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dest = pack / "cache" / DAY / f"{STEM}.html"
    assert freeze.write_snapshot("<p>café</p>", dest=dest, meta={"x": 1})
    data = "<p>café</p>".encode()
    assert dest.read_bytes() == data
    meta = json.loads(freeze.meta_path_for(dest).read_text(encoding="utf-8"))
    assert meta == {"x": 1, "snapshot_sha256": sha256_bytes(data), "bytes": 12}
    assert not freeze.write_snapshot("<p>other</p>", dest=dest, meta={})
    assert dest.read_bytes() == data
    assert f"refuse overwrite {dest}" in capsys.readouterr().out


def test_without_a_cache_url_nothing_is_uploaded(pack: Path) -> None:
    dest = write_freeze(pack, example_slot(), COURSE_HTML)
    freeze.maybe_upload_blob(dest)


def test_a_cache_url_uploads_the_snapshot_under_its_pack_path(
    pack: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    uploads = fake_blob_client(monkeypatch)
    monkeypatch.setenv("XTRA_CACHE_URL", "https://blob.example.net/cache/")
    dest = write_freeze(pack, example_slot(), COURSE_HTML)
    freeze.maybe_upload_blob(dest)
    assert uploads == [
        {
            "url": f"https://blob.example.net/cache/cache/{DAY}/{STEM}.html",
            "body": COURSE_HTML.encode(),
            "overwrite": False,
        }
    ]
    assert f"uploaded cache/{DAY}/{STEM}.html" in capsys.readouterr().out


def test_a_snapshot_outside_the_pack_uploads_under_todays_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fixed_clock: str
) -> None:
    uploads = fake_blob_client(monkeypatch)
    monkeypatch.setenv("XTRA_CACHE_URL", "https://blob.example.net/cache")
    outside = tmp_path / "x.html"
    outside.write_text("<p>x</p>", encoding="utf-8")
    freeze.maybe_upload_blob(outside)
    assert uploads[0]["url"] == f"https://blob.example.net/cache/{DAY}/x.html"


def test_a_missing_sdk_or_a_failed_upload_keeps_the_local_copy(
    pack: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XTRA_CACHE_URL", "https://blob.example.net/cache")
    dest = write_freeze(pack, example_slot(), COURSE_HTML)
    monkeypatch.setitem(sys.modules, "azure.storage.blob", None)
    freeze.maybe_upload_blob(dest)
    assert "azure-storage-blob is not installed" in capsys.readouterr().err
    fake_blob_client(monkeypatch, fails=True)
    freeze.maybe_upload_blob(dest)
    assert "blob upload skipped (409 BlobAlreadyExists)" in (
        capsys.readouterr().err
    )
    assert dest.is_file()


def test_an_existing_freeze_is_found_in_priority_order(
    pack: Path, tmp_path: Path
) -> None:
    """Cache, then legacy snapshots/, then the slot's copy, then the old
    handoff and golden_sets folders. Each newly saved copy outranks the
    ones saved before it."""
    repo = tmp_path / "repo"
    slot = example_slot(copy_html=tmp_path / "saved" / f"{STEM}.html")
    lowest_first = [
        repo
        / "golden_sets"
        / "sources"
        / "html"
        / f"{STEM}.html"
        / f"{STEM}.html",
        repo / "handoff" / "golden_set_v4" / "snapshots" / f"{STEM}.html",
        tmp_path / "saved" / f"{STEM}.html",
        pack / "snapshots" / f"{STEM}.html",
    ]
    assert freeze._existing_html(slot) is None
    for place in lowest_first:
        place.parent.mkdir(parents=True, exist_ok=True)
        place.write_text("<p>x</p>", encoding="utf-8")
        assert freeze._existing_html(slot) == place
    cached = write_freeze(pack, slot, "<p>cached</p>")
    assert freeze._existing_html(slot) == cached


def test_copy_existing_copies_a_saved_page_into_todays_cache(
    pack: Path, tmp_path: Path, fixed_clock: str
) -> None:
    saved = tmp_path / "saved" / f"{STEM}.html"
    saved.parent.mkdir()
    saved.write_text(COURSE_HTML, encoding="utf-8")
    (saved.parent / f"{STEM}.meta.json").write_text(
        json.dumps({"retrieved_at": "2026-01-02T03:04:05Z"}), encoding="utf-8"
    )
    dynamic_slots.write_slots(
        [example_slot(copy_html=saved, retrieved_at=None)]
    )
    rows = freeze.copy_existing()
    dest = pack / "cache" / DAY / f"{STEM}.html"
    assert rows == [
        {"stem": STEM, "status": "copied", "path": f"cache/{DAY}/{STEM}.html"}
    ]
    meta = json.loads(freeze.meta_path_for(dest).read_text(encoding="utf-8"))
    assert meta["retrieved_at"] == "2026-01-02T03:04:05Z"
    assert meta["capture"] == "copied_existing_html_freeze"
    assert meta["requested_url"] == meta["final_url"] == URL
    assert meta["http_status"] is None


@pytest.mark.parametrize(
    ("slot_time", "expected"), [("2026-09-14T18:12:00Z", None), (None, NOW)]
)
def test_the_copy_is_dated_by_the_slot_else_now(
    pack: Path,
    tmp_path: Path,
    fixed_clock: str,
    slot_time: str | None,
    expected: str | None,
) -> None:
    saved = tmp_path / "saved.html"
    saved.write_text(COURSE_HTML, encoding="utf-8")
    dynamic_slots.write_slots(
        [example_slot(copy_html=saved, retrieved_at=slot_time)]
    )
    freeze.copy_existing()
    meta = json.loads(freeze.meta_path(STEM).read_text(encoding="utf-8"))
    assert meta["retrieved_at"] == (expected or slot_time)


def test_an_already_cached_page_is_reused_and_a_blocked_path_refused(
    pack: Path, tmp_path: Path, fixed_clock: str
) -> None:
    write_freeze(pack, example_slot(), "<p>cached</p>")
    other = example_slot(
        record_id="example-math101-course",
        requested_url="https://catalog.example.edu/math/math101",
        copy_html=tmp_path / "math.html",
    )
    (tmp_path / "math.html").write_text("<p>math</p>", encoding="utf-8")
    (pack / "cache" / DAY / f"{other.stem}.html").mkdir()
    dynamic_slots.write_slots([example_slot(), other])
    assert [row["status"] for row in freeze.copy_existing()] == [
        "reused",
        "refused",
    ]


def test_with_every_page_saved_the_browser_is_never_started(
    pack: Path,
) -> None:
    write_freeze(pack, example_slot(), COURSE_HTML)
    dynamic_slots.write_slots([example_slot()])
    assert freeze.fetch_missing() == []


def test_fetching_without_playwright_says_how_to_install_it(
    pack: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dynamic_slots.write_slots([example_slot()])
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    with pytest.raises(SystemExit, match="Playwright is required"):
        freeze.fetch_missing()


def test_a_missing_page_is_fetched_with_its_response_details(
    pack: Path,
    fixed_clock: str,
    fake_browser: Callable[..., FakeSyncPlaywright],
) -> None:
    final = URL + "/"
    browser = fake_browser(
        {URL: FakePage(html=COURSE_HTML, final_url=final)},
        redirects={URL: ["http://catalog.example.edu/english/engl101"]},
    )
    dynamic_slots.write_slots([example_slot()])
    rows = freeze.fetch_missing()
    assert rows == [
        {
            "stem": STEM,
            "url": URL,
            "status": "ok",
            "error": None,
            "http_status": 200,
            "path": f"cache/{DAY}/{STEM}.html",
        }
    ]
    meta = json.loads(freeze.meta_path(STEM).read_text(encoding="utf-8"))
    assert meta["final_url"] == final
    assert meta["content_type"] == "text/html; charset=utf-8"
    assert meta["redirect_chain"] == [
        "http://catalog.example.edu/english/engl101"
    ]
    assert meta["capture"] == "playwright_page_content"
    assert meta["retrieved_at"] == NOW
    assert browser.contexts[0]["ignore_https_errors"] is True
    assert browser.closed == ["page", "context", "browser"]


def test_a_load_timeout_retries_once_without_waiting_for_load(
    pack: Path, fake_browser: Callable[..., FakeSyncPlaywright]
) -> None:
    browser = fake_browser(
        {URL: [FakePage(raises="Timeout 60000ms exceeded."), FakePage()]},
        chrome_missing=True,
    )
    dynamic_slots.write_slots([example_slot()])
    assert freeze.fetch_missing()[0]["status"] == "ok"
    assert browser.gotos == [(URL, "load"), (URL, "domcontentloaded")]
    assert [launch.get("channel") for launch in browser.launches] == [
        "chrome",
        None,
    ]


def test_a_failed_navigation_is_an_error_row_not_a_crash(
    pack: Path, fake_browser: Callable[..., FakeSyncPlaywright]
) -> None:
    fake_browser({URL: FakePage(raises="net::ERR_CONNECTION_REFUSED")})
    dynamic_slots.write_slots([example_slot()])
    row = freeze.fetch_missing()[0]
    assert row["status"] == "error"
    assert row["error"] == "net::ERR_CONNECTION_REFUSED"
    assert not freeze.snapshot_path(STEM).exists()


def test_freeze_all_reports_and_saves_what_it_did(pack: Path) -> None:
    write_freeze(pack, example_slot(), COURSE_HTML)
    dynamic_slots.write_slots(
        [example_slot(), example_slot(record_id="x-link")]
    )
    report = freeze.freeze_all()
    assert report == {
        "copied": [
            {
                "stem": STEM,
                "status": "reused",
                "path": freeze.snapshot_rel(STEM),
            }
        ],
        "fetched": [],
        "unique_pages": 1,
        "records": 2,
    }
    saved = json.loads(
        (pack / "cache" / "freeze_report.json").read_text(encoding="utf-8")
    )
    assert saved == report
    assert (pack / "snapshots").is_dir()
