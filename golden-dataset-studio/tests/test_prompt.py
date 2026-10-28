"""The prompt for Claude Code (W6, spec §7.5)."""

from __future__ import annotations

import pytest

from golden_datasets.cli import main
from golden_datasets.context import Ctx
from golden_datasets.prompt import _location, build_prompt, cell, has_raw_html, table

OCC = "html > body > main > div:nth-of-type(4)"


def test_location_labels():
    a = {"expected": {"css_path": f"{OCC} > div > div", "char_start": 3, "char_end": 9},
         "current_css_path": f"{OCC} > div > div", "occurrence_css_path": OCC}
    assert _location(a) == " (chars 3–9 of the extracted element)"
    a["current_css_path"] = None
    assert _location(a) == " (chars 3–9 of `<occurrence> > div > div`)"
    a["expected"]["css_path"] = None
    assert _location(a) == ""


def test_table_cells_stay_on_one_line():
    assert cell("a | b\nc") == "a \\| b⏎ c"
    assert table(["x", "y"], [[1, "p|q"]]) == ["| x | y |", "|---|---|", "| 1 | p\\|q |"]


def test_raw_html_detector():
    assert has_raw_html("x <div class=a>") and has_raw_html("<HTML>") and not has_raw_html("a < b, `css > div`")


@pytest.fixture(scope="module")
def ctx(tmp_path_factory, avc_v1_root):
    dst = tmp_path_factory.mktemp("w6p") / "root"
    assert main(["sync", "--from", str(avc_v1_root), "--to", str(dst), "-c", "avc", "--pages", "link"]) == 0
    return Ctx(str(dst), "avc")


@pytest.mark.slow
def test_one_rule_prompt(ctx):
    out = build_prompt(ctx, "course-description")
    text = out["text"]
    assert out["rules"] == ["course-description"] and out["annotations"] == 5 and out["page_refs"] == 5
    assert out["chars"] == len(text) and out["tokens"] == round(len(text) / 4)
    assert not has_raw_html(text) and "<html" not in text.lower() and "<div" not in text.lower()
    assert text.startswith("# Improve rule `course-description` — AVC catalog\n")
    for section in ("## Setup", "## Context", "## Limits", "## Rule `course-description` v1", "### Open annotations (5)",
                    "### Marked correct: must not change (9)", "## How to work"):
        assert section in text
    for code in ("GEOG222", "PHYS102", "DFST202", "AUTO230", "ENGR955"):
        assert f"| **WRONG** | {code} | `" in text
    for code in ("ACCT199", "AERO199", "CFE114", "NS922L"):
        assert f"\n| {code} | \"" in text
    for cmd in ("rule show", "rule annotations", "rule draft", "rule try", "rule publish", "pages get",
                "pages sample", "sql"):
        assert f"golden-datasets {cmd}" in text
    assert "uv tool install --reinstall 'git+https://github.com/CredentialEngine/ctdl-xtra.git@" in text
    assert f"GOLDEN_DATASETS_ROOT={ctx.root.uri}\n" in text and "GOLDEN_DATASETS_CATALOG=avc\n" in text
    assert "az login" not in text and out["target"] == "local" and out["root"] == ctx.root.uri
    assert "BETTER" in text and "Never use `--force`" in text
    assert "Questions for the institution" not in text  # AVC's questions are on program pages


@pytest.mark.slow
def test_azure_version(ctx):
    azure = "azure://https://acct.blob.core.windows.net/box/prefix"
    out = build_prompt(ctx, "course-description", target="azure", azure_root=azure)
    text = out["text"]
    assert out["root"] == azure and f"GOLDEN_DATASETS_ROOT={azure}\n" in text and str(ctx.root.uri) not in text
    assert "az login" in text and "`acct` storage account" in text
    # everything after the setup is the same as the local version, but the root
    local = build_prompt(ctx, "course-description")["text"]
    assert text.split("## Limits")[1] == local.split("## Limits")[1]


@pytest.mark.slow
def test_k2_version_is_a_run(ctx):
    """target k2 (agent_runs.py): run header and reporting, a folder per run, SAS tokens from K2's file, no az."""
    azure = "azure://https://acct.blob.core.windows.net/box/prefix"
    run = {"run_id": "20261028T031209Z-a1b2", "started_by": "Jared Diener", "k2": {"agent": "golden-rules"}}
    out = build_prompt(ctx, None, True, target="k2", azure_root=azure, run=run)
    text = out["text"]
    d = "/var/lib/k2/work/golden-rules/runs/20261028T031209Z-a1b2"
    assert out["target"] == "k2" and out["root"] == azure
    assert "az login --use-device-code" not in text and "az account show" not in text
    assert "## This is a Golden Rules Studio run" in text and "started by Jared Diener" in text
    assert f'cd {d} && golden-datasets run note --run 20261028T031209Z-a1b2 "<one line>"' in text
    assert f"mkdir -p {d} && printf '%s\\n' 'GOLDEN_DATASETS_ROOT={azure}' 'GOLDEN_DATASETS_CATALOG=avc' > {d}/golden-datasets.env" in text
    assert "/var/lib/k2/work/golden-datasets.env" in text and "If the install fails, don't install another version" in text
    assert "## End the run" in text and f"cd {d} && golden-datasets run done --run 20261028T031209Z-a1b2 --summary-file summary.md --outcome" in text
    assert f"`{d}/summary.md`" in text
    assert "Report back:" not in text
    # the work itself is the same as the Azure version
    az = build_prompt(ctx, None, True, target="azure", azure_root=azure)["text"]
    assert text.split("## Limits")[1].split("## End the run")[0] == az.split("## Limits")[1].split("Report back:")[0]


@pytest.mark.slow
def test_deterministic(ctx):
    a = build_prompt(ctx, None, True)
    b = build_prompt(Ctx(ctx.root, "avc"), None, True)
    assert a == b
    assert build_prompt(ctx, "course-description")["text"] == build_prompt(ctx, "course-description")["text"]


@pytest.mark.slow
def test_needs_work_scope(ctx):
    out = build_prompt(ctx, None, True)
    assert out["rules"] == ["program-page-with-courses", "course-description"]
    text = out["text"]
    assert text.startswith("# Improve 2 rules that need work — AVC catalog")
    assert "## Rule `program-page-with-courses` v1 — page rule" in text and "### Open annotations (7)" in text
    assert "## The 2 rules\n" in text and "## Setup" in text and "GOLDEN_DATASETS_ROOT=" in text
    q = text.split("## Questions for the institution (not bugs)")[1].split("## How to work")[0]
    assert q.count("\n| ") == 9 and "Should I reject all these properties?" in q  # a header row + 8
    assert "QUESTION" not in text.split("## Questions")[0]  # questions aren't listed as bugs
    assert not has_raw_html(text)


@pytest.mark.slow
def test_cli_and_api_give_the_same_text(ctx, capsys):
    from fastapi.testclient import TestClient

    from golden_datasets.server.app import create_app

    capsys.readouterr()
    assert main(["prompt", "--root", ctx.root.uri, "-c", "avc", "--rule", "course-description"]) == 0
    cli_text = capsys.readouterr().out
    c = TestClient(create_app(ctx.root.uri))
    api = c.get("/api/catalogs/avc/prompt", params={"rule": "course-description"}).json()
    assert api["text"] == cli_text and api["scope"] == {"rule": "course-description", "needs_work": False}
    assert api["studio_root"] == ctx.root.uri
    assert api["target"] == "azure" and api["root"].startswith("azure://")  # the only version the Studio gives
    assert c.get("/api/catalogs/avc/prompt", params={"needs_work": "true"}).json()["rules"] == \
        ["program-page-with-courses", "course-description"]
    assert c.get("/api/catalogs/avc/prompt", params={"rule": "nope"}).status_code == 404
