"""ceterms:description, read from a course, against pages from real catalogs.

The expected values follow what the Golden Dataset Studio's reviewers
accepted: the description as the page shows it, without the requisite
statements that open it.
"""

from __future__ import annotations

import pytest
from extract_doubles import fixture_page

from implementations.discover_dom import parse
from implementations.extract.ceterms.ceterms_description import (
    CLASS,
    PROPERTY,
    drop_lead_statements,
    read,
    shown_text,
)
from implementations.extract_course import course_occurrences as occurrences
from implementations.extract_run import Page


def test_the_module_declares_its_ctdl_property() -> None:
    assert PROPERTY == "ceterms:description"


def test_it_is_read_from_courses() -> None:
    assert CLASS == ("ceterms:Course",)


# --- shown_text --------------------------------------------------------------


def _shown(html: str) -> str:
    soup = parse(f"<body>{html}</body>")
    return shown_text(soup.body.contents[0])


def test_whitespace_collapses_as_a_browser_shows_it() -> None:
    assert (
        _shown("<p>  Introduction to\n   Computer  Aided Drafting. </p>")
        == "Introduction to Computer Aided Drafting."
    )


def test_a_pre_wrap_keeps_its_newlines_and_spaces() -> None:
    # eLumen: what the reviewers accepted, newline and double space kept.
    assert (
        _shown(
            '<div style="white-space: pre-wrap;">\n<p>Topics in logic. '
            "\n(C-ID: PHIL 100)  (UC, CSU, AVC)</p>\n</div>"
        )
        == "Topics in logic. \n(C-ID: PHIL 100)  (UC, CSU, AVC)"
    )


def test_a_br_is_a_line_break_and_paragraphs_a_blank_line() -> None:
    assert (
        _shown(
            "<div><p>First paragraph.<br>Its second line.</p><p>Second.</p></div>"
        )
        == "First paragraph.\nIts second line.\n\nSecond."
    )


def test_hidden_text_is_left_out() -> None:
    assert (
        _shown(
            '<p>Continuation of <a>SCWK 80755</a><span style="display: none'
            ' !important"> </span>. <span class="sr-only">Opens a window</span>'
            "</p>"
        )
        == "Continuation of SCWK 80755."
    )


# --- drop_lead_statements ----------------------------------------------------


@pytest.mark.parametrize(
    ("text", "description"),
    [
        # WVU's CourseLeaf: on the same line, a sentence each.
        (
            "PR: PHAR 191 and PR or CONC: PHAR 192. Supervised practice.",
            "Supervised practice.",
        ),
        (
            "Prerequisite: Completion of PSY 101. This course provides.",
            "This course provides.",
        ),
        # eLumen: each statement a line of its own, however many sentences.
        (
            "LIMITATION ON ENROLLMENT: Must have a job. Must attend an "
            "orientation.\n\nWork Experience Education is supervised employment.",
            "Work Experience Education is supervised employment.",
        ),
        (
            "Limitation on Enrollment: Formal admission. \nPrerequisite: "
            "Completion of RADT 202 \nThis course provides clinical practice.",
            "This course provides clinical practice.",
        ),
        (
            "Advisory: Completion of DA 125.\xa0This course continues tap dance.",
            "This course continues tap dance.",
        ),
        (
            "Co-Req: CIET 115. A practical study of steel.",
            "A practical study of steel.",
        ),
        # No sentence mark ends the statement: the description starts at
        # its own first sentence.
        (
            "PR: Consent Study of place as a psychological and social "
            "phenomenon. (equivalent to RPTR 570).",
            "Study of place as a psychological and social phenomenon. "
            "(equivalent to RPTR 570).",
        ),
        (
            "PR:ELET 420 Microcomputer operating systems, assembly languages, "
            "application of software.",
            "Microcomputer operating systems, assembly languages, "
            "application of software.",
        ),
        (
            "Advisory: Placement by Multiple Measures This honors course, "
            "intended for students in the Honors Program, is an introduction."
            "\n\nNote: Duplicate credit will not be awarded.",
            "This honors course, intended for students in the Honors Program, "
            "is an introduction.\n\nNote: Duplicate credit will not be awarded.",
        ),
        # A course name in the statement isn't where the description starts.
        (
            "Advisory: Completion of Intermediate Algebra or higher or "
            "placement by multiple measures.\nThis course is a survey.",
            "This course is a survey.",
        ),
        (
            "PR: Admission to the Honors College in good academic standing "
            "and have completed HONR 201. This course is a forum.",
            "This course is a forum.",
        ),
        # A requisite statement and nothing else: no description.
        ("Pre-req: Admitted Honors College.", ""),
        # Statements after the description are part of it.
        (
            "Economic policies.\n\nPrerequisite: Placement.",
            "Economic policies.\n\nPrerequisite: Placement.",
        ),
        # A description that opens with words and a colon of its own.
        (
            "Progressive Prosecution: Law & Policy is a seminar course.",
            "Progressive Prosecution: Law & Policy is a seminar course.",
        ),
    ],
)
def test_the_requisite_statements_that_open_it_are_dropped(
    text: str, description: str
) -> None:
    assert drop_lead_statements(text) == description


# --- read, page by page ------------------------------------------------------


def descriptions(page: Page) -> list[tuple[str | None, str]]:
    return [((r := read(o, page)).value, r.strategy) for o in occurrences(page)]


def test_courseleaf_reads_each_block_description_without_its_pr() -> None:
    read_ = descriptions(fixture_page("courseleaf-courseblocks"))
    assert {strategy for _, strategy in read_} == {"profile_description"}
    assert read_[1][0] == (
        "Orientation to degree programs and requirements, departmental "
        "resources, curriculum options, student responsibilities, and "
        "opportunities."
    )
    # "PR: BIOL 115 and BIOL 115L with a minimum grade of C- and PR or
    # CONC: BIOL 117 … C-. Focused study …"
    assert read_[2][0].startswith("Focused study of the adverse effects")


def test_the_courseleaf_detail_theme_reads_its_first_courseblockextra() -> None:
    assert descriptions(fixture_page("courseleaf-detail-code")) == [
        (
            "Introduction to the study of human society. This class "
            "emphasizes critical thinking skills.",
            "profile_description",
        ),
        (
            "Introduction to the study of human society for the honors "
            "student. This course emphasizes critical thinking skills.",
            "profile_description",
        ),
        (
            "Selected topics not covered in regular course offerings.",
            "profile_description",
        ),
    ]


def test_curriqunet_reads_its_catalog_description() -> None:
    read_ = descriptions(fixture_page("curriqunet-courses"))
    assert [strategy for _, strategy in read_] == ["profile_description"] * 3
    assert read_[0][0].startswith(
        "This course is an introduction to psychology"
    )


def test_another_curriqunet_catalog_is_read_by_its_class_words() -> None:
    # Butte names it course-description-value, not CCSF's
    # course-catalog-description, and its requisite row is passed over.
    read_ = descriptions(fixture_page("curriqunet-units-in-title"))
    assert [strategy for _, strategy in read_] == ["description_class"] * 2
    assert read_[0][0] == (
        "This course is an introduction to the craft of creative writing "
        "through the study and analysis of works by established literary "
        "writers. Students will practice writing in various genres and will "
        "be introduced to the workshop method. Graded only. (C-ID ENGL 200)."
    )


def test_elumen_reads_its_intro_text() -> None:
    ((value, strategy),) = descriptions(fixture_page("elumen-course"))
    assert strategy == "profile_description"
    assert value.startswith(
        "This course introduces students to the characteristics of the "
        "criminal justice system"
    )


def test_acalog_reads_the_prose_after_the_credit_line() -> None:
    assert descriptions(fixture_page("acalog-course")) == [
        (
            "Was ACOM 7390. Applied communication theories, terminology, "
            "program writing, presentation responsibilities; emphasis on "
            "research skills necessary for the field.",
            "first_prose",
        )
    ]


@pytest.mark.parametrize(
    "name",
    [
        "courseleaf-courseblocks",
        "courseleaf-detail-code",
        "courseleaf-detail-title",
        "elumen-course",
        "acalog-course",
    ],
)
def test_without_its_platform_a_page_reads_the_same(name: str) -> None:
    """The generic strategies find what the platform's profile finds.

    Not CurriQunet: without its platform, ceterms:Course finds no blocks
    there and reads the page as one course.
    """
    with_profile = [v for v, _ in descriptions(fixture_page(name))]
    without = [v for v, _ in descriptions(fixture_page(name, platform=""))]
    assert without == with_profile


# --- read, generic pages -----------------------------------------------------


def _page(html: str, platform: str = "") -> Page:
    return Page(
        stem="s", url="u", soup=parse(html), platform=platform, profile={}
    )


def _read_whole_page(html: str):
    page = _page(html)
    (occurrence,) = occurrences(page)
    return read(occurrence, page)


def test_a_description_heading_gives_what_follows_it() -> None:
    reading = _read_whole_page(
        "<main><h1>ART 101 Drawing</h1><h3>Description</h3>"
        "<p>Basic drawing techniques.</p><h3>Outcomes</h3><p>Draw.</p></main>"
    )
    assert (reading.value, reading.strategy) == (
        "Basic drawing techniques.",
        "description_label",
    )


def test_credit_and_label_lines_before_the_prose_are_passed_over() -> None:
    reading = _read_whole_page(
        "<main><h1>BIOL 101 - Biology</h1><hr>Three hours lecture. Two hours "
        "laboratory per week. Four credit hours.<br><br>"
        "<strong>Offered:</strong> Spring even years.<br><br>"
        "A survey of living things.<br><br>"
        "<strong>Prerequisites:</strong> None<br><hr>"
        '<a class="portfolio_link">Add to Bookmarks (opens a new window)</a>'
        "</main>"
    )
    assert (reading.value, reading.strategy) == (
        "A survey of living things.",
        "first_prose",
    )


def test_a_course_with_only_a_prerequisite_has_no_description() -> None:
    reading = _read_whole_page(
        "<main><h1>ASCI 90006 - Dissertation</h1><hr>Six credit hours."
        "<br><br><strong>Prerequisites:</strong> Advisor consent.<br><hr>"
        "<a>Add to Bookmarks (opens a new window)</a></main>"
    )
    assert reading.value is None
    assert reading.reason == "no_candidate"


def test_a_description_element_holding_only_a_requisite_is_the_answer() -> None:
    page = _page(
        '<main><div class="courseblock"><p class="courseblocktitle">'
        "LAW 793. Topics. 3 Hours.</p>"
        '<div class="courseblockextra">Pre-req: Consent.</div>'
        "<p>Not the description.</p></div></main>",
        platform="courseleaf",
    )
    (occurrence,) = occurrences(page)
    reading = read(occurrence, page)
    assert reading.value is None
    assert reading.reason == "requisites_only"


def test_an_empty_description_element_is_no_description() -> None:
    page = _page(
        '<main><div class="courseblock"><p class="courseblocktitle">'
        'LAW 793. Topics. 3 Hours.</p><p class="courseblockdesc"> </p>'
        "</div></main>",
        platform="courseleaf",
    )
    (occurrence,) = occurrences(page)
    assert read(occurrence, page).reason == "empty_description"


def test_nothing_to_read_says_so() -> None:
    reading = _read_whole_page("<main><h1>ART 101 Drawing</h1></main>")
    assert reading.value is None
    assert reading.reason == "no_candidate"


# --- the narrative of a description element ---------------------------------
# UARK prints a whole program page in its #long_desc: the description, then
# headed sections of outcomes, certification and prior learning. The
# reviewers took only the opening narrative.


def test_a_description_element_ends_at_its_next_heading() -> None:
    reading = _read_whole_page(
        '<main><h1>ART 101 Drawing</h1><div id="long_desc">'
        '<p class="lead">Basic drawing techniques.</p><p>Charcoal and ink.</p>'
        "<h2>Course Outcomes</h2><p>Draw a figure.</p></div></main>"
    )
    assert (reading.value, reading.strategy) == (
        "Basic drawing techniques.\n\nCharcoal and ink.",
        "description_class",
    )


def test_a_tagline_heading_before_the_narrative_is_passed_over() -> None:
    reading = _read_whole_page(
        '<main><h1>ART 101 Drawing</h1><div id="long_desc">'
        "<style>p { font-size: 18px; }</style>"
        "<h2>Build the Skills That Support Growth</h2>"
        "<p>Basic drawing techniques.</p><h2>Included</h2><p>Paper.</p>"
        "</div></main>"
    )
    assert reading.value == "Basic drawing techniques."


def test_a_description_element_ends_before_a_list_and_its_lead_in() -> None:
    reading = _read_whole_page(
        '<main><h1>ART 101 Drawing</h1><div id="long_desc">'
        "<p>Basic drawing techniques.</p>"
        "<p>By the end of the course, students will:</p>"
        "<ul><li>Draw a figure.</li></ul></div></main>"
    )
    assert reading.value == "Basic drawing techniques."


def test_a_short_title_line_leading_into_a_list_is_left_out() -> None:
    reading = _read_whole_page(
        '<main><h1>LEAD 100 Leadership</h1><div id="long_desc">'
        "<div>A six-part developmental pathway for new managers.</div>"
        "<p>Courses in the Series</p>"
        "<ul><li>Leading Self</li></ul></div></main>"
    )
    assert reading.value == "A six-part developmental pathway for new managers."


def test_a_description_heading_inside_the_element_starts_the_narrative() -> (
    None
):
    reading = _read_whole_page(
        '<main><h1>PT 101 Play Therapy</h1><div id="long_desc">'
        "<h2>APT Approved Provider #: 15-403</h2><h2>Objectives</h2>"
        "<p>After this workshop, you will be able to:</p>"
        "<h2>Description</h2><p>Involving parents is a challenge.</p>"
        "</div></main>"
    )
    assert reading.value == "Involving parents is a challenge."


def test_a_description_element_without_headings_or_lists_is_read_whole() -> (
    None
):
    reading = _read_whole_page(
        '<main><h1>ART 101 Drawing</h1><div id="long_desc">'
        "<p>Basic drawing techniques.</p><p>Charcoal and ink.</p></div></main>"
    )
    assert reading.value == "Basic drawing techniques.\n\nCharcoal and ink."
