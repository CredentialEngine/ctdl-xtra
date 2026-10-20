"""Downloads: golden sample, labels, flagged items, and the feedback document for Claude."""

from __future__ import annotations

from collections import defaultdict

from bs4 import BeautifulSoup

from .runs import ROOT_ID, CrawlRun, split_page
from .store import Store
from .template import ConfigMissing, load_template
from .views import ExtractionView


def _flag_marks(flags: dict | None, key: str) -> dict:
    """``flagged`` / ``flag_note`` for an item that has an open flag, else nothing."""
    flag = (flags or {}).get(key)
    return {"flagged": True, "flag_note": flag["note"]} if flag else {}


def property_terms(store: Store) -> dict[str, str | None]:
    """Canonical property name -> CTDL term (``ceterms:codedNotation``), from the field
    template published in the storage root."""
    try:
        return {p.name: p.term for p in load_template(store)}
    except ConfigMissing:
        return {}


def golden_for_page(
    view: ExtractionView,
    decisions: dict,
    stem: str,
    review_id: str,
    flags: dict | None = None,
    terms: dict[str, str | None] | None = None,
) -> list[dict]:
    """The page's records with the reviewer's decisions applied.

    Same shape as the extracted-value format. A field the reviewer rejected
    without supplying a correction is left out (and counted in ``unresolved``)
    rather than exported as if it were right. Items flagged for an expert carry
    ``flagged``/``flag_note``; a flag never changes ``review_status``. Every field has a
    ``ctdl_property``: the rule's, else the field template's term for that property (a
    value the reviewer added has no rule, so it always comes from the template).
    ``terms`` can be passed in to avoid re-reading the template for each page.
    """
    terms = property_terms(view.store) if terms is None else terms
    page = view.page(stem)
    records = []
    for record in page["records"]:
        fields, unresolved = [], 0
        for f in record["fields"]:
            decision = decisions.get(f["field_id"])
            out = {k: v for k, v in f.items() if k != "field_id"}
            out["ctdl_property"] = out.get("ctdl_property") or terms.get(
                f["canonical_label"]
            )
            out.update(_flag_marks(flags, f["field_id"]))
            if decision is None:
                out["review_status"] = "pending"
            elif decision["status"] == "accepted":
                out["review_status"] = "accepted"
            elif decision["status"] == "rejected":
                expected = decision.get("expected_value")
                if expected:
                    out.update(
                        value=expected, presence="present", review_status="corrected"
                    )
                elif "should_be_absent" in decision.get("reasons", []):
                    out.update(value=None, presence="absent", review_status="corrected")
                else:
                    unresolved += 1
                    continue
            fields.append(out)
        for decision in decisions.values():
            if (
                decision["status"] == "missing"
                and decision["kind"] == "field"
                and decision.get("record_id") == record["record_id"]
                and decision["source_url"] == page["url"]
            ):
                fields.append(
                    {
                        "canonical_label": decision["canonical_label"],
                        "ctdl_property": terms.get(decision["canonical_label"]),
                        "value": decision["expected_value"],
                        "presence": "present",
                        "rule_id": None,
                        "source_url": page["url"],
                        "review_status": "added",
                        **_flag_marks(flags, decision["key"]),
                    }
                )
        records.append(
            {
                "record_id": record["record_id"],
                "catalogue_type": "COURSES",
                "entity_type": "Course",
                "source_expected": {"fields": fields},
                "verification": {
                    "status": "reviewed",
                    "review_id": review_id,
                    "unresolved_fields": unresolved,
                    **{
                        f"page_{k}": v
                        for k, v in _flag_marks(flags, f"page::{stem}").items()
                    },
                },
            }
        )
    return records


def labels_for_page(
    view: ExtractionView, decisions: dict, stem: str, flags: dict | None = None
) -> list[dict]:
    """Labels that apply to the page after review: rejected ones dropped, added ones kept."""
    page = view.page(stem)
    labels = []
    for entry in page["labels"]:
        decision = decisions.get(entry["key"])
        if decision and decision["status"] == "rejected":
            continue
        labels.append(
            {
                "label": entry["label"],
                "source_url": page["url"],
                "rule_id": entry["rule_id"],
                "review_status": decision["status"] if decision else "pending",
                **_flag_marks(flags, entry["key"]),
            }
        )
    for decision in decisions.values():
        if (
            decision["kind"] == "label"
            and decision["status"] == "missing"
            and decision["source_url"] == page["url"]
        ):
            labels.append(
                {
                    "label": decision["expected_value"],
                    "source_url": page["url"],
                    "rule_id": None,
                    "review_status": "added",
                    **_flag_marks(flags, decision["key"]),
                }
            )
    return labels


def _extracted_value(view: ExtractionView, flag: dict) -> str | None:
    """What the rules extracted for a flagged field, for the expert's context."""
    if flag["scope"] != "field" or not flag.get("record_id"):
        return None
    try:
        for f in view.record(flag["record_id"])["source_expected"]["fields"]:
            if f["field_id"] == flag["target"]:
                return f["value"]
    except FileNotFoundError:
        pass
    return None


def flagged_sections(
    view: ExtractionView, flags: dict, level: str = "###"
) -> list[str]:
    """Markdown lines listing every open flag, grouped by page (page flag first)."""
    by_stem: dict[str, list[dict]] = defaultdict(list)
    for flag in flags.values():
        by_stem[flag["stem"]].append(flag)
    lines: list[str] = []
    for stem in sorted(by_stem, key=lambda s: view.pages.get(s, {}).get("url", s)):
        row = view.pages.get(stem, {})
        title = row.get("title") or stem
        group = by_stem[stem]
        page_flag = next((f for f in group if f["scope"] == "page"), None)
        lines += [f"{level} {title}", "", f"- page: {group[0]['source_url']}"]
        if page_flag:
            lines.append(
                f"- **whole page flagged** by {page_flag['author']}"
                + (f": {page_flag['note']}" if page_flag["note"] else "")
            )
        for flag in group:
            if flag["scope"] == "page":
                continue
            what = flag.get("canonical_label") or flag["target"]
            where = f" · record {flag['record_id']}" if flag.get("record_id") else ""
            kind = "label" if flag["scope"] == "label" else "property"
            lines.append(
                f"- **{what}** ({kind}{where}) flagged by {flag['author']}"
                + (f": {flag['note']}" if flag["note"] else "")
            )
            value = _extracted_value(view, flag)
            if value is not None:
                lines.append(f"  - extracted: `{value}`")
        lines.append("")
    return lines


def flagged_markdown(
    view: ExtractionView, flags: dict, run: CrawlRun, review_id: str
) -> str:
    """A standalone document of open flags, to forward to subject matter experts."""
    pages = {f["stem"] for f in flags.values()}
    items = sum(f["scope"] != "page" for f in flags.values())
    out = [
        f"# Flagged for review: {run.catalog_folder}",
        "",
        f"Review `{review_id}`: {len(pages)} page(s), {items} flagged item(s).",
        "These are questions the reviewer could not answer alone.",
        "",
    ]
    return "\n".join(
        out + (flagged_sections(view, flags) or ["Nothing is flagged.", ""])
    )


def _excerpt(
    store: Store,
    run: CrawlRun,
    cache: dict,
    stem: str,
    path: str | None,
    content_root: str,
) -> str:
    if not path:
        return ""
    if stem not in cache:
        main, _ = split_page(
            store.read_text(f"{run.key}/pages/{stem}.html"), content_root
        )
        cache[stem] = (
            BeautifulSoup(f'<div id="{ROOT_ID}">{main}</div>', "lxml") if main else None
        )
    soup = cache[stem]
    element = soup.select_one(path) if soup else None
    text = str(element) if element is not None else ""
    return text if len(text) <= 500 else text[:500] + " …"


def feedback_markdown(
    store: Store,
    run: CrawlRun,
    view: ExtractionView,
    state: dict,
    stem_of_url: dict[str, str],
) -> str:
    decisions, notes, counts = state["decisions"], state["notes"], state["counts"]
    ruleset, report = view.ruleset(), view.report()
    rules = {r["rule_id"]: r for r in ruleset["field_rules"] + ruleset["label_rules"]}
    cache: dict = {}

    problems: dict[str | None, list[dict]] = defaultdict(list)
    for key, d in decisions.items():
        if d["status"] in ("rejected", "missing"):
            problems[d.get("rule_id")].append({**d, "key": key})
    field_notes = defaultdict(list)
    for n in notes:
        if n["scope"] == "field":
            field_notes[n["target"]].append(n)

    def locate(d: dict) -> str | None:
        if d["kind"] != "field" or not d.get("record_id"):
            return None
        try:
            for f in view.record(d["record_id"])["source_expected"]["fields"]:
                if f["field_id"] == d["key"]:
                    return (f.get("location") or {}).get("css_path")
        except FileNotFoundError:
            pass
        return None

    out = [
        f"# Review feedback: {run.catalog_folder}",
        "",
        (
            f"- review `{state['session']['review_id']}` of extraction "
            f"`{view.extraction_id}` "
            f"(ruleset `{ruleset['ruleset_id']}` v{ruleset['version']})"
        ),
        (
            f"- {counts['accepted']} accepted, {counts['rejected']} rejected, "
            f"{counts['missing']} missed, {counts['pending']} not yet reviewed "
            f"of {counts['total']} items"
        ),
        "- the loop ends when every item is accepted",
        "",
    ]
    flags = state.get("flags", {})
    if flags:
        out.insert(
            -2,
            f"- {counts['flagged_pages']} page(s) and {counts['flagged_items']} item(s) "
            "flagged for an expert (not rule bugs; see below)",
        )
    general = [n for n in notes if n["scope"] == "general"]
    if general:
        out += ["## General notes", ""]
        out += [f"- ({n['author']}) {n['text']}" for n in general]
        out.append("")
    if flags:
        out += [
            "## Flagged for review (waiting on subject matter experts)",
            "",
            "The reviewer could not judge these. Do not change rules for them unless a",
            "note says what is wrong; they are still undecided.",
            "",
        ]
        out += flagged_sections(view, flags)
    property_notes = [n for n in notes if n["scope"] == "property"]
    if property_notes:
        out += ["## Notes on a property (apply to every rule for it)", ""]
        out += [
            f"- **{n['target']}** ({n['author']}): {n['text']}" for n in property_notes
        ]
        out.append("")

    out += ["## Problems, grouped by rule", ""]
    if not problems:
        out += ["Nothing rejected or missed.", ""]
    for rule_id, items in sorted(problems.items(), key=lambda kv: str(kv[0])):
        if rule_id is None:
            out += ["### No rule found these (missed)", ""]
        else:
            rule = rules.get(rule_id, {})
            out += [
                f"### `{rule_id}`: {rule.get('canonical_label') or rule.get('label', '')}",
                "",
            ]
            if rule:
                props = rule.get("properties") or {
                    k: rule[k]
                    for k in ("url_regex", "requires_selector", "forbids_selector")
                    if k in rule
                }
                out += [f"current: `{props}`", ""]
            for n in notes:
                if n["scope"] == "rule" and n["target"] == rule_id:
                    out.append(f"- rule note ({n['author']}): {n['text']}")
            out.append("")
        for d in items:
            stem = stem_of_url.get(d["source_url"], "")
            out.append(
                f"- **{d['canonical_label']}** on {d['source_url']}"
                + (f" (record {d['record_id']})" if d.get("record_id") else "")
                + f" [{d['status']}"
                + (f": {', '.join(d['reasons'])}" if d.get("reasons") else "")
                + "]"
            )
            if d["status"] == "rejected":
                out.append(f"  - extracted: `{d.get('value')}`")
            if d.get("expected_value"):
                out.append(f"  - expected: `{d['expected_value']}`")
            for n in field_notes.get(d["key"], []):
                out.append(f"  - note ({n['author']}): {n['text']}")
            excerpt = _excerpt(
                store, run, cache, stem, locate(d), ruleset["content_root"]
            )
            if excerpt:
                out.append(f"  - html: `{excerpt}`")
        out.append("")

    other = [n for n in notes if n["scope"] == "rule" and n["target"] not in problems]
    if other:
        out += ["## Notes on rules with no rejected values", ""]
        for n in other:
            rule = rules.get(n["target"], {})
            out.append(
                f"- `{n['target']}` ({rule.get('canonical_label') or rule.get('label', '')}), "
                f"{n['author']}: {n['text']}"
            )
        out.append("")

    regression = report.get("regression", {})
    if regression.get("regressions"):
        out += ["## Regressions in the extraction under review", ""]
        out += [
            f"- `{r['key']}`: was `{r['was']}`, now `{r['now']}`"
            for r in regression["regressions"]
        ]
        out.append("")
    return "\n".join(out)
