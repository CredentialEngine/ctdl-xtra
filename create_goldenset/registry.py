"""Exact-URL Credential Registry lookup. Never match by name."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from config import PACK, RECORD_DIR
from normalize import sha256_bytes

SEARCH_URL = "https://apps.credentialengine.org/assistant/search/ctdl"
GRAPH_URL = "https://credentialengineregistry.org/graph"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _api_key() -> str | None:
    return (
        os.environ.get("REGISTRY_API_KEY")
        or os.environ.get("CE_API_KEY")
        or os.environ.get("CE_REGISTRY_API_KEY")
        or None
    )


def _walk_subject_webpages(obj, acc: list[tuple[str, dict]]) -> None:
    if isinstance(obj, dict):
        sw = obj.get("ceterms:subjectWebpage")
        urls: list[str] = []
        if isinstance(sw, str):
            urls = [sw]
        elif isinstance(sw, list):
            urls = [u for u in sw if isinstance(u, str)]
        if urls:
            acc.append((urls[0] if len(urls) == 1 else "", obj))
            for u in urls:
                acc.append((u, obj))
        for val in obj.values():
            _walk_subject_webpages(val, acc)
    elif isinstance(obj, list):
        for item in obj:
            _walk_subject_webpages(item, acc)


def _ctid_of(obj: dict) -> str | None:
    for key in ("ceterms:ctid", "ctid", "@id"):
        val = obj.get(key)
        if isinstance(val, str) and "ce-" in val:
            start = val.find("ce-")
            return val[start : start + 39] if len(val) >= start + 39 else val[start:]
    return None


def _post_search(catalog_url: str) -> tuple[int, dict | str]:
    key = _api_key()
    payload = {
        "SearchTerms": "",
        "Skip": 0,
        "Take": 10,
        "Filters": [
            {
                "URI": "ceterms:subjectWebpage",
                "ItemTexts": [catalog_url],
            }
        ],
        "ExactMatch": True,
        "golden_set_match_key": "ceterms:subjectWebpage",
        "golden_set_match_value": catalog_url,
        "golden_set_note": "Only an exact subjectWebpage match is allowed. Do not match by name.",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Nicolas-xTRA-golden-set/courses-30",
    }
    if key:
        headers["Authorization"] = key if key.lower().startswith("bearer ") else f"Bearer {key}"
    req = urllib.request.Request(SEARCH_URL, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return resp.status, raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw
    except urllib.error.URLError as exc:
        return 0, {"error": str(exc.reason)}


def lookup_url(catalog_url: str) -> dict:
    status, payload = _post_search(catalog_url)
    hits: list[tuple[str, dict]] = []
    if isinstance(payload, (dict, list)):
        _walk_subject_webpages(payload, hits)
    exact = [(u, obj) for u, obj in hits if u == catalog_url]
    result = {
        "catalog_url": catalog_url,
        "http_status": status,
        "api_key_present": bool(_api_key()),
        "search_url": SEARCH_URL,
        "exact_subjectWebpage_hits": len({_ctid_of(obj) or u for u, obj in exact}),
        "payload": payload if not isinstance(payload, str) or len(payload) < 8000 else payload[:8000],
    }
    if status in {401, 403} or not _api_key():
        result["decision"] = "not_checked"
        result["notes"] = (
            "Registry assistant search was not authorized (missing or rejected API key). "
            "No name search was performed. Status is not_checked, not a match."
        )
        return result
    if status != 200:
        result["decision"] = "not_checked"
        result["notes"] = f"Registry search HTTP {status}. Exact subjectWebpage query only; not a name match."
        return result
    if not exact:
        result["decision"] = "record_not_found"
        result["notes"] = (
            "Search returned no Registry document whose ceterms:subjectWebpage equals this catalog URL. "
            "Name matching is forbidden."
        )
        return result
    obj = exact[0][1]
    ctid = _ctid_of(obj)
    result["decision"] = "matched"
    result["registry_ctid"] = ctid
    result["matched_object"] = obj
    result["notes"] = "Exact ceterms:subjectWebpage match."
    return result


def apply_to_record(rec: dict, lookup: dict, *, rel_path: str, sha256: str | None) -> None:
    decision = lookup["decision"]
    rec["registry_expected"] = {
        "status": decision,
        "checked_at": _now() if decision != "not_checked" else None,
        "registry_ctid": lookup.get("registry_ctid") if decision == "matched" else None,
        "registry_url": (
            f"https://credentialengineregistry.org/resources/{lookup['registry_ctid']}"
            if decision == "matched" and lookup.get("registry_ctid")
            else None
        ),
        "registry_snapshot_path": rel_path,
        "registry_resource_sha256": sha256,
        "property_comparisons": [],
        "notes": lookup.get("notes"),
    }
    if decision == "not_checked":
        rec["registry_expected"]["checked_at"] = _now()
        rec["registry_expected"]["registry_ctid"] = None
        rec["registry_expected"]["registry_url"] = None
        rec["registry_expected"]["registry_resource_sha256"] = sha256


def lookup_pack() -> list[dict]:
    out_dir = PACK / "registry"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in sorted(RECORD_DIR.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        url = rec["source"]["requested_url"]
        lookup = lookup_url(url)
        dest = out_dir / f"{rec['record_id']}.json"
        blob = json.dumps(lookup, indent=2, ensure_ascii=False).encode("utf-8")
        dest.write_bytes(blob)
        rel = f"registry/{rec['record_id']}.json"
        apply_to_record(rec, lookup, rel_path=rel, sha256=sha256_bytes(blob))
        path.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        rows.append(
            {
                "record_id": rec["record_id"],
                "decision": lookup["decision"],
                "http_status": lookup["http_status"],
            }
        )
        print(f"registry {rec['record_id']} {lookup['decision']} http={lookup['http_status']}")
    (out_dir / "summary.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return rows
