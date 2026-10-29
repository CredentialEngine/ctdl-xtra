"""Spec §10 budgets, end to end through the HTTP API of a real `golden-datasets serve` process.

    uv run python bench/bench_budgets.py --root .data/root-demo
    uv run python bench/bench_budgets.py --root azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output/zz-scratch-review-ui-v3

"cold" = a fresh server process with an empty disk cache (GOLDEN_DATASETS_CACHE in a temp dir); "warm" = the same
requests again. Recording a verdict appends to the root's annotations.jsonl (author "bench"), so point it at a
scratch root, never at a shared one.
"""

from __future__ import annotations

import argparse
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time

import httpx

BUDGETS = {  # action: (cold ms, warm ms) — spec §10, "cold" measured against the Azure scratch prefix
    "open catalog (rule list shown)": (2000, 300),
    "switch rule (rows shown)": (500, 150),
    "next row (page pane updated)": (1000, 100),
    "record a verdict": (300, 300),
    "open Compare (two extractions)": (2000, 300),
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def timed(fn) -> float:
    t = time.perf_counter()
    fn()
    return 1000 * (time.perf_counter() - t)


def run(root: str, catalog: str, rules: list[str]) -> dict[str, tuple[float, float]]:
    cache = tempfile.mkdtemp(prefix="gds-bench-cache-")
    port = free_port()
    env = {**os.environ, "GOLDEN_DATASETS_CACHE": cache}
    proc = subprocess.Popen([sys.executable, "-m", "golden_datasets.cli", "serve", "--root", root, "--port", str(port)],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        c = httpx.Client(base_url=base, timeout=120, headers={"Accept-Encoding": "gzip"})
        for _ in range(200):
            try:
                if c.get("/api/health").status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)

        def get(u):
            r = c.get(u)
            r.raise_for_status()
            return r

        out: dict[str, list[float]] = {k: [] for k in BUDGETS}
        open_cat = lambda: (get(f"/api/catalogs/{catalog}"), get(f"/api/catalogs/{catalog}/rules"))  # noqa: E731
        out["open catalog (rule list shown)"].append(timed(open_cat))
        rows = {}
        for rid in rules:
            out["switch rule (rows shown)"].append(timed(
                lambda rid=rid: rows.__setitem__(rid, get(f"/api/catalogs/{catalog}/rules/{rid}/rows?limit=200").json())))
        stems = [r["page_stem"] for r in rows[rules[0]]["rows"][:6]]
        render = lambda s: get(f"/api/catalogs/{catalog}/pages/{s}/render")  # noqa: E731
        out["next row (page pane updated)"].append(timed(lambda: render(stems[0])))  # not prefetched: cold
        row = rows[rules[0]]["rows"][0]
        body = {"type": "comment", "author": "bench", "note": "bench: timing a write",
                "target": {"kind": "match", "rule_id": rules[0], "occurrence_key": row["occurrence_key"]}}
        out["record a verdict"].append(timed(lambda: c.post(f"/api/catalogs/{catalog}/annotations", json=body)
                                             .raise_for_status()))
        out["open Compare (two extractions)"].append(timed(lambda: get(f"/api/catalogs/{catalog}/compare")))
        # warm: the same again; "next row" = a page the UI prefetched while the previous row was shown
        for s in stems[1:5]:
            render(s)  # the prefetch
        warm: dict[str, list[float]] = {k: [] for k in BUDGETS}
        for _ in range(5):
            warm["open catalog (rule list shown)"].append(timed(open_cat))
            for rid in rules:
                warm["switch rule (rows shown)"].append(timed(
                    lambda rid=rid: get(f"/api/catalogs/{catalog}/rules/{rid}/rows?limit=200")))
            warm["open Compare (two extractions)"].append(timed(lambda: get(f"/api/catalogs/{catalog}/compare")))
        for s in stems[1:5]:
            warm["next row (page pane updated)"].append(timed(lambda s=s: render(s)))
        for _ in range(3):
            warm["record a verdict"].append(timed(lambda: c.post(f"/api/catalogs/{catalog}/annotations", json=body)
                                                  .raise_for_status()))
        return {k: (max(out[k]), statistics.median(warm[k])) for k in BUDGETS}
    finally:
        proc.terminate()
        proc.wait(10)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--catalog", default="avc")
    ap.add_argument("--rules", nargs="+", default=["course-description", "stub-name", "locator-program-requirement"])
    args = ap.parse_args()
    res = run(args.root, args.catalog, args.rules)
    print(f"root: {args.root}")
    print(f"{'action':34} {'cold ms':>9} {'budget':>7}  {'warm ms':>8} {'budget':>7}")
    ok = True
    for k, (cold, warm) in res.items():
        bc, bw = BUDGETS[k]
        good = cold <= bc and warm <= bw
        ok &= good
        print(f"{k:34} {cold:9.0f} {bc:7d}  {warm:8.1f} {bw:7d}  {'ok' if good else 'OVER'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
