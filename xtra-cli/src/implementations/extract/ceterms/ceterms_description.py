"""ceterms:description, read from a ceterms:Course: what the course is about.

https://credreg.net/ctdl/terms/description, "Statement, characterization or
account of the entity."

The description as the page shows it: its paragraphs, its own notes
(a transfer note, "Was ANTH 4398."), and none of the requisite statements
that open it. Those are ceterms:prerequisite, ceterms:corequisite,
ceterms:recommends (an Advisory) and ceterms:entryCondition (a Limitation on
Enrollment).

The description is looked for in this order, first one accepted wins:

1. `profile_description`: the description element the platform's markup
   names.
2. `description_class`: an element whose class or id says it is a
   description. Only its opening narrative is read: an element that holds
   a whole program page goes on to headed sections and lists of
   outcomes, which are not the description.
3. `description_label`: the text after a "Description" heading or label.
4. `first_prose`: after the course's title, the first paragraph that reads
   as prose, as Acalog prints it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import Comment, NavigableString, PageElement, Tag

from implementations.discover_rules import (
    COMBINED_REQUISITE_RE,
    COURSE_BLOCK_DESC_CLASS_RE,
    COURSE_BLOCK_TITLE_CLASS_RE,
    LINE_KEEPING_WHITE_SPACE,
    REQUISITE_WORD_RE,
    WHITE_SPACE_STYLE_RE,
    WHITESPACE_RE,
    collapse,
)
from implementations.extract_course import code_at_start
from implementations.extract_platform import DESCRIPTION_SELECTORS
from implementations.extract_run import (
    HEADINGS,
    REASON_NO_CANDIDATE,
    UNPRINTED,
    Occurrence,
    Page,
    Reading,
    class_text,
    css_path,
    shown,
)

PROPERTY = "ceterms:description"
# The classes it is read from, each a CTDL class the command knows.
CLASS = ("ceterms:Course",)

STRATEGY_PROFILE_DESCRIPTION = "profile_description"
STRATEGY_DESCRIPTION_CLASS = "description_class"
STRATEGY_DESCRIPTION_LABEL = "description_label"
STRATEGY_FIRST_PROSE = "first_prose"

REASON_EMPTY_DESCRIPTION = "empty_description"
REASON_REQUISITES_ONLY = "requisites_only"

# A class or id naming a description: courseblockdesc, long_desc,
# course-descr, course-catalog-description, detail-description. Not
# "descs", CourseLeaf's wrapper around every course on the page.
DESCRIPTION_CLASS_RE = re.compile(r"desc(?:r|ription)?(?![a-z])", re.IGNORECASE)

# "Description", "Course Description:", as a heading or a label.
DESCRIPTION_LABEL_RE = re.compile(
    r"^(?:course\s+)?description\s*:?$", re.IGNORECASE
)
LABEL_TAGS = ("h2", "h3", "h4", "h5", "h6", "strong", "b", "dt", "th", "label")

# Elements a browser starts on a line of their own.
BLOCK_TAGS = frozenset(
    {
        "address", "article", "aside", "blockquote", "dd", "details", "div",
        "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form",
        "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main",
        "nav", "ol", "p", "pre", "section", "table", "tbody", "td", "tfoot",
        "th", "thead", "tr", "ul",
    }
)  # fmt: skip
_PARAGRAPH = "\x00"

# The labels of the statements that open a description and belong to
# another property: prerequisites, corequisites, concurrent enrollment,
# advisories and recommendations (ceterms:recommends), limitations on
# enrollment (ceterms:entryCondition). One CourseLeaf theme writes them "PR:"
# and "CR:", in capitals.
_LEAD_LABEL = (
    rf"(?i:{COMBINED_REQUISITE_RE.pattern}"
    r"|\b(?:pre|co)[\s-]?req(?:uisite)?s?(?:\s*\(s\))?"
    r"|\bconcurrent(?:ly)?(?:\s+enrollment)?(?:\s+in)?"
    r"|\badvisor(?:y|ies)|\brecommended(?:\s+\w+)?"
    r"|\blimitations?\s+on\s+enrollment|\benrollment\s+limitations?)"
    r"|\b(?:PR|CR)\b[^:\n]{0,12}"
)
LEAD_LABEL_RE = re.compile(rf"\s*(?:{_LEAD_LABEL})\s*:")
# A statement on the same line as the description ends with its sentence
# ("experience.&nbsp;This").
LEAD_SENTENCE_RE = re.compile(
    rf"{LEAD_LABEL_RE.pattern}"
    r"[^\n]*?(?:[.!?][\"')\]]*[^\S\n]+(?=[A-Z(])|$)"
)
# A statement no sentence mark ends runs into the description: "PR: Consent
# Study of place as…", "…Placement by Multiple Measures This honors course,
# intended for…". The description starts at a capitalized word that follows
# a capitalized word or a number and is followed by lower-case words, and
# its sentence says nothing a requisite says. Course names keep to the
# statement: "Intermediate Algebra or higher or placement…", "Social Work or
# instructor permission…", "Honors College in good academic standing…",
# "ACT Math with a score of 24…".
WORD_RE = re.compile(r"\S+")
TITLE_WORD_RE = re.compile(r"[A-Z][a-z]+")
LOWER_RUN_WORDS = 4
REQUISITE_TERMS_RE = re.compile(
    r"\b(?:consent|permission|approval|standing|score|placement|instructor"
    r"|completion|completed|concurrent(?:ly)?|enroll(?:ment|ed)?|admission"
    r"|admitted|eligib\w*|grade|requisites?)\b",
    re.IGNORECASE,
)

# A line of credits and hours, every sentence of it: "Three credit
# hours.", "One, two, or three credit hours.", "Three hours lecture. Two
# hours laboratory per week. Four credit hours.", and the misspelt ones
# ("Threes credit hours.", "Seminar hours lecture."). A sentence that
# names the unit and is short; a word or two between them ("Three.").
CREDIT_UNIT_RE = re.compile(
    r"\b(?:credits?|hours?|hrs?|units?)\b", re.IGNORECASE
)
CREDIT_SENTENCE_WORDS = 14
CREDIT_LINE_MAX = 160
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
# "Credits Hours: 3", "Required: Elective": a short label and its value.
LABEL_LINE_RE = re.compile(r"^[^:.]{1,40}:\s*(?P<value>.*)$")
SENTENCE_END_RE = re.compile(r"[.!?][\"')\]]*$")
# Fewer words than this, a line has to end as a sentence to be prose.
PROSE_WORDS = 8

# Inside a description element, these end its narrative once it has begun.
LIST_TAGS = frozenset({"ul", "ol", "dl", "table"})


@dataclass(frozen=True)
class _Candidate:
    text: str
    strategy: str
    css_path: str
    # True when the element found is the course's own description element,
    # so an empty one means the course has none, not "look further".
    is_description_element: bool


def shown_text(tag: Tag, nodes: list[PageElement] | None = None) -> str:
    """The element's text the way a browser shows it.

    Whitespace collapses to one space, except where a `white-space` style
    keeps lines (eLumen's `pre-wrap`), which keeps it as written. A <br>
    is a line break. Block elements are paragraphs, joined by a blank
    line. Site furniture and anything hidden is left out. With `nodes`,
    only those children of the element are read.
    """
    pieces: list[tuple[str, bool]] = []
    _walk_nodes(
        tag.children if nodes is None else nodes,
        pieces,
        keeps_lines=_keeps_lines(tag, inherited=_inherits(tag)),
    )
    paragraphs = "".join(text for text, _ in pieces).split(_PARAGRAPH)
    return "\n\n".join(p.strip() for p in paragraphs if p.strip())


def _inherits(tag: Tag) -> bool:
    keeps = False
    for node in reversed(list(tag.parents)):
        if isinstance(node, Tag):
            keeps = _keeps_lines(node, inherited=keeps)
    return keeps


def _keeps_lines(tag: Tag, *, inherited: bool) -> bool:
    match = WHITE_SPACE_STYLE_RE.search(tag.get("style") or "")
    if match is not None:
        return match.group(1).lower() in LINE_KEEPING_WHITE_SPACE
    return inherited or tag.name == "pre"


def _walk(
    node: Tag, pieces: list[tuple[str, bool]], *, keeps_lines: bool
) -> None:
    _walk_nodes(node.children, pieces, keeps_lines=keeps_lines)


def _walk_nodes(
    nodes, pieces: list[tuple[str, bool]], *, keeps_lines: bool
) -> None:
    for child in nodes:
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString):
            _add_text(pieces, str(child), keeps_lines)
            continue
        if not isinstance(child, Tag) or child.name in UNPRINTED:
            continue
        if not shown(child):
            continue
        if child.name == "br":
            _end_line(pieces, keeps_lines)
            continue
        block = child.name in BLOCK_TAGS
        if block:
            pieces.append((_PARAGRAPH, False))
        _walk(
            child,
            pieces,
            keeps_lines=_keeps_lines(child, inherited=keeps_lines),
        )
        if block:
            pieces.append((_PARAGRAPH, False))


def _add_text(pieces: list[tuple[str, bool]], text: str, keeps: bool) -> None:
    text = text.replace("\r", "")
    if not keeps:
        text = WHITESPACE_RE.sub(" ", text)
        # A space at the start of a line doesn't show.
        if not pieces or pieces[-1][0].endswith(("\n", " ", _PARAGRAPH)):
            text = text.lstrip(" ")
    if text:
        pieces.append((text, keeps))


def _end_line(pieces: list[tuple[str, bool]], keeps: bool) -> None:
    # Nor does a space at the end of one, outside a pre-wrap.
    if pieces and not pieces[-1][1]:
        pieces[-1] = (pieces[-1][0].rstrip(" "), False)
    pieces.append(("\n", keeps))


def drop_lead_statements(text: str) -> str:
    """The text without the requisite statements that open it.

    A statement on a line of its own is the whole line, however many
    sentences it runs to. One the description follows on the same line
    ends with its sentence: "PR: PHAR 191. Supervised practice." is
    "Supervised practice.". One with no sentence mark ends where the
    description's first sentence starts.
    """
    text = text.strip()
    while LEAD_LABEL_RE.match(text):
        line, newline, rest = text.partition("\n")
        start = _unpunctuated_end(line)
        if start is not None:
            text = (line[start:] + newline + rest).strip()
            continue
        if newline and rest.strip():
            text = rest.strip()
            continue
        match = LEAD_SENTENCE_RE.match(line)
        text = line[match.end() :].strip() if match else ""
    return text


def _unpunctuated_end(line: str) -> int | None:
    """Where the description starts inside a lead statement's first
    sentence, when no sentence mark ends the statement; None otherwise."""
    label = LEAD_LABEL_RE.match(line)
    sentence = LEAD_SENTENCE_RE.match(line)
    if label is None or sentence is None:
        return None
    words = list(WORD_RE.finditer(line, label.end(), sentence.end()))
    for index in range(1, len(words)):
        previous, word = words[index - 1].group(), words[index].group()
        if not (previous[0].isupper() or previous[0].isdigit()):
            continue
        if not previous[-1].isalnum() or not TITLE_WORD_RE.fullmatch(word):
            continue
        following = words[index + 1 : index + 1 + LOWER_RUN_WORDS]
        if len(following) < LOWER_RUN_WORDS or not all(
            w.group()[0].islower() for w in following
        ):
            continue
        description = line[words[index].start() :]
        first_sentence = SENTENCE_SPLIT_RE.split(description)[0]
        if len(
            first_sentence.split()
        ) >= PROSE_WORDS and not REQUISITE_TERMS_RE.search(first_sentence):
            return words[index].start()
    return None


def _without_label(text: str) -> str:
    """Without a first paragraph or line that only says "Description"."""
    first, _, rest = text.partition("\n")
    if DESCRIPTION_LABEL_RE.match(first.strip()):
        return rest.strip()
    return text


def read(occurrence: Occurrence, page: Page) -> Reading:
    """The course's description, read from inside one occurrence."""
    for find in (
        _profile_description,
        _description_class,
        _description_label,
        _first_prose,
    ):
        candidate = find(occurrence, page)
        if candidate is None:
            continue
        value = _without_label(drop_lead_statements(candidate.text))
        if value:
            return Reading(
                value=value,
                raw_text=candidate.text,
                strategy=candidate.strategy,
                css_path=candidate.css_path,
            )
        if candidate.is_description_element:
            return Reading(
                value=None,
                raw_text=candidate.text,
                strategy=candidate.strategy,
                css_path=candidate.css_path,
                reason=(
                    REASON_REQUISITES_ONLY
                    if candidate.text
                    else REASON_EMPTY_DESCRIPTION
                ),
            )
    return Reading(
        value=None,
        raw_text=None,
        strategy="",
        css_path=occurrence.css_path,
        reason=REASON_NO_CANDIDATE,
    )


def _element(tag: Tag, strategy: str) -> _Candidate:
    return _Candidate(
        text=shown_text(tag),
        strategy=strategy,
        css_path=css_path(tag),
        is_description_element=True,
    )


def _profile_description(
    occurrence: Occurrence, page: Page
) -> _Candidate | None:
    """The first description element the platform names."""
    for selector in DESCRIPTION_SELECTORS.get(page.platform, ()):
        for tag in occurrence.element.select(selector):
            if shown(tag):
                return _element(tag, STRATEGY_PROFILE_DESCRIPTION)
    return None


def _description_class(occurrence: Occurrence, page: Page) -> _Candidate | None:
    """The first element whose class or id says it is a description, or
    is one of the description classes discovery reads (CourseLeaf's
    `courseblockextra`).

    Not one that names a requisite, as CurriQunet's
    `course-requisite-description-row` does, and not a title.
    """
    for tag in occurrence.element.find_all(True):
        words = f"{class_text(tag)} {tag.get('id') or ''}"
        if not (
            DESCRIPTION_CLASS_RE.search(words)
            or COURSE_BLOCK_DESC_CLASS_RE.search(words)
        ):
            continue
        if REQUISITE_WORD_RE.search(
            words
        ) or COURSE_BLOCK_TITLE_CLASS_RE.search(words):
            continue
        if not shown(tag):
            continue
        return _Candidate(
            text=shown_text(tag, _narrative(tag)),
            strategy=STRATEGY_DESCRIPTION_CLASS,
            css_path=css_path(tag),
            is_description_element=True,
        )
    return None


def _narrative(tag: Tag) -> list[PageElement]:
    """The children of a description element that make its opening
    narrative.

    Headings before it are passed over: a tagline, a provider number. A
    "Description" heading among them starts it. It ends at the next heading
    or list, and the line that leads into a list ("By the end of the
    course, students will:", "Courses in the Series") goes with the list.
    An element with no heading or list after its text is read whole.
    """
    children = list(tag.children)
    for index, child in enumerate(children):
        if (
            isinstance(child, Tag)
            and child.name in HEADINGS
            and DESCRIPTION_LABEL_RE.match(shown_text(child))
        ):
            children = children[index + 1 :]
            break

    nodes: list[PageElement] = []
    for child in children:
        if isinstance(child, Tag) and shown(child):
            begun = bool(shown_text(tag, nodes))
            if child.name in HEADINGS:
                if begun:
                    break
                continue
            if child.name in LIST_TAGS and begun:
                _drop_lead_in(tag, nodes)
                break
        nodes.append(child)
    return nodes


def _drop_lead_in(tag: Tag, nodes: list[PageElement]) -> None:
    """Drop the last line before a list when it introduces the list."""
    for index in range(len(nodes) - 1, -1, -1):
        line = shown_text(tag, [nodes[index]])
        if not line:
            continue
        if line.endswith(":") or (
            len(line.split()) < PROSE_WORDS and not SENTENCE_END_RE.search(line)
        ):
            del nodes[index:]
        return


def _description_label(occurrence: Occurrence, page: Page) -> _Candidate | None:
    """What follows a "Description" heading or label, up to the next
    heading or label."""
    for label in occurrence.element.find_all(LABEL_TAGS):
        if not DESCRIPTION_LABEL_RE.match(shown_text(label)) or not shown(
            label
        ):
            continue
        parts: list[str] = []
        for sibling in label.next_siblings:
            if isinstance(sibling, Tag) and (
                sibling.name in LABEL_TAGS or sibling.name == "hr"
            ):
                break
            if isinstance(sibling, Tag):
                if shown(sibling):
                    parts.append(shown_text(sibling))
            elif isinstance(sibling, NavigableString) and not isinstance(
                sibling, Comment
            ):
                parts.append(collapse(str(sibling)))
        text = "\n\n".join(p for p in parts if p)
        if text:
            return _Candidate(
                text=text,
                strategy=STRATEGY_DESCRIPTION_LABEL,
                css_path=css_path(label.parent or label),
                is_description_element=False,
            )
    return None


def _first_prose(occurrence: Occurrence, page: Page) -> _Candidate | None:
    """After the course's title, the first paragraph that reads as prose.

    Acalog prints a course as runs of text between <br>s: the credits,
    the description, then "Prerequisites:" and other labelled lines. The
    title and every heading are passed over, and so is anything after an
    <hr> that follows text.
    """
    for paragraph in _paragraphs_after_title(occurrence):
        lines = drop_lead_statements(paragraph).split("\n")
        for index, line in enumerate(lines):
            line = line.strip()
            if _passed_over(line):
                continue
            if not _is_prose(line):
                break
            return _Candidate(
                text="\n".join(lines[index:]).strip(),
                strategy=STRATEGY_FIRST_PROSE,
                css_path=occurrence.css_path,
                is_description_element=False,
            )
    return None


def _paragraphs_after_title(occurrence: Occurrence) -> list[str]:
    """The occurrence's paragraphs after its title, up to an <hr> that
    ends them. Headings and title elements are never read."""
    reader = _AfterTitle(_title(occurrence.element))
    reader.walk(occurrence.element)
    text = "".join(reader.pieces_text())
    paragraphs: list[str] = []
    for block in text.split(_PARAGRAPH):
        paragraphs.extend(p.strip() for p in block.split("\n\n") if p.strip())
    return paragraphs


class _AfterTitle:
    """One walk, reading only what comes after the title."""

    def __init__(self, title: Tag | None) -> None:
        self.title = title
        self.started = title is None
        self.stopped = False
        self.pieces: list[tuple[str, bool]] = []

    def pieces_text(self) -> list[str]:
        return [text for text, _ in self.pieces]

    def _has_text(self) -> bool:
        return bool("".join(self.pieces_text()).strip(_PARAGRAPH + " \n"))

    def walk(self, node: Tag) -> None:
        for child in node.children:
            if self.stopped:
                return
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                if self.started:
                    _add_text(self.pieces, str(child), False)
                continue
            if not isinstance(child, Tag) or child.name in UNPRINTED:
                continue
            if child is self.title or _is_title_like(child):
                # Never read; reading starts after the title, or after
                # the heading the title is printed in.
                if self.title is not None and (
                    child is self.title or _contains(child, self.title)
                ):
                    self.started = True
                continue
            if not shown(child):
                continue
            if child.name == "hr":
                if self.started and self._has_text():
                    self.stopped = True
                    return
                continue
            if child.name == "br":
                if self.started:
                    _end_line(self.pieces, False)
                continue
            block = child.name in BLOCK_TAGS
            if block and self.started:
                self.pieces.append((_PARAGRAPH, False))
            self.walk(child)
            if block and self.started:
                self.pieces.append((_PARAGRAPH, False))


def _contains(tag: Tag, inner: Tag) -> bool:
    return any(parent is tag for parent in inner.parents)


def _is_title_like(tag: Tag) -> bool:
    if tag.name in HEADINGS:
        return True
    return bool(COURSE_BLOCK_TITLE_CLASS_RE.search(class_text(tag)))


def _title(root: Tag) -> Tag | None:
    """The course's title element: its title class, else its first
    shown heading."""
    for tag in root.find_all(True):
        if COURSE_BLOCK_TITLE_CLASS_RE.search(class_text(tag)) and shown(tag):
            return tag
    for tag in root.find_all(HEADINGS):
        if shown(tag) and shown_text(tag):
            return tag
    return None


def _passed_over(line: str) -> bool:
    """A line that comes before a description and isn't one."""
    if not any(char.isalpha() for char in line):
        return True
    if _is_credit_line(line):
        return True
    if code_at_start(line) is not None:
        return True
    # "Offered: Spring even years." is a field; "Progressive Prosecution:
    # Law & Policy is a seminar course." is a description.
    label = LABEL_LINE_RE.match(line)
    if label is None:
        return False
    value = label.group("value")
    return len(value.split()) < PROSE_WORDS or not _is_prose(value)


def _is_credit_line(line: str) -> bool:
    if len(line) > CREDIT_LINE_MAX:
        return False
    return all(
        _is_credit_sentence(sentence)
        for sentence in SENTENCE_SPLIT_RE.split(line.strip())
    )


def _is_credit_sentence(sentence: str) -> bool:
    words = len(sentence.split())
    if words <= 2:
        return True
    return words <= CREDIT_SENTENCE_WORDS and bool(
        CREDIT_UNIT_RE.search(sentence)
    )


def _is_prose(line: str) -> bool:
    if not any(char.islower() for char in line):
        return False
    words = len(line.split())
    if words >= PROSE_WORDS:
        return True
    return words >= 2 and SENTENCE_END_RE.search(line) is not None
