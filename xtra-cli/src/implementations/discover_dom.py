"""What a page's markup says, read as a tree instead of as flattened text.

Discovery used to read every page as one long string. That works for the
questions a sentence answers ("does this say prerequisite?") and fails for
the two questions that decide what a page is:

    Which runs of text are course descriptions?
    Which lists of course codes are a program's requirements?

Both are marked up. CourseLeaf puts every description in
`<div class="courseblock">` and every requirement list in
`<table class="sc_courselist">`; Drupal gives each course its own node;
Acalog names its cores. Flattened, the two become the same thing: a page
with twenty course codes on it. Guessing between them from the prose is
what made a credential's requirement table read as twenty course
descriptions, and a page of descriptions read as a program.

So this module parses the page properly and reports what the markup
already knows. Three things come out of it that a string cannot give:

    the page's own content  - the main container, with the menus, the
                              breadcrumb and the footer dropped, and the
                              page's own h1 rather than the site's
    course blocks           - the described courses, counted as elements
    requirement lists       - the code lists that are references, so the
                              codes in them are not descriptions

It also reads what the publisher declares about the page in machine
readable form - JSON-LD, microdata, and the type a CMS stamps on its
nodes - because a site that says "this is a Course" has answered the
question outright.

BeautifulSoup does the parsing, over lxml where it is installed. That
matters beyond convenience: the hand-written parser this replaced closed
tags by searching backwards for a matching name, so one unclosed `<div>`
inside a `<nav>` - which is most catalog pages - left every heading after
it counted as site furniture. lxml recovers from the same markup the way
a browser does.

Every literal it matches on lives in discover_rules, next to the regexes,
so there is still one file to read when a page is read wrong.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

from implementations.discover_rules import (
    CHROME_CLASS_RE,
    CHROME_ROLES,
    CHROME_TAGS,
    CMS_FULL_VIEW_RE,
    CMS_NODE_TYPE_RE,
    COURSE_BLOCK_CLASS_RE,
    COURSE_CODE_RE,
    COURSE_LIST_CLASS_RE,
    COURSE_REFERENCE_CLASS_RE,
    CREDIT_COLUMN_CLASS_RE,
    DETAIL_FIELD_CLASS_RE,
    DETAIL_LABEL_CLASS_RE,
    FIELD_LABEL_CLASS_RE,
    FIELD_NAME_RE,
    FIELD_VALUE_CLASS_RE,
    FIELD_WRAPPER_CLASS_RE,
    MAIN_CONTAINER_CLASSES,
    MAIN_CONTAINER_IDS,
    MAIN_ROLE,
    MAIN_TAG,
    REQUIREMENT_LIST_CLASS_RE,
    SCHEMA_AWARD_KEYS,
    SCHEMA_MAX_DEPTH,
    SCHEMA_TYPE_LABELS,
    TAB_CLASS_RE,
    TAB_ROLE_RE,
    WHITESPACE_RE,
    collapse,
    evidence,
    normalize_course_code,
)

# Markup that prints nothing, plus <head>, whose <title> is read on its own.
_SKIP_TAGS = frozenset(
    {
        "script",
        "style",
        "noscript",
        "svg",
        "iframe",
        "template",
        "head",
        "map",
    }
)
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_REPORT_HEADING_TAGS = frozenset({"h2", "h3", "h4"})
_SECTION_HEADING_TAGS = _HEADING_TAGS - {"h1"}
_LABEL_TAGS = frozenset({"dt", "th", "label"})
_BOLD_TAGS = frozenset({"strong", "b"})
# The elements that mean something once their text is known.
_CLOSING_TAGS = _HEADING_TAGS | _LABEL_TAGS | _BOLD_TAGS | frozenset({"li"})
_TAB_CONTAINERS = frozenset({"nav", "ul", "ol", "div", "li", "a", "button"})
# The block elements that start a new line of content text: the same set
# the shared normalizer breaks on, plus the table and list cells, so a
# badge in its own <div> and a label in its own <dt> each read as one line.
_CONTENT_BREAK_TAGS = frozenset(
    {
        "p",
        "div",
        "br",
        "tr",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "section",
        "td",
        "th",
        "dt",
        "dd",
        "table",
        "ul",
        "ol",
    }
)
# lxml is the recovering parser, and the one that reads a real catalog
# page the way a browser does. html.parser ships with Python and is the
# fallback, so a thin install still profiles pages rather than crashing.
_PARSERS = ("lxml", "html.parser")


def parse(html: str) -> BeautifulSoup:
    """The page as a tree, however badly it is written."""
    last: Exception | None = None
    for parser in _PARSERS:
        try:
            return BeautifulSoup(html or "", parser)
        # Any parser failure means try the next one, not give up.
        except Exception as exc:  # noqa: BLE001  # pragma: no cover
            last = exc
    raise RuntimeError(f"no usable HTML parser: {last}")


@dataclass
class Declaration:
    """One thing the publisher says this page is, and where it says so."""

    label: str
    source: str
    quote: str
    award: str = ""


@dataclass
class CourseBlock:
    """One described course, as the markup marks it."""

    code: str
    quote: str


@dataclass
class Markup:
    """One page's markup, read once.

    The first block is what the page prints: its name, its headings, the
    text that is the page's own rather than the site's. The second is what
    only the tree can say: which elements are described courses, which are
    requirement lists, and what the publisher declares outright.

    `h1` is the page's own h1 - the one inside its main container, or
    failing that the first outside the menus. Never one from the menus:
    Coursedog prints the college's name as an `<h1>` inside the sidebar
    `<nav>` of every page, so a fallback that reaches into the furniture
    names all 62 pages of a catalog after the college.
    """

    title: str = ""
    h1: str = ""
    site_name: str = ""
    headings: list[str] = field(default_factory=list)
    label_texts: list[str] = field(default_factory=list)
    tabs_evidence: str = ""
    outcomes_evidence: str = ""
    content_text: str = ""
    content_headings: list[str] = field(default_factory=list)
    list_items: list[str] = field(default_factory=list)
    course_blocks: list[CourseBlock] = field(default_factory=list)
    requirement_lists: list[str] = field(default_factory=list)
    reference_codes: set[str] = field(default_factory=set)
    declarations: list[Declaration] = field(default_factory=list)
    cms_page_type: str = ""
    # The printed label/value pairs, read once here so the entity reader
    # does not parse the page a second time to find a credits field.
    field_pairs: list[FieldPair] = field(default_factory=list)

    @property
    def described_course_count(self) -> int:
        """Distinct courses the markup says this page describes."""
        return len({block.code for block in self.course_blocks})

    def declaration(self) -> Declaration | None:
        """What the publisher declares this page is, if anything."""
        return self.declarations[0] if self.declarations else None


def element_text(tag: Tag) -> str:
    """One element's text, joined the way the content lines join it.

    Not `get_text(" ")`: that puts a space between every pair of strings,
    so a list item reading "based on verifiable evidence;" comes back as
    "based on verifiable evidence ;" and no longer matches the line the
    same words produced in the content text. The outcome rules compare
    the two, and one stray space dropped a competency list.
    """
    return collapse(
        "".join(
            str(string)
            for string in tag.strings
            if type(string) is NavigableString
        )
    )


def _class_text(tag: Tag) -> str:
    value = tag.get("class")
    if isinstance(value, list):
        return " ".join(value)
    return value or ""


def _class_words(tag: Tag) -> list[str]:
    return _class_text(tag).split()


def _attribute_words(tag: Tag) -> list[str]:
    """The class and id values, one at a time, for the furniture test.

    A site names a menu with either. Drupal writes `class="breadcrumb"`
    and CourseLeaf writes `id="breadcrumb"`.
    """
    identifier = tag.get("id")
    words = _class_words(tag)
    return (
        [*words, identifier]
        if isinstance(identifier, str) and identifier
        else words
    )


def is_chrome(tag: Tag) -> bool:
    """True when this element is the site around the page, not the page.

    A `<header>` is not furniture by its tag: Clean Catalog prints a
    program's h1 and the badge naming its award inside a `<header>` of the
    program's own.
    """
    if tag.name in CHROME_TAGS:
        return True
    role = (tag.get("role") or "").strip().lower()
    if role in CHROME_ROLES:
        return True
    return any(CHROME_CLASS_RE.match(word) for word in _attribute_words(tag))


def _is_main(tag: Tag) -> bool:
    return (
        tag.name == MAIN_TAG
        or (tag.get("role") or "").strip().lower() == MAIN_ROLE
    )


def find_main(soup: BeautifulSoup) -> Tag | None:
    """The element holding the page's own content, or None.

    `<main>` and `role="main"` first, because they say so. Then the
    handful of ids and classes the catalog platforms use instead:
    Coursedog's `<div id="main-content">`, Drupal's `region-content`.
    An empty one is a page drawn by script after load, and is no use.
    """
    candidates = [tag for tag in soup.find_all(True) if _is_main(tag)]
    if not candidates:
        candidates = [
            tag
            for tag in soup.find_all(True)
            if (tag.get("id") or "").strip().lower() in MAIN_CONTAINER_IDS
            or any(
                word.lower() in MAIN_CONTAINER_CLASSES
                for word in _class_words(tag)
            )
        ]
    best: Tag | None = None
    best_size = 0
    for tag in candidates:
        size = len(tag.get_text(" ", strip=True))
        if size > best_size:
            best, best_size = tag, size
    return best if best_size else None


class _Reader:
    """One walk of the tree, collecting everything the page prints."""

    def __init__(self, soup: BeautifulSoup, main: Tag | None) -> None:
        self.soup = soup
        self.main = main
        self.markup = Markup()
        self._parts: list[str] = []
        self._content_h1s: list[str] = []
        self._main_h1s: list[str] = []

    def read(self) -> Markup:
        root = (
            self.main
            if self.main is not None
            else (self.soup.body or self.soup)
        )
        self._walk(root, in_chrome=False)
        markup = self.markup
        markup.content_text = _lines("".join(self._parts))
        markup.h1 = (self._main_h1s or self._content_h1s or [""])[0]
        return markup

    def _walk(self, node: Tag, *, in_chrome: bool) -> None:
        for child in node.children:
            if type(child) is NavigableString:
                if not in_chrome:
                    self._parts.append(WHITESPACE_RE.sub(" ", str(child)))
                continue
            if not isinstance(child, Tag) or child.name in _SKIP_TAGS:
                continue
            chrome = in_chrome or is_chrome(child)
            self._note_tabs(child)
            breaks = child.name in _CONTENT_BREAK_TAGS
            if breaks and not chrome:
                self._parts.append("\n")
            self._walk(child, in_chrome=chrome)
            if breaks and not chrome:
                self._parts.append("\n")
            self._close(child, chrome=chrome)

    def _close(self, tag: Tag, *, chrome: bool) -> None:
        """What a finished element means, now that its text is known."""
        name = tag.name
        if name not in _CLOSING_TAGS:
            return
        text = element_text(tag)
        if not text:
            return
        markup = self.markup
        if name == "h1":
            # Acalog rules a page off with an <h1> of underscores. A name
            # with no letter or digit in it is a divider, not a name.
            if not chrome and any(char.isalnum() for char in text):
                self._content_h1s.append(text)
                if self.main is not None:
                    self._main_h1s.append(text)
            return
        if name in _SECTION_HEADING_TAGS:
            if name in _REPORT_HEADING_TAGS:
                markup.headings.append(text)
            if not chrome:
                markup.content_headings.append(text)
            return
        if name in _LABEL_TAGS:
            markup.label_texts.append(text)
            return
        if name in _BOLD_TAGS:
            if _bold_is_a_label(tag, text):
                markup.label_texts.append(text)
            return
        if not chrome:
            markup.list_items.append(text)

    def _note_tabs(self, tag: Tag) -> None:
        if self.markup.tabs_evidence or tag.name not in _TAB_CONTAINERS:
            return
        role = tag.get("role") or ""
        classes = _class_text(tag)
        if TAB_ROLE_RE.search(role) or TAB_CLASS_RE.search(classes):
            self.markup.tabs_evidence = evidence(
                f"<{tag.name}> {role or classes}"
            )


def _bold_is_a_label(tag: Tag, text: str) -> bool:
    """`<strong>Credits</strong> 3` is a label. A bold title is not.

    A bold run is a label when it ends with a colon, or when more text
    follows it inside the same parent. A bold run that fills its parent is
    a course title, and course titles are not labels.
    """
    if text.endswith(":"):
        return True
    for following in tag.next_siblings:
        if type(following) is NavigableString and str(following).strip():
            return True
    return False


def _lines(raw: str) -> str:
    lines = (collapse(line) for line in raw.splitlines())
    return "\n".join(line for line in lines if line)


def _outermost(soup: BeautifulSoup, pattern: re.Pattern[str]) -> list[Tag]:
    """Every element whose class matches, never one inside another.

    Membership is by identity. BeautifulSoup compares two tags by their
    name, their attributes and their whole contents, so `in` on a list of
    tags is a deep comparison against every one of them, and two course
    blocks printed identically would read as the same element.
    """
    found: list[Tag] = []
    taken: set[int] = set()
    for tag in soup.find_all(True):
        classes = _class_text(tag)
        if not classes or not pattern.search(classes):
            continue
        if any(id(parent) in taken for parent in tag.parents):
            continue
        found.append(tag)
        taken.add(id(tag))
    return found


def read_course_blocks(soup: BeautifulSoup) -> list[CourseBlock]:
    """The courses this page's markup says it describes.

    A block counts once it names a course code. The same code marked up
    twice - the breadcrumb above the heading, the print view below it - is
    still one course.
    """
    blocks: list[CourseBlock] = []
    seen: set[str] = set()
    for tag in _outermost(soup, COURSE_BLOCK_CLASS_RE):
        text = collapse(tag.get_text(" "))
        match = COURSE_CODE_RE.search(text)
        if match is None:
            continue
        code = normalize_course_code(match.group(0))
        if code in seen:
            continue
        seen.add(code)
        blocks.append(CourseBlock(code=code, quote=evidence(text)))
    return blocks


def _prints_credits_per_course(tag: Tag) -> bool:
    """True when a course list says what each of its courses is worth.

    That is the difference between a program's requirements and any other
    table of course codes. CourseLeaf gives the requirement list a
    `<col class="hourscol">` and gives a transfer equivalency table two
    columns of codes and nothing else.
    """
    for cell in tag.find_all(["col", "th", "td"]):
        if CREDIT_COLUMN_CLASS_RE.search(_class_text(cell)):
            return True
    return False


def read_requirement_lists(
    soup: BeautifulSoup,
) -> tuple[list[str], set[str]]:
    """The requirement lists on the page, and the codes they refer to.

    Two different answers come out of one pass, because a table of course
    codes raises two questions and they have different answers.

    Every code in any such table is a reference to a course described
    elsewhere. Counting them as descriptions is what made a certificate
    page, whose whole content is a table of the twelve courses it
    requires, read as twelve course descriptions.

    Only some of those tables are a program's own requirements, though: a
    list whose class says so, or one that prints what each course is
    worth. An index of courses and a transfer equivalency table are
    neither, and taking them for requirements makes a policy page a
    program.
    """
    quotes: list[str] = []
    references: set[str] = set()
    lists = _outermost(
        soup,
        re.compile(
            f"{COURSE_LIST_CLASS_RE.pattern}|{REQUIREMENT_LIST_CLASS_RE.pattern}",
            re.IGNORECASE,
        ),
    )
    for tag in lists:
        text = collapse(tag.get_text(" "))
        if not text:
            continue
        references.update(
            normalize_course_code(code) for code in COURSE_CODE_RE.findall(text)
        )
        named = REQUIREMENT_LIST_CLASS_RE.search(_class_text(tag))
        if named or _prints_credits_per_course(tag):
            quotes.append(evidence(text))
    for tag in soup.find_all(True):
        classes = _class_text(tag)
        if classes and COURSE_REFERENCE_CLASS_RE.search(classes):
            references.update(
                normalize_course_code(code)
                for code in COURSE_CODE_RE.findall(tag.get_text(" "))
            )
    return quotes, references


def _typed_nodes(value: Any, depth: int = 0) -> list[dict[str, Any]]:
    """Every object carrying an @type, however the document nests them."""
    if depth > SCHEMA_MAX_DEPTH:
        return []
    if isinstance(value, list):
        return [
            node for item in value for node in _typed_nodes(item, depth + 1)
        ]
    if not isinstance(value, dict):
        return []
    found = [value] if value.get("@type") else []
    for nested in value.values():
        found.extend(_typed_nodes(nested, depth + 1))
    return found


def _type_names(node: dict[str, Any]) -> list[str]:
    raw = node.get("@type")
    values = raw if isinstance(raw, list) else [raw]
    return [str(value).rsplit("/", 1)[-1].lower() for value in values if value]


def _award_named(node: dict[str, Any]) -> str:
    for key, value in node.items():
        if key.lower() not in SCHEMA_AWARD_KEYS:
            continue
        if isinstance(value, str) and value.strip():
            return collapse(value)
        if isinstance(value, dict):
            named = value.get("name") or value.get("credentialCategory")
            if isinstance(named, str) and named.strip():
                return collapse(named)
    return ""


@dataclass(frozen=True)
class FieldPair:
    """One printed label and the value beside it, as the markup pairs them.

    `key` is the platform's own name for the field when it has one, which
    is the only thing to go on where a label is not printed: Clean Catalog
    wraps a course description in `field--name-field-description` and
    prints no heading over it.
    """

    label: str
    value: str
    key: str = ""
    path: str = ""


def _element_path(tag: Tag) -> str:
    """A short path to the element, so a reviewer can find the value."""
    parts: list[str] = []
    node: Tag | None = tag
    while isinstance(node, Tag) and node.name not in ("[document]", "html"):
        classes = _class_words(node)
        step = node.name + (f".{classes[0]}" if classes else "")
        parts.append(step)
        node = node.parent
        if len(parts) >= 4:
            break
    return " > ".join(reversed(parts))


def _named(tag: Tag, pattern: re.Pattern[str]) -> bool:
    """True when one of the element's class words is this name."""
    return any(pattern.match(word) for word in _class_words(tag))


def _paired(container: Tag) -> tuple[Tag | None, Tag | None]:
    label = next(
        (
            child
            for child in container.find_all(True)
            if _named(child, FIELD_LABEL_CLASS_RE)
        ),
        None,
    )
    value = next(
        (
            child
            for child in container.find_all(True)
            if _named(child, FIELD_VALUE_CLASS_RE)
        ),
        None,
    )
    return label, value


def read_field_pairs(soup: BeautifulSoup) -> list[FieldPair]:
    """Every printed label and the value beside it.

    Three shapes, which between them are how every catalog platform seen
    marks a field up: a wrapper naming its label and its value (Drupal's
    `field__label`/`field__item`, Coursedog's `field-label`/`field-value`),
    a definition list, and a two-cell table row.

    This is what makes extraction platform-independent. The text form of
    the same page reads "Credits3", because the normalizer the extractors
    share glues a label to its value, and every college then needs its own
    rule for putting them back apart.
    """
    pairs: list[FieldPair] = []
    seen: set[int] = set()
    for wrapper in soup.find_all(True):
        classes = _class_text(wrapper)
        if not classes or not _named(wrapper, FIELD_WRAPPER_CLASS_RE):
            continue
        if any(id(parent) in seen for parent in wrapper.parents):
            continue
        label_tag, value_tag = _paired(wrapper)
        name = FIELD_NAME_RE.search(classes)
        key = (name.group(1).replace("-", " ") if name else "").strip()
        if value_tag is None and label_tag is None and key:
            # A field with no label printed over it, named only by the
            # class the CMS stamped on it.
            value = element_text(wrapper)
            if value:
                seen.add(id(wrapper))
                pairs.append(FieldPair("", value, key, _element_path(wrapper)))
            continue
        if value_tag is None:
            continue
        seen.add(id(wrapper))
        label = element_text(label_tag) if label_tag is not None else ""
        value = element_text(value_tag)
        if label or key:
            pairs.append(FieldPair(label, value, key, _element_path(value_tag)))
    for term in soup.find_all("dt"):
        value = term.find_next_sibling("dd")
        if isinstance(value, Tag):
            pairs.append(
                FieldPair(
                    element_text(term),
                    element_text(value),
                    path=_element_path(value),
                )
            )
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) == 2 and cells[0].name == "th":
            pairs.append(
                FieldPair(
                    element_text(cells[0]),
                    element_text(cells[1]),
                    path=_element_path(cells[1]),
                )
            )
    pairs.extend(_detail_pairs(soup))
    return [pair for pair in pairs if pair.value]


def _detail_pairs(soup: BeautifulSoup) -> list[FieldPair]:
    """The parts of a course block the newer CourseLeaf theme names.

    `<span class="detail-prerequisites"><span class="label">Prerequisite:
    </span>Junior standing</span>` is a label and a value in one element,
    so the label is taken out of the value rather than left in front of
    it.
    """
    pairs: list[FieldPair] = []
    for tag in soup.find_all(True):
        names = [
            match.group(1)
            for word in _class_words(tag)
            if (match := DETAIL_FIELD_CLASS_RE.match(word))
        ]
        if not names:
            continue
        value = element_text(tag)
        label = ""
        inner = next(
            (
                child
                for child in tag.find_all(True)
                if _named(child, DETAIL_LABEL_CLASS_RE)
            ),
            None,
        )
        if inner is not None:
            label = element_text(inner)
            if value.startswith(label):
                value = value[len(label) :].strip()
        pairs.append(
            FieldPair(
                label,
                value,
                names[0].replace("-", " ").replace("_", " "),
                _element_path(tag),
            )
        )
    return pairs


def read_declarations(soup: BeautifulSoup) -> list[Declaration]:
    """What the publisher says this page is, in machine readable form.

    JSON-LD first, then microdata. A declaration is worth more than any
    reading of the prose, because it is the college answering the
    question rather than the page being interpreted.
    """
    found: list[Declaration] = []
    for script in soup.find_all(
        "script", attrs={"type": "application/ld+json"}
    ):
        try:
            document = json.loads(script.get_text() or "")
        except ValueError:
            continue
        for node in _typed_nodes(document):
            for name in _type_names(node):
                label = SCHEMA_TYPE_LABELS.get(name)
                if label is None:
                    continue
                award = _award_named(node)
                found.append(
                    Declaration(
                        label=label,
                        source="json-ld",
                        quote=evidence(f"@type {name}"),
                        award=award,
                    )
                )
    for tag in soup.find_all(attrs={"itemtype": True}):
        raw = tag.get("itemtype")
        name = str(raw).rsplit("/", 1)[-1].lower()
        label = SCHEMA_TYPE_LABELS.get(name)
        if label is not None:
            found.append(
                Declaration(
                    label=label,
                    source="microdata",
                    quote=evidence(f"itemtype {raw}"),
                )
            )
    return found


def read_cms_page_type(soup: BeautifulSoup) -> str:
    """The type a CMS stamps on the node it rendered, if it stamps one.

    Only a full node counts. A department hub at Atlantic Cape carries a
    teaser for every degree under it, and reading those as the page's own
    type made the hub a degree page thirty times over.
    """
    for tag in soup.find_all(True):
        classes = _class_text(tag)
        if not classes or not CMS_FULL_VIEW_RE.search(classes):
            continue
        match = CMS_NODE_TYPE_RE.search(classes)
        if match is not None:
            return (match.group(1) or match.group(2) or "").lower()
    # WordPress stamps the type on <body> instead, where there is one
    # node and so no view to distinguish.
    body = soup.body
    match = CMS_NODE_TYPE_RE.search(_class_text(body)) if body else None
    return (match.group(1) or match.group(2) or "").lower() if match else ""


def _site_name(soup: BeautifulSoup) -> str:
    meta = soup.find("meta", attrs={"property": "og:site_name"})
    content = meta.get("content") if isinstance(meta, Tag) else ""
    return collapse(content or "")


def read_markup(html: str) -> Markup:
    """Read one page's markup. Nothing is fetched and nothing is written."""
    soup = parse(html)
    for tag in soup.find_all(_SKIP_TAGS - {"head"}):
        tag.decompose()
    main = find_main(soup)
    markup = _Reader(soup, main).read()
    title = soup.title
    markup.title = collapse(title.get_text(" ")) if title is not None else ""
    markup.site_name = _site_name(soup)
    if markup.h1 and markup.site_name and markup.h1 == markup.site_name:
        # The site's own name is not the page's name, wherever it is
        # printed. Coursedog prints it as the only h1 on every page.
        markup.h1 = ""
    markup.course_blocks = read_course_blocks(soup)
    markup.requirement_lists, markup.reference_codes = read_requirement_lists(
        soup
    )
    markup.declarations = read_declarations(soup)
    markup.cms_page_type = read_cms_page_type(soup)
    markup.field_pairs = read_field_pairs(soup)
    return markup
