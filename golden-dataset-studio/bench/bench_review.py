"""Spec §10 budgets for the review UI (W4), on a local root.

    uv run --with playwright python bench/bench_review.py --root .data/root-w4 [--catalog avc] [--browser] [--shots DIR]

The root is first synced (pages linked, never copied) into a temporary root, so recording a verdict doesn't touch
yours. Then, against a fresh server process (cold) and again on the same process (warm):

- open the catalog: `/catalogs/{c}` + `/rules` (the rule list shown);
- switch rule: `/rules/{id}` + `/rules/{id}/rows` (rows shown);
- next row: the render of the next row's page, prefetched while the previous row was shown (spec §10);
- record a verdict: `POST /annotations`.

`--browser` also times, in headless Chromium, "next row" end to end (Tab pressed → the page pane shows the new page
with its highlight) and "switch rule" (click → first row shown). `--shots DIR` takes the W4 screenshots
(`bench/shots_review.py`) against the same server.
"""

from __future__ import annotations

import argparse
import json
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

BUDGET = {  # (cold, warm) in ms, spec §10
    "open catalog (rule list)": (2000, 300),
    "switch rule (rows)": (500, 150),
    "next row (page pane, prefetched)": (1000, 100),
    "record a verdict": (300, 300),
}
RULES = ["course-description", "course-name", "locator-program-requirement", "program-page-with-courses", "stub-name"]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, root: str):
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.proc = subprocess.Popen([sys.executable, "-m", "golden_datasets.cli", "serve", "--root", root,
                                      "--port", str(self.port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     cwd=HERE.parent)
        for _ in range(200):
            try:
                urllib.request.urlopen(self.base + "/api/health", timeout=1)
                return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("server didn't start")

    def get(self, path: str):
        with urllib.request.urlopen(self.base + path, timeout=60) as r:
            body = r.read()
        return json.loads(body) if r.headers.get_content_type() == "application/json" else body

    def post(self, path: str, body: dict):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    def stop(self):
        self.proc.terminate()
        self.proc.wait(10)


def ms(fn) -> tuple[float, object]:
    t = time.perf_counter()
    out = fn()
    return 1000 * (time.perf_counter() - t), out


def measure(srv: Server, cat: str, rule: str, i: int) -> dict[str, float]:
    c = f"/api/catalogs/{cat}"
    out = {}
    out["open catalog (rule list)"], _ = ms(lambda: (srv.get(c), srv.get(c + "/rules")))
    out["switch rule (rows)"], (detail, rows) = ms(lambda: (srv.get(f"{c}/rules/{rule}"),
                                                            srv.get(f"{c}/rules/{rule}/rows?limit=100")))
    rws = rows["rows"]
    kind = {"field": "match", "locator": "occurrence", "page": "page"}[detail["kind"]]
    stem = rws[i + 1]["page_stem"]
    srv.get(f"{c}/pages/{stem}/render")  # the prefetch, made while row i was shown
    out["next row (page pane, prefetched)"], _ = ms(lambda: srv.get(f"{c}/pages/{stem}/render"))
    r = rws[i]
    target = {"kind": kind, "rule_id": rule, "occurrence_key": r["occurrence_key"], "page_stem": r["page_stem"]}
    out["record a verdict"], _ = ms(lambda: srv.post(c + "/annotations", {
        "type": "comment", "author": "golden-datasets bench", "target": target, "note": "bench"}))
    return out


def browser_times(base: str, cat: str) -> dict[str, float]:
    from playwright.sync_api import sync_playwright

    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.goto(f"{base}/#/c/{cat}/rules/course-description")
        page.wait_for_selector(".row.on")
        page.wait_for_function("() => !document.querySelector('.gpp-loading')", timeout=30000)
        page.wait_for_timeout(1500)  # prefetch of the next rows
        nexts = []
        for _ in range(5):
            src = page.eval_on_selector(".gpp-body iframe", "f => f.getAttribute('src')")
            t = time.perf_counter()
            page.keyboard.press("Tab")
            page.wait_for_function("(src) => { const f = document.querySelector('.gpp-body iframe');"
                                   " return f && f.getAttribute('src') !== src && !document.querySelector('.gpp-loading'); }",
                                   arg=src, timeout=30000)
            nexts.append(1000 * (time.perf_counter() - t))
            page.wait_for_timeout(600)
        out["browser: next row (page pane shown)"] = statistics.median(nexts)
        switches = []
        for rid in ["course-name", "course-description", "stub-name"]:
            head = page.inner_text(".rule-head .rh-title")
            t = time.perf_counter()
            page.click(f"[data-rule='{rid}']")
            page.wait_for_function("(head) => !!document.querySelector('.row.on') &&"
                                   " document.querySelector('.rule-head .rh-title')?.innerText !== head",
                                   arg=head, timeout=30000)
            switches.append(1000 * (time.perf_counter() - t))
        out["browser: switch rule (rows shown)"] = statistics.median(switches)
        b.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".data/root-w4")
    ap.add_argument("--catalog", default="avc")
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--shots", type=Path)
    a = ap.parse_args()

    from golden_datasets.catalogs import resolve
    from golden_datasets.storage import LocalRoot
    from golden_datasets.sync import sync_catalog

    with tempfile.TemporaryDirectory(prefix="bench-review-") as tmp:
        root = Path(tmp) / "root"
        sync_catalog(LocalRoot(str(Path(a.root).resolve())), LocalRoot(str(root)), resolve(a.catalog), None, "link",
                     False, False)
        rows = []
        srv = Server(str(root))
        try:
            cold = measure(srv, a.catalog, RULES[0], 0)
            warm_runs = [measure(srv, a.catalog, rule, k + 1) for k, rule in enumerate(RULES * 2)]
            warm = {k: statistics.median(r[k] for r in warm_runs) for k in BUDGET}
            br = browser_times(srv.base, a.catalog) if a.browser else {}
            if a.shots:
                subprocess.run([sys.executable, str(HERE / "shots_review.py"), "--base", srv.base, "--out", str(a.shots)],
                               check=False)
        finally:
            srv.stop()
        print(f"\nSpec §10 budgets · root {a.root} (synced copy) · catalog {a.catalog} · local disk\n")
        print(f"{'action':38} {'cold ms':>9} {'budget':>8}   {'warm ms':>9} {'budget':>8}")
        ok = True
        for k, (bc, bw) in BUDGET.items():
            c, w = cold[k], warm[k]
            ok &= c <= bc and w <= bw
            rows.append((k, c, bc, w, bw))
            print(f"{k:38} {c:9.1f} {bc:8d} {'✓' if c <= bc else '✗'} {w:9.1f} {bw:8d} {'✓' if w <= bw else '✗'}")
        for k, v in br.items():
            budget = BUDGET["next row (page pane, prefetched)"][0] if "next" in k else BUDGET["switch rule (rows)"][0]
            ok &= v <= budget
            print(f"{k:38} {'':9} {'':8}   {v:9.1f} {budget:8d} {'✓' if v <= budget else '✗'}  (median, end to end)")
        print("\nwarm = median over", len(RULES) * 2, "runs on the same server process (5 rules × 2)")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
