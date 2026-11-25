"""`golden-datasets migrate --to-classes` (LearningProgram plan, Phase 2), outside in: a scored Course catalog, built
with today's code, is written back the way roots were before class folders (`to_legacy`: `golden-dataset-studio/`
folders, `course_key`, copies of the crawl, of the extract output and of the scores in the Studio's root); the
migration brings it back. Nothing it serves changes, `check` passes, and a second run does nothing."""

from __future__ import annotations

import io
import json

import pyarrow.parquet as pq
from test_golden_versions import CAT, studio  # noqa: F401  (studio: the fixture)
from test_scores import scored  # noqa: F401

from golden_datasets import check, manifest, migrate, properties, scores
from golden_datasets.cli import main
from golden_datasets.context import Ctx
from golden_datasets.storage import LocalRoot

OLD = "golden-dataset-studio"
BACK = {"record_external_identifier": "course_key", "skipped_no_record_external_identifier": "skipped_no_course_key"}


def _back(obj):
    if isinstance(obj, dict):
        return {BACK.get(k, k): _back(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_back(v) for v in obj]
    return obj


def _old_bytes(path: str, data: bytes) -> bytes:
    if path.endswith(".parquet"):
        t = pq.read_table(io.BytesIO(data))
        if not any(n in BACK for n in t.column_names):
            return data
        buf = io.BytesIO()
        pq.write_table(t.rename_columns([BACK.get(n, n) for n in t.column_names]), buf)
        return buf.getvalue()
    if path.endswith(".jsonl"):
        return "".join(json.dumps(_back(json.loads(x))) + "\n" for x in data.decode().splitlines() if x).encode()
    if path.endswith(".json"):
        doc = _back(json.loads(data))
        if "/rulesets/" in path:
            doc["settings"]["course_key_rule"] = {"locator-course-page": "course-code",
                                                  "locator-program-requirement": "stub-code"}
        return json.dumps(doc).encode()
    return data


def _mv(src, path: str, dst, new: str) -> None:
    dst.write_bytes(new, _old_bytes(new, src.read_bytes(path)))
    src.delete(path)


def to_legacy(root: LocalRoot, xtra: LocalRoot) -> dict:
    """Today's root as it was before class folders (the inverse of the migration); returns the manifest it had."""
    import hashlib

    doc = manifest.load(root)[0]
    legacy = {"schema": "golden-datasets-manifest/1", "updated_at": doc["updated_at"], "catalogs": []}
    for cat in doc["catalogs"]:
        c, cls = cat["catalog"], cat["classes"]["course"]
        old = f"{c}/{OLD}"

        def back(p: str, c=c, old=old) -> str:
            return p.replace(f"{c}/course/", f"{old}/", 1)

        for p in root.list(f"{c}/course"):
            _mv(root, p, root, back(p))
        entry = {k: v for k, v in cat.items() if k not in ("classes", "crawls", "crawls_root")}
        entry.update(rule_versions=[back(p) for p in cls["rule_versions"]],
                     rulesets=[{**r, "path": back(r["path"])} for r in cls["rulesets"]],
                     annotations=back(cls["annotations"]) if cls["annotations"] else None, crawls=[])
        for k in cat["crawls"]:
            crawl, kc = k["crawl"], k["classes"]["course"]
            base, studio_dir = f"{c}/{crawl}", f"{c}/{crawl}/{OLD}"

            def kback(p: str, base=base, studio_dir=studio_dir) -> str:
                rel = p[len(base) + 1:]
                rel = rel.replace("course/rule-runs/", "extractions/", 1).replace("course/golden/", "golden/", 1)
                rel = rel.replace("course/scores-pending.json", "scores/pending.json", 1)
                return f"{studio_dir}/{rel}"

            for p in root.list(base):
                _mv(root, p, root, kback(p))
            for e in kc["extractions"]:  # the tables' hashes as they were
                meta_path = kback(f"{e['path']}/extraction.json")
                meta = json.loads(root.read_bytes(meta_path))
                for name, info in meta["files"].items():
                    info["sha256"] = hashlib.sha256(root.read_bytes(f"{meta_path.rsplit('/', 1)[0]}/{name}")).hexdigest()
                root.write_json(meta_path, meta)
            for s in kc["scores"]:
                for p in xtra.list(s["path"]):
                    _mv(xtra, p, root, f"{studio_dir}/scores/{s['id']}/{p[len(s['path']) + 1:]}")
            outs = []
            for o in k.get("extract_outputs", []):
                copy = f"{studio_dir}/extract-outputs/{o['id']}"
                for p in xtra.list(base):
                    if not p.startswith((f"{base}/extract/", f"{base}/pages/")) and not p.endswith("crawl.json"):
                        root.write_bytes(f"{copy}/{p[len(base) + 1:]}", xtra.read_bytes(p))
                outs.append({**o, "copy": copy})
            for p in [f"{base}/crawl.json", *xtra.list(f"{base}/pages")]:  # the copy of the crawl
                root.write_bytes(p, xtra.read_bytes(p))
            nk = {x: v for x, v in k.items() if x not in ("classes", "extract_outputs")}
            nk.update(pages=kback(k["pages"]), extract_outputs=outs,
                      extractions=[{**e, "path": kback(e["path"])} for e in kc["extractions"]],
                      golden=[{**g, "path": kback(g["path"])} for g in kc["golden"]],
                      scores=[{"id": s["id"]} for s in kc["scores"]])
            if k.get("assets"):
                nk["assets"] = {x: (kback(v) if isinstance(v, str) and v.startswith(base) else v)
                                for x, v in k["assets"].items()}
            entry["crawls"].append(nk)
        legacy["catalogs"].append(entry)
    root.write_json(f"{OLD}/manifest.json", legacy)
    root.delete("manifest.json")
    for name in migrate.ROOT_FILES:
        if root.exists(name):
            _mv(root, name, root, f"{OLD}/{name}")
    return doc


def _served(c) -> dict:
    """What the Studio serves for the catalog: rule rows, records, rules and scores."""
    b = f"/api/catalogs/{CAT}"
    return {"rows": [(r["key"], r["record_external_identifier"], r["value"], r["state"])
                     for r in c.get(f"{b}/rules/course-name/rows").json()["rows"]],
            "records": c.get(f"{b}/courses").json(),
            "rules": [(g["id"], [r["rule_id"] for r in g["rules"]]) for g in c.get(f"{b}/rules").json()["groups"]],
            "scores": [(s["id"], s["status"], s["golden"]) for s in c.get(f"{b}/scores").json()],
            "golden": [v["id"] for v in c.get(f"{b}/golden").json()["versions"]]}


def test_migration_brings_a_legacy_root_back_and_a_second_run_changes_nothing(scored, capsys):  # noqa: F811
    from fastapi.testclient import TestClient

    from golden_datasets.server.app import create_app

    c, ctx, tmp = scored
    assert scores.score(ctx, "ruleset-v1")["status"] == "done"
    root, xtra = LocalRoot(ctx.root.base), LocalRoot(tmp / "xtra-cli-output")
    before = _served(TestClient(create_app(root.uri)))
    want = to_legacy(root, xtra)
    assert root.exists(f"{CAT}/{OLD}/annotations.jsonl") and not root.exists(f"{CAT}/course/annotations.jsonl")
    assert b'"course_key"' in root.read_bytes(f"{CAT}/{OLD}/annotations.jsonl")
    capsys.readouterr()

    # the dry run prints every step and changes nothing
    assert main(["migrate", "--to-classes", "--dry-run", "--root", root.uri, "--xtra-root", xtra.uri]) == 0
    out = capsys.readouterr().out
    assert f"would move {CAT}/{OLD}/annotations.jsonl → {CAT}/course/annotations.jsonl" in out
    assert f"/{OLD}/extractions/rs-0001/occurrences.parquet → {CAT}/{ctx.crawl}/course/rule-runs/rs-0001/" in out
    assert "/scores/sc-0001/score.json →" in out and "(xtra-cli's container" in out
    assert f"would remove the crawl copy {CAT}/{ctx.crawl}/crawl.json" in out
    assert root.exists(f"{OLD}/manifest.json") and not root.exists("manifest.json")

    assert main(["migrate", "--to-classes", "--root", root.uri, "--xtra-root", xtra.uri]) == 0
    out = capsys.readouterr().out
    assert "original kept as annotations.jsonl.legacy" in out
    got = manifest.load(root)[0]
    for doc in (got, want):
        doc.pop("updated_at")
        for cat in doc["catalogs"]:
            for k in cat["crawls"]:
                for o in k["extract_outputs"]:
                    o.pop("copy")  # the migrated copy is kept in xtra-cli's container
    assert got == want
    out_id = want["catalogs"][0]["crawls"][0]["extract_outputs"][0]["id"]
    assert xtra.exists(f"{CAT}/{ctx.crawl}/extract/{out_id}/extract-report.json")
    assert root.exists(f"{CAT}/course/annotations.jsonl.legacy")
    assert b'"record_external_identifier"' in root.read_bytes(f"{CAT}/course/annotations.jsonl")
    assert "course_key_rule" not in json.loads(root.read_bytes(f"{CAT}/course/rulesets/v0001.json"))["settings"]
    assert not root.exists(f"{CAT}/{ctx.crawl}/crawl.json") and not root.list(f"{CAT}/{ctx.crawl}/pages")
    assert root.exists(f"{OLD}/manifest.json.legacy")
    assert _served(TestClient(create_app(root.uri))) == before
    properties.apply(Ctx(root, CAT), "test")  # a publish after the migration (and `check` wants every property)
    assert not [r for r in check.run(Ctx(root, CAT)) if r[3]]

    # a second run changes nothing
    files = sorted(root.list(""))
    assert main(["migrate", "--to-classes", "--root", root.uri, "--xtra-root", xtra.uri]) == 0
    assert "already migrated" in capsys.readouterr().out and sorted(root.list("")) == files


def test_a_crawl_copy_found_nowhere_else_stays_and_is_read_where_it_is(scored, tmp_path):  # noqa: F811
    c, ctx, tmp = scored
    root, xtra, crawl = LocalRoot(ctx.root.base), LocalRoot(tmp / "xtra-cli-output"), ctx.crawl
    to_legacy(root, xtra)
    for p in xtra.list(f"{CAT}/{crawl}/pages"):  # xtra-cli's copy of the crawl is gone
        xtra.delete(p)
    migrate.migrate(root, xtra, None, dry_run=False, log=lambda *a: None)
    assert root.exists(f"{CAT}/{crawl}/crawl.json")
    entry = manifest.catalog_entry(manifest.load(root)[0], CAT, create=False)
    assert entry["crawls_root"] == root.uri
    assert Ctx(root, CAT).page_path("page-0").exists()


def test_a_symlinked_pages_folder_is_unlinked_and_its_target_kept(scored):  # noqa: F811
    c, ctx, tmp = scored
    root, xtra, crawl = LocalRoot(ctx.root.base), LocalRoot(tmp / "xtra-cli-output"), ctx.crawl
    to_legacy(root, xtra)
    pages = root.base / CAT / crawl / "pages"
    for f in pages.iterdir():
        f.unlink()
    pages.rmdir()
    pages.symlink_to(xtra.base / CAT / crawl / "pages")  # `sync --pages link`, as local roots had
    migrate.migrate(root, xtra, None, dry_run=False, log=lambda *a: None)
    assert not pages.exists() and not pages.is_symlink()
    assert sorted(p.name for p in (xtra.base / CAT / crawl / "pages").iterdir())  # the mirror is intact
