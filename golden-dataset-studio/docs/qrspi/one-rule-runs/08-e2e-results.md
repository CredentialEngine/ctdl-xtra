# End-to-end test with real Claude runs: results (2026-11-05)

Three real Claude Code sessions improved AVC rules through K2 host sessions, two at once with one waiting. They were
started from the Studio's own buttons, and the reports were read, checked and acted on in the Studio. The test found
seven bugs. All seven are fixed, with tests, and pushed. Video: [`screens/e2e.mp4`](screens/e2e.mp4) (script:
[`07-e2e-script.md`](07-e2e-script.md)).

## Setup

| | |
|---|---|
| K2 | A separate K2 v0.46.5 daemon on the laptop (the K2 app's own `k2-daemon` binary), with its own home folder `/private/tmp/k2e2e`, listening on `127.0.0.1:7498` only, with no tunnel or federation. Eric's K2 app (`~/.k2`, its own port) and the K2 server were not called or changed. |
| Workspace | `golden-rules` at `/private/tmp/k2e2e/work/golden-rules`, default agent Claude (the built-in preset). |
| Cap | `host_session_cell_cap` 2. |
| Guest policy | The Studio's text from spec §6.3. Each session received it in place of "Prefer read-only work". |
| Key | `studio-e2e`, limited to `golden-rules` and `host-sessions` (redacted). |
| Claude | The real Claude Code 2.1.318, signed in with Eric's login. A wrapper first on the daemon's `PATH` runs it with `HOME` set to Eric's home (the login is in the keychain), `--setting-sources project,local` and `--strict-mcp-config` (so Eric's hooks to the K2 app, his plugins and his MCP servers stay out), plus `skipDangerousModePermissionPrompt`. The workspace folder was marked trusted in `~/.claude.json`, and that entry was removed afterwards. |
| Azure | `golden-datasets.env` in `/private/tmp/k2e2e/work` with the SAS tokens (redacted), and `GOLDEN_DATASETS_GOLDEN_ROOT` set to a local scratch folder. |
| Data | AVC copied server-side from the live root `zz-scratch-review-ui-v3` (read only) to **`xtra-cli-output/zz-scratch-one-rule-runs/`**: the catalog folder (4,250 blobs, 4.1 GB; the annotation log and run logs recreated as append blobs), `golden-dataset-studio/profiles.json`, and `manifest.json` cut down to AVC. |
| Studio | This branch on `127.0.0.1:8770`, with `--k2-max-runs 2`, `GOLDEN_DATASETS_K2_URL=http://127.0.0.1:7498`, `GOLDEN_DATASETS_K2_KEY`, `GOLDEN_DATASETS_K2_WORK=/private/tmp/k2e2e/work` (new, commit `14604f7`) and `GOLDEN_DATASETS_GIT_REF=studio-one-rule-runs`. Each run installed the CLI from the pushed branch on GitHub. |
| Browser | Playwright Chromium at 1440×900, profile "Eric Riddoch". |

A smoke session ("run `pwd`", then killed) checked first that the real Claude starts in the workspace and sees the
Studio's guest policy and `$K2_SESSION_ID`.

## The runs

All three were started from the UI, in the recorded part of the video. Times are UTC on Nov 6 (5:05 PM MST, Nov 5).

| Run | Rules to improve | Started from | Waited | Worked | Outcome | Rulesets |
|---|---|---|---|---|---|---|
| `20261106T000540Z-9f9d` | Credit Value | sidebar ✦ Improve | 6 s | 5 min 51 s | **finished**: "Claude published Credit Value in v11." Also changed Credit Unit Type (it read Credit Value; it now reads the header's units line itself). | v10 → **v11** |
| `20261106T000551Z-4f72` | In Catalog, Subject Webpage | "Improve rules with AI…", 2 ticked | 2 s | 5 min 49 s | **finished**: "Claude published In Catalog in v12." Subject Webpage was held, with one question for people: "Now that In Catalog holds the course page's address, should Subject Webpage be empty for every course in the catalog?" | started on v10, **rebased on v11**, published **v12** |
| `20261106T000600Z-8ab6` | Description | sidebar ✦ Improve | **5 min 42 s in line** | 1 min 26 s | **needs_you**: "2 decisions before Claude can publish Description." (Should the Limitation on Enrollment paragraph be left out? Should the closing line about repeat enrollment be part of it?) ACCT199 and DA107A conflict with values marked correct, so Claude held v3. | none (v12 stays) |

Every check said "All 45 rules against 181 golden values. Nothing that was right got worse." Claude wrote 7 row
comments (2, 2 and 3), each saved on its row with "(v11, AI run Nov 5)", "(v12, …)" and so on. Two runs had a value Claude worked out
(ACCT199's empty Credit Value, and ACCT199's In Catalog address taken from Jared's note).

**Two runs at once, for real.** Runs 1 and 2 worked side by side. Run 2's publish waited on run 1's publish lock
("Publishing: waiting for run 20261106T000540Z-9f9d to finish publishing"), then rebased: "Rebased on v11 (Eric
Riddoch's run published Credit Unit Type, Credit Value meanwhile)". Its report says "Based on v11; started on v10."

**The queue was observed twice.**
- In the Studio, recorded in the video (and in [`screens/e2e-queue.png`](screens/e2e-queue.png)): "Working now: 2 of 2
  places" (both runs), "Waiting: 1st in line, AVC: Description (yours), Starts in about 6 min". The run bar said
  "Your run on Description is 1st in line. It should start in about 6 min.", and the sidebar showed "◷ 1st" by
  Description. It started 5 s after run 2 ended.
- On K2 directly: a third `POST …/host-sessions` while runs 1 and 2 were live got **429 after 30.0 s**,
  `{"code": "workspace-cell-cap", …}`.

The Studio never got a 429 itself, because it counts places first. It killed each session within 4 s of its
`run done` (K2 log: "released concurrent-cell quota slot", "reaped child").

**After the runs, in the UI (recorded):**
- ✕ on Credit Unit Type's ACCT199 row in run 1's report. Claude had said "The value is unchanged." A new tab opened
  on the Rules tab at **v11**, with ACCT199 selected, ✕ open and the page beside it. A note was saved: "E2E test of
  the report's ✕ (not a real verdict)." Back in the report, the row showed the ✕, and the footer showed "1 row has
  new feedback since this run." and ✦ Run again.
- Compare v10 → v11 from the report's band.
- Revert v11 published **v13** ("Revert v11: Credit Value, Credit Unit Type back to v10", `reverts: 11`). A second
  revert of v11 is refused: "Credit Value and Credit Unit Type were changed again in v13".
- ✦ Run again opened the picker with Credit Value ticked. It was cancelled, so no fourth run was started.

## Bugs found and fixed

| Commit | Bug | Fix | Test |
|---|---|---|---|
| `14604f7` | The run prompt's paths (run folder, SAS file) were hard-coded to `/var/lib/k2/work`. | `$GOLDEN_DATASETS_K2_WORK` (default unchanged). | `test_prompt_paths_follow_the_k2_work_folder` |
| `7af3705` | With two runs at once, run 1's record said `ruleset_after: 12` (the latest), so its bar said "published … in ruleset v12" and Compare showed v10 → v12. Run 2's report compared v10 → v12, which showed run 1's change as run 2's. | `ruleset_after` is the run's own last publish. A new field, `ruleset_base`, holds what its first publish was built on. The report's Compare starts there. The web uses `compareOf(run)` and the report's own pair. | 2 pytest tests (another publish after mine; a rebased publish), 2 vitest tests |
| `ffca312` | Revert's confirm was the browser's `window.confirm`, not one of the app's components (spec §1.0). It doesn't show in a recording. | The run button's own `.ac.run-ask` dialog: "Revert v11?", the CLI's sentence, Cancel, Revert v11. | vitest (Cancel posts nothing; confirm posts; no native confirm) |
| `0dbf2f6`, `e49c202` | Compare in a report opened the Compare tab **under** the AI runs drawer. The first fix listened for `hashchange`, but a browser re-renders App inside the same event, so a listener re-subscribed for each new `onClose` was removed before it ran. | The drawer subscribes once and reads `onClose` from a ref. It closes when the tab changes, but not on the Rules tab's own `?row=` changes. | vitest. The second test reproduces the browser's render between listeners with `flushSync`, and it fails on the earlier code. |
| `696fa9a` | With run 1 still waiting for the 5 s loop and 2 places free, the picker said "0 AI runs are working. This one would be 2nd in line, about 1 min." Both runs started at once. | "1 of 2 places is taken, so this one starts now." | pytest |
| `fc12729` | Nothing appeared after Revert. `.toast` had no z-index, so every toast raised inside the drawer (an `.ac-back`, z-index 1000) was hidden behind it: Reverted, Correct, Comment saved. | `z-index: 2000`. | Checked in the browser: over an open report, the toast is the topmost element ([`screens/e2e-toast-after-fix.png`](screens/e2e-toast-after-fix.png)). A unit test wasn't possible because the test setup doesn't load CSS. |

Runs 1 and 2 had ended before `7af3705`. Their `run.json` and report Compare pair on the scratch prefix were rewritten
by a one-off script using that commit's `_versions_after` and Compare rule: run 1 changed from v10 → 12 to v10 → 11,
and run 2 from Compare v10 → v12 to v11 → v12. Nothing else was changed by hand.

## Tests

- `uv run pytest -q`: **209 passed** (52 deselected: slow and Azure). There were 206 before this test, plus 3 new
  tests and 1 new assertion.
- `uv run ruff check src tests bench`: clean.
- `cd web && npm run typecheck && npm test && npm run build`: **250 passed** (246 before; 4 new), build OK.

## The video and screenshots

[`screens/e2e.mp4`](screens/e2e.mp4): H.264, 1440×900, **2 min 1 s, 3.5 MB**. It is cut from four Playwright
recordings with ffmpeg, and each step's number and words are shown as a subtitle bar. Steps 1–3 were recorded while
the runs started, and the queue is live. Steps 4–9 use the finished runs.

| | |
|---|---|
| [`e2e-queue.png`](screens/e2e-queue.png) | Working now: 2 of 2 places, and Description waiting |
| [`e2e-report.png`](screens/e2e-report.png) | Run 1's report: published v11, facts, the value Claude worked out with Claude's comment |
| [`e2e-report-rebased.png`](screens/e2e-report-rebased.png) | Run 2's report: "Based on v11; started on v10.", Compare v11 → v12, a decision |
| [`e2e-reject-new-tab.png`](screens/e2e-reject-new-tab.png) | ✕ from the report: the new tab at v11, ✕ open, the page beside it |
| [`e2e-compare.png`](screens/e2e-compare.png) | Compare v10 → v11 from the report |
| [`e2e-revert.png`](screens/e2e-revert.png) | The Revert v11 dialog |
| [`e2e-run-again.png`](screens/e2e-run-again.png) | "1 row has new feedback since this run.", ✦ Run again |

The video records two of these bugs before they were fixed. At step 2 the dialog shows the old "2nd in line, about
1 min" note (fixed in `696fa9a`). At step 8 no toast follows the revert (fixed in `fc12729`). Step 7 was re-recorded
after `e49c202`.

## What didn't work, or is left

- **The ruleset picker doesn't refresh after a revert in the same page.** It still says "v12 (latest)" until the
  page reloads, then shows v13. This is not fixed.
- **The report still offers "Revert v11" after v11 was reverted.** The confirm then shows a stale sentence, and the
  server refuses. `GET …/revert` already returns `blocked`, but the report doesn't use it. This is not fixed.
- A rule Claude made empty on purpose (Credit Value, `rule_type: none`) shows "no rule yet" in its row card. That is
  the Rules tab's existing wording.
- Run 3's notes say "Inferring BIOL110 value", but its report has no inferred value. That was Claude's choice, not
  checked further.
- In K2's answer for a killed session, `phase` was `never_started` (the transcript had `gone`). The Studio treats
  `live: false` as over, so nothing depends on it.
- Text selection on the page (a drag in the page pane) wasn't recorded. The ✕ was saved with a note.

To clean up later, delete the prefix `xtra-cli-output/zz-scratch-one-rule-runs/`.
