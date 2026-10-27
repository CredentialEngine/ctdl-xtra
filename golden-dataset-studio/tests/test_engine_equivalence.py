"""The Studio engine gives the same labels and values as review-ui-v2's engine, on real pages of all five catalogs.

Marked `slow`: it reads the read-only mirror ~/review-ui-v3-data/xtra-cli-output (never writes to it).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import lxml.html
import pytest

from golden_datasets import engine, v2engine
from golden_datasets.import_v2 import IN_SCOPE, PAGE_RULE_IDS, build_v1_rules

MIRROR = Path.home() / "review-ui-v3-data" / "xtra-cli-output"
CATALOGS = {  # catalog → (crawl, v2 extraction whose rules.json the latest session used)
    "avc-elumenapp-com-catalog-2026-27-welcome": ("2026-10-12T20-59-13Z", "2026-10-19T17-27-31Z"),
    "ccsf-curricunet-com-catalog": ("2026-10-01T16-02-34Z", "2026-10-19T17-18-22Z"),
    "catalog-marshall-edu": ("2026-10-20T13-18-30Z", "2026-10-21T14-21-32Z"),
    "catalog-ualr-edu": ("2026-10-18T21-05-00Z", "2026-10-21T14-14-38Z"),
    "catalog-wvu-edu": ("2026-10-20T13-19-46Z", "2026-10-21T14-25-24Z"),
}
SAMPLE = 45


def _v2_main(html: str, content_root: str) -> str | None:
    doc = lxml.html.fromstring(html)
    mains = doc.cssselect(content_root)
    return lxml.html.tostring(mains[0], encoding="unicode", with_tail=False) if mains else None


@pytest.mark.slow
@pytest.mark.parametrize("catalog", sorted(CATALOGS))
def test_same_labels_and_values_as_v2(catalog):
    crawl, v2_ext = CATALOGS[catalog]
    base = MIRROR / catalog / crawl
    if not base.exists():
        pytest.skip("local mirror not available")
    v2 = json.loads((base / "extractions" / v2_ext / "rules.json").read_text())
    v2_scoped = {**v2, "field_rules": [f for f in v2["field_rules"] if f["canonical_label"] in IN_SCOPE]}
    drafts, settings, _ = build_v1_rules(SimpleNamespace(catalog=catalog), v2)
    rules = {rid: {**d, "version": 1} for rid, d in drafts.items()}
    metas = sorted((base / "pages").glob("*.meta.json"))
    # Spread the sample over the crawl, and make sure it includes pages where rules fire.
    sample = metas[:: max(1, len(metas) // SAMPLE)]
    need = {"labels": True, "matched": None, "locators": sorted(r for r in rules if rules[r]["kind"] == "locator"),
            "fields": sorted(r for r in rules if rules[r]["kind"] == "field"), "page_facts": False}
    compared = values = 0
    for meta_path in sample:
        meta = json.loads(meta_path.read_text())
        url = meta.get("final_url") or meta["requested_url"]
        html = (base / "pages" / f"{meta['stem']}.html").read_text(errors="replace")
        ref = v2engine.run_page(v2_scoped, url, _v2_main(html, v2["content_root"]))
        ours = engine.run_page(meta["stem"], url, html.encode(), rules, settings, need)
        assert sorted(PAGE_RULE_IDS[x["rule_id"]] for x in ref["labels"]) == \
            sorted(r["rule_id"] for r in ours["page_labels"] if r["matched"]), meta["stem"]
        a = sorted((f["rule_id"], f["value"]) for e in ref["entities"] for f in e["fields"] if f["value"] is not None)
        b = sorted((m["rule_id"], m["value"]) for m in ours["matches"] if m["status"] == "found")
        assert a == b, meta["stem"]
        compared += 1
        values += len(b)
    assert compared >= SAMPLE * 0.9 and values > 0
