"""Bench: open Compare (spec §10, "Open Compare (two extractions)": ≤ 2 s cold server, ≤ 300 ms warm).

Starts a fresh `golden-datasets serve` process on a local root (empty caches), times the first
`GET /api/catalogs/<c>/compare` (cold), then repeats it (warm) and switches the rule filter. Read-only.

    uv run python bench/bench_compare.py [--root .data/root-demo] [--catalog avc] [--runs 3] [--warm 20]
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
BUDGET_COLD, BUDGET_WARM = 2.0, 0.300


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(url: str) -> tuple[float, dict, int]:
    t0 = time.perf_counter()
    with urllib.request.urlopen(url, timeout=60) as r:
        body = r.read()
    return time.perf_counter() - t0, json.loads(body), len(body)


def wait_up(base: str, proc: subprocess.Popen, timeout: float = 30) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if proc.poll() is not None:
            raise SystemExit(f"server exited: {proc.stderr.read().decode() if proc.stderr else ''}")
        try:
            urllib.request.urlopen(base + "/api/catalogs", timeout=1).read()
            return
        except OSError:
            time.sleep(0.05)
    raise SystemExit("server did not start")


def one_run(root: str, catalog: str, warm_n: int) -> dict:
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(["uv", "run", "golden-datasets", "serve", "--root", root, "--port", str(port)],
                            cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=os.environ.copy())
    try:
        wait_up(base, proc)
        url = f"{base}/api/catalogs/{catalog}/compare"
        cold, d, size = get(url)
        warm = [get(url)[0] for _ in range(warm_n)]
        rules = [r["rule_id"] for r in d["changed_rules"]]
        rule_warm = [get(f"{url}?rule={r}")[0] for r in rules for _ in range(3)]
        return {"cold": cold, "server_cold_ms": d["elapsed_ms"], "warm": warm, "rule_warm": rule_warm, "size": size,
                "summary": f"v{d['a']} → v{d['b']}: {d['records_changed']} records changed · {d['totals']}"}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(HERE / ".data" / "root-demo"))
    ap.add_argument("--catalog", default="avc")
    ap.add_argument("--runs", type=int, default=3, help="fresh server processes (cold opens)")
    ap.add_argument("--warm", type=int, default=20, help="warm opens per process")
    args = ap.parse_args()

    runs = [one_run(args.root, args.catalog, args.warm) for _ in range(args.runs)]
    cold = [r["cold"] for r in runs]
    warm = [w for r in runs for w in r["warm"]]
    rule_warm = [w for r in runs for w in r["rule_warm"]]

    def line(name: str, xs: list[float], budget: float) -> str:
        worst = max(xs)
        ok = "ok" if worst <= budget else "OVER BUDGET"
        return (f"  {name:<28} median {1000 * statistics.median(xs):7.1f} ms   max {1000 * worst:7.1f} ms   "
                f"budget {1000 * budget:5.0f} ms   {ok}")

    print(f"Open Compare · {args.catalog} · root {args.root} · {args.runs} cold servers × {args.warm} warm opens")
    print(f"  {runs[0]['summary']}   response {runs[0]['size'] / 1024:.0f} KB")
    print(line("cold (new server process)", cold, BUDGET_COLD))
    print(f"  {'':<28} server-side cold: {', '.join(f'{r['server_cold_ms']:.0f} ms' for r in runs)}")
    print(line("warm", warm, BUDGET_WARM))
    if rule_warm:
        print(line("warm, one rule selected", rule_warm, BUDGET_WARM))
    return 0 if max(cold) <= BUDGET_COLD and max(warm + rule_warm) <= BUDGET_WARM else 1


if __name__ == "__main__":
    sys.exit(main())
