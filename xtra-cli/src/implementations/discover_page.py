"""What one saved page is, read from the page itself.

The crawler saved bytes. This turns one of those pages into a profile: what
it prints, which of the printed things look like field labels, which special
cases it carries, and what it is. Every literal it consults lives in
discover_rules, so the reasoning here stays readable.

Two readings of the page meet here. discover_dom reads the markup as a
tree and reports what the publisher marked up: the page's own content, the
elements that are course descriptions, the tables that are requirement
lists, and any machine readable declaration of what the page is.
discover_rules reads the flattened text for everything a sentence says.
The tree is believed first where the two overlap, because a page that
marks its course descriptions up has told us where they are, and the
prose rules are what answer for the many catalogs that mark up nothing.
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass
from typing import Any, NamedTuple

from implementations.discover_dom import Markup, read_markup
from implementations.discover_ner import (
    Entity,
    entities_by_kind,
    read_entities,
)
from implementations.discover_rules import (
    ARCHIVED_RE,
    AWARD_DECLARATION_RE,
    CEU_RE,
    COREQUISITE_RE,
    COURSE_CODE_HEAD_CHARS,
    COURSE_CODE_RE,
    COURSE_TITLE_RE,
    DECLARATION_REACH_CHARS,
    DECLARATION_REACH_LINES,
    EMPTY_OR_ERROR_RE,
    EMPTY_PAGE_CHARS,
    HEAD_LINE_CHARS,
    HEAD_MAX_LINES,
    INTRO_CHARS,
    LAB_CLINICAL_HOURS_RE,
    LABEL_COMPETENCY,
    LABEL_COURSE,
    LABEL_CREDENTIAL,
    LABEL_LEARNING_OPPORTUNITY,
    LECTURE_LAB_CREDIT_RE,
    MAX_FIELD_LABEL_CHARS,
    MIN_COURSE_LIST_CODES,
    MIN_OUTCOME_ITEMS,
    MIN_PLAN_CODES,
    MIN_TERM_HEADINGS,
    OUTCOME_LEAD_GAP_LINES,
    PAGE_TYPE_MULTIPLE,
    PAGE_TYPE_UNKNOWN,
    POLICY_OR_DEFINITION_RE,
    PREREQ_COREQ_COMBINED_RE,
    PREREQUISITE_RE,
    PRINTED_ZERO_HOURS_RE,
    RECOMMENDED_RE,
    REQUIREMENT_WORD_RE,
    REQUIREMENTS_HEADING_RE,
    SECTION_HEADING_CHARS,
    SHORT_LINE_CHARS,
    TERM_HEADING_RE,
    TITLE_SEPARATOR_RE,
    award_in_heading,
    award_in_intro,
    award_in_name,
    award_in_name_line,
    catalog_year_value,
    course_block_count,
    course_codes,
    distinct_awards,
    evidence,
    has_program_structure,
    heading_body,
    is_contact_line,
    is_outcome_statement,
    is_outcomes_lead_in,
    names_a_list_or_rule,
    names_a_listing,
    names_an_organization_or_policy,
    near_course_code,
    normalize_course_code,
    normalize_field_label,
    path_names_courses,
    program_structure_terms,
    quote_around,
    singular_award,
    total_credits_line,
    url_label,
    url_template,
)
from implementations.engine import load_engine


def normalized_text(html: str) -> str:
    """Visible text, via the normalizer the extractors already agree on."""
    load_engine()
    from normalize import normalize_html

    return normalize_html(html)


def outcome_list(
    content_text: str, *, headings: set[str], list_items: set[str]
) -> tuple[str, list[str]]:
    """The page's first list of learning outcomes: its lead-in and items.

    A list is a lead-in and at least MIN_OUTCOME_ITEMS outcomes directly
    after it, read from the page's own content lines so the markup does not
    matter: Clean Catalog puts the lead-in in a <div> and its outcomes in
    <li>s, Coursedog puts each outcome in a <div> of its own. An item is a
    list item, or a line that reads as an outcome ("Demonstrate...", "An
    ability to..."). A sentence may sit between the lead-in and its first
    item; a heading may not, and the first line after the items that is not
    one ends the list.

    Discovery needs only the lead-in, to say the page carries a competency
    list. Extraction needs the items, because each one is a competency.
    """
    lines = content_text.splitlines()
    for index, line in enumerate(lines):
        if not is_outcomes_lead_in(line):
            continue
        found: list[str] = []
        gap = 0
        for following in lines[index + 1 :]:
            if _is_outcome_item(following, list_items):
                found.append(following)
                continue
            if found or following in headings or is_outcomes_lead_in(following):
                break
            gap += 1
            if gap > OUTCOME_LEAD_GAP_LINES:
                break
        if len(found) >= MIN_OUTCOME_ITEMS:
            return evidence(line), found
    return "", []


def outcome_list_evidence(
    content_text: str, *, headings: set[str], list_items: set[str]
) -> str:
    """The lead-in of the page's first list of learning outcomes, or ""."""
    return outcome_list(content_text, headings=headings, list_items=list_items)[
        0
    ]


# A list typed as text, one bullet character per line, is still a list.
_TEXT_BULLETS = ("•", "·", "▪", "◦")


def _is_outcome_item(line: str, list_items: set[str]) -> bool:
    """An outcome statement, or a list item that could be one.

    A list item needs two words, and cannot be a course or a purpose ("To
    provide a broad flexible program"), which is how a program writes what
    it does rather than what its students learn.
    """
    if is_outcome_statement(line):
        return True
    return (
        (line in list_items or line.startswith(_TEXT_BULLETS))
        and len(line.split()) >= 2
        and not line.endswith(":")
        and not line.lower().startswith("to ")
        and not COURSE_TITLE_RE.match(line)
    )


def parse_structure(html: str) -> Markup:
    """One page's markup, with its outcome list found.

    The tree reading happens in discover_dom. Whether a list of lines is a
    list of learning outcomes is a question about the words, so it is
    answered here, against the content the tree handed back.
    """
    markup = read_markup(html)
    markup.outcomes_evidence = outcome_list_evidence(
        markup.content_text,
        headings={
            *markup.content_headings,
            *([markup.h1] if markup.h1 else []),
        },
        list_items=set(markup.list_items),
    )
    return markup


def field_labels_of(structure: Markup, text: str) -> list[str]:
    """Label-shaped text from the markup and from short lines ending in a colon."""
    candidates = list(structure.label_texts)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.endswith(":") and len(stripped) <= MAX_FIELD_LABEL_CHARS:
            candidates.append(stripped)
    labels = {
        label
        for label in (normalize_field_label(raw) for raw in candidates)
        if label
    }
    return sorted(labels)


def page_head(structure: Markup, text: str) -> str:
    """The heading area: the title, the h1, and the first lines of text.

    A course page prints its code here. The same code further down the
    page is a cross-reference or a prerequisite.

    The lines are the heading area of the page's own content, not the
    first 300 characters of the document. Those are a CourseLeaf page's
    Quicklinks menu, so read whole the heading area of every page in that
    catalog was "Skip to Content AZ Index Catalog Home Campus Map"; read
    as 300 characters of content they are the first rows of whatever the
    page opens with, and a degree plan opens with a table of courses.
    """
    opening = (
        "\n".join(head_lines(structure.content_text))
        or text[:COURSE_CODE_HEAD_CHARS]
    )
    return f"{structure.title} {structure.h1} {opening}"


def title_name(title: str) -> str:
    """A <title> without the site: "Programs | Example College" is Programs."""
    return TITLE_SEPARATOR_RE.split(title)[0].strip()


def page_name(structure: Markup) -> str:
    """What the page calls itself: its h1, or its title without the site."""
    return structure.h1 or title_name(structure.title)


def head_lines(content_text: str) -> list[str]:
    """The short lines that open the content, up to its first paragraph.

    This is where Clean Catalog prints the badge naming a program's award,
    one line above the program's name, and where CourseLeaf prints
    "Graduate Microcertificate in Analytics" one line below it.
    """
    lines: list[str] = []
    used = 0
    for line in content_text.splitlines():
        if (
            len(line) > HEAD_LINE_CHARS
            or len(lines) >= HEAD_MAX_LINES
            or used + len(line) > COURSE_CODE_HEAD_CHARS
        ):
            break
        lines.append(line)
        used += len(line)
    return lines


def first_paragraph(content_text: str) -> str:
    """The first line of the content long enough to be a paragraph.

    Not the contact block a bulletin opens with. "Dr. David Welky, Chair,
    Department of History, Irby 105B, (501) 450-5624" is long enough to
    be a paragraph and is not one, and taking it made a minor's
    description a string of telephone numbers and hid the sentence under
    it that says which award the page is about.
    """
    for line in content_text.splitlines():
        if len(line) > HEAD_LINE_CHARS and not is_contact_line(line):
            return line[:INTRO_CHARS]
    return ""


class Award(NamedTuple):
    """An award a page names, and the words around it that show where."""

    award: str
    quote: str


@dataclass
class ProgramEvidence:
    """What a page's own content says about a program and its award.

    Two questions, kept apart. Does the page print a program's own
    requirements: a marked-up requirement list, a credit total, a
    requirements heading over a course list, a plan of study, or a heading
    naming the award those requirements are for? And where does it name
    the award: in its name, beside its name, in a section heading, after
    "Degrees Conferred", or in its first paragraph? Nothing here reads the
    site's menus.
    """

    template: str = ""
    name: str = ""
    total_credits: str = ""
    requirements_heading: str = ""
    award_requirements_heading: str = ""
    awards_in_headings: tuple[str, ...] = ()
    term_headings: int = 0
    course_codes: int = 0
    name_award: Award | None = None
    head_award: Award | None = None
    heading_award: Award | None = None
    declared_award: Award | None = None
    intro_award: Award | None = None
    organization_or_policy: bool = False
    listing: bool = False
    list_or_rule: bool = False
    url_label: str | None = None
    mentions_requirements: bool = False
    requirement_list: str = ""

    @property
    def prints_requirements(self) -> bool:
        """The page prints a program's own requirements.

        A requirement list the platform marked up settles it on its own.
        CourseLeaf writes every one of them as `table.sc_courselist`, and
        a certificate page whose whole content is that table prints no
        total, no requirements heading and no term headings, so on the
        prose alone it read as nothing at all.

        A heading naming the page's one award, standing over a list of
        courses, counts for the same reason a requirements heading does.
        The bulletin at Central Arkansas heads the section
        "Baccalaureate Degree: Bachelor of Science" and lists the tracks
        under it, and never prints the word requirement or a total.
        """
        listed = (
            self.course_codes >= MIN_COURSE_LIST_CODES
            or self.term_headings >= MIN_TERM_HEADINGS
        )
        plan = (
            self.term_headings >= MIN_TERM_HEADINGS
            and self.course_codes >= MIN_PLAN_CODES
        )
        award_over_a_list = (
            self.heading_award is not None
            and not self.names_several_awards
            and self.course_codes >= MIN_PLAN_CODES
        )
        return bool(
            self.requirement_list
            or self.total_credits
            or self.award_requirements_heading
            or self.declared_award
            or (self.requirements_heading and listed)
            or plan
            or award_over_a_list
        )

    @property
    def names_several_awards(self) -> bool:
        """The page's headings name more than one award.

        "Accounting (ACCT)" at the University of Arkansas heads sections
        for a B.S.B.A., a Master of Accountancy and a Ph.D.; the School of
        Music at Central Arkansas heads sections for a B.A., a B.M., a
        B.M.E. and a master's. Each is a department printing the
        requirements of every credential it offers, not one credential.
        """
        return len(self.awards_in_headings) > 1

    @property
    def is_program(self) -> bool:
        """A program's own page, not a college's overview or a rule's.

        A college's page and a graduation policy both print requirements
        and both name awards, for every program at once. Only a heading
        naming the award those requirements are for makes such a page a
        program's: "Requirements for B.S.N. in Nursing" on the page of a
        school of nursing - and then only when that award is the one award
        the page is about. A School of Music heads a section
        "Bachelor of Music Education Large Ensemble Requirements" and
        offers four degrees, so the heading says which requirements they
        are, not what the page is.

        A page named as a list ("Graduate Certificates") is a program's
        only when a badge names its one award, as "Professional Series"
        does on "Bookkeeper Credentials".
        """
        if not self.prints_requirements:
            return False
        if self.listing and self.head_award is None:
            return False
        if not self.organization_or_policy:
            return True
        return bool(self.award_requirements_heading) and not (
            self.names_several_awards
        )

    @property
    def lists_its_own_requirements(self) -> bool:
        """Why a page full of course codes is not a run of descriptions."""
        return bool(
            self.prints_requirements
            or self.mentions_requirements
            or self.name_award
            or self.url_label
        )

    def requirements_quote(self) -> str:
        """The strongest evidence that the page prints requirements."""
        for value in (
            self.award_requirements_heading,
            self.total_credits,
            self.requirements_heading,
            self.declared_award.quote if self.declared_award else "",
            self.requirement_list,
        ):
            if value:
                return evidence(value)
        return f"{self.term_headings} term headings, {self.course_codes} codes"

    def award_in_content(self) -> tuple[str, Award] | None:
        """Where the page names its award, other than in its name."""
        for where, found in (
            ("award beside the name", self.head_award),
            ("award in a heading", self.heading_award),
            ("award declared", self.declared_award),
            ("award in the first paragraph", self.intro_award),
        ):
            if found is not None:
                return where, found
        return None


def _quoted(text: str, award: str | None) -> Award | None:
    """The award with the words around it, so a reviewer sees where."""
    return Award(award, quote_around(text, award)) if award else None


def _declared_award(lines: list[str]) -> Award | None:
    """The award a declaration names: "Degrees Conferred: M.S.E.E.".

    The label can name the award itself, as "Graduate Certificate Offered:"
    does, so it is read together with the lines after it.
    """
    for index, line in enumerate(lines):
        if AWARD_DECLARATION_RE.match(line) is None:
            continue
        reach = "\n".join(lines[index : index + 1 + DECLARATION_REACH_LINES])[
            :DECLARATION_REACH_CHARS
        ]
        award = singular_award(reach)
        if award:
            return Award(award, quote_around(reach, award))
    return None


def _badge_award(lines: list[str]) -> Award | None:
    """The award named by a badge line beside the page's name, if one is."""
    for line in lines:
        award = award_in_name_line(line)
        if award:
            return Award(award, quote_around(line, award))
    return None


def read_program_evidence(structure: Markup, template: str) -> ProgramEvidence:
    """Read one page for the program and credential rules.

    Headings are the page's h2 to h6, each without the outline number a
    catalog may print in front of it. Short lines stand in for headings a
    catalog prints as a bold run or a table cell. Neither may be the page's
    own name, which is not a section of it, or a course title, which
    CourseLeaf prints as a heading.
    """
    text = structure.content_text
    name = page_name(structure)
    own = {
        value.lower()
        for value in (name, structure.h1, title_name(structure.title))
        if value
    }

    def is_section(line: str) -> bool:
        return line.lower() not in own and not COURSE_TITLE_RE.match(line)

    lines = text.splitlines()
    headings = [
        body
        for heading in structure.content_headings
        if len(heading) <= SECTION_HEADING_CHARS
        and is_section(body := heading_body(heading))
    ]
    short_lines = [
        heading_body(line)
        for line in lines
        if len(line) <= SHORT_LINE_CHARS and is_section(line)
    ]
    candidates = headings + short_lines

    requirements = next(
        (line for line in candidates if REQUIREMENTS_HEADING_RE.match(line)),
        "",
    )
    award_requirements = next(
        (
            heading
            for heading in headings
            if REQUIREMENT_WORD_RE.search(heading) and award_in_heading(heading)
        ),
        "",
    )
    awards_in_headings = distinct_awards(
        [award for heading in headings if (award := award_in_heading(heading))]
    )
    heading_award = next(
        (
            Award(award, evidence(heading))
            for heading in headings
            if (award := award_in_heading(heading))
        ),
        None,
    )
    total = total_credits_line(lines)
    # The name is judged by its own rule, which refuses a list or a policy;
    # the badge beside it must not let the same words back in.
    head = [line for line in head_lines(text) if line.lower() not in own]
    intro = first_paragraph(text)

    return ProgramEvidence(
        template=template,
        name=name,
        total_credits=evidence(total) if total else "",
        requirements_heading=requirements,
        award_requirements_heading=award_requirements,
        awards_in_headings=tuple(awards_in_headings),
        term_headings=len(
            {line for line in candidates if TERM_HEADING_RE.match(line)}
        ),
        course_codes=len(
            {normalize_course_code(code) for code in course_codes(text)}
        ),
        requirement_list=(
            structure.requirement_lists[0]
            if structure.requirement_lists
            else ""
        ),
        name_award=_quoted(name, award_in_name(name)),
        head_award=_badge_award(head),
        heading_award=heading_award,
        declared_award=_declared_award(lines),
        intro_award=_quoted(intro, award_in_intro(intro, name)),
        organization_or_policy=names_an_organization_or_policy(name),
        listing=names_a_listing(name),
        list_or_rule=names_a_list_or_rule(name),
        url_label=url_label(template),
        mentions_requirements=has_program_structure(
            program_structure_terms(lines)
        ),
    )


def program_label(
    program: ProgramEvidence,
) -> tuple[str, str, Award | None] | None:
    """Credential or LearningOpportunity, the rule that fired, and the award.

    In order, strongest first:

    - the page's name names one award: a Credential, whatever else it is
    - the page prints a program's requirements: a Credential when it names
      the award anywhere in its content, a LearningOpportunity when not
    - the URL is a program's or a credential's: a Credential when the page
      names one award, otherwise what the URL says, unless the page's name
      says it is a list or a rule
    """
    if program.name_award is not None:
        return (
            LABEL_CREDENTIAL,
            f"award in the name: {program.name_award.award}",
            program.name_award,
        )
    found = program.award_in_content()
    if program.is_program:
        if found is not None:
            where, award = found
            return LABEL_CREDENTIAL, f"{where}: {award.award}", award
        return (
            LABEL_LEARNING_OPPORTUNITY,
            f"program requirements, no award: {program.requirements_quote()}",
            None,
        )
    if program.url_label is not None and not program.list_or_rule:
        if found is not None:
            where, award = found
            return (
                LABEL_CREDENTIAL,
                f"url template {program.template} and {where}: {award.award}",
                award,
            )
        return program.url_label, f"url template {program.template}", None
    return None


def detect_markers(
    text: str,
    structure: Markup,
    *,
    blocks: int,
    visible_chars: int,
    program: ProgramEvidence,
) -> dict[str, str]:
    """Every special case this page carries, with a quote showing why."""
    markers: dict[str, str] = {}

    lecture = LECTURE_LAB_CREDIT_RE.search(text)
    if lecture is not None and near_course_code(text, lecture):
        markers["lecture_lab_credit_numbers"] = evidence(text, lecture)

    for name, rule in (
        ("lab_clinical_field_study_hours", LAB_CLINICAL_HOURS_RE),
        ("printed_zero_hours", PRINTED_ZERO_HOURS_RE),
        ("ceu", CEU_RE),
        ("prerequisite_corequisite_combined", PREREQ_COREQ_COMBINED_RE),
        ("prerequisite", PREREQUISITE_RE),
        ("corequisite", COREQUISITE_RE),
        ("recommended", RECOMMENDED_RE),
        ("archived", ARCHIVED_RE),
        ("policy_or_definition_page", POLICY_OR_DEFINITION_RE),
    ):
        match = rule.search(text)
        if match is not None:
            markers[name] = evidence(text, match)

    if structure.outcomes_evidence:
        markers["learning_outcomes"] = structure.outcomes_evidence
    # The same test the program labels use. "Degrees & Certificates" is what
    # a navigation menu is called, and "Fall semester" is in every refund
    # schedule, so only requirements printed in the page's own content count.
    if program.is_program:
        markers["program_markers"] = program.requirements_quote()
    decided = program_label(program)
    if decided is not None and decided[2] is not None:
        markers["credential_award"] = decided[2].quote
    if structure.tabs_evidence:
        markers["tabs_present"] = structure.tabs_evidence
    if structure.requirement_lists:
        markers["course_requirement_list"] = structure.requirement_lists[0]
    # The same shape as multi_course_page, one entity up. A department
    # page heads a section for each credential it offers and prints the
    # requirements of every one, so a single record from it is wrong.
    if program.is_program and program.names_several_awards:
        markers["multi_credential_page"] = evidence(
            ", ".join(program.awards_in_headings)
        )
    published = structure.declaration()
    if published is not None:
        markers["published_as"] = (
            f"{published.source} {published.label}: {published.quote}"
        )
    elif structure.cms_page_type:
        markers["published_as"] = f"cms node type: {structure.cms_page_type}"

    year = catalog_year_value(f"{structure.title} {structure.h1}")
    if year:
        markers["catalog_year"] = year
    if blocks >= 2:
        markers["multi_course_page"] = f"{blocks} course blocks"

    error = EMPTY_OR_ERROR_RE.search(text)
    if visible_chars < EMPTY_PAGE_CHARS:
        markers["empty_or_error_page"] = f"{visible_chars} visible characters"
    elif error is not None:
        markers["empty_or_error_page"] = evidence(text, error)

    return markers


def declared_label(
    structure: Markup, program: ProgramEvidence
) -> tuple[str, str] | None:
    """What the publisher declares this page is, and why that is believed.

    A page carrying `"@type": "Course"` in JSON-LD, or an `itemtype` of
    schema.org/EducationalOccupationalProgram, has said what it is in the
    one form that cannot be misread. Nothing else on the page beats it.

    The one thing still read from the prose is the award, because
    schema.org has a program type and a credential type and catalogs use
    the program type for both: a declared program that names the award it
    grants is the award's page, by the same rule the prose follows.
    """
    published = structure.declaration()
    if published is None:
        return None
    label = published.label
    if label == LABEL_LEARNING_OPPORTUNITY and (
        published.award
        or program.name_award is not None
        or program.award_in_content() is not None
    ):
        award = published.award or "named in the page"
        return LABEL_CREDENTIAL, (
            f"declared in {published.source} as a program awarding {award}"
        )
    return label, f"declared in {published.source}: {published.quote}"


def course_label(
    *,
    text: str,
    structure: Markup,
    template: str,
    blocks: int,
    codes: int,
    program: ProgramEvidence,
) -> str | None:
    """Why this page is a run of course descriptions, or None.

    A page holding many codes is a run of course descriptions unless it is
    a program printing its own requirements. The markup answers that when
    the platform marked the requirement list up; otherwise the printed
    structure and the URL do: /programs/ARCH.AS lists fifteen courses and
    describes none of them.
    """
    code_at_the_top = COURSE_CODE_RE.search(page_head(structure, text))
    lists_its_own_requirements = program.lists_its_own_requirements
    if blocks >= 1 and code_at_the_top is not None:
        return (
            f"{blocks} course block(s), "
            f"code {code_at_the_top.group(0)} at the top"
        )
    if structure.course_blocks and not lists_its_own_requirements:
        # The platform marked its course descriptions up, so there is
        # nothing to infer. One marked-up description is enough: a
        # CourseLeaf subject with a single graduate course prints one
        # `courseblock` and no credits anywhere the text rules can see.
        quote = structure.course_blocks[0].quote
        return (
            f"{len(structure.course_blocks)} course block(s) marked up: {quote}"
        )
    if blocks >= 2 and not lists_its_own_requirements:
        return f"{blocks} course blocks"
    if (
        codes >= MIN_COURSE_LIST_CODES
        and path_names_courses(template)
        and not lists_its_own_requirements
    ):
        # No credits anywhere, so no course blocks. Texas A&M International
        # encodes the credit count in the course number and prints nothing
        # else, which left a page of twenty-six course descriptions
        # labelled as a program.
        return f"{codes} course codes under {template}"
    return None


def apply_labels(
    *,
    text: str,
    structure: Markup,
    template: str,
    blocks: int,
    codes: int,
    markers: dict[str, str],
    program: ProgramEvidence,
) -> tuple[list[str], dict[str, str]]:
    """Which entities this page is about, and the evidence for each.

    Course is decided first and it settles the question of who the course
    codes belong to. A credential page prints the courses it requires, and
    that list of twenty codes is not twenty course descriptions, so a page
    that describes its own requirements is never a Course page on the
    strength of the list alone.

    Credential and LearningOpportunity are then exclusive: whichever a
    page is, it is only one of them. A program page that names the award
    it leads to is a Credential page, because the award is the entity that
    gets published; a program page that names none is a
    LearningOpportunity. An empty or error page is neither, whatever its
    menu says. Competency is independent of all three, since a course and
    a credential can both carry an outcome list.

    A page that declares its own type in JSON-LD or microdata is taken at
    its word before any of that, because the publisher has answered the
    question the rest of this is reasoning towards. An empty page is the
    one exception: a bot wall can carry the declaration of the page it
    refused to serve.
    """
    labels: list[str] = []
    fired: dict[str, str] = {}
    empty = "empty_or_error_page" in markers

    declared = None if empty else declared_label(structure, program)
    if declared is not None:
        labels.append(declared[0])
        fired[declared[0]] = declared[1]
    else:
        course = course_label(
            text=text,
            structure=structure,
            template=template,
            blocks=blocks,
            codes=codes,
            program=program,
        )
        if course is not None:
            labels.append(LABEL_COURSE)
            fired[LABEL_COURSE] = course
        # Once the page is a course page, the award words and the program
        # vocabulary on it belong to the catalog's sidebar, not to the
        # course. Only the outcome list below can still be a second entity.
        elif not empty:
            decided = program_label(program)
            if decided is not None:
                labels.append(decided[0])
                fired[decided[0]] = decided[1]

    if "learning_outcomes" in markers:
        labels.append(LABEL_COMPETENCY)
        fired[LABEL_COMPETENCY] = markers["learning_outcomes"]

    return labels, fired


def page_type_of(labels: list[str]) -> str:
    if not labels:
        return PAGE_TYPE_UNKNOWN
    if len(labels) > 1:
        return PAGE_TYPE_MULTIPLE
    return labels[0]


@dataclass
class PageProfile:
    """One line of pages.jsonl."""

    url: str
    final_url: str
    stem: str
    bytes: int
    http_status: int | None
    title: str
    h1: str
    visible_chars: int
    text_sha256: str
    url_template: str
    course_code_count: int
    course_block_count: int
    field_labels: list[str]
    headings: list[str]
    markers: dict[str, str]
    labels: list[str]
    page_type: str
    rules_fired: dict[str, str]
    # What the page names, typed. Written out by kind, because the quote
    # for each one belongs in entities.csv the way a marker's belongs in
    # patterns.md - see entities_csv in discover.py.
    entities: list[Entity] = dataclasses.field(default_factory=list)
    duplicate_of: str | None = None
    signature: str = ""
    pattern_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "stem": self.stem,
            "bytes": self.bytes,
            "http_status": self.http_status,
            "title": self.title,
            "h1": self.h1,
            "visible_chars": self.visible_chars,
            "text_sha256": self.text_sha256,
            "duplicate_of": self.duplicate_of,
            "url_template": self.url_template,
            "course_code_count": self.course_code_count,
            "course_block_count": self.course_block_count,
            "field_labels": self.field_labels,
            "headings": self.headings,
            "markers": self.markers,
            "labels": self.labels,
            "page_type": self.page_type,
            "rules_fired": self.rules_fired,
            "entities": entities_by_kind(self.entities),
            "signature": self.signature,
            "pattern_id": self.pattern_id,
        }


def profile_page(
    *,
    url: str,
    html: str,
    stem: str,
    final_url: str = "",
    http_status: int | None = None,
    byte_size: int | None = None,
) -> PageProfile:
    """Read one saved page. Nothing is written and nothing is fetched.

    `course_code_count` counts distinct codes, so a page that prints its own
    code six times still reports one course, and never counts a code the
    markup shows to be a reference: the courses a requirement table lists
    are described on their own pages, not on this one.

    `course_block_count` is what the markup marks up as a course
    description when it marks any, and otherwise what the text says: a
    code with a credits value printed near it.
    """
    text = normalized_text(html)
    structure = parse_structure(html)
    template = url_template(url)
    blocks = structure.described_course_count or course_block_count(
        text, structure.reference_codes
    )
    program = read_program_evidence(structure, template)
    visible_chars = len(text)
    markers = detect_markers(
        text,
        structure,
        blocks=blocks,
        visible_chars=visible_chars,
        program=program,
    )
    printed = {normalize_course_code(code) for code in course_codes(text)}
    codes = len(printed - structure.reference_codes)
    labels, fired = apply_labels(
        text=text,
        structure=structure,
        template=template,
        blocks=blocks,
        codes=codes,
        markers=markers,
        program=program,
    )
    return PageProfile(
        url=url,
        final_url=final_url or url,
        stem=stem,
        bytes=byte_size if byte_size is not None else len(html.encode("utf-8")),
        http_status=http_status,
        title=structure.title,
        h1=structure.h1,
        visible_chars=visible_chars,
        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        url_template=template,
        course_code_count=codes,
        course_block_count=blocks,
        field_labels=field_labels_of(structure, text),
        headings=sorted(set(structure.headings)),
        markers=markers,
        labels=labels,
        page_type=page_type_of(labels),
        rules_fired=fired,
        entities=read_entities(structure),
    )
