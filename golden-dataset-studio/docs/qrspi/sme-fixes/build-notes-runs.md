# Build notes: AI runs (spec §4)

Branch `sme-fixes-runs`, from `b160a3a`. Scope: [`03-spec.md`](03-spec.md) §4 only.

## What changed

| Behaviour | Where |
|---|---|
| **Not responding.** A `running` run with no line from Claude (any note kind but `studio`) 5 minutes after `sent_at` turns the bar amber: "Claude isn't responding. No update in 5 minutes; it may have stopped." The usual headline moves to the tooltip. Buttons: Watch, **Mark as ended** (the existing end action, now shared with the Watch panel), Cancel. Client-side only, from the poll's server `now` and notes; never shown in `sending`/`waiting`. | `web/src/agent/RunBar.tsx:34-49` (`SILENT_MS`, `isSilent`, `markEnded`), `:83-101` (bar); `web/src/agent/agent.css:29-30` |
| **Prompt rule.** The run header says Claude's first action is a `golden-datasets run note`, as soon as Setup step 1 has installed the CLI and made the run folder (the note needs both), and that 5 minutes of silence tells people it may have stopped. | `src/golden_datasets/prompt.py:233-235`; `tests/test_prompt.py:92` |
| **Watch → report.** When the watched run ends, the same panel becomes "Claude's report": a banner with how it ended and **Compare vN → vN+1** (when a ruleset was published; the same link the bar and Past AI runs already use), the `summary.md` Markdown (fetched with `agentApi.detail`, rendered with the Past AI runs `Markdown`), and "Progress notes (N)" folded in a `<details>`. The footer's *Past AI runs* opens that run's full detail (facts, prompt). | `web/src/agent/RunBar.tsx:51-55` (`CompareLink`), `:119-155` (`WatchPanel`), `:159-190` (`RunReport`); `agent.css:91-100` |
| **Read the report.** An ended run's bar shows "Read the report" where *Details* was, opening the same report view. | `web/src/agent/RunBar.tsx:97-98` |
| **Lock.** `_Recent` holds a `threading.Lock` around get, set and evict. | `src/golden_datasets/review.py:30`, `:66-83` |

Tests:
- `web/src/agent/agent.test.tsx:174` not-responding timer with fake timers (4 min 50 s: normal; polls to 5 min 2 s:
  amber text, no "K2", Mark as ended posts `/end`); `:194` stays quiet with a note or while `waiting`; `:211` Watch
  panel turns into the report when the watched run ends (banner, Compare href, Markdown, folded notes); `:233`
  "Read the report" replaces Details and opens the report.
- `tests/test_recent_lock.py`: 8 threads hammer the cache; a copy without the lock fails (KeyError, sometimes
  "dictionary changed size during iteration"); the locked one never does.

`make check`: ruff clean; pytest 156 passed (52 slow deselected); web typecheck, vitest 181 passed, build OK.

## Seeing it locally (screenshots)

Any local root works; the bar shows runs even when runs on the remote agent are off. Catalog folder names are the
full ones (`avc-elumenapp-com-catalog-2026-27-welcome`, not `avc`). Save this as `fake_run.py` outside the repo:

```python
"""Put a fake running run on a local root: delivered 6 minutes ago, no note from Claude yet.
usage: python fake_run.py <root> <catalog folder> [ruleset_before]"""
import json, sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

root, cat = Path(sys.argv[1]), sys.argv[2]
before = int(sys.argv[3]) if len(sys.argv) > 3 else None
d = root / cat / "golden-dataset-studio" / "agent-runs"
t = datetime.now(UTC)
f = lambda x: x.strftime("%Y-%m-%dT%H:%M:%SZ")
rid = f"{t:%Y%m%dT%H%M%SZ}-demo"
ago = f(t - timedelta(minutes=6))
run = {"run_id": rid, "catalog": cat, "scope": {"kind": "needs_work", "rules": ["course-description"]},
       "started_by": "Jared Diener", "created_at": ago, "updated_at": ago, "deadline": f(t + timedelta(minutes=84)),
       "state": "running", "sent_at": ago, "next_try_at": None,
       "k2": {"url": "https://example.invalid", "agent": "golden-rules", "delivery_id": None},
       "ruleset_before": before, "ruleset_after": None, "outcome": None, "ended_at": None, "ended_by": None,
       "fallback_reason": None}
(d / rid).mkdir(parents=True, exist_ok=True)
(d / "current.json").write_text(json.dumps(run))
(d / rid / "log.jsonl").write_text(json.dumps({"at": ago, "kind": "studio", "text": "Started by Jared Diener",
                                                "by": "Golden Dataset Studio"}) + "\n")
print(rid)
```

Use a scratch copy of the root (this writes `current.json`, which holds the catalog's run lock).

1. **Not responding:** `RID=$(uv run python fake_run.py $GOLDEN_DATASETS_ROOT avc-elumenapp-com-catalog-2026-27-welcome 6)`,
   then `golden-datasets serve` and open the AVC catalog. The bar is amber with *Mark as ended* (within 3 s).
   Change `minutes=6` to `minutes=4` in the script's `ago` to see the normal "no update from Claude yet" bar turn amber a minute later.
2. **A note clears it:** `GOLDEN_DATASETS_CATALOG=avc golden-datasets run note --run $RID "Starting: course-description"`.
3. **Watch → report:** open *Watch*, then end the run with a report:
   `GOLDEN_DATASETS_CATALOG=avc golden-datasets run done --run $RID --summary-file summary.md --outcome "Published ruleset v7: 3 of 5 rules improved"`.
   The panel becomes "Claude's report" on the next poll. The Compare button shows when the root's latest ruleset is
   newer than the `ruleset_before` you gave the script (pass the version below the latest, e.g. latest 7 → `6`).
4. **Read the report:** close the panel (or reload); the ended bar shows *Read the report*, which opens the same view.
   Dismiss the bar with × (remembered per browser in `localStorage` `studio.run.dismissed.<run_id>`).

To reset, delete the catalog's `golden-dataset-studio/agent-runs/` folder in the scratch root.

## Left undone / notes

- Screenshots for `screens/` aren't taken here (a screenshots pass covers every stream).
- Only "no note yet" is detected, as the spec says. A long silence later in a run (the research suggests 15 minutes)
  is not flagged.
- The not-responding check runs on each poll (every 3 s, server time), so it shows up to 3 s late and only while the
  tab is visible, which is when anyone can see it.
- The lock makes `_Recent`'s own operations safe. Callers still do `if k not in cache: cache[k] = build(); return
  cache[k]`; in theory 8 other rules could be added between the set and the get and evict `k` (a KeyError at the
  caller). That needs a `get_or_build` in review.py's callers, outside this stream's diff; not seen in practice.
- The "Past AI runs" detail view (RunsPanel.tsx) is unchanged; the report view reuses its Markdown renderer and
  CSS, and the bar's Compare link.
