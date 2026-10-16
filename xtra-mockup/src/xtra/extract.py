"""Step 2: extract (specification sections 5 to 8). Reads only the page store. No internet.

For every course it writes one file with three parts: the record (plain CTDL JSON-LD, nothing of
ours mixed in), the provenance (one entry per value, addressed by the value's path), and what was
recognised on the page but left out.
"""

from __future__ import annotations

import json
import re
import shutil
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from . import prereq
from .crawl import INDEX_ADDRESS, REGISTRY_RECORD_ADDRESS, subject_links
from .ctid import CtidService, Ledger, normalise_code
from .document import DisplayDocument, context, load_display_copy, make_display_copy, normalise_text
from .llm import PROMPT_VERSION, make_proposer
from .rules import Hit, Registry, load_registry
from .schema import CONTEXT_ADDRESS, REGISTRY_RESOURCE, SCHEMA_COPY_DATE, Schema
from .store import PageStore

LANG = "en-US"
ACTS_SCHEME_NAME = "Arkansas Course Transfer System (ACTS) Course Index Number"
EDITION_SCHEME_NAME = "Catalog edition"
PLACEHOLDER = "Made here, never published. A placeholder (decision D14)."
POSITION_CHECK = "The text at each recorded position equals the recorded quote."
NOT_PROVEN = "The guards do not prove that “and” and “or” were read correctly outside bracketed groups."

REQUIREMENT_KINDS = [
    # property, rule, label for ceterms:name, task for the language model, slot
    ("ceterms:requires", "description.prerequisite", "Prerequisite", "prerequisite sentence", "requires"),
    ("ceterms:corequisite", "description.corequisite", "Corequisite", "corequisite sentence", "corequisite"),
    ("ceterms:coPrerequisite", "description.pre-or-corequisite", "Pre- or corequisite", "pre-or-corequisite sentence", "coPrerequisite"),
]


class Source:
    """One stored document, ready for rules: its display copy, its text, its facts."""

    def __init__(self, role: str, name: str, fetch, raw: bytes):
        self.role, self.name, self.fetch = role, name, fetch
        self.digest = fetch.digest
        self.address = fetch.final or fetch.requested
        charset = re.search(r"charset=([\w-]+)", fetch.content_type or "", re.I)
        self.raw = raw.decode(charset.group(1) if charset else "utf-8", "replace")
        self.is_html = "html" in (fetch.content_type or "")
        self.doc: DisplayDocument | None = None
        self.display = None
        if self.is_html:
            self.display = make_display_copy(self.raw, self.address)
            self.doc = load_display_copy(self.display)

    def meta(self, current_digest: str | None) -> dict:
        out = {
            "digest": self.digest,
            "role": self.role,
            "name": self.name,
            "kind": "page" if self.is_html else "record",
            "address": self.fetch.requested,
            "finalAddress": self.address,
            "fetchedAt": self.fetch.time,
            "status": self.fetch.status,
            "contentType": self.fetch.content_type,
            "size": self.fetch.size,
            "current": current_digest == self.digest,
            "file": f"documents/{self.digest}.{'html' if self.is_html else 'json'}",
        }
        if self.doc:
            title = self.doc.soup.title.get_text() if self.doc.soup.title else ""
            out.update(title=title, textLength=len(self.doc.text), textSha256=self.doc.text_sha256)
        return out


class Entries:
    """The provenance of one course: one entry per value, by path."""

    def __init__(self) -> None:
        self.by_path: dict[str, dict] = {}

    def add(
        self,
        path: str,
        slot: str,
        method: str,
        produced_by: str,
        how: str,
        evidence: list[dict],
        checks: list[dict] | None = None,
        flags: list[dict] | None = None,
        confidence: tuple[str, str] | None = None,
        **more,
    ) -> dict:
        for n, item in enumerate(evidence, start=1):
            item["n"] = n
        checks = list(checks or [])
        if any(e.get("segments") for e in evidence):
            checks.append({"text": POSITION_CHECK, "status": "pass"})
        flags = list(flags or [])
        entry = {
            "slot": slot,
            "method": method,
            "producedBy": produced_by,
            "how": how,
            "evidence": evidence,
            "checks": checks,
            "flags": flags,
            **{k: v for k, v in more.items() if v is not None},
        }
        level, why = confidence or _confidence(entry)
        entry["confidence"] = {"level": level, "why": why}
        flag_ids = {f["id"] for f in flags}
        entry["judgement"] = bool(
            method == "language model"
            or any(c["status"] == "fail" for c in checks)
            or flag_ids & {"partly-structured", "loses-detail", "language-model"}
        )
        self.by_path[path] = entry
        return entry


def _confidence(entry: dict) -> tuple[str, str]:
    """Low, medium or high. A rule of thumb about how the value was produced, not a measurement."""
    flag_ids = {f["id"] for f in entry["flags"]}
    if any(c["status"] == "fail" for c in entry["checks"]):
        return "low", "A check on this value did not pass."
    if entry["method"] == "language model":
        return "low", "A language model proposed it, and no person has confirmed it."
    if "partly-structured" in flag_ids:
        return "low", "Only part of the sentence could be written as structure."
    if "loses-detail" in flag_ids:
        return "medium", "The mapping is sound but loses detail that the page gives."
    if "sentence-only" in flag_ids:
        return "medium", "The sentence is an exact copy, but its structure could not be read."
    if entry["method"] == "table":
        return "medium", "A table mapped the page's wording to a CTDL value; the table has not been reviewed by a person."
    if entry["method"] == "minted":
        return "medium", "Nothing on the page was read. The identifier was made here and is a placeholder."
    if entry["method"] == "lookup":
        return "medium", "Looked up in an outside record, and supported by the page."
    if entry["method"] == "fixed":
        return "high", "A design decision, the same for every course."
    return "high", "Read by a rule from one place on the page, and every check passed."


# ------------------------------------------------------------------------------------- evidence


def seg(source: Source, start: int, end: int) -> dict:
    text = source.doc.text
    before, after = context(text, start, end)
    return {"start": start, "end": end, "quote": text[start:end], "before": before, "after": after}


def ev_text(source: Source, segments: list[dict], role: str, says: str, rule: str | None = None) -> dict:
    return {"kind": "text", "document": source.digest, "role": role, "says": says, "rule": rule, "segments": segments}


def ev_hit(source: Source, hit: Hit, role: str, says: str | None = None, group: str | None = None) -> dict:
    start, end = hit.spans[group] if group else (hit.start, hit.end)
    return {**ev_text(source, [seg(source, start, end)], role, says or hit.says(), hit.rule.name), "matched": matched(source, hit)}


def matched(source: Source, hit: Hit) -> dict:
    """Everything the rule's pattern matched, and each named part of it, so the viewer can show the rule at work."""
    return {
        "start": hit.match_start,
        "end": hit.match_end,
        "text": source.doc.text[hit.match_start : hit.match_end],
        "parts": [{"name": name, "start": s, "end": e} for name, (s, e) in hit.spans.items()],
    }


def ev_markup(source: Source, hit: Hit, role: str) -> dict:
    return {
        "kind": "markup",
        "document": source.digest,
        "role": role,
        "says": hit.says(),
        "rule": hit.rule.name,
        "element": hit.rule.extra.get("element"),
        "attribute": hit.rule.extra.get("attribute"),
        "source": {"start": hit.start, "end": hit.end, "quote": hit.quote, "of": "the stored HTML source"},
    }


def ev_record(source: Source, role: str, says: str, fields: list[dict]) -> dict:
    return {
        "kind": "record",
        "document": source.digest,
        "role": role,
        "says": says,
        "address": source.address,
        "readAt": source.fetch.time,
        "fields": fields,
    }


def ev_derived(role: str, says: str, start_from: str, step: str, result: str, table: str | None = None) -> dict:
    return {"kind": "derived", "role": role, "says": says, "from": start_from, "step": step, "result": result, "table": table}


def ev_address(source: Source, role: str, says: str) -> dict:
    return {"kind": "address", "document": source.digest, "role": role, "says": says, "address": source.address}


def ev_none(says: str) -> dict:
    return {"kind": "none", "role": "no source", "says": says}


def text_map(value: str) -> dict:
    return {LANG: value}


# ----------------------------------------------------------------------------------- one course


class CourseBuilder:
    def __init__(self, run: "Run", subject_source: Source, block: dict):
        self.run = run
        self.src = subject_source
        self.block = block
        self.code = block["code"]
        self.record: dict = {}
        self.entries = Entries()
        self.left_out: list[dict] = []
        self.references: dict[str, dict] = {}
        self.requirement_summary = "none"

    # --- helpers ----------------------------------------------------------------------------

    def rule(self, name: str, scope: str) -> list[Hit]:
        start, end = self.block[scope]
        return self.run.rules.rule(name).apply(self.src.doc.text[start:end], start, self.code)

    def uri_for(self, code: str) -> str:
        ctid = self.run.ctids.ctid_for(self.run.org_ctid, code)
        uri = REGISTRY_RESOURCE + ctid
        has_record = normalise_code(code) in self.run.known_codes
        self.references[uri] = {"code": normalise_code(code), "hasRecord": has_record}
        if not has_record:
            self.run.referenced_only.add(normalise_code(code))
        return uri

    def reference_flags(self, uris: list[str]) -> list[dict]:
        missing = [self.references[u]["code"] for u in uris if not self.references[u]["hasRecord"]]
        if not missing:
            return []
        return [{"id": "referenced-no-record", "text": "Referenced, no record yet (outside the crawled subjects): " + ", ".join(dict.fromkeys(missing)) + "."}]

    def class_choice(self, path: str, slot: str, chip: str | None = None) -> None:
        self.entries.add(
            f"{path}/@type", slot, "fixed", "the schema",
            "Nothing was read. The schema allows only this class here.",
            [ev_none("A choice of class. Nothing was read from the page.")],
            choiceOnly=True, chip=chip,
        )

    def alignment_entries(self, path: str, scheme: str, concept: str, evidence_factory, method: str, produced_by: str, how: str, flags=None, checks=None) -> None:
        member = {"text": f"{concept} is a member of the {self.run.schema.label(scheme)} list.", "status": "pass" if concept in self.run.schema.concepts(scheme) else "fail"}
        self.class_choice(path, "CredentialAlignmentObject")
        self.entries.add(
            f"{path}/ceterms:targetNode", "targetNode", method, produced_by, how, evidence_factory(),
            checks=[member] + list(checks or []), flags=flags, concept=concept, scheme=scheme,
        )

    # --- the fields -------------------------------------------------------------------------

    def build(self) -> None:
        self.fixed_and_minted()
        self.title_line()
        self.description()
        self.credit()
        self.acts()
        self.requirements()
        self.offer_frequency()
        self.similar()
        self.language()
        self.life_cycle()
        self.owner()
        self.addresses()
        self.edition()
        self.recognised_but_left_out()
        order = [
            "@context", "@id", "@type", "ceterms:ctid", "ceterms:name", "ceterms:codedNotation", "ceterms:description",
            "ceterms:creditValue", "ceterms:identifier", "ceterms:requires", "ceterms:prerequisite", "ceterms:corequisite",
            "ceterms:coPrerequisite", "ceterms:offerFrequencyType", "ceterms:isSimilarTo", "ceterms:inLanguage",
            "ceterms:lifeCycleStatusType", "ceterms:ownedBy", "ceterms:offeredBy", "ceterms:subjectWebpage",
            "ceterms:inCatalog", "ceterms:versionIdentifier",
        ]
        self.record = {k: self.record[k] for k in order if k in self.record}

    def fixed_and_minted(self) -> None:
        ctid = self.run.ctids.ctid_for(self.run.org_ctid, self.code)
        self.ctid = ctid
        self.record["@context"] = CONTEXT_ADDRESS
        self.record["@id"] = REGISTRY_RESOURCE + ctid
        self.record["@type"] = "ceterms:Course"
        self.record["ceterms:ctid"] = ctid
        self.entries.add(
            "/@context", "context", "fixed", "decision", "Fixed by design: the same for every CTDL record.",
            [ev_none("Nothing was read. Every CTDL record names the same context.")], choiceOnly=True,
        )
        placeholder = [{"id": "placeholder", "text": PLACEHOLDER}]
        inputs = f"Made by the CTID service from two inputs: the organisation ({self.run.org_ctid}) and the course code ({self.code})."
        self.entries.add(
            "/@id", "id", "minted", "the CTID service",
            "The Registry's address form, followed by this course's CTID.",
            [ev_none("There is no source. " + inputs)], flags=placeholder,
            checks=[{"text": "The address ends with the record's CTID.", "status": "pass"}],
        )
        self.entries.add(
            "/@type", "Course", "fixed", "decision D1", "Fixed by design: every catalog entry is a course.",
            [ev_none("Nothing was read. Every entry in this catalog is written as a Course (decision D1).")], choiceOnly=True,
        )
        self.entries.add(
            "/ceterms:ctid", "ctid", "minted", "the CTID service",
            "Minted once and remembered in the ledger; running again returns the same one.",
            [ev_none("There is no source. " + inputs)], flags=placeholder,
            checks=[{"text": "It has the form “ce-” plus a UUID.", "status": "pass"}, {"text": "The ledger holds it under this organisation and course code.", "status": "pass"}],
        )

    def title_line(self) -> None:
        self.rule("title-line.form", "title")
        for hit in self.rule("title-line.name", "title")[:1]:
            self.record["ceterms:name"] = text_map(normalise_text(hit.quote))
            self.entries.add("/ceterms:name", "name", "rule", hit.rule.name, "A rule read it.", [ev_hit(self.src, hit, "the name")])
        for hit in self.rule("title-line.code", "title")[:1]:
            self.record["ceterms:codedNotation"] = normalise_text(hit.quote)
            note = "The page writes the code with a non-breaking space; the record uses an ordinary space." if " " in hit.quote else None
            self.entries.add("/ceterms:codedNotation", "codedNotation", "rule", hit.rule.name, "A rule read it.", [ev_hit(self.src, hit, "the code")], normalised=note)

    def description(self) -> None:
        for hit in self.rule("description.whole", "desc")[:1]:
            value = normalise_text(hit.quote)
            self.record["ceterms:description"] = text_map(value)
            note = "Line breaks, repeated spaces and non-breaking spaces on the page became single spaces." if value != hit.quote else None
            self.entries.add("/ceterms:description", "description", "rule", hit.rule.name, "A rule read it.", [ev_hit(self.src, hit, "the paragraph")], normalised=note)

    def credit(self) -> None:
        hits = self.rule("title-line.credit", "title")
        if not hits:
            return
        hit = hits[0]
        unit_hit, index = self.run.unit_hit, self.run.index
        low, high = int(hit.groups["min"]), hit.groups.get("max")
        scheme, concept = "ceterms:CreditUnit", "creditUnit:SemesterHour"
        profile: dict = {"@type": "ceterms:ValueProfile"}
        number = self.block["number"]
        if high:
            profile["schema:minValue"], profile["schema:maxValue"] = low, int(high)
            amount = f"{low}–{int(high)}"
            cross = {"text": f"The course number {number} ends in V (variable credit) and the title line gives a range.", "status": "pass" if number.endswith("V") else "fail"}
        else:
            profile["schema:value"] = low
            amount = str(low)
            cross = {"text": f"The course number {number} ends in {number[-1]} and the title line says {hit.quote.strip()}", "status": "pass" if number[-1] == str(low) else "fail"}
        unit_ok = unit_hit is not None
        if unit_ok:
            profile["ceterms:creditUnitType"] = [self.run.schema.alignment(scheme, concept)]
        self.record["ceterms:creditValue"] = [profile]
        base = "/ceterms:creditValue"
        unit_label = self.run.schema.label(concept)

        def number_ev():
            return ev_hit(self.src, hit, "gives the number")

        def unit_ev():
            return ev_hit(index, unit_hit, "gives the unit")

        evidence = [number_ev()] + ([unit_ev()] if unit_ok else [])
        self.entries.add(
            base, "creditValue", "rule", f"{hit.rule.name}" + (f", {unit_hit.rule.name}" if unit_ok else ""),
            "Rules read both." if unit_ok else "A rule read it.", evidence, checks=[cross],
            chip=f"{amount} · {unit_label}" if unit_ok else amount,
        )
        self.class_choice(f"{base}/0", "ValueProfile")
        if high:
            self.entries.add(f"{base}/0/schema:minValue", "minValue", "rule", hit.rule.name, "A rule read it.", [ev_hit(self.src, hit, "the smaller number", group="min")], checks=[cross])
            self.entries.add(f"{base}/0/schema:maxValue", "maxValue", "rule", hit.rule.name, "A rule read it.", [ev_hit(self.src, hit, "the larger number", group="max")], checks=[cross])
        else:
            self.entries.add(f"{base}/0/schema:value", "value", "rule", hit.rule.name, "A rule read it.", [ev_hit(self.src, hit, "the number", group="min")], checks=[cross])
        if unit_ok:
            self.entries.add(f"{base}/0/ceterms:creditUnitType", "creditUnitType", "rule", unit_hit.rule.name, "A rule read it, on the index page.", [unit_ev()], chip=unit_label, concept=concept, scheme=scheme)
            self.alignment_entries(f"{base}/0/ceterms:creditUnitType/0", scheme, concept, lambda: [unit_ev()], "rule", unit_hit.rule.name, "A rule read it, on the index page.")

    def acts(self) -> None:
        hits = self.rule("title-line.acts", "title")
        if not hits:
            return
        hit = hits[0]
        code = normalise_text(hit.quote)
        self.record["ceterms:identifier"] = [
            {"@type": "ceterms:IdentifierValue", "ceterms:identifierTypeName": text_map(ACTS_SCHEME_NAME), "ceterms:identifierValueCode": code}
        ]
        base = "/ceterms:identifier"
        self.entries.add(base, "identifier", "rule", hit.rule.name, "A rule read it.", [ev_hit(self.src, hit, "the transfer number")], chip=f"ACTS · {code}")
        self.class_choice(f"{base}/0", "IdentifierValue")
        self.entries.add(
            f"{base}/0/ceterms:identifierTypeName", "identifierTypeName", "fixed", "decision",
            "Fixed wording, the same for every course with a transfer tag.",
            [ev_none("The scheme's name is ours. The page says only “ACTS”.")],
        )
        self.entries.add(f"{base}/0/ceterms:identifierValueCode", "identifierValueCode", "rule", hit.rule.name, "A rule read it.", [ev_hit(self.src, hit, "the transfer number")])

    # --- prerequisites, corequisites, pre-or-corequisites (section 7) ----------------------------

    def requirements(self) -> None:
        built = []
        for prop, rule_name, label, task, slot in REQUIREMENT_KINDS:
            hits = self.rule(rule_name, "desc")
            if hits:
                built.append(self.requirement(prop, hits, label, task, slot))
        if built:
            rank = {"language model": 3, "nobody": 2, "parser": 1}
            self.requirement_summary = max((b for group in built for b in group), key=lambda b: rank[b])

    def requirement(self, prop: str, hits: list[Hit], label: str, task: str, slot: str) -> list[str]:
        text = self.src.doc.text
        schema = self.run.schema
        profiles, structures, builders = [], [], []
        sentence_segments, link_segments, condition_segments = [], [], []
        all_uris: list[str] = []
        checks: list[dict] = []
        flags: list[dict] = []
        inner: list[tuple] = []
        plain_lists: list[list[prereq.Node]] = []

        for i, hit in enumerate(hits):
            start, end = hit.start, hit.end
            sentence = text[start:end]
            links = [l for l in self.block["links"] if l.start >= start and l.end <= end]
            tree = prereq.parse(sentence, start, links, self.run.rules.phrases)
            guards = prereq.run_guards(tree, {}, sentence, start, links) if tree else []
            builder, proposal, discarded = "nobody", None, None
            if tree and all(g.passed for g in guards):
                builder = "parser"
            else:
                tree = None
                proposal = self.run.proposer.propose(
                    task, sentence.replace(" ", " "), [l.code for l in links], self.run.definitions
                )
                if proposal is not None:
                    candidate, problems = prereq.tree_from_proposal(proposal.structure, sentence, start, links)
                    guards = prereq.run_guards(candidate, problems, sentence, start, links)
                    if all(g.passed for g in guards):
                        tree, builder = candidate, "language model"
                    else:
                        discarded = {"structure": proposal.structure, "argument": proposal.argument}
            builders.append(builder)
            self.run.count_requirement(prop, builder, guards, proposal is not None)

            mapped = prereq.to_condition_profile(tree, self.uri_for, lambda n: normalise_text(text[n.start : n.end]))
            profile = {
                "@type": "ceterms:ConditionProfile",
                "ceterms:name": text_map(label),
                "ceterms:description": text_map(normalise_text(sentence)),
                **{k: v for k, v in mapped.profile.items() if k != "@type"},
            }
            profiles.append(profile)
            base = f"/{prop}/{i}"
            landed = {id(p.node): p for p in mapped.placements}
            uris = [self.uri_for(l.code) for l in links]
            all_uris += uris

            def node_json(node: prereq.Node) -> dict:
                out = {"kind": node.kind, "start": node.start, "end": node.end, "quote": text[node.start : node.end]}
                if node.kind == prereq.COURSE:
                    uri = self.uri_for(node.code)
                    out.update(code=node.code, uri=uri, hasRecord=self.references[uri]["hasRecord"])
                place = landed.get(id(node))
                if place:
                    out["landed"] = {"path": base + place.path, "how": place.how}
                if node.children:
                    out["children"] = [node_json(c) for c in node.children]
                return out

            who = {"parser": "the parser", "language model": f"the language model {self.run.proposer.name}", "nobody": "nobody"}[builder]
            structure = {
                "sentence": seg(self.src, start, end),
                "builtBy": builder,
                "tree": node_json(tree) if tree else None,
                "guards": [g.to_json() for g in guards],
                "partlyStructured": mapped.partly_structured,
                "summary": prereq.describe(tree),
            }
            if proposal is not None:
                structure["languageModel"] = {"name": proposal.model, "promptVersion": proposal.prompt_version, "argument": proposal.argument}
            if discarded:
                structure["discarded"] = discarded
            structures.append(structure)

            sentence_segments.append(seg(self.src, start, end))
            link_segments += [seg(self.src, l.start, l.end) for l in links]
            if tree:
                condition_segments += [seg(self.src, n.start, n.end) for n in tree.leaves() if n.kind == prereq.TEXT]

            if builder == "language model":
                flags.append({"id": "language-model", "text": "The structure is the language model's reading. No person has confirmed it."})
                checks += [g.to_json() for g in guards] + [{"text": NOT_PROVEN, "status": "note"}]
            elif builder == "parser":
                checks += [g.to_json() for g in guards]
            elif proposal is not None:
                failed = [g for g in guards if not g.passed]
                flags.append({"id": "sentence-only", "text": "The language model's reading did not pass the guards and was discarded. The record carries the sentence and the links only."})
                checks += [{**g.to_json(), "text": g.text + " (The discarded proposal failed this.)"} for g in failed]
            else:
                flags.append({"id": "sentence-only", "text": "The parser declined this sentence and no language model was available. The record carries the sentence only."})
            if mapped.partly_structured:
                flags.append({"id": "partly-structured", "text": "Partly structured: one profile holds one set of choices, so part of this sentence is kept as text in ceterms:condition. The complete structure is shown below."})

            method = "language model" if builder == "language model" else "rule"
            by = self.run.proposer.name if builder == "language model" else "the prerequisite parser"
            how = f"Read by {who}."
            inner.append((f"{base}", "ConditionProfile", None))
            inner.append((f"{base}/ceterms:name", "conditionName", ("fixed", "decision", f"Fixed wording for sentences labelled “{label}”.", [ev_none("Nothing was read. It repeats the label that introduced the sentence.")], None)))
            inner.append((f"{base}/ceterms:description", "conditionDescription", ("rule", hit.rule.name, "A rule read it.", [{**ev_text(self.src, [seg(self.src, start, end)], "the sentence", hit.says(), hit.rule.name), "matched": matched(self.src, hit)}], None)))
            kept = [{"id": "partly-structured", "text": "Kept as text: CTDL could not carry this part of the structure exactly."}]
            for place in mapped.placements:
                node, path = place.node, base + place.path
                segment = [seg(self.src, node.start, node.end)]
                words = normalise_text(text[node.start : node.end])
                if place.how == "course":
                    uri = self.uri_for(node.code)
                    inner.append((path, "targetLearningOpportunity", (method, by, how, [ev_text(self.src, segment, "the course link", f"“{node.code}” is a link in the sentence.")], self.reference_flags([uri]), node.code)))
                elif place.how == "condition":
                    inner.append((path, "condition", (method, by, how, [ev_text(self.src, segment, "the condition", f"“{words}” in the sentence.")], None)))
                elif place.how == "kept as text":
                    inner.append((path, "condition", (method, by, how, [ev_text(self.src, segment, "kept as text", f"“{words}” in the sentence.")], kept)))
                elif place.how == "alternatives":
                    inner.append((path, "alternativeCondition", (method, by, how, [ev_text(self.src, segment, "the choices", f"“{words}” in the sentence.")], None, f"any one of {len(node.children)}")))
                elif place.how == "choice":
                    inner.append((path, "ConditionProfile", (method, by, how, [ev_text(self.src, segment, "one choice", f"“{words}” in the sentence.")], None, node.code or prereq.describe(node))))
            if prop == "ceterms:requires" and builder == "parser" and prereq.is_plain_list_of_courses(tree):
                plain_lists.append(tree.courses())

        self.record[prop] = profiles
        any_lm = "language model" in builders
        evidence = [ev_text(self.src, sentence_segments, "the sentence", "The sentence, kept word for word.", hits[0].rule.name)]
        if link_segments:
            n = len(link_segments)
            evidence.append(ev_text(self.src, link_segments, "the course links", f"The {n} course link{'s' if n != 1 else ''} in it."))
        if condition_segments:
            n = len(condition_segments)
            evidence.append(ev_text(self.src, condition_segments, "other conditions", f"{n} condition{'s' if n != 1 else ''} that {'are' if n != 1 else 'is'} not {'courses' if n != 1 else 'a course'}."))
        how = "Rules read both." if link_segments else "A rule read it."
        summary = structures[0]["summary"] if len(structures) == 1 else f"{len(structures)} sentences"
        self.entries.add(
            f"/{prop}", slot, "language model" if any_lm else "rule",
            f"{hits[0].rule.name}; structure by " + ", ".join(dict.fromkeys(builders)),
            how, evidence, checks=checks, flags=flags + self.reference_flags(all_uris),
            chip=f"{label} · {summary}", structure=structures,
            unstable=schema.unstable(prop) or None,
        )
        for path, inner_slot, spec in inner:
            if spec is None:
                self.class_choice(path, inner_slot)
                continue
            method, by, how, ev, fl, *chip = spec
            self.entries.add(path, inner_slot, method, by, how, ev, flags=fl, chip=chip[0] if chip else None)

        if plain_lists:
            courses = [c for group in plain_lists for c in group]
            uris = [self.uri_for(c.code) for c in courses]
            self.record["ceterms:prerequisite"] = uris
            segments = [seg(self.src, c.start, c.end) for c in courses]
            proven = {"text": "The parser read the whole sentence as a plain list of courses: no “or”, no grade, no other condition.", "status": "pass"}
            self.entries.add(
                "/ceterms:prerequisite", "prerequisite", "rule", "the prerequisite parser", "A rule read it.",
                [ev_text(self.src, segments, "the course links", f"The {len(segments)} course link{'s' if len(segments) != 1 else ''} in the prerequisite sentence.")],
                checks=[proven], flags=self.reference_flags(uris),
                chip=", ".join(c.code for c in courses) if len(courses) <= 2 else f"{len(courses)} courses",
            )
            for j, c in enumerate(courses):
                self.entries.add(
                    f"/ceterms:prerequisite/{j}", "prerequisite", "rule", "the prerequisite parser", "A rule read it.",
                    [ev_text(self.src, [segments[j]], "the course link", f"“{c.code}” is a link in the prerequisite sentence.")],
                    checks=[proven], flags=self.reference_flags([uris[j]]), chip=c.code,
                )
        return builders

    def offer_frequency(self) -> None:
        hits = self.rule("description.typically-offered", "desc")
        if not hits:
            return
        hit = hits[0]
        wording = normalise_text(hit.quote)
        table = self.run.rules.tables["offer-frequency"]
        row = table.look_up(wording, self.code)
        if row is None or not row["concept"]:
            reason = row["because"] if row else "The wording is not in the offer-frequency table, so no value was chosen. Omit, never invent."
            self.left_out.append({"what": f"Typically offered: {wording}", "reason": reason, "rule": hit.rule.name, "segment": seg(self.src, hit.start, hit.end), "document": self.src.digest})
            self.run.count_left_out("offer-frequency: no fitting value" if row else "offer-frequency: wording not in table", reason, self.code, wording)
            return
        scheme, concept = table.scheme, row["concept"]
        label = self.run.schema.label(concept)
        self.record["ceterms:offerFrequencyType"] = [self.run.schema.alignment(scheme, concept)]
        flags = []
        if row.get("loses"):
            flags.append({"id": "loses-detail", "text": f"Loses detail: {row['loses']}. The wording is still in the description."})
        checks = [{"text": "This row of the table has been reviewed by a person." if row.get("reviewed_by_a_person") else "This row of the table has not yet been reviewed by a person.", "status": "pass" if row.get("reviewed_by_a_person") else "note"}]

        def evidence():
            return [
                ev_hit(self.src, hit, "the wording"),
                ev_derived("the table row", f"The offer-frequency table maps that wording to {label}.", f"“{wording}”", row["because"], f"{label} ({concept})", "offer-frequency"),
            ]

        base = "/ceterms:offerFrequencyType"
        self.entries.add(
            base, "offerFrequencyType", "table", f"{hit.rule.name}, then the offer-frequency table",
            "A rule found the wording; a table mapped it.", evidence(), checks=checks, flags=flags,
            chip=label, concept=concept, scheme=scheme, unstable=True,
        )
        self.alignment_entries(f"{base}/0", scheme, concept, evidence, "table", "the offer-frequency table", "A rule found the wording; a table mapped it.", flags=flags, checks=checks)

    def similar(self) -> None:
        uris, items, phrases = [], [], []
        for rule_name, word in (("description.cross-listed", "cross-listed with"), ("description.equivalent", "equivalent to")):
            for hit in self.rule(rule_name, "desc"):
                links = [l for l in self.block["links"] if l.start >= hit.start and l.end <= hit.end]
                phrases.append(seg(self.src, hit.match_start, hit.match_end))
                for link in links:
                    items.append((link, word, hit))
                    uris.append(self.uri_for(link.code))
        if not uris:
            return
        self.record["ceterms:isSimilarTo"] = uris
        codes = [l.code for l, _, _ in items]
        self.entries.add(
            "/ceterms:isSimilarTo", "isSimilarTo", "rule", ", ".join(dict.fromkeys(h.rule.name for _, _, h in items)), "Rules read both.",
            [
                ev_text(self.src, phrases, "the sentence", "The page says this course is " + " and ".join(dict.fromkeys(w for _, w, _ in items)) + " another."),
                ev_text(self.src, [seg(self.src, l.start, l.end) for l, _, _ in items], "the course links", f"The course link{'s' if len(items) != 1 else ''} in that sentence."),
            ],
            flags=self.reference_flags(uris), chip=", ".join(codes) if len(codes) <= 2 else f"{len(codes)} courses",
        )
        for j, (link, word, hit) in enumerate(items):
            self.entries.add(
                f"/ceterms:isSimilarTo/{j}", "isSimilarTo", "rule", hit.rule.name, "A rule read it.",
                [ev_text(self.src, [seg(self.src, link.start, link.end)], "the course link", f"“{link.code}” is the course this one is {word}.")],
                flags=self.reference_flags([uris[j]]), chip=link.code,
            )

    def language(self) -> None:
        hit = self.run.page_hits[self.src.digest].get("page.language")
        if not hit:
            return
        self.run.rules.rule("page.language").matched.append(self.code)
        self.record["ceterms:inLanguage"] = [hit.quote.split("-")[0].lower()]
        self.entries.add(
            "/ceterms:inLanguage", "inLanguage", "rule", hit.rule.name, "A rule read it, from the page's markup.",
            [ev_markup(self.src, hit, "the page's declared language")],
            confidence=("high", "Read by a rule from the page's own markup."),
        )

    def life_cycle(self) -> None:
        edition = self.run.page_hits[self.src.digest].get("page.edition")
        approved = self.run.approved_hit
        if not (edition and approved):
            return
        scheme, concept = "ceterms:LifeCycleStatus", "lifeCycle:Active"
        self.record["ceterms:lifeCycleStatusType"] = self.run.schema.alignment(scheme, concept)

        def evidence():
            return [
                ev_hit(self.src, edition, "the current edition", "“{}” labels this page: it is in the current catalog.".format(normalise_text(edition.quote))),
                ev_hit(self.run.index, approved, "approved for offering", "The index page calls the listing “all courses approved for offering”."),
            ]

        why = ("medium", "The page does not state a status. Active is inferred from two pieces of wording.")
        how = "Rules read both; that they add up to Active is a design decision."
        base = "/ceterms:lifeCycleStatusType"
        self.entries.add(base, "lifeCycleStatusType", "rule", f"{edition.rule.name}, {approved.rule.name}", how, evidence(), chip=self.run.schema.label(concept), concept=concept, scheme=scheme, confidence=why, unstable=True)
        self.alignment_entries(base, scheme, concept, evidence, "rule", f"{edition.rule.name}, {approved.rule.name}", how)

    def owner(self) -> None:
        org, registry = self.run.org, self.run.registry
        title = self.run.page_hits[self.src.digest].get("page.title-organisation")
        approved = self.run.approved_hit
        name = org["ceterms:name"][LANG] if isinstance(org.get("ceterms:name"), dict) else str(org.get("ceterms:name"))
        fields = [
            {"path": "ceterms:name", "value": name},
            {"path": "ceterms:ctid", "value": org.get("ceterms:ctid")},
            {"path": "@type", "value": org.get("@type")},
            {"path": "@id", "value": org.get("@id")},
        ]
        for prop, slot, verb in (("ceterms:ownedBy", "ownedBy", "owns"), ("ceterms:offeredBy", "offeredBy", "offers")):
            evidence = [ev_record(registry, "the organisation's Registry record", f"The Registry already holds a record for “{name}”. Its address is the value.", fields)]
            if approved:
                evidence.append(ev_hit(self.run.index, approved, "names the institution", "The index page says the courses are “approved for offering by the University of Arkansas”.", group="organisation"))
            if title:
                evidence.append(ev_markup(self.src, title, "names the institution"))
                if prop == "ceterms:ownedBy":
                    title.rule.matched.append(self.code)
            self.record[prop] = [org["@id"]]
            self.entries.add(
                f"/{prop}", slot, "lookup", "the stored Registry record",
                "Looked up in the stored Registry record; supported by the page.", evidence, chip=name,
                checks=[{"text": "The Registry record is of type ceterms:CredentialOrganization.", "status": "pass" if org.get("@type") == "ceterms:CredentialOrganization" else "fail"}],
            )

    def addresses(self) -> None:
        self.record["ceterms:subjectWebpage"] = self.src.address
        self.entries.add(
            "/ceterms:subjectWebpage", "subjectWebpage", "lookup", "the page store's sidecar",
            "Taken from the stored page's own record of where it was fetched from.",
            [ev_address(self.src, "the page's address", "It is the address this subject page was fetched from.")],
            confidence=("high", "It is the address of the page the course was read from."),
        )
        index = self.run.index
        self.record["ceterms:inCatalog"] = index.address
        self.entries.add(
            "/ceterms:inCatalog", "inCatalog", "lookup", "the crawl's starting point",
            "Taken from the crawl's starting point.",
            [ev_address(index, "the index page's address", "It is the address of the index page, where the crawl started.")],
            confidence=("medium", "The address is certain; whether this page is the right “catalog” for the field is a judgement."), unstable=True,
        )

    def edition(self) -> None:
        hit = self.run.page_hits[self.src.digest].get("page.edition")
        if not hit:
            return
        self.run.rules.rule("page.edition").matched.append(self.code)
        value = hit.groups["edition"]
        self.record["ceterms:versionIdentifier"] = [
            {"@type": "ceterms:IdentifierValue", "ceterms:identifierTypeName": text_map(EDITION_SCHEME_NAME), "ceterms:identifierValueCode": value}
        ]
        base = "/ceterms:versionIdentifier"
        says = f"“{normalise_text(hit.quote)}” labels this page of the catalog."
        self.entries.add(base, "versionIdentifier", "rule", hit.rule.name, "A rule read it.", [ev_hit(self.src, hit, "the edition", says, group="edition")], chip=f"{EDITION_SCHEME_NAME} · {value}")
        self.class_choice(f"{base}/0", "IdentifierValue")
        self.entries.add(f"{base}/0/ceterms:identifierTypeName", "identifierTypeName", "fixed", "decision", "Fixed wording, the same for every course.", [ev_none("The scheme's name is ours. Nothing was read.")])
        self.entries.add(f"{base}/0/ceterms:identifierValueCode", "identifierValueCode", "rule", hit.rule.name, "A rule read it.", [ev_hit(self.src, hit, "the edition", says, group="edition")])

    def recognised_but_left_out(self) -> None:
        for name in ("left-out.repeatable", "left-out.no-double-credit", "left-out.contact-hours"):
            for hit in self.rule(name, "desc"):
                reason = hit.rule.extra["left_out_reason"]
                self.left_out.append({"what": normalise_text(hit.quote), "reason": reason, "rule": name, "segment": seg(self.src, hit.start, hit.end), "document": self.src.digest})
                self.run.count_left_out(name, reason, self.code, normalise_text(hit.quote))
        for hit in self.rule("left-out.level", "title"):
            reason = hit.rule.extra["left_out_reason"]
            self.left_out.append({"what": f"Course level, suggested by the first digit of the number ({hit.quote})", "reason": reason, "rule": hit.rule.name, "segment": seg(self.src, hit.start, hit.end), "document": self.src.digest})
            self.run.count_left_out(hit.rule.name, reason, self.code, hit.quote)
        rule = self.run.rules.rule("unrecognised-label")
        start, end = self.block["desc"]
        for hit in rule.find_all(self.src.doc.text[start:end], start):
            label = normalise_text(hit.quote)
            if label not in rule.extra["recognised"]:
                self.run.unrecognised.setdefault(label, []).append(self.code)


# ------------------------------------------------------------------------------------- the run


class Run:
    def __init__(self, data: Path, rules_dir: Path, reference_dir: Path, language_model: str):
        self.data = Path(data)
        self.store = PageStore(self.data / "store")
        self.rules: Registry = load_registry(Path(rules_dir) / "rules.toml")
        self.teaching = tomllib.loads((Path(rules_dir) / "teaching.toml").read_text(encoding="utf-8"))
        self.schema = Schema(reference_dir)
        self.ledger = Ledger(self.data / "ledger" / "ctid-ledger.jsonl")
        self.ctids = CtidService(self.ledger)
        self.proposer = make_proposer(language_model, self.data / "llm-cache")
        self.definitions = {
            "ceterms:requires": self.schema.definition("ceterms:requires"),
            "ceterms:ConditionProfile": self.schema.definition("ceterms:ConditionProfile"),
            "ceterms:alternativeCondition": self.schema.definition("ceterms:alternativeCondition"),
            "ceterms:targetLearningOpportunity": self.schema.definition("ceterms:targetLearningOpportunity"),
        }
        self.sources: dict[str, Source] = {}
        self.page_hits: dict[str, dict[str, Hit]] = {}
        self.known_codes: set[str] = set()
        self.referenced_only: set[str] = set()
        self.unrecognised: dict[str, list[str]] = {}
        self.left_out_counts: dict[str, dict] = {}
        self.requirement_counts: dict[str, dict] = {}
        self.guard_failures: dict[str, int] = {}
        self.problems: list[str] = []

    def count_left_out(self, key: str, reason: str, code: str, example: str) -> None:
        row = self.left_out_counts.setdefault(key, {"what": key, "reason": reason, "count": 0, "courses": [], "examples": []})
        row["count"] += 1
        row["courses"].append(code)
        if example not in row["examples"] and len(row["examples"]) < 6:
            row["examples"].append(example)

    def count_requirement(self, prop: str, builder: str, guards, asked_model: bool) -> None:
        row = self.requirement_counts.setdefault(prop, {"sentences": 0, "parser": 0, "language model": 0, "nobody": 0, "askedLanguageModel": 0})
        row["sentences"] += 1
        row[builder] += 1
        row["askedLanguageModel"] += int(asked_model)
        if builder == "nobody":
            for g in guards:
                if not g.passed:
                    self.guard_failures[g.id] = self.guard_failures.get(g.id, 0) + 1

    def load(self, role: str, name: str, address: str) -> Source | None:
        fetch = self.store.current(address)
        if fetch is None:
            self.problems.append(f"not in the page store: {address} (run `xtra crawl` first)")
            return None
        source = Source(role, name, fetch, self.store.read(fetch.digest))
        self.sources[source.digest] = source
        return source

    def page_facts(self, source: Source) -> None:
        hits: dict[str, Hit] = {}
        for name in ("page.language", "page.title-organisation"):
            found = self.rules.rule(name).find_all(source.raw)
            if found:
                hits[name] = found[0]
            else:
                self.rules.rule(name).not_matched.append(source.name)
        found = self.rules.rule("page.edition").find_all(source.doc.text)
        if found:
            hits["page.edition"] = found[0]
        else:
            self.rules.rule("page.edition").not_matched.append(source.name)
        self.page_hits[source.digest] = hits


def course_blocks(source: Source, subject: str) -> list[dict]:
    doc = source.doc
    blocks = []
    code_rule = re.compile(r"^\s*([A-Z]{3,4})\s(\S+?)\.")
    for i, div in enumerate(doc.soup.select("div.courseblock"), start=1):
        title = div.select_one("p.courseblocktitle")
        desc = div.select_one("p.courseblockdesc")
        if title is None or desc is None:
            continue
        title_text = doc.element_text(title)
        m = code_rule.match(title_text)
        code = normalise_code(f"{m.group(1)} {m.group(2)}") if m else f"{subject} block {i}"
        links = []
        for a in desc.select("a.bubblelink.code"):
            start, end = doc.span(a)
            links.append(prereq.Link(start, end, normalise_code(doc.text[start:end])))
        blocks.append(
            {
                "code": code,
                "number": m.group(2) if m else "",
                "subject": subject,
                "ordinal": i,
                "block": doc.span(div),
                "title": doc.span(title),
                "desc": doc.span(desc),
                "links": links,
            }
        )
    return blocks


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _leaf_paths(value, path=""):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _leaf_paths(v, f"{path}/{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _leaf_paths(v, f"{path}/{i}")
    else:
        yield path


def _covered(path: str, entries: dict) -> bool:
    while path:
        if path in entries:
            return True
        path = path.rsplit("/", 1)[0]
    return False


def run_extract(data: Path, rules_dir: Path, reference_dir: Path, subjects: tuple[str, ...], language_model: str) -> int:
    run = Run(data, rules_dir, reference_dir, language_model)
    out = Path(data) / "out"

    index = run.load("index", "Index page", INDEX_ADDRESS)
    registry = run.load("registry", "Registry record", REGISTRY_RECORD_ADDRESS)
    if index is None or registry is None:
        print("\n".join(run.problems))
        return 1
    run.index, run.registry = index, registry
    run.org = json.loads(registry.raw)
    run.org_ctid = run.org["ceterms:ctid"]
    unit = run.rules.rule("catalog.credit-unit").find_all(index.doc.text)
    approved = run.rules.rule("catalog.approved-for-offering").find_all(index.doc.text)
    run.unit_hit = unit[0] if unit else None
    run.approved_hit = approved[0] if approved else None

    links = subject_links(run.store.read(index.digest), index.address)
    pages: list[tuple[Source, list[dict]]] = []
    for subject in subjects:
        address = links.get(subject)
        source = run.load("subject", "Subject page", address) if address else None
        if source is None:
            run.problems.append(f"no stored page for subject {subject}")
            continue
        run.page_facts(source)
        blocks = course_blocks(source, subject)
        pages.append((source, blocks))
        for block in blocks:  # pass 1: every course gets its CTID, in page order
            run.known_codes.add(block["code"])
            run.ctids.ctid_for(run.org_ctid, block["code"])
    for name, hit in (("catalog.credit-unit", run.unit_hit), ("catalog.approved-for-offering", run.approved_hit)):
        (run.rules.rule(name).matched if hit else run.rules.rule(name).not_matched).append("Index page")

    if (out / "courses").exists():
        shutil.rmtree(out / "courses")
    courses_index = []
    conformance_failures = []
    unstable_terms: set[str] = set()
    missing_provenance = []
    segments = mismatches = 0

    for source, blocks in pages:  # pass 2: build
        for block in blocks:
            builder = CourseBuilder(run, source, block)
            builder.build()
            record, entries = builder.record, builder.entries.by_path
            checks, unstable = run.schema.check(record, run.ledger.knows)
            unstable_terms.update(unstable)
            for check in checks:
                if check["status"] == "fail":
                    conformance_failures.append({"course": block["code"], "check": check["id"], "detail": check["detail"]})
            for path in _leaf_paths(record):
                if not _covered(path, entries):  # EX3: a value without provenance is a defect
                    missing_provenance.append(f"{block['code']} {path}")
            for entry in entries.values():
                for item in entry["evidence"]:
                    doc = run.sources[item["document"]].doc if item.get("document") else None
                    for s in item.get("segments", []):
                        segments += 1
                        if doc.text[s["start"] : s["end"]] != s["quote"]:
                            mismatches += 1
            course_id = block["code"].replace(" ", "-")
            used = {item["document"] for e in entries.values() for item in e["evidence"] if item.get("document")}
            documents = [s.digest for s in (source, index, registry) if s.digest in used]
            name = record.get("ceterms:name", {}).get(LANG, "")
            stops = [p for p in entries if p.count("/") == 1]
            _write(
                out / "courses" / f"{course_id}.json",
                {
                    "id": course_id,
                    "code": block["code"],
                    "subject": block["subject"],
                    "ordinal": block["ordinal"],
                    "documents": documents,
                    "block": {"document": source.digest, "start": block["block"][0], "end": block["block"][1]},
                    "record": record,
                    "provenance": entries,
                    "leftOut": builder.left_out,
                    "references": builder.references,
                    "conformance": checks,
                    "unstableTerms": unstable,
                },
            )
            credit = entries.get("/ceterms:creditValue", {}).get("chip", "")
            courses_index.append(
                {
                    "id": course_id,
                    "code": block["code"],
                    "name": name,
                    "uri": record["@id"],
                    "subject": block["subject"],
                    "credit": credit.split(" · ")[0] if credit else "",
                    "requirements": builder.requirement_summary,
                    "flags": sorted({f["id"] for p in stops for f in entries[p]["flags"]}),
                    "checksFailed": sum(1 for c in checks if c["status"] == "fail") + sum(1 for p in stops for c in entries[p]["checks"] if c["status"] == "fail"),
                    "stops": len(stops),
                    "judgementCalls": sum(1 for p in stops if entries[p]["judgement"]),
                    "lowConfidence": sum(1 for p in stops if entries[p]["confidence"]["level"] == "low"),
                }
            )

    # --- documents, teaching notes, rules, report ---------------------------------------------
    for source in run.sources.values():
        target = out / "documents" / f"{source.digest}.{'html' if source.is_html else 'json'}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.display if source.is_html else source.raw, encoding="utf-8")
    _write(out / "documents.json", {s.digest: s.meta(getattr(run.store.current(s.fetch.requested), "digest", None)) for s in run.sources.values()})

    slots = {}
    scheme_names = set()
    for slot_id, slot in run.teaching["slot"].items():
        entry = {k: v for k, v in slot.items() if k != "alternative"}
        entry["alternatives"] = slot.get("alternative", [])
        if "term" in slot:
            entry["ctdl"] = run.schema.describe(slot["term"])
            if entry["ctdl"].get("scheme"):
                scheme_names.add(entry["ctdl"]["scheme"])
        if "options" in slot:
            scheme_names.add(slot["options"])
        slots[slot_id] = entry
    _write(
        out / "teaching.json",
        {
            "schemaCopyDate": SCHEMA_COPY_DATE,
            "slots": slots,
            "schemes": {s: run.schema.describe_scheme(s) for s in sorted(scheme_names)},
            "glossary": run.teaching.get("glossary", []),
        },
    )

    rule_rows = []
    for rule in run.rules.rules.values():
        misses = rule.not_matched if rule.expect == "every course" else [m["where"] for m in rule.near_misses]
        rule_rows.append(
            {
                **rule.to_json(),
                "matched": len(rule.matched),
                "notMatched": len(rule.not_matched),
                "misses": misses,
                "nearMisses": rule.near_misses,
            }
        )
    table_rows = [
        {**t.to_json(), "matched": t.matched, "notMatched": [{"wording": w, "courses": c} for w, c in t.not_matched.items()]}
        for t in run.rules.tables.values()
    ]
    _write(out / "forms.json", run.schema.forms())
    _write(out / "rules.json", {"rules": [r.to_json() for r in run.rules.rules.values()], "tables": [t.to_json() for t in run.rules.tables.values()], "phrases": [{"text": p.text, "role": p.role} for p in run.rules.phrases]})
    _write(out / "courses.json", courses_index)

    per_subject: dict[str, int] = {}
    for c in courses_index:
        per_subject[c["subject"]] = per_subject.get(c["subject"], 0) + 1
    proposer = run.proposer
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "subjects": list(subjects),
        "courses": {"total": len(courses_index), "bySubject": per_subject},
        "rules": rule_rows,
        "tables": table_rows,
        "leftOut": list(run.left_out_counts.values()),
        "unrecognisedLabels": [{"label": k, "count": len(v), "courses": v} for k, v in sorted(run.unrecognised.items(), key=lambda kv: -len(kv[1]))],
        "requirements": {"byProperty": run.requirement_counts, "guardFailuresAmongDiscarded": run.guard_failures},
        "languageModel": {
            "name": proposer.name,
            "promptVersion": PROMPT_VERSION,
            "calls": getattr(proposer, "calls", 0),
            "answersFromCache": getattr(proposer, "cache_hits", 0),
            "errors": getattr(proposer, "errors", [])[:20],
        },
        "conformance": {"failures": conformance_failures, "unstableTermsUsed": sorted(unstable_terms)},
        "provenance": {"valuesWithoutAnEntry": missing_provenance, "textSegments": segments, "segmentsWhoseTextDoesNotMatch": mismatches},
        "ctids": {"inLedger": len(run.ledger.entries()), "referencedWithNoRecordYet": sorted(run.referenced_only)},
        "schemaCopyDate": SCHEMA_COPY_DATE,
        "problems": run.problems,
    }
    _write(out / "run-report.json", report)

    print(f"courses: {len(courses_index)}  " + "  ".join(f"{k} {v}" for k, v in per_subject.items()))
    for prop, row in run.requirement_counts.items():
        print(f"  {prop}: {row['sentences']} sentences · parser {row['parser']} · language model {row['language model']} · sentence only {row['nobody']}")
    print(f"  language model {proposer.name}: {report['languageModel']['calls']} calls, {report['languageModel']['answersFromCache']} from cache, {len(getattr(proposer, 'errors', []))} errors")
    print(f"  conformance failures: {len(conformance_failures)}   values without provenance: {len(missing_provenance)}   segment mismatches: {mismatches} of {segments}")
    for rule in rule_rows:
        if rule["expect"] == "every course" and rule["notMatched"]:
            print(f"  rule {rule['name']} did not match: {rule['misses'][:8]}")
    for problem in run.problems:
        print(f"  PROBLEM: {problem}")
    return 1 if (missing_provenance or mismatches or run.problems) else 0
