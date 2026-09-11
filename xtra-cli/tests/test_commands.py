"""Command tests for xtra-cli ETL stages. Uses fixture HTML, no live crawl."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "xtra-cli"
LIB = CLI / "lib"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(LIB))

from catalog import detect_family, is_course_detail_url
from discover import hrefs_from_html, navigation_failure
from html_text import pack_join, slug_url
from normalize import normalize_html
from slots import Slot
from transcribe_courses import detect_template, extract_course
from transcribe_lib import TranscriptionError


def _run(args: list[str], *, env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(CLI / "xtra_cli.py"), *args]
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        env=merged,
        capture_output=True,
        text=True,
    )


def _slot(**kwargs) -> Slot:
    defaults = dict(
        record_id="example-engl101-course",
        entity_type="Course",
        requested_url="https://catalog.example.edu/english/engl101",
        institution_name="Example College",
        source_family="custom_html",
        template_id="clean_catalog_course_detail",
        template_version="1",
        page_id="example-engl101",
        copy_html=None,
        retrieved_at="2026-09-10T00:00:00Z",
    )
    defaults.update(kwargs)
    return Slot(**defaults)


def _seed_pack(pack: Path) -> str:
    html = (FIXTURES / "html" / "example-engl101.html").read_text(encoding="utf-8")
    url = "https://catalog.example.edu/english/engl101"
    stem = slug_url(url)
    slot = _slot()
    (pack / "slots.json").write_text(
        json.dumps(
            {
                "schema": "xtra-slots-1",
                "slots": [
                    {
                        "record_id": slot.record_id,
                        "entity_type": slot.entity_type,
                        "requested_url": slot.requested_url,
                        "institution_name": slot.institution_name,
                        "source_family": slot.source_family,
                        "template_id": slot.template_id,
                        "template_version": slot.template_version,
                        "page_id": slot.page_id,
                        "copy_html": None,
                        "retrieved_at": slot.retrieved_at,
                        "multi_entity_bundle": False,
                        "notes": "",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    cache = pack / "cache" / "2026-09-10"
    cache.mkdir(parents=True)
    (cache / f"{stem}.html").write_text(html, encoding="utf-8")
    (cache / f"{stem}.meta.json").write_text(
        json.dumps(
            {
                "requested_url": url,
                "final_url": url,
                "source_kind": "html",
                "media_type": "text/html",
                "retrieved_at": "2026-09-10T00:00:00Z",
                "http_status": 200,
                "capture": "test_fixture",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return stem


def _prepared(pack: Path) -> str:
    stem = _seed_pack(pack)
    assert _run(["page", "download", "--pack", str(pack), "--normalize"]).returncode == 0
    return stem


def test_score_reference_stays_relative():
    import importlib.util

    spec = importlib.util.spec_from_file_location("xtra_cli_score", CLI / "scoring" / "score.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    assert mod._pack_root_for_scorer("my_pack/courses") == "my_pack"
    assert mod._pack_root_for_scorer("my_pack") == "my_pack"
    assert mod._pack_root_for_scorer("examples/tiny_golden/courses") == "examples/tiny_golden"
    rel = mod._pack_root_for_scorer("my_pack/courses")
    assert not Path(rel).is_absolute()
    assert "Users" not in rel
    assert "Downloads" not in rel


def test_pack_join_posix_rel_on_windows_flavour():
    from pathlib import PureWindowsPath

    pack = PureWindowsPath(r"C:\packs\my_pack")
    dest = pack_join(pack, "cache/2026-09-10/stem.html")
    assert dest == PureWindowsPath(r"C:\packs\my_pack\cache\2026-09-10\stem.html")
    assert dest.parts[-3:] == ("cache", "2026-09-10", "stem.html")


def test_boot_does_not_shadow_pythonpath_with_src():
    text = (CLI / "_boot.py").read_text(encoding="utf-8")
    assert "sys.path.append(str(src))" in text
    assert "insert(0, str(src))" not in text


def test_help_lists_noun_verb_and_aliases():
    proc = _run(["--help"])
    assert proc.returncode == 0
    out = proc.stdout
    for name in (
        "catalog crawl",
        "page download",
        "page classify",
        "course extract",
        "course transform",
        "course score",
        "pack check",
        "pack promote",
        "pipeline run",
        "field union",
    ):
        assert name in out, name
    assert "Hidden aliases" in out or "hidden alias" in out.lower()


def test_catalog_crawl_requires_url():
    proc = _run(["catalog", "crawl", "--pack", "tmp_pack"])
    assert proc.returncode == 2
    assert "need --url or --url-file" in (proc.stderr + proc.stdout)


def test_crawl_alias_still_works():
    proc = _run(["crawl", "--pack", "tmp_pack"])
    assert proc.returncode == 2
    assert "need --url or --url-file" in (proc.stderr + proc.stdout)


def test_navigation_failure_dns_is_one_line():
    msg = navigation_failure(
        "https://catalog.example.edu",
        RuntimeError("Page.goto: net::ERR_NAME_NOT_RESOLVED at https://catalog.example.edu/"),
    )
    assert "host not found" in msg
    assert "catalog.brookdalecc.edu" in msg
    assert "Traceback" not in msg


def test_crawling_harvests_course_hrefs_from_fixture_html():
    html = (FIXTURES / "html" / "example-catalog-home.html").read_text(encoding="utf-8")
    base = "https://catalog.example.edu"
    urls = hrefs_from_html(html, base)
    assert "https://catalog.example.edu/english/engl101" in urls
    family = detect_family(html, base)
    assert family == "custom_html"
    assert is_course_detail_url("https://catalog.example.edu/english/engl101", family)
    assert not is_course_detail_url("https://catalog.example.edu/about", family)


def test_page_download_reuses_cached_html_and_normalizes(tmp_path: Path):
    pack = tmp_path / "pack"
    pack.mkdir()
    stem = _seed_pack(pack)
    proc = _run(["page", "download", "--pack", str(pack), "--normalize"])
    assert proc.returncode == 0, proc.stderr
    text = (pack / "normalized" / f"{stem}.txt").read_text(encoding="utf-8")
    assert "ENGL101:" in text
    assert "Credits" in text
    cached = pack / "cache" / "2026-09-10" / f"{stem}.html"
    assert cached.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_page_classify_stamps_template(tmp_path: Path):
    pack = tmp_path / "pack"
    pack.mkdir()
    _prepared(pack)
    proc = _run(["page", "classify", "--pack", str(pack)])
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((pack / "slots.json").read_text(encoding="utf-8"))
    assert payload["schema"] == "xtra-slots-1"
    assert payload["slots"][0]["template_id"] == "clean_catalog_course_detail"


def test_course_extract_and_transform_from_cached_page(tmp_path: Path):
    pack = tmp_path / "pack"
    pack.mkdir()
    _prepared(pack)
    ext = _run(["course", "extract", "--pack", str(pack)])
    assert ext.returncode == 0, ext.stderr
    rec_path = pack / "records" / "example-engl101-course.json"
    assert rec_path.is_file()
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    assert rec["verification"]["status"] == "candidate"
    labels = {f["canonical_label"]: f["value"] for f in rec["source_expected"]["fields"]}
    assert labels["course_id"] == "ENGL101"
    assert labels["course_name"] == "Composition I"
    assert labels["course_credits"] == 3
    tr = _run(["course", "transform", "--pack", str(pack)])
    assert tr.returncode == 0, tr.stderr
    scoring = json.loads((pack / "courses" / "example-engl101-course.json").read_text(encoding="utf-8"))
    assert scoring["catalogue_type"] == "COURSES"
    assert scoring["expected"]["course_id"] == "ENGL101"
    node = json.loads((pack / "jsonld" / "example-engl101-course.json").read_text(encoding="utf-8"))
    assert node["@type"] == "ceterms:Course"
    assert "ceterms:ctid" not in node
    assert node["ceterms:codedNotation"] == "ENGL101"


def _assert_identity_score(stdout: str) -> None:
    """in-repo xtra_accuracy prints JSON; xTRA-Scoring prints a text report."""
    text = stdout.strip()
    if text.startswith("{"):
        payload = json.loads(text)
        assert payload["records"] == 1
        assert payload["overall_accuracy"] == 1.0
        return
    assert "Overall score" in text or "100.00%" in text


def test_score_identity_on_transformed_pack(tmp_path: Path):
    pytest.importorskip("xtra_accuracy")
    pack = tmp_path / "pack"
    pack.mkdir()
    _prepared(pack)
    assert _run(["course", "extract", "--pack", str(pack)]).returncode == 0
    assert _run(["course", "transform", "--pack", str(pack)]).returncode == 0
    cand = tmp_path / "candidate"
    cand.mkdir()
    src = pack / "courses" / "example-engl101-course.json"
    (cand / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    proc = _run(
        [
            "course",
            "score",
            "--reference",
            str(pack / "courses"),
            "--candidate",
            str(cand),
            "--catalogue-type",
            "COURSES",
        ]
    )
    assert proc.returncode == 0, proc.stderr
    _assert_identity_score(proc.stdout)


def test_score_golden_alias_warns(tmp_path: Path):
    pytest.importorskip("xtra_accuracy")
    pack = tmp_path / "pack"
    pack.mkdir()
    _prepared(pack)
    assert _run(["course", "extract", "--pack", str(pack)]).returncode == 0
    assert _run(["course", "transform", "--pack", str(pack)]).returncode == 0
    cand = tmp_path / "candidate"
    cand.mkdir()
    src = pack / "courses" / "example-engl101-course.json"
    (cand / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    proc = _run(
        [
            "course",
            "score",
            "--golden",
            str(pack / "courses"),
            "--candidate",
            str(cand),
            "--catalogue-type",
            "COURSES",
        ]
    )
    assert proc.returncode == 0, proc.stderr
    assert "deprecated" in proc.stderr
    assert "--reference" in proc.stderr


def test_pack_promote_copies_unsigned_files(tmp_path: Path):
    pack = tmp_path / "pack"
    pack.mkdir()
    _prepared(pack)
    assert _run(["course", "extract", "--pack", str(pack)]).returncode == 0
    assert _run(["course", "transform", "--pack", str(pack)]).returncode == 0
    dest = tmp_path / "golden_sets" / "courses"
    proc = _run(["pack", "promote", "--pack", str(pack), "--to", str(dest)])
    assert proc.returncode == 0, proc.stderr
    copied = dest / "example-engl101-course.json"
    assert copied.is_file()
    blob = json.loads(copied.read_text(encoding="utf-8"))
    assert "verification_status" not in blob
    assert blob["expected"]["course_id"] == "ENGL101"


def test_pack_check_on_transformed_pack(tmp_path: Path):
    pack = tmp_path / "pack"
    pack.mkdir()
    _prepared(pack)
    assert _run(["course", "extract", "--pack", str(pack)]).returncode == 0
    assert _run(["course", "transform", "--pack", str(pack)]).returncode == 0
    proc = _run(["pack", "check", "--pack", str(pack)])
    assert proc.returncode == 0, proc.stderr
    check = json.loads((pack / "CHECK.json").read_text(encoding="utf-8"))
    assert check["ok"] is True


def test_field_union_from_pack(tmp_path: Path):
    pack = tmp_path / "pack"
    pack.mkdir()
    _prepared(pack)
    assert _run(["course", "extract", "--pack", str(pack)]).returncode == 0
    assert _run(["course", "transform", "--pack", str(pack)]).returncode == 0
    proc = _run(["field", "union", "--from-pack", str(pack)])
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    counts = payload["union_label_counts"]
    assert counts.get("course_id", 0) >= 1
    assert counts.get("course_name", 0) >= 1


def test_pipeline_run_requires_url():
    proc = _run(["pipeline", "run"])
    assert proc.returncode == 2
    combined = proc.stderr + proc.stdout
    assert "Need --url" in combined or "--url" in combined


def test_link_endpoints_derived_from_record_id():
    from build import _link_endpoints

    slot = _slot(
        record_id="acme-nursing-link-results-in-credential",
        entity_type="Link",
    )
    assert _link_endpoints(slot) == (
        "acme-nursing-learning-program",
        "acme-nursing-credential",
    )
    bad = _slot(record_id="acme-nursing-link", entity_type="Link")
    with pytest.raises(TranscriptionError, match="must end with"):
        _link_endpoints(bad)


def test_extract_course_from_fixture_html():
    html = (FIXTURES / "html" / "example-engl101.html").read_text(encoding="utf-8")
    text = normalize_html(html)
    assert detect_template(text) == "clean_catalog_course_detail"
    drafts = extract_course(_slot(), text)
    by_label = {d.canonical_label: d.value for d in drafts}
    assert by_label["course_id"] == "ENGL101"
    assert by_label["course_name"] == "Composition I"
    assert by_label["course_credits"] == 3


def test_pdf_fixture_is_readable_pdf():
    pdf = FIXTURES / "pdf" / "sample-placeholder.pdf"
    data = pdf.read_bytes()
    assert data.startswith(b"%PDF")
    assert b"%%EOF" in data
    assert b"/Type/Page" in data or b"/Type /Page" in data
    assert len(data) > 64


def test_stage_scripts_are_runnable_directly(tmp_path: Path):
    pack = tmp_path / "pack"
    pack.mkdir()
    proc = subprocess.run(
        [sys.executable, str(CLI / "crawling" / "crawl.py"), "--pack", str(pack)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert proc.returncode == 2
    for rel in (
        "downloading/download.py",
        "extraction/extract.py",
        "transformation/transform.py",
        "scoring/score.py",
        "scoring/check.py",
        "extraction/classify.py",
        "extraction/run.py",
        "lib/union_fields.py",
    ):
        help_proc = subprocess.run(
            [sys.executable, str(CLI / rel), "-h"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        assert help_proc.returncode == 0, (rel, help_proc.stderr)
