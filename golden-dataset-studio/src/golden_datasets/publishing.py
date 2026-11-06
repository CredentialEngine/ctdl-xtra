"""Publishing with two runs at once (one-rule-runs spec §3.4–§3.6, §4).

- **The publish lock**, `<catalog>/golden-dataset-studio/publish.json`: one publish at a time per catalog, so
  version N+1 is always built from version N. Taken and released with ETags; nothing is deleted (releasing writes
  `{"holder": null}`); a lock older than 10 minutes counts as free. A second publish waits and says for whom.
- **Rebase or refuse** (optimistic concurrency): *mine* = the rules the draft changes compared with its base;
  *theirs* = the rules changed by every version published since. No overlap: mine go on top of the latest version
  and the whole suite reruns. Overlap: refused, nothing written; draft again from the latest and redo the change.
- **Revert** a version: one new version with every rule that version changed back to its previous version.
- **Downstream**: the rules that read a rule, directly or not (the blast radius, for Claude's information).
"""

from __future__ import annotations

import contextlib
import time
from datetime import UTC, datetime, timedelta

from . import layout, model
from .context import Ctx
from .errors import ConflictError, UserError

LOCK_MINUTES = 10


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def lock_path(catalog: str) -> str:
    return f"{layout.catalog_dir(catalog)}/publish.json"


class LockBusy(Exception):
    def __init__(self, holder: dict):
        super().__init__(f"{who(holder)} is publishing")
        self.holder = holder


def who(holder: dict | None) -> str:
    h = holder or {}
    return f"run {h['run']}" if h.get("run") else (h.get("by") or "someone")


@contextlib.contextmanager
def publish_lock(ctx: Ctx, run: str | None, by: str, wait_s: float | None = None, say=print,
                 sleep=time.sleep, clock=_now):
    """Hold the catalog's publish lock for the block. Waits for another holder (saying so every 10 s), up to `wait_s`
    seconds (None = until its lock expires); raises LockBusy after that."""
    root, path = ctx.root, lock_path(ctx.catalog)
    t0 = time.monotonic()
    said = -10.0
    while True:
        st = root.stat(path)
        doc = None
        if st is not None:
            try:
                doc = root.read_json(path)
            except FileNotFoundError:
                st = None
        t = clock()
        held = doc and doc.get("holder") and doc.get("expires_at") and \
            datetime.strptime(doc["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC) > t
        if not held:
            mine = {"holder": {"run": run, "by": by, "since": _iso(t)},
                    "expires_at": _iso(t + timedelta(minutes=LOCK_MINUTES))}
            try:
                etag = root.write_json(path, mine, if_none_match=True) if st is None \
                    else root.write_json(path, mine, if_match=st.etag)
                break
            except ConflictError:
                continue
        waited = time.monotonic() - t0
        if wait_s is not None and waited >= wait_s:
            raise LockBusy(doc["holder"])
        if waited - said >= 10:
            say(f"waiting for {who(doc['holder'])} to finish publishing ({int(waited)} s)")
            said = waited
        sleep(0.5)
    try:
        yield
    finally:
        with contextlib.suppress(ConflictError):  # it expired and someone else took it: theirs now
            root.write_json(path, {"holder": None, "expires_at": None, "released_at": _iso(clock())}, if_match=etag)


# =====================================================================================================
# Rebase or refuse
# =====================================================================================================
def mine(ctx: Ctx, doc: dict, base: int) -> list[str]:
    """The draft's rules whose definition differs from the base version's (or that are new)."""
    _, rules = ctx.ruleset_rules(base)
    out = []
    for item in doc.get("rules", []):
        rid = item.get("rule_id")
        old = rules.get(rid)
        if old is None or "definition" not in item or model.sha(item["definition"]) != old["content_hash"]:
            out.append(rid)
    return sorted(out)


def theirs(ctx: Ctx, base: int, latest: int) -> dict[str, dict]:
    """rule → {version, by} for every rule a version after `base` changed (the latest change wins)."""
    out: dict[str, dict] = {}
    for v in range(base + 1, latest + 1):
        rs = ctx.ruleset(v)
        for rid in rs.get("changed_rules") or []:
            out[rid] = {"version": v, "by": by_words(rs)}
    return out


def by_words(rs: dict) -> str:
    """Who published a version: "Seth Alt's run", or the publisher's name."""
    if rs.get("started_by"):
        return f"{rs['started_by']}'s run"
    return rs.get("published_by") or "someone"


def rebase(ctx: Ctx, doc: dict, names: dict[str, str]) -> tuple[dict, str | None]:
    """The draft to publish on top of the latest version, and the line saying it was rebased (None when it was
    drafted from the latest). Raises UserError naming the overlap; nothing is written then."""
    base, latest = doc.get("base_ruleset"), ctx.latest_ruleset() if ctx.ruleset_versions() else 0
    if not base or not latest or base >= latest:
        return doc, None
    m, t = mine(ctx, doc, base), theirs(ctx, base, latest)
    overlap = [rid for rid in m if rid in t]
    if overlap:
        raise UserError(" ".join(
            f"{names.get(rid, rid)} was also changed in v{t[rid]['version']} by {t[rid]['by']}." for rid in overlap)
            + f" Draft it again from v{latest} (`rule draft`) and redo your change.")
    keep = set(m)
    doc = {**doc, "base_ruleset": latest, "rules": [r for r in doc.get("rules", []) if r.get("rule_id") in keep]}
    meanwhile: dict[str, list[str]] = {}
    for rid, x in t.items():
        meanwhile.setdefault(x["by"], []).append(names.get(rid, rid))
    said = "; ".join(f"{by} published {', '.join(sorted(rs))} meanwhile" for by, rs in meanwhile.items())
    return doc, f"Rebased on v{latest} ({said})"


# =====================================================================================================
# Revert
# =====================================================================================================
def revert_plan(ctx: Ctx, version: int) -> dict:
    """What reverting `version` would publish: {version, parent, next_version, rules: [{rule, from_version,
    to_version}], blocked}. `blocked` names a rule a later version changed again (then nothing can be written)."""
    versions = ctx.ruleset_versions()
    if version not in versions:
        raise FileNotFoundError(f"no ruleset v{version}")
    rs = ctx.ruleset(version)
    parent = rs.get("parent_version")
    if not parent:
        raise UserError(f"v{version} is the first ruleset: there is nothing before it to go back to")
    changed = list(rs.get("changed_rules") or [])
    if not changed:
        raise UserError(f"v{version} changed no rule")
    _, now_rules = ctx.ruleset_rules(version)
    _, before = ctx.ruleset_rules(parent)
    blocked = None
    for v in versions:
        if v > version:
            again = [rid for rid in changed if rid in (ctx.ruleset(v).get("changed_rules") or [])]
            if again:
                from .report import rule_names

                names = rule_names({**before, **now_rules})
                blocked = (f"{' and '.join(names.get(r, r) for r in again)} "
                           f"{'was' if len(again) == 1 else 'were'} changed again in v{v}; revert v{v} first, "
                           "or change it by hand")
                break
    rules = [{"rule": rid, "from_version": (now_rules.get(rid) or {}).get("version"),
              "to_version": (before.get(rid) or {}).get("version")} for rid in sorted(changed)]
    return {"version": version, "parent": parent, "next_version": versions[-1] + 1, "rules": rules,
            "blocked": blocked}


def revert_text(plan: dict, names: dict[str, str]) -> str:
    rules = [names.get(r["rule"], r["rule"]) for r in plan["rules"]]
    listed = rules[0] if len(rules) == 1 else ", ".join(rules[:-1]) + " and " + rules[-1]
    return (f"Revert v{plan['version']}? This publishes v{plan['next_version']} with {listed} back to how "
            f"{'it was' if len(rules) == 1 else 'they were'} in v{plan['parent']}.")


def revert(ctx: Ctx, version: int, by: str, say=print, wait_s: float | None = None) -> dict:
    """Publish one new version with every rule `version` changed back to its previous version. Runs the whole
    suite (and says what moved) but publishes either way: a person chose to go back. Raises UserError when a later
    version changed one of those rules again."""
    from . import extract, rulesets
    from .check import check_before_write
    from .loop import evaluate
    from .report import rule_names

    with publish_lock(ctx, None, by, wait_s=wait_s, say=say):
        ctx.invalidate()
        plan = revert_plan(ctx, version)
        if plan["blocked"]:
            raise UserError(plan["blocked"])
        latest = ctx.latest_ruleset()
        rs_latest, latest_rules = ctx.ruleset_rules(latest)
        _, before = ctx.ruleset_rules(plan["parent"])
        rules = dict(latest_rules)
        for r in plan["rules"]:
            if r["rule"] in before:
                rules[r["rule"]] = before[r["rule"]]
            else:
                rules.pop(r["rule"], None)  # the version added it
        names = rule_names({**latest_rules, **before})
        changed = sorted(rid for rid in set(rules) | set(latest_rules)
                         if rid not in rules or rid not in latest_rules
                         or rules[rid]["content_hash"] != latest_rules[rid]["content_hash"])
        p = {"latest": latest, "ruleset": rs_latest, "base": latest_rules,
             "drafts": {rid: rules[rid] for rid in changed if rid in rules}, "rules": rules,
             "settings": rs_latest["settings"], "changed": changed, "settings_changed": False,
             "example_failures": []}
        ev = evaluate(ctx, p)
        check_before_write(ctx, {"settings": p["settings"]}, rules, ev["result"]["tables"])
        listed = ", ".join(names.get(r["rule"], r["rule"]) for r in plan["rules"])
        doc = rulesets.publish(ctx, rules, p["settings"], f"Revert v{version}: {listed} back to v{plan['parent']}",
                               by, extra={"reverts": version})
        if doc is None:
            raise UserError(f"nothing to revert: the latest version already has v{plan['parent']}'s rules")
        ext = extract.next_extraction_id(ctx, doc["version"], again=False)
        extract.write_extraction(ctx, ext, doc["version"], ev["parent_extraction"], ev["result"], by)
    s = ev["suite"]
    return {"version": doc["version"], "reverted": version, "extraction": ext,
            "rules": [r | {"name": names.get(r["rule"], r["rule"])} for r in plan["rules"]],
            "suite": {k: s[k] for k in ("rules", "golden", "now_right", "got_worse")} | {"line": ev["suite_lines"][0]}}


# =====================================================================================================
# Downstream
# =====================================================================================================
def downstream(rules: dict[str, dict], rule_id: str) -> list[str]:
    """Every rule that reads `rule_id`, directly or through other rules, in display order."""
    readers: dict[str, set[str]] = {}
    for rid, r in rules.items():
        for dep in r.get("depends_on") or model.dependencies(r):
            readers.setdefault(dep, set()).add(rid)
    seen: set[str] = set()
    todo = [rule_id]
    while todo:
        for r in readers.get(todo.pop(), ()):
            if r not in seen and r != rule_id:
                seen.add(r)
                todo.append(r)
    return sorted(seen, key=lambda r: (model.KIND_ORDER[rules[r]["kind"]], r))
