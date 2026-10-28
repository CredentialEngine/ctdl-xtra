"""Transcribe a page's printed fields from its markup.

The extractors under lib/templates read the flattened page and each one
knows one college's layout: where Brookdale puts its credits, what
Raritan calls its prerequisites. That works, and it is one file per
college for ever, because flattening the page throws away the one thing
every catalog platform does provide - it marks each field up, names the
label, and names the value beside it.

This reads those instead. Drupal writes `field__label` and `field__item`
inside a `field--name-*` div, Coursedog writes `field-label` and
`field-value`, CourseLeaf prints a course block whose title line carries
the code, the name and the credits together, and the rest of the web
writes a definition list or a table row. None of that needs to know which
college it is looking at.

eLumen marks up none of that. It prints a course as a heading group - the
name, a heading that is nothing but the code, the units on a line of their
own - and its hours as a heading over a number. Both shapes are read here
too, still without knowing the college: before they were, every eLumen
course was named after the catalog's hidden banner, "2026-2027 Catalog",
and carried no code and no units.

Credits keep the word they are counted in. "4.0 Units", "3 Hours." and a
"Credit Hours" label each give the number and, beside it, the unit as
printed, and the two always come from the same reading.

A course's prerequisite is read wherever its page prints one: as a
labelled field, under a heading or a bold label of its own, on a line that
opens "Prerequisite:", or in the run of requisites eLumen opens a
description with. It is the text after the label, as printed, and there is
one per course - the first the page prints, with the alternatives an
eLumen list joins by OR kept together. "None" is no prerequisite, and a
label naming both relations, "Prerequisite/Corequisite", names neither on
its own.

It is also the only way the three entities beside Course get extracted at
all. Discovery labels credential, learning-opportunity and competency
pages, and until now nothing downstream could read one: the templates are
course templates, and a credential page has no course block for them to
find.

What it will not do is guess. A field is written down only when the page
prints it, with the element it came from recorded, so a reviewer can go
and look. A page that prints nothing this can read raises, the way the
template extractors do, rather than producing an empty record that looks
like a real one.
"""

from __future__ import annotations

from typing import Any

from bs4 import NavigableString, Tag

from implementations.discover_dom import (
    FieldPair,
    Markup,
    element_path,
    element_text,
    find_main,
    is_chrome,
    lines_after,
    parse,
    printed_text,
    read_field_pairs,
)
from implementations.discover_page import (
    first_paragraph,
    outcome_list,
    page_name,
    parse_structure,
)
from implementations.discover_rules import (
    COMBINED_REQUISITE_RE,
    COURSE_BLOCK_CREDITS_RE,
    COURSE_BLOCK_DESC_CLASS_RE,
    COURSE_BLOCK_TITLE_CLASS_RE,
    COURSE_CODE_RE,
    COURSE_FIELD_LABELS,
    COURSE_HEADING_REACH,
    CREDIT_UNIT_RE,
    ENTITY_TYPE_OF_LABEL,
    HEADING_GROUP_TAGS,
    MAX_FIELD_LABEL_CHARS,
    NO_PREREQUISITE_RE,
    NUMERIC_FIELDS,
    PREREQUISITE_COURSES_LABEL_RE,
    PREREQUISITE_LABEL_RE,
    PREREQUISITE_LEAD_RE,
    PREREQUISITE_MAX_CHARS,
    PREREQUISITE_RUN_ON_CHARS,
    REQUISITE_CONNECTOR_RE,
    REQUISITE_LABEL_RE,
    REQUISITE_LEAD_RE,
    REQUISITE_WORD_RE,
    SECTION_HEADING_CHARS,
    SENTENCE_END_RE,
    TAB_ROLE_RE,
    collapse,
    course_block_credits,
    normalize_field_label,
    split_course_title,
)
from implementations.engine import load_engine

# The entity types map_fields knows, which are the ones a record may
# carry. Discovery's labels are not all spelled the same way: what it
# calls a LearningOpportunity is a ceterms:LearningProgram.
ENTITY_COURSE = "Course"
ENTITY_CREDENTIAL = "Credential"
ENTITY_PROGRAM = "LearningProgram"
ENTITY_COMPETENCY = "Competency"

# The canonical name field for each entity, so one rule writes the page's
# own name into whichever record is being built.
NAME_FIELD = {
    ENTITY_COURSE: "course_name",
    ENTITY_CREDENTIAL: "credential_name",
    ENTITY_PROGRAM: "learning_program_name",
    ENTITY_COMPETENCY: "competency_framework_name",
}
DESCRIPTION_FIELD = {
    ENTITY_COURSE: "course_description",
    ENTITY_CREDENTIAL: "credential_description",
    ENTITY_PROGRAM: "learning_program_description",
}
ID_FIELD = {
    ENTITY_COURSE: "course_id",
    ENTITY_PROGRAM: "learning_program_id",
}


# How many fields make a record. One is the page's own name, which every
# page has and which on its own says nothing was read.
MIN_FIELDS = 2


class NothingToExtract(ValueError):
    """The page prints too little for a record."""


def entity_types_for(labels: list[str]) -> list[str]:
    """Every record a page with these labels should produce, best first.

    Usually one. A page carrying two labels produces two, because it
    really is about two things and each is published as its own entity:
    every one of the 85 program pages at Atlantic Cape prints both the
    credential and the list of what its students will be able to do, and
    a single record has nowhere to put the second.

    ENTITY_TYPE_OF_LABEL is in precedence order, so the first is the one
    the page is mainly about, and the page's own id belongs to it.
    """
    return [
        entity_type
        for label, entity_type in ENTITY_TYPE_OF_LABEL.items()
        if label in labels
    ]


def entity_type_for(labels: list[str]) -> str | None:
    """The record a page with these labels is mainly about, or None."""
    found = entity_types_for(labels)
    return found[0] if found else None


def _number(text: str) -> Any:
    """A printed number as a number, or the text when it is a range."""
    value = collapse(text)
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _credits_and_unit(text: str) -> tuple[Any, str] | None:
    """A line that is nothing but credits, "4.0 Units", as its number and
    its unit, or None."""
    match = COURSE_BLOCK_CREDITS_RE.fullmatch(collapse(text))
    if match is None:
        return None
    credits, unit = course_block_credits(match)
    return _number(credits), unit


def _printed_unit(label: str) -> str:
    """The unit a credits label names, "CREDIT HOURS" in "CREDIT HOURS
    MIN:", or "" when it names none."""
    match = CREDIT_UNIT_RE.search(collapse(label))
    return match.group(0) if match else ""


def canonical_field(pair: FieldPair) -> str | None:
    """The canonical field this printed label is, or None.

    The label the page prints comes first, because that is what a reader
    sees. The platform's own name for the field is the fallback, for the
    fields a CMS prints with no label over them: Clean Catalog's course
    description is a div called `field--name-field-description`.
    """
    for candidate in (pair.label, pair.key):
        key = normalize_field_label(candidate) if candidate else None
        if key and key in COURSE_FIELD_LABELS:
            return COURSE_FIELD_LABELS[key]
    return None


def _draft(
    field_id: str, label: str, value: Any, excerpt: str, locator: str
) -> Any:
    load_engine()
    from transcribe_lib import FieldDraft

    return FieldDraft(
        field_id=field_id,
        canonical_label=label,
        value=value,
        raw_text=excerpt,
        excerpt=excerpt,
        locator_strategy="dom_path",
        locator_value=locator,
    )


def _collect(found: dict[str, tuple[Any, str, str]]) -> list[Any]:
    """The drafts in a stable order, numbered the way a record expects."""
    drafts = []
    for index, label in enumerate(sorted(found), start=1):
        value, excerpt, locator = found[label]
        drafts.append(_draft(f"f_{index:03d}", label, value, excerpt, locator))
    return drafts


def _prerequisite_value(text: str) -> str | None:
    """A printed prerequisite as the record keeps it, or None for none.

    The text after its label, as printed. "None" is no prerequisite, and a
    statement naming both relations is not a prerequisite on its own.
    """
    value = collapse(text).lstrip(" :").rstrip(" ;,")
    if COMBINED_REQUISITE_RE.match(value):
        return None
    # Atlantic Cape's BIOL302 prints its label again inside the field.
    lead = PREREQUISITE_LEAD_RE.match(value)
    if lead is not None:
        value = value[lead.end() :].rstrip(" ;,")
    if not value or NO_PREREQUISITE_RE.fullmatch(value):
        return None
    return value


def _from_field_pairs(
    pairs: list[FieldPair],
) -> dict[str, tuple[Any, str, str]]:
    found: dict[str, tuple[Any, str, str]] = {}
    for pair in pairs:
        label = canonical_field(pair)
        if label is None or label in found:
            continue
        if label == "course_credits":
            found.update(_credits_from_pair(pair))
            continue
        if label == "course_prerequisites":
            value = _prerequisite_value(pair.value)
            if value is not None:
                found[label] = (value, pair.value, pair.path)
            continue
        value = _number(pair.value) if label in NUMERIC_FIELDS else pair.value
        found[label] = (value, pair.value, pair.path)
    return found


def _credits_from_pair(pair: FieldPair) -> dict[str, tuple[Any, str, str]]:
    """A labelled credits field, and the unit its credits are counted in.

    The unit is the value's own when the value prints one, "3 Units", and
    otherwise the label's, "Credit Hours" over a 3. A field the page left
    unlabelled, known here only by its class name, prints no unit at all.
    """
    read = _credits_and_unit(pair.value)
    if read is not None:
        credits, unit = read
        return {
            "course_credits": (credits, pair.value, pair.path),
            "course_credits_unit": (unit, pair.value, pair.path),
        }
    found: dict[str, tuple[Any, str, str]] = {
        "course_credits": (_number(pair.value), pair.value, pair.path)
    }
    named = normalize_field_label(pair.label) or ""
    unit = _printed_unit(pair.label)
    if COURSE_FIELD_LABELS.get(named) == "course_credits" and unit:
        found["course_credits_unit"] = (unit, pair.label, pair.path)
    return found


def _from_course_block(soup: Any) -> dict[str, tuple[Any, str, str]]:
    """The code, name and credits CourseLeaf prints on one title line."""
    found: dict[str, tuple[Any, str, str]] = {}
    title = next(
        (
            tag
            for tag in soup.find_all(True)
            if _class_named(tag, COURSE_BLOCK_TITLE_CLASS_RE)
        ),
        None,
    )
    if title is not None:
        line = element_text(title)
        code, name, credits, unit = split_course_title(line)
        if code:
            found["course_id"] = (code, line, "p.courseblocktitle")
        if name:
            found["course_name"] = (name, line, "p.courseblocktitle")
        if credits:
            found["course_credits"] = (
                _number(credits),
                line,
                "p.courseblocktitle",
            )
            found["course_credits_unit"] = (unit, line, "p.courseblocktitle")
    body = next(
        (
            tag
            for tag in soup.find_all(True)
            if _class_named(tag, COURSE_BLOCK_DESC_CLASS_RE)
        ),
        None,
    )
    if body is not None:
        text = element_text(body)
        if text:
            found["course_description"] = (text, text, "p.courseblockdesc")
    return found


def _class_named(tag: Any, pattern: Any) -> bool:
    value = tag.get("class")
    classes = " ".join(value) if isinstance(value, list) else (value or "")
    return bool(classes) and bool(pattern.search(classes))


_HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")


def _content_headings(soup: Any) -> list[Any]:
    """The page's own headings: inside its main container, never a menu's."""
    root = find_main(soup) or soup.body or soup
    return [
        heading
        for heading in root.find_all(_HEADINGS)
        if not any(is_chrome(parent) for parent in heading.parents)
    ]


def _bare_code(text: str) -> str:
    """The code, when a heading holds nothing else: "ELEC 150:"."""
    code = text.rstrip(" :.")
    return code if COURSE_CODE_RE.fullmatch(code) else ""


def _first_printed(nodes: Any) -> tuple[str, Any] | None:
    """The first of these siblings that prints anything, and its element."""
    for node in nodes:
        if isinstance(node, Tag):
            text = element_text(node)
            if text:
                return text, node
        elif type(node) is NavigableString:
            text = collapse(str(node))
            if text:
                return text, node.parent
    return None


def _from_course_heading(soup: Any) -> dict[str, tuple[Any, str, str]]:
    """The code, name and units eLumen prints as its heading group.

    `<header><h2>Electrical Maintenance</h2><h3>ELEC 150:</h3><p>4.0
    Units</p></header>` at Antelope Valley and Cabrillo; Bakersfield's
    theme prints the name in a <p> and the code in the h1, and the units
    two wrappers below. None of the three is labelled, so the code is the
    heading that is nothing but a code, the name is what the group prints
    beside it, and the units are the first line after it that is nothing
    but units. That line gives the unit word too, as printed: "Units" at
    Antelope Valley, "UNITS" at Bakersfield.
    """
    found: dict[str, tuple[Any, str, str]] = {}
    heading = next(
        (
            tag
            for tag in _content_headings(soup)
            if _bare_code(element_text(tag))
        ),
        None,
    )
    if heading is None:
        return found
    line = element_text(heading)
    found["course_id"] = (_bare_code(line), line, element_path(heading))
    beside = (
        _first_printed(heading.previous_siblings)
        if heading.parent is not None
        and heading.parent.name in HEADING_GROUP_TAGS
        else None
    )
    if beside is not None:
        name, holder = beside
        # A code beside the code is another course, and a paragraph is the
        # description; neither is the name.
        too_long = len(name) > SECTION_HEADING_CHARS
        if not too_long and not COURSE_CODE_RE.search(name):
            found["course_name"] = (name, name, element_path(holder))
    for tag in heading.find_all_next(True, limit=COURSE_HEADING_REACH):
        text = element_text(tag)
        read = _credits_and_unit(text)
        if read is not None:
            credits, unit = read
            found["course_credits"] = (credits, text, element_path(tag))
            found["course_credits_unit"] = (unit, text, element_path(tag))
            break
    return found


def _from_heading_labels(soup: Any) -> dict[str, tuple[Any, str, str]]:
    """A number printed under a heading that names it.

    eLumen prints "Total Course Lecture Hours" as an <h5> and "54.0" in the
    element after it; SmartCatalog prints <h3>Credits</h3> over "3". Only
    the numeric fields are read this way, and only when the value is a
    number: Coursedog prints "Credit Hours" over the word "Min", and a
    heading over a text field is as often a section over a whole page. A
    credits heading names the unit as well: SmartCatalog's is "Credits".
    """
    found: dict[str, tuple[Any, str, str]] = {}
    for heading in _content_headings(soup):
        name = element_text(heading)
        label = canonical_field(FieldPair(name, ""))
        if label not in NUMERIC_FIELDS or label in found:
            continue
        beside = _first_printed(heading.next_siblings)
        if beside is None:
            continue
        printed, holder = beside
        value = _number(printed)
        if not isinstance(value, (int, float)):
            continue
        found[label] = (value, printed, element_path(holder))
        unit = _printed_unit(name) if label == "course_credits" else ""
        if unit:
            found["course_credits_unit"] = (unit, name, element_path(heading))
    return found


# --- the prerequisite a course names -------------------------------------------

# What a requisite label is: one naming both relations, Clean Catalog's
# list of the courses a statement names, the prerequisite itself, or any
# other of the family, which only ever ends a prerequisite.
_BOTH = "both"
_COURSES = "courses"
_PREREQUISITE = "prerequisite"
_OTHER = "other"
# What may hold a requisite label on its own: a heading, a paragraph or a
# division whose whole text is the label - Cabrillo's bold-only <p> - and
# the label cell of a row. Not a list item: in-page tab strips are lists.
_LABEL_BLOCK_TAGS = frozenset({*_HEADINGS, "p", "div", "td", "th", "dt"})
# A label inside a link or a button is something to click on.
_LINK_TAGS = ("a", "button")
# What ends a value read from under a label, whatever it says.
_VALUE_STOP_TAGS = frozenset({*_HEADINGS, "th", "dt"})


def _label_tier(text: str) -> str | None:
    """Which requisite label this text is, or None when it is none."""
    label = collapse(text)
    if COMBINED_REQUISITE_RE.fullmatch(label.rstrip(" :")):
        return _BOTH
    if PREREQUISITE_COURSES_LABEL_RE.fullmatch(label):
        return _COURSES
    if PREREQUISITE_LABEL_RE.fullmatch(label):
        return _PREREQUISITE
    if REQUISITE_LABEL_RE.fullmatch(label):
        return _OTHER
    return None


def _is_site_furniture(tag: Any, main: Any) -> bool:
    """True when this element is the site around the page, not the page.

    What is_chrome says, except for a sidebar inside the page's own main
    container, which belongs to the page: Arapahoe prints every course's
    credits and prerequisite in an <aside> beside its description, inside
    <main>. Discovery keeps that sidebar in main_text for the same reason.
    """
    if (
        tag.name == "aside"
        and main is not None
        and any(parent is main for parent in tag.parents)
    ):
        return False
    return is_chrome(tag)


def _label_blocks(soup: Any) -> list[tuple[Any, str]]:
    """Every element whose whole text is a requisite label, in page order.

    The element is the outermost one printing just the label: the <p>
    around Cabrillo's <strong>Prerequisite</strong>, Foothill's label
    cell. A bold label sharing its line with the value is not one, and the
    line reading takes those, so nothing is read twice.
    """
    main = find_main(soup)
    root = main or soup.body or soup
    found: list[tuple[Any, str]] = []
    seen: set[int] = set()
    for string in root.find_all(string=REQUISITE_WORD_RE):
        if type(string) is not NavigableString:
            continue
        text = element_text(string.parent)
        tier = _label_tier(text)
        if tier is None:
            continue
        block = None
        node = string.parent
        while isinstance(node, Tag) and element_text(node) == text:
            if node.name in _LABEL_BLOCK_TAGS:
                block = node
            node = node.parent
        if block is None or id(block) in seen:
            continue
        seen.add(id(block))
        if _is_site_furniture(block, main) or any(
            _is_site_furniture(up, main) for up in block.parents
        ):
            continue
        if block.find_parent(_LINK_TAGS) or block.find(_LINK_TAGS):
            continue
        if TAB_ROLE_RE.search(block.get("role") or ""):
            continue
        found.append((block, tier))
    return found


def _opens_with_a_label(wrapper: Any) -> bool:
    """True when what holds a label starts with a requisite label.

    Then the wrapper is the requisites' own, and everything after the
    label up to the next one is its value. A wrapper that starts with
    anything else is the page itself, an h1 above the label, and only the
    block right under the label is the value.
    """
    if wrapper is None:
        return False
    first = _first_printed(wrapper.children)
    return first is not None and _label_tier(first[0]) is not None


def _ends_the_value(entry: Any, lines: list[str], first: bool) -> bool:
    """True when this entry under a label is no longer its value.

    The text decides, never the bold: Bakersfield prints the prerequisite
    course in bold under its label, and it is the value.
    """
    if entry is not None and entry.name in _VALUE_STOP_TAGS:
        return True
    if len(lines) == 1:
        text = lines[0]
        if _label_tier(text) is not None:
            return True
        if REQUISITE_CONNECTOR_RE.fullmatch(text):
            return True
        if len(text) <= MAX_FIELD_LABEL_CHARS and text.endswith(":"):
            return True
    return not first and bool(REQUISITE_LEAD_RE.match(lines[0]))


def _read_label_block(label: Any, joiner: str) -> tuple[str, str, str] | None:
    """The value under a label, as printed, with its excerpt and locator.

    The value is what the label's wrapper prints after it, up to the next
    heading or requisite label. A connector joins the next prerequisite on
    to it - eLumen's "Prerequisite A OR Prerequisite B" is one value - and
    nothing else: Cabrillo's AND before a Co-Requisite is the
    corequisite's. Too long to be a prerequisite, the label was a section
    heading, and nothing is read.
    """
    entries = lines_after(label)
    whole = _opens_with_a_label(label.parent)
    statements: list[list[str]] = [[]]
    connectors: list[str] = []
    printed = [element_text(label)]
    index = 0
    while index < len(entries):
        entry, lines = entries[index]
        if _ends_the_value(entry, lines, first=not statements[-1]):
            after = entries[index + 1][1] if index + 1 < len(entries) else []
            joins = (
                bool(statements[-1])
                and len(lines) == 1
                and bool(REQUISITE_CONNECTOR_RE.fullmatch(lines[0]))
                and len(after) == 1
                and _label_tier(after[0]) == _PREREQUISITE
            )
            if not joins:
                break
            connectors.append(lines[0])
            printed.extend([lines[0], after[0]])
            statements.append([])
            index += 2
            continue
        statements[-1].extend(lines)
        printed.extend(lines)
        if not whole:
            break
        index += 1
    parts: list[str] = []
    for position, lines in enumerate(statements):
        if not lines:
            continue
        if parts:
            parts.append(connectors[position - 1])
        parts.append(joiner.join(lines))
    value = " ".join(parts)
    # Morgan prints "None" and then a note under the same heading: the
    # course has no prerequisite, and the note is not one.
    if statements[0] and NO_PREREQUISITE_RE.fullmatch(statements[0][0]):
        value = statements[0][0]
    if not value or len(value) > PREREQUISITE_MAX_CHARS:
        return None
    return value, " ".join(printed), element_path(label.parent)


def _prerequisite_line(content_text: str) -> tuple[str, str, str] | None:
    """The first prerequisite a line of the page prints after its label.

    "Prerequisite: BEH 1001 with a grade of C or better" on a line of its
    own, as Acalog, CourseLeaf, CurriQunet and WordPress print it, or in
    the run of requisites eLumen opens a description with: "... to take
    this course. Prerequisite: Completion of AFAB 210, ENGL 315, and PSY
    301. Corequisite: ...". A label counts at the start of a line or of a
    sentence, never inside one, and the value ends at the next requisite
    label or at the end of its sentence.

    The lines are the ones a browser prints. Antelope Valley's descriptions
    are white-space: pre-wrap, and put "Prerequisite: Completion of ENGR
    905" on a line of its own with only a newline before "Building upon
    the foundational knowledge..."; collapsed into one paragraph, the
    prerequisite ran on to the end of the description's first sentence.

    Inside the paragraph a description is read from, a prerequisite that
    nothing ends is read only as long as a prerequisite can be: a page that
    prints no full stop and no line break between the two would otherwise
    give the whole description as the prerequisite.
    """
    opening = first_paragraph(content_text, limit=None)
    for line in content_text.splitlines():
        for lead in REQUISITE_LEAD_RE.finditer(line):
            before = line[: lead.start()].rstrip()
            if before and not before.endswith((".", ";")):
                continue
            tier = _label_tier(lead.group(0))
            if tier not in (_PREREQUISITE, _BOTH):
                continue
            rest = line[lead.end() :]
            stop = REQUISITE_LEAD_RE.search(rest)
            if stop is not None:
                rest = rest[: stop.start()]
            end = SENTENCE_END_RE.search(rest)
            if end is not None:
                rest = rest[: end.start() + 1]
            value = collapse(rest)
            if not value:
                continue
            ended = stop is not None or end is not None
            run_on = len(value) > PREREQUISITE_RUN_ON_CHARS
            if line == opening and not ended and run_on:
                continue
            printed = collapse(f"{lead.group(0)} {value}")
            # Read whole, a statement naming both relations is turned away
            # by the cleaner like any other, and still decides there is no
            # prerequisite.
            raw = printed if tier == _BOTH else value
            return raw, printed, f"content line {line[:40]!r}"
    return None


def _from_prerequisite_labels(
    soup: Any, content_text: str
) -> dict[str, tuple[Any, str, str]]:
    """The course's prerequisite, read from whatever prints it.

    A label over its value first, as eLumen, SmartCatalog and Drupal print
    one; then a line printing the label and the value together; then
    Clean Catalog's list of courses, which shortens the statement it sits
    beside and stands in only when there is no statement. The first
    statement the page prints decides, one per course, the way the unit
    comes from one reading: a listing of courses discovery took for one
    course would otherwise give several courses' prerequisites in one
    value. A first statement of "None", or naming both relations, decides
    there is none.
    """
    courses = None
    reading = None
    for label, tier in _label_blocks(soup):
        if tier == _BOTH:
            return {}
        if tier == _COURSES:
            courses = courses if courses is not None else label
            continue
        if tier != _PREREQUISITE:
            continue
        reading = _read_label_block(label, " ")
        if reading is not None:
            break
    if reading is None:
        reading = _prerequisite_line(content_text)
    if reading is None and courses is not None:
        reading = _read_label_block(courses, "; ")
    if reading is None:
        return {}
    raw, excerpt, locator = reading
    value = _prerequisite_value(raw)
    if value is None:
        return {}
    return {"course_prerequisites": (value, excerpt, locator)}


def _page_fields(
    entity_type: str, markup: Markup
) -> dict[str, tuple[Any, str, str]]:
    """The name and the description every entity has, from the page itself."""
    found: dict[str, tuple[Any, str, str]] = {}
    name = page_name(markup)
    if name and entity_type in NAME_FIELD:
        found[NAME_FIELD[entity_type]] = (name, name, "h1")
    intro = first_paragraph(markup.content_text, limit=None)
    if intro and entity_type in DESCRIPTION_FIELD:
        found[DESCRIPTION_FIELD[entity_type]] = (intro, intro, "main > p")
    return found


def extract_fields(entity_type: str, html: str) -> list[Any]:
    """Every field this page prints for this entity, read from its markup.

    Raises NothingToExtract when the page prints none, because a record
    with nothing in it is worse than no record: it looks extracted.
    """
    soup = parse(html)
    markup = parse_structure(html)
    if entity_type == ENTITY_COMPETENCY:
        return _competency_drafts(markup)

    # Strongest source first, and each one fills only what the one before
    # it left empty. A field the page labelled says what it is; the course
    # block is what CourseLeaf gives instead of labelled fields, and the
    # heading group what eLumen gives; the page itself is the last resort,
    # because the h1 of a CourseLeaf subject page is the subject's name,
    # not the course's, and eLumen's is the catalog's. A prerequisite
    # printed any way but as a labelled field is read after all of them,
    # by its own label; it fills nothing else.
    sources: list[dict[str, tuple[Any, str, str]]] = []
    if entity_type == ENTITY_COURSE:
        sources = [
            _from_field_pairs(read_field_pairs(soup)),
            _from_course_block(soup),
            _from_course_heading(soup),
            _from_heading_labels(soup),
            # Read from the lines a browser prints, so a prerequisite that
            # a pre-wrap description sets on a line of its own ends there.
            _from_prerequisite_labels(soup, printed_text(soup)),
        ]
    sources.append(_page_fields(entity_type, markup))
    found: dict[str, tuple[Any, str, str]] = {}
    for source in sources:
        # A unit belongs to the number printed with it, so it comes from
        # the reading whose credits are kept or from none: a credits field
        # known only by its class name has no unit, and an eLumen header
        # further down must not lend it one.
        keeps_credits = (
            "course_credits" in source and "course_credits" not in found
        )
        for label, value in source.items():
            if label == "course_credits_unit" and not keeps_credits:
                continue
            found.setdefault(label, value)
    # The page's own name is not a record. Every page has one, so a
    # record holding nothing else is an empty record that looks extracted,
    # which is the one thing this must not produce. A unit is not a field
    # to count either: it is only ever read with the credits.
    read = len(found.keys() - {"course_credits_unit"})
    if read < MIN_FIELDS:
        raise NothingToExtract(
            f"the page prints {read} field(s) this can read from its "
            f"markup, fewer than the {MIN_FIELDS} a record needs"
        )
    return _collect(found)


def _competency_drafts(markup: Markup) -> list[Any]:
    """One draft per outcome the page lists, plus what the list is called."""
    lead_in, items = outcome_list(
        markup.content_text,
        headings={
            *markup.content_headings,
            *([markup.h1] if markup.h1 else []),
        },
        list_items=set(markup.list_items),
    )
    if not items:
        raise NothingToExtract("the page lists no learning outcome")
    drafts = []
    name = page_name(markup)
    if name:
        drafts.append(
            _draft("f_001", "competency_framework_name", name, name, "h1")
        )
    for index, item in enumerate(items, start=len(drafts) + 1):
        drafts.append(
            _draft(
                f"f_{index:03d}",
                "competency_text",
                item,
                item,
                f"outcome list under {lead_in[:40]!r}",
            )
        )
    return drafts
