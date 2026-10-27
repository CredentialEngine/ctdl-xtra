"""Time the Claude loop against spec §10: `rule try` (budget ≤ 30 s on WVU, the largest catalog) and the upload of
`rule publish` (budget ≤ 15 s), plus `prompt` and `rule annotations`.

    uv run python bench/bench_loop.py [--from .data/root] [--catalog avc] [--runs 3]
    uv run python bench/bench_loop.py --root azure://https://…/xtra-cli-output/zz-scratch-… --catalog avc --no-copy

By default the source root is copied to a temporary folder (`sync --pages link`), so the publish writes only there.
With `--no-copy --root R` it publishes into R itself: use a scratch root only. The draft is the prototype's
course-description v2 (drop leading Prerequisite / Corequisite lines); for another catalog pass `--rule` and a
`--regex` (group 1) that changes it.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from golden_datasets import extract, loop, rulesets  # noqa: E402
from golden_datasets.check import check_before_write  # noqa: E402
from golden_datasets.cli import main  # noqa: E402
from golden_datasets.context import Ctx  # noqa: E402
from golden_datasets.prompt import build_prompt  # noqa: E402

DESCRIPTION_V2_REGEX = (r"\A\s*(?:(?i:pre-?requisites?|co-?requisites?)\s*:[^\n]*?(?:\.[ \t]+(?=[A-Z(])|\n|\Z)\s*)*"
                        r"(\S[\s\S]*?)\s*\Z")
BUDGET_TRY_S, BUDGET_UPLOAD_S = 30.0, 15.0


def timed(fn):
    t = time.perf_counter()
    out = fn()
    return out, time.perf_counter() - t


def main_(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", default=str(Path(__file__).resolve().parents[1] / ".data" / "root"))
    ap.add_argument("--root", default=None, help="publish into this root (with --no-copy)")
    ap.add_argument("--no-copy", action="store_true")
    ap.add_argument("--catalog", default="avc")
    ap.add_argument("--rule", default="course-description")
    ap.add_argument("--regex", default=DESCRIPTION_V2_REGEX)
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args(argv)

    if args.no_copy:
        if not args.root:
            ap.error("--no-copy needs --root")
        root = args.root
    else:
        root = str(Path(tempfile.mkdtemp(prefix="bench-loop-")) / "root")
        _, t = timed(lambda: main(["sync", "--from", args.src, "--to", root, "-c", args.catalog, "--pages", "link"]))
        print(f"copied {args.src} → {root} ({t:.1f} s)")

    ctx = Ctx(root, args.catalog)
    doc = loop.draft_of(ctx, [args.rule])
    r = doc["rules"][0]
    r["definition"] = {**r["definition"], "regex": args.regex, "group": 1}
    r["examples"] = []

    _, t_prompt = timed(lambda: build_prompt(ctx, args.rule))
    _, t_ann = timed(lambda: loop.rule_annotations(loop.current_review(ctx), args.rule))

    tries = []
    for _ in range(args.runs):
        plan = loop.plan_draft(Ctx(root, args.catalog), json.loads(json.dumps(doc)), warn=lambda m: None)
        ev, t = timed(lambda plan=plan: loop.evaluate(ctx, plan))
        tries.append(t)
    card = ev["cards"][0]
    print(f"\n{loop.scorecard.format_card(card, 'draft')}\n")

    # Publish = the same computation, then rule versions + ruleset version + extraction; time the writes only.
    check_before_write(ctx, {"settings": plan["settings"]}, plan["rules"], ev["result"]["tables"])
    t0 = time.perf_counter()
    rs = rulesets.publish(ctx, plan["rules"], plan["settings"], "bench_loop", "bench_loop")
    t_rules = time.perf_counter() - t0
    ext = extract.next_extraction_id(ctx, rs["version"], again=False)
    extract.write_extraction(ctx, ext, rs["version"], ev["parent_extraction"], ev["result"], "bench_loop")
    t_upload = time.perf_counter() - t0

    pages = ev["result"]["meta"]["pages_total"]
    rerun = ev["result"]["meta"]["rerun_pages"]
    med = statistics.median(tries)
    print(f"root {ctx.root.uri} · {ctx.catalog} · {pages:,} pages ({rerun:,} rerun)")
    print(f"{'action':<34} {'time':>8}  {'budget':>8}  result")
    print(f"{'prompt --rule ' + args.rule:<34} {t_prompt:>7.2f}s  {'—':>8}")
    print(f"{'rule annotations ' + args.rule:<34} {t_ann:>7.2f}s  {'—':>8}")
    print(f"{'rule try (median of ' + str(args.runs) + ')':<34} {med:>7.2f}s  {BUDGET_TRY_S:>7.0f}s  "
          f"{'ok' if med <= BUDGET_TRY_S else 'OVER'}   runs: {', '.join(f'{x:.2f}' for x in tries)}")
    print(f"{'rule publish upload':<34} {t_upload:>7.2f}s  {BUDGET_UPLOAD_S:>7.0f}s  "
          f"{'ok' if t_upload <= BUDGET_UPLOAD_S else 'OVER'}   (rules+ruleset {t_rules:.2f}s, extraction "
          f"{t_upload - t_rules:.2f}s → {ext})")
    print("note: the §10 `rule try` budget is for WVU; scale by pages rerun "
          f"(≈ {med / max(rerun, 1) * 1000:.1f} ms per page here).")
    return 0 if med <= BUDGET_TRY_S and t_upload <= BUDGET_UPLOAD_S else 1


if __name__ == "__main__":
    sys.exit(main_())
