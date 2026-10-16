"""Prerequisite structure (specification section 7): the tree, the parser, the guards, and the
fixed mapping from a tree to CTDL.

Nothing here knows about pages or files. A sentence comes in as its text, its position in the
document, and the course links found inside it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .rules import Phrase

ALL_OF, ANY_OF, COURSE, TEXT = "all_of", "any_of", "course", "text"


@dataclass(frozen=True)
class Link:
    """A course code that the page marks up as a link."""

    start: int
    end: int
    code: str  # normalised: "MATH 20503"


@dataclass
class Node:
    kind: str
    start: int = -1
    end: int = -1
    code: str | None = None
    children: list["Node"] = field(default_factory=list)

    def leaves(self) -> list["Node"]:
        if self.kind in (COURSE, TEXT):
            return [self]
        return [leaf for child in self.children for leaf in child.leaves()]

    def courses(self) -> list["Node"]:
        return [leaf for leaf in self.leaves() if leaf.kind == COURSE]

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


def simplify(node: Node) -> Node:
    """A group of one is that one. A group inside a group of the same kind, with no brackets of
    its own to keep, stays as written; nothing is rearranged."""
    node.children = [simplify(c) for c in node.children]
    if node.kind in (ALL_OF, ANY_OF) and len(node.children) == 1:
        return node.children[0]
    return node


# --------------------------------------------------------------------------------------- tokens


@dataclass(frozen=True)
class Token:
    kind: str  # course, phrase, (, ), comma, and, or, end
    start: int
    end: int
    link: Link | None = None
    phrase: Phrase | None = None


_CONJ = re.compile(r"(and|or)\b", re.IGNORECASE)


def tokenise(text: str, offset: int, links: list[Link], phrases: list[Phrase]) -> list[Token] | None:
    """Split a sentence into the only things the parser knows. Returns None at the first
    character that is none of them."""
    by_start = {link.start: link for link in links}
    ordered = sorted(phrases, key=lambda p: -len(p.text))
    lowered = text.replace(" ", " ").lower()
    tokens: list[Token] = []
    i = 0
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        here = offset + i
        if here in by_start:
            link = by_start[here]
            tokens.append(Token("course", link.start, link.end, link=link))
            i = link.end - offset
            continue
        phrase = next(
            (
                p
                for p in ordered
                if lowered.startswith(p.text.lower(), i)
                and not lowered[i + len(p.text) : i + len(p.text) + 1].isalnum()
            ),
            None,
        )
        if phrase:
            tokens.append(Token("phrase", here, here + len(phrase.text), phrase=phrase))
            i += len(phrase.text)
            continue
        if text[i] in "(),":
            kind = "comma" if text[i] == "," else text[i]
            tokens.append(Token(kind, here, here + 1))
            i += 1
            continue
        conj = _CONJ.match(text, i)
        if conj:
            tokens.append(Token(conj.group(1).lower(), here, here + len(conj.group(1))))
            i = conj.end()
            continue
        if text[i] == "." and not text[i + 1 :].strip():
            tokens.append(Token("end", here, here + 1))
            i += 1
            continue
        return None
    return tokens


# --------------------------------------------------------------------------------------- parser


class _Declined(Exception):
    pass


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.i = 0

    def peek(self, ahead: int = 0) -> Token | None:
        j = self.i + ahead
        return self.tokens[j] if j < len(self.tokens) else None

    def take(self) -> Token:
        token = self.tokens[self.i]
        self.i += 1
        return token

    def is_modifier(self, token: Token | None, each: bool | None = None) -> bool:
        if token is None or token.kind != "phrase" or token.phrase.role != "modifier":
            return False
        starts_with_each = token.phrase.text.lower().startswith("each ")
        return each is None or each == starts_with_each

    def parse_list(self) -> Node:
        items: list[Node] = [self.parse_item()]
        words: set[str] = set()
        list_modifier: Token | None = None
        while True:
            token = self.peek()
            if token is None:
                break
            if token.kind == "comma":
                after = self.peek(1)
                if self.is_modifier(after):  # "…, each with a grade of C or better"
                    self.take()
                    list_modifier = self.take()
                    break
                self.take()
                if self.peek() and self.peek().kind in ("and", "or"):
                    words.add(self.take().kind)
                items.append(self.parse_item())
            elif token.kind in ("and", "or"):
                words.add(self.take().kind)
                items.append(self.parse_item())
            elif self.is_modifier(token, each=True):  # "… each with a grade of C or better"
                list_modifier = self.take()
                break
            else:
                break
        if len(items) == 1:
            node = items[0]
        else:
            if len(words) != 1:
                # Commas alone, or "and" mixed with "or" at one level: the reading is not certain.
                raise _Declined()
            with_grade = [n for n in items if _is_course_with_modifier(n)]
            bare = [n for n in items if n.kind == COURSE]
            if with_grade and bare:
                # "A or B with a grade of C or better": does the grade cover A as well?
                raise _Declined()
            node = Node(ALL_OF if words == {"and"} else ANY_OF, items[0].start, items[-1].end, children=items)
        if list_modifier:
            text = Node(TEXT, list_modifier.start, list_modifier.end)
            if node.kind == ALL_OF:
                node.children.append(text)
                node.end = text.end
            else:
                node = Node(ALL_OF, node.start, text.end, children=[node, text])
        return node

    def parse_item(self) -> Node:
        token = self.peek()
        if token is None:
            raise _Declined()
        if token.kind == "course":
            self.take()
            node = Node(COURSE, token.start, token.end, code=token.link.code)
        elif token.kind == "phrase" and token.phrase.role == "condition":
            self.take()
            node = Node(TEXT, token.start, token.end)
        elif token.kind == "(":
            opened = self.take()
            node = self.parse_list()
            closed = self.peek()
            if closed is None or closed.kind != ")":
                raise _Declined()
            self.take()
            if node.kind in (ALL_OF, ANY_OF):
                node.start, node.end = opened.start, closed.end
            else:
                node = Node(ALL_OF, opened.start, closed.end, children=[node])
        else:
            raise _Declined()
        if self.is_modifier(self.peek(), each=False):  # "ACCT 20103 with a grade of C or better"
            mod = self.take()
            node = Node(ALL_OF, node.start, mod.end, children=[node, Node(TEXT, mod.start, mod.end)])
        return node


def _is_course_with_modifier(node: Node) -> bool:
    return (
        node.kind == ALL_OF
        and len(node.children) == 2
        and node.children[0].kind == COURSE
        and node.children[1].kind == TEXT
    )


def parse(text: str, offset: int, links: list[Link], phrases: list[Phrase]) -> Node | None:
    """Read the whole sentence, or decline. Never guess."""
    tokens = tokenise(text, offset, links, phrases)
    if not tokens:
        return None
    if tokens[-1].kind == "end":
        tokens = tokens[:-1]
    if not tokens or any(t.kind == "end" for t in tokens):
        return None
    parser = _Parser(tokens)
    try:
        node = parser.parse_list()
    except _Declined:
        return None
    if parser.i != len(tokens):
        return None
    return simplify(node)


def bracketed_groups(text: str, offset: int, links: list[Link]) -> list[tuple[str, list[int]]]:
    """Bracketed groups made of nothing but course codes joined by one word, "and" or "or".
    The parser can read these on their own even when it declines the sentence (guard G4)."""
    by_start = {link.start: link for link in links}
    groups = []
    for m in re.finditer(r"\(([^()]*)\)", text):
        inner_start = offset + m.start(1)
        inner = m.group(1)
        starts: list[int] = []
        words: set[str] = set()
        i = 0
        ok = True
        while i < len(inner):
            if inner[i].isspace() or inner[i] == ",":
                i += 1
                continue
            here = inner_start + i
            if here in by_start:
                starts.append(here)
                i = by_start[here].end - inner_start
                continue
            conj = _CONJ.match(inner, i)
            if conj:
                words.add(conj.group(1).lower())
                i = conj.end()
                continue
            ok = False
            break
        if ok and len(starts) >= 2 and len(words) == 1:
            groups.append((ALL_OF if words == {"and"} else ANY_OF, starts))
    return groups


# -------------------------------------------------------------------- a proposal becomes a tree


@dataclass
class Guard:
    id: str
    text: str
    passed: bool
    detail: str = ""

    def to_json(self) -> dict:
        return {"id": self.id, "text": self.text, "status": "pass" if self.passed else "fail", "detail": self.detail}


GUARD_TEXT = {
    "G1": "The proposal is in the agreed form, and every quote is word for word in the sentence.",
    "G2": "Every course in the structure is a link in the sentence.",
    "G3": "Every link in the sentence appears in the structure.",
    "G4": "Where the parser read a bracketed group on its own, the structure agrees with it.",
    "G5": "The structure's parts appear in the sentence's order and do not overlap.",
}

_MAX_DEPTH = 6
_KIND_WORDS = {ALL_OF: "all of", ANY_OF: "any one of"}


def _note(problems: dict[str, str], guard: str, finding: str) -> None:
    """Record one specific finding against a guard. Every finding is kept, one to a line."""
    lines = problems[guard].split("\n") if guard in problems else []
    if finding not in lines:
        problems[guard] = "\n".join([*lines, finding])


def _short(words: str, limit: int = 60) -> str:
    words = " ".join(words.split())
    return words if len(words) <= limit else words[: limit - 1].rstrip() + "…"


def tree_from_proposal(raw: object, text: str, offset: int, links: list[Link]) -> tuple[Node | None, dict[str, str]]:
    """Turn a proposed structure (kind / quote / items) into a tree with positions, by finding
    each quote in the sentence in order. Returns the tree and, per guard, what went wrong."""
    problems: dict[str, str] = {}
    plain = text.replace(" ", " ")
    cursor = 0
    used: set[int] = set()

    def build(item: object, depth: int) -> Node | None:
        nonlocal cursor
        if not isinstance(item, dict):
            _note(problems, "G1", f"A part is {type(item).__name__}, not a part with a kind and a quote.")
            return None
        if depth > _MAX_DEPTH:
            _note(problems, "G1", f"Groups are nested more than {_MAX_DEPTH} deep.")
            return None
        kind = item.get("kind")
        if kind in (ALL_OF, ANY_OF):
            items = item.get("items") or []
            if not items:
                _note(problems, "G1", f"An “{_KIND_WORDS[kind]}” group has nothing in it.")
                return None
            children = [build(child, depth + 1) for child in items]
            children = [c for c in children if c is not None]
            if not children:
                return None  # every part of it was refused, and each refusal is already noted
            return Node(kind, children[0].start, children[-1].end, children=children)
        quote = item.get("quote")
        if kind not in (COURSE, TEXT):
            _note(problems, "G1", f"A part has the kind “{kind}”. Only all_of, any_of, course and text are allowed.")
            return None
        if not isinstance(quote, str) or not quote.strip():
            _note(problems, "G1", f"A “{kind}” part has no quote.")
            return None
        quote = quote.replace(" ", " ").strip()
        if kind == COURSE:
            code = " ".join(quote.split())
            same = [l for l in links if l.code == code]
            if not same:
                _note(problems, "G2", f"“{_short(code)}” is not a course link in the sentence.")
                return None
            nxt = next((l for l in same if l.start - offset >= cursor and l.start not in used), None)
            if nxt is None:
                times = len(same)
                _note(problems, "G5", f"“{code}” appears {times} time{'s' if times != 1 else ''} in the sentence, but the proposal uses it again or out of order.")
                return None
            used.add(nxt.start)
            cursor = nxt.end - offset
            return Node(COURSE, nxt.start, nxt.end, code=code)
        at = plain.find(quote, cursor)
        if at < 0:
            if plain.find(quote) < 0:
                _note(problems, "G1", f"“{_short(quote)}” is not in the sentence word for word.")
            else:
                _note(problems, "G5", f"“{_short(quote)}” is in the sentence, but before the part the proposal puts ahead of it.")
            return None
        cursor = at + len(quote)
        return Node(TEXT, offset + at, offset + at + len(quote))

    tree = build(raw, 0)
    return (simplify(tree) if tree and not problems else None), problems


def run_guards(
    tree: Node | None,
    problems: dict[str, str],
    text: str,
    offset: int,
    links: list[Link],
) -> list[Guard]:
    """Guards G1 to G5 (section 7.3), applied to every structure, whoever built it."""
    problems = dict(problems)
    if tree is not None:
        for leaf in tree.courses():
            if not any(l.start == leaf.start and l.code == leaf.code for l in links):
                _note(problems, "G2", f"“{leaf.code}” is not a course link in the sentence.")
        used = {leaf.start for leaf in tree.courses()}
        missing = [l.code for l in links if l.start not in used]
        if missing:
            _note(problems, "G3", f"Left out {len(missing)} of the {len(links)} course links: " + ", ".join(missing) + ".")
        for leaf in tree.leaves():
            if leaf.kind == TEXT:
                inside = [l.code for l in links if l.start >= leaf.start and l.end <= leaf.end]
                if inside:
                    words = _short(text[leaf.start - offset : leaf.end - offset])
                    _note(problems, "G3", f"The text condition “{words}” swallows the course link{'s' if len(inside) != 1 else ''} " + ", ".join(inside) + ".")
        for kind, starts in bracketed_groups(text, offset, links):
            wanted = set(starts)
            agrees = any(
                n.kind == kind and {c.start for c in n.courses()} == wanted for n in tree.walk()
            )
            if not agrees:
                codes = ", ".join(l.code for l in links if l.start in wanted)
                word = "and" if kind == ALL_OF else "or"
                other = "or" if kind == ALL_OF else "and"
                together = [n for n in tree.walk() if n.children and wanted <= {c.start for c in n.courses()}]
                got = "does not keep them together as one group" if not together else (
                    f"joins them with “{other}”" if together[-1].kind != kind and {c.start for c in together[-1].courses()} == wanted
                    else "puts them in a larger group with other parts"
                )
                _note(problems, "G4", f"The page brackets ({codes}) and joins them with “{word}”. The proposal {got}.")
        leaves = tree.leaves()
        for a, b in zip(leaves, leaves[1:]):
            if b.start < a.end:
                first, second = (_short(text[n.start - offset : n.end - offset], 40) for n in (a, b))
                _note(problems, "G5", f"“{first}” is placed before “{second}”, but they overlap or come the other way round in the sentence.")
    elif not problems:
        _note(problems, "G1", "No structure could be read from the proposal.")
    return [Guard(g, GUARD_TEXT[g], g not in problems, problems.get(g, "")) for g in GUARD_TEXT]


# --------------------------------------------------------------------------- from a tree to CTDL


@dataclass
class Placement:
    """Where one node of the tree landed in the CTDL profile."""

    node: Node
    path: str  # relative to the profile, e.g. "/ceterms:targetLearningOpportunity/0"
    how: str  # "course", "condition", "alternatives", "choice", "kept as text"


@dataclass
class Mapped:
    profile: dict
    placements: list[Placement]
    partly_structured: bool


def _as_all_of(node: Node) -> list[Node]:
    return list(node.children) if node.kind == ALL_OF else [node]


def to_condition_profile(tree: Node | None, uri_for, words_of, language: str = "en-US") -> Mapped:
    """The fixed mapping of section 7.4. `uri_for(code)` gives a course's address; `words_of(node)`
    gives a node's exact words, normalised for the record.

    One profile holds one set of choices. A second set of choices in the same group, or a group
    with a condition of its own nested inside an "all of", cannot be written exactly without
    repeating branches, so its words go into ceterms:condition as text and the result is
    reported as partly structured."""
    placements: list[Placement] = []
    partly = False

    def profile_for(node: Node, base: str) -> dict:
        nonlocal partly
        profile: dict = {"@type": "ceterms:ConditionProfile"}
        courses: list[str] = []
        conditions: list[str] = []
        alternatives: list[dict] | None = None
        pending: list[tuple[Node, str, str, int]] = []
        for child in _as_all_of(node):
            if child.kind == COURSE:
                pending.append((child, "course", "ceterms:targetLearningOpportunity", len(courses)))
                courses.append(uri_for(child.code))
            elif child.kind == TEXT:
                pending.append((child, "condition", "ceterms:condition", len(conditions)))
                conditions.append(words_of(child))
            elif child.kind == ANY_OF and alternatives is None:
                alternatives = []
                placements.append(Placement(child, f"{base}/ceterms:alternativeCondition", "alternatives"))
                for choice in child.children:
                    at = f"{base}/ceterms:alternativeCondition/{len(alternatives)}"
                    placements.append(Placement(choice, at, "choice"))
                    alternatives.append(profile_for(choice, at))
            elif child.kind == ALL_OF and all(c.kind == COURSE for c in child.children):
                for course in child.children:  # "(A and B) and C" is A and B and C
                    pending.append((course, "course", "ceterms:targetLearningOpportunity", len(courses)))
                    courses.append(uri_for(course.code))
            else:
                partly = True
                pending.append((child, "kept as text", "ceterms:condition", len(conditions)))
                conditions.append(words_of(child))
        for child, how, prop, index in pending:
            suffix = f"/{language}/{index}" if prop == "ceterms:condition" else f"/{index}"
            placements.append(Placement(child, f"{base}/{prop}{suffix}", how))
        if courses:
            profile["ceterms:targetLearningOpportunity"] = courses
        if conditions:
            profile["ceterms:condition"] = {language: conditions}
        if alternatives is not None:
            profile["ceterms:alternativeCondition"] = alternatives
        return profile

    if tree is None:
        return Mapped({"@type": "ceterms:ConditionProfile"}, [], False)
    profile = profile_for(tree, "")
    return Mapped(profile, placements, partly)


def is_plain_list_of_courses(tree: Node | None) -> bool:
    """True when the whole structure is one course, or a single "all of" holding only courses.
    Only then may direct ceterms:prerequisite links be emitted (decision D7)."""
    if tree is None:
        return False
    if tree.kind == COURSE:
        return True
    return tree.kind == ALL_OF and all(c.kind == COURSE for c in tree.children)


def describe(tree: Node | None) -> str:
    """A few words for the folded record: "any one of 2 groups", "ACCT 20103", "2 courses"."""
    if tree is None:
        return "sentence only"
    if tree.kind == COURSE:
        return tree.code or ""
    if tree.kind == TEXT:
        return "a condition"
    n = len(tree.children)
    if all(c.kind == COURSE for c in tree.children):
        return f"{n} courses" if tree.kind == ALL_OF else f"any one of {n} courses"
    if tree.kind == ANY_OF:
        groups = all(c.kind in (ALL_OF, ANY_OF) for c in tree.children)
        return f"any one of {n} {'groups' if groups else 'options'}"
    return f"all of {n} parts"
