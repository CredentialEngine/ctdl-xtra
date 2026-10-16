"""The CTDL schema copy, and the conformance checks V1 to V8 written against it (section 5.5).

The copy in reference/ctdl/ is a list of terms, not a ready-made validator, so the checks are ours.
Every definition the viewer shows is read from this copy, word for word (WH2, risk R1).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .ctid import CTID_FORM

CONTEXT_ADDRESS = "https://credreg.net/ctdl/schema/context/json"
SCHEMA_COPY_DATE = "2026-06-07"  # the Internet Archive capture date (research section 2)
REGISTRY_RESOURCE = "https://credentialengineregistry.org/resources/"

REQUIRED = ["ceterms:name", "ceterms:description", "ceterms:ctid", "ceterms:inLanguage", "ceterms:lifeCycleStatusType"]
REQUIRED_ONE_OF = ["ceterms:ownedBy", "ceterms:offeredBy"]

_LANGUAGE_TAG = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
_ADDRESS = re.compile(r"^https?://\S+$")
_CURIE = re.compile(r"^[A-Za-z][A-Za-z0-9]*:[A-Za-z0-9_]+$")


def _en(value) -> str | None:
    if isinstance(value, dict):
        return value.get("en-US") or next(iter(value.values()), None)
    return value


class Schema:
    def __init__(self, reference_dir: Path):
        graph = json.loads((Path(reference_dir) / "ctdl" / "ctdl-schema.json").read_text(encoding="utf-8"))["@graph"]
        self.terms = {t["@id"]: t for t in graph}
        self.context = json.loads((Path(reference_dir) / "ctdl" / "ctdl-context.json").read_text(encoding="utf-8"))["@context"]

    # --- lookups ----------------------------------------------------------------------------

    def has(self, term: str) -> bool:
        return term in self.terms

    def definition(self, term: str) -> str:
        t = self.terms[term]
        return _en(t.get("rdfs:comment")) or _en(t.get("skos:definition")) or ""

    def label(self, term: str) -> str:
        t = self.terms[term]
        return _en(t.get("rdfs:label")) or _en(t.get("skos:prefLabel")) or term

    def is_property(self, term: str) -> bool:
        return self.terms.get(term, {}).get("@type") == "rdf:Property"

    def is_class(self, term: str) -> bool:
        return self.terms.get(term, {}).get("@type") == "rdfs:Class"

    def domain(self, prop: str) -> list[str]:
        return self.terms[prop].get("schema:domainIncludes", [])

    def range(self, prop: str) -> list[str]:
        return self.terms[prop].get("schema:rangeIncludes", [])

    def unstable(self, term: str) -> bool:
        return self.terms.get(term, {}).get("vs:term_status") == "vs:unstable"

    def scheme_of(self, prop: str) -> str | None:
        schemes = self.terms.get(prop, {}).get("meta:targetScheme")
        return schemes[0] if schemes else None

    def concepts(self, scheme: str) -> list[str]:
        return self.terms[scheme].get("meta:hasConcept", [])

    def can_stand_alone(self, cls: str) -> bool:
        """Classes that may carry a CTID are resources in their own right and can be pointed at
        by address. The others (profiles, alignment objects) must be written in place."""
        return "ceterms:ctid" in self.terms.get(cls, {}).get("meta:domainFor", [])

    def term_page(self, term: str) -> str:
        return "https://credreg.net/ctdl/terms/" + term.split(":", 1)[1]

    def describe(self, term: str) -> dict:
        """Everything the viewer shows about one term, quoted from the schema copy."""
        t = self.terms[term]
        out = {
            "term": term,
            "label": self.label(term),
            "kind": {"rdf:Property": "property", "rdfs:Class": "class", "skos:Concept": "concept", "skos:ConceptScheme": "list"}[t["@type"]],
            "definition": self.definition(term),
            "page": self.term_page(term),
            "unstable": self.unstable(term),
        }
        if _en(t.get("dct:description")):
            out["note"] = _en(t["dct:description"])
        if _en(t.get("vann:usageNote")):
            out["usageNote"] = _en(t["vann:usageNote"])
        if t["@type"] == "rdf:Property":
            out["range"] = self.range(term)
            if self.scheme_of(term):
                out["scheme"] = self.scheme_of(term)
        return out

    def describe_scheme(self, scheme: str) -> dict:
        return {
            **self.describe(scheme),
            "concepts": [
                {"term": c, "label": self.label(c), "definition": self.definition(c)} for c in self.concepts(scheme)
            ],
        }

    def alignment(self, scheme: str, concept: str) -> dict:
        """The labelled card that picks one value from a list (research, comment C7)."""
        return {
            "@type": "ceterms:CredentialAlignmentObject",
            "ceterms:framework": self.term_page(scheme),
            "ceterms:targetNode": concept,
            "ceterms:frameworkName": {"en-US": self.label(scheme)},
            "ceterms:targetNodeName": {"en-US": self.label(concept)},
            "ceterms:targetNodeDescription": {"en-US": self.definition(concept)},
        }

    def uri(self, term: str) -> str:
        """The term's full address, from the prefixes in the context copy."""
        prefix, _, name = term.partition(":")
        base = self.context.get(prefix)
        return base + name if isinstance(base, str) and name else term

    def term_record(self, term: str) -> dict:
        """Everything the schema copy states about one term, as the term's page on credreg.net lays it out."""
        t = self.terms[term]
        out = {
            "term": term,
            "uri": self.uri(term),
            # An entry of a fixed list has its page under the list's vocabulary, not under the terms.
            "page": self.uri(term).replace("https://purl.org/", "https://credreg.net/") if t["@type"] == "skos:Concept" else self.term_page(term),
            "label": self.label(term),
            "definition": self.definition(term),
            "type": t["@type"],
            "status": t.get("vs:term_status"),
            "history": t.get("meta:changeHistory"),
        }
        if self.is_class(term):
            out["standAlone"] = self.can_stand_alone(term)
        optional = {
            "comment": "dct:description",
            "usageNote": "vann:usageNote",
            "domainIncludes": "schema:domainIncludes",
            "rangeIncludes": "schema:rangeIncludes",
            "subClassOf": "rdfs:subClassOf",
            "subPropertyOf": "rdfs:subPropertyOf",
            "equivalentClass": "owl:equivalentClass",
            "equivalentProperty": "owl:equivalentProperty",
            "inverseOf": "owl:inverseOf",
            "targetScheme": "meta:targetScheme",
            "domainFor": "meta:domainFor",
            "hasConcept": "meta:hasConcept",
            "inScheme": "skos:inScheme",
            "broader": "skos:broader",
            "narrower": "skos:narrower",
            "relatedMatch": "skos:relatedMatch",
            "narrowMatch": "skos:narrowMatch",
        }
        for key, source in optional.items():
            value = t.get(source)
            if value in (None, [], ""):
                continue
            if isinstance(value, dict):
                value = _en(value)
            elif key not in ("comment", "usageNote") and not isinstance(value, list):
                value = [value]
            out[key] = value
        return out

    def forms(self, root: str = "ceterms:Course") -> dict:
        """What an editing form needs to know, read from the schema copy: for the root class and
        every class that has to be written in place under it, its properties, what each may hold,
        and the entries of every list a property picks from."""
        classes: dict[str, dict] = {}
        properties: dict[str, dict] = {}
        schemes: set[str] = set()
        waiting = [root]
        while waiting:
            cls = waiting.pop()
            if cls in classes or not self.is_class(cls):
                continue
            own = sorted(p for p in self.terms[cls].get("meta:domainFor", []) if self.is_property(p))
            classes[cls] = {"term": cls, "label": self.label(cls), "definition": self.definition(cls), "properties": own, "page": self.term_page(cls)}
            for prop in own:
                if prop in properties:
                    continue
                ctx = self.context.get(prop, {})
                ctx = ctx if isinstance(ctx, dict) else {}
                rng = self.range(prop)
                properties[prop] = {
                    "term": prop,
                    "label": self.label(prop),
                    "definition": self.definition(prop),
                    "range": rng,
                    "languageText": ctx.get("@container") == "@language",
                    "datatype": ctx.get("@type"),
                    "unstable": self.unstable(prop),
                    "page": self.term_page(prop),
                }
                for key, source in (("note", "dct:description"), ("usageNote", "vann:usageNote")):
                    if _en(self.terms[prop].get(source)):
                        properties[prop][key] = _en(self.terms[prop][source])
                if self.scheme_of(prop):
                    properties[prop]["scheme"] = self.scheme_of(prop)
                    schemes.add(self.scheme_of(prop))
                waiting += [r for r in rng if self.is_class(r) and not self.can_stand_alone(r)]
        siblings = [c for c in ("ceterms:Course", "ceterms:LearningOpportunityProfile", "ceterms:LearningProgram") if self.is_class(c)]
        return {
            "root": root,
            "rootChoices": [{"term": c, "label": self.label(c), "definition": self.definition(c)} for c in siblings],
            "required": REQUIRED,
            "requiredOneOf": REQUIRED_ONE_OF,
            "classes": classes,
            "properties": properties,
            "schemes": {s: self.describe_scheme(s) for s in sorted(schemes) if s in self.terms},
            "standAlone": sorted({r for p in properties.values() for r in p["range"] if self.is_class(r) and self.can_stand_alone(r)}),
            # What each prefix stands for, from the context copy, to spell out a shorthand name in full.
            "prefixes": {k: v for k, v in sorted(self.context.items()) if isinstance(v, str) and v.startswith("http")},
            # Every term in the schema copy, in full, for the definition pages (section 9.8).
            "terms": {term: self.term_record(term) for term in sorted(self.terms)},
            # Everything else a property may hold, so the viewer can say what each one is.
            "others": {
                r: {"term": r, "label": self.label(r), "definition": self.definition(r), "page": self.term_page(r)}
                for r in sorted({r for p in properties.values() for r in p["range"]})
                if r not in classes and r in self.terms
            },
        }

    # --- conformance ------------------------------------------------------------------------

    def check(self, record: dict, ledger_knows) -> tuple[list[dict], list[str]]:
        """Run V1 to V8. Returns the checks, and the unstable terms the record uses (flagged,
        not rejected)."""
        problems: dict[str, list[str]] = {f"V{i}": [] for i in range(1, 9)}
        unstable: list[str] = []

        if record.get("@context") != CONTEXT_ADDRESS:
            problems["V1"].append("@context is not the CTDL context.")
        if not isinstance(record.get("@id"), str) or not isinstance(record.get("@type"), str):
            problems["V1"].append("@id or @type is missing.")
        try:
            json.dumps(record)
        except (TypeError, ValueError) as error:
            problems["V1"].append(f"Not serialisable as JSON: {error}")

        def visit(obj: dict, path: str) -> None:
            cls = obj.get("@type")
            if cls is not None and not self.is_class(cls):
                problems["V2"].append(f"{path}/@type: {cls} is not a CTDL class.")
            for key, value in obj.items():
                if key.startswith("@"):
                    continue
                here = f"{path}/{key}"
                if not self.is_property(key):
                    problems["V2"].append(f"{here}: not a CTDL property.")
                    continue
                if cls and cls not in self.domain(key):
                    problems["V2"].append(f"{here}: the schema does not allow this property on {cls}.")
                if self.unstable(key) and key not in unstable:
                    unstable.append(key)
                self._check_value(key, value, here, problems, visit, ledger_knows)

        visit(record, "")

        for prop in REQUIRED:
            if prop not in record:
                problems["V5"].append(f"{prop} is required and missing.")
        if not any(p in record for p in REQUIRED_ONE_OF):
            problems["V5"].append("One of ceterms:ownedBy and ceterms:offeredBy is required.")

        ctid = record.get("ceterms:ctid")
        if not isinstance(ctid, str) or not CTID_FORM.match(ctid):
            problems["V7"].append("ceterms:ctid is not “ce-” plus a UUID.")
        elif not str(record.get("@id", "")).endswith(ctid):
            problems["V7"].append("@id does not end with the record's CTID.")

        texts = {
            "V1": "The record is well-formed JSON-LD with the CTDL context.",
            "V2": "Every key is a real CTDL property, allowed on the class it appears on.",
            "V3": "Every value is of a kind the schema allows for its property.",
            "V4": "Every value chosen from a fixed list is a member of that list.",
            "V5": "The six properties required by the Minimum Data Policy are present.",
            "V6": "Text values are wrapped by language.",
            "V7": "Every CTID has the form “ce-” plus a UUID.",
            "V8": "Every link to another course points at a CTID the ledger knows.",
        }
        checks = [
            {"id": v, "text": texts[v], "status": "fail" if problems[v] else "pass", "detail": problems[v]}
            for v in texts
        ]
        return checks, unstable

    def _check_value(self, prop, value, here, problems, visit, ledger_knows) -> None:
        allowed = self.range(prop)
        if "rdf:langString" in allowed:
            ok = isinstance(value, dict) and value and all(
                _LANGUAGE_TAG.match(k) and (isinstance(v, str) or (isinstance(v, list) and all(isinstance(x, str) for x in v)))
                for k, v in value.items()
            )
            if not ok:
                problems["V6"].append(f"{here}: text is not wrapped by language.")
            return
        values = value if isinstance(value, list) else [value]
        scheme = self.scheme_of(prop)
        classes = [r for r in allowed if self.is_class(r)]
        for index, item in enumerate(values):
            at = f"{here}/{index}" if isinstance(value, list) else here
            if isinstance(item, dict):
                cls = item.get("@type")
                takes_alignment = "skos:Concept" in allowed and cls == "ceterms:CredentialAlignmentObject"
                if cls not in classes and not takes_alignment:
                    problems["V3"].append(f"{at}: a {cls} is not allowed here; the schema expects {', '.join(allowed)}.")
                if scheme and cls == "ceterms:CredentialAlignmentObject":
                    node = item.get("ceterms:targetNode")
                    if node not in self.concepts(scheme):
                        problems["V4"].append(f"{at}: {node} is not in the list {scheme}.")
                visit(item, at)
            elif isinstance(item, bool):
                problems["V3"].append(f"{at}: true/false is not allowed here.")
            elif isinstance(item, (int, float)):
                if not any(r in allowed for r in ("xsd:float", "xsd:integer", "xsd:decimal")):
                    problems["V3"].append(f"{at}: a number is not allowed here.")
            elif isinstance(item, str):
                if "ceterms:Course" in classes and item.startswith(REGISTRY_RESOURCE):
                    if not ledger_knows(item[len(REGISTRY_RESOURCE) :]):
                        problems["V8"].append(f"{at}: {item} is not a CTID in the ledger.")
                if "xsd:string" in allowed:
                    pass
                elif "xsd:language" in allowed:
                    if not _LANGUAGE_TAG.match(item):
                        problems["V3"].append(f"{at}: “{item}” is not a language code.")
                elif "xsd:anyURI" in allowed:
                    if not (_ADDRESS.match(item) or _CURIE.match(item)):
                        problems["V3"].append(f"{at}: “{item}” is not an address.")
                elif classes and any(self.can_stand_alone(c) for c in classes):
                    if not _ADDRESS.match(item):
                        problems["V3"].append(f"{at}: expected the address of a {classes[0]}.")
                else:
                    problems["V3"].append(f"{at}: text is not allowed here; the schema expects {', '.join(allowed)}.")
            else:
                problems["V3"].append(f"{at}: unexpected kind of value.")
