"""What reading a page's fields out of its markup has to get right.

The point of this reading is that it is not one college's. Each test here
is a shape a different catalog platform prints, read by the same code.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from implementations.extract_dom import (
    ENTITY_COMPETENCY,
    ENTITY_COURSE,
    ENTITY_CREDENTIAL,
    ENTITY_PROGRAM,
    NothingToExtract,
    entity_type_for,
    extract_fields,
)

PAGE = "<html><head><title>{title}</title></head><body>{body}</body></html>"


def values(drafts) -> dict:
    return {draft.canonical_label: draft.value for draft in drafts}


# --- which record a page produces ---------------------------------------------


def test_a_pages_labels_decide_which_record_it_produces() -> None:
    assert entity_type_for(["Course"]) == ENTITY_COURSE
    assert entity_type_for(["Credential"]) == ENTITY_CREDENTIAL
    # Discovery's name for it is not the name CTDL gives the class.
    assert entity_type_for(["LearningOpportunity"]) == ENTITY_PROGRAM
    assert entity_type_for(["Competency"]) == ENTITY_COMPETENCY
    assert entity_type_for([]) is None


def test_a_page_that_is_two_things_produces_the_first_of_them() -> None:
    """A credential that lists what its students will learn is a credential.

    The competency list on it belongs to that credential, not to a
    framework of its own.
    """
    assert entity_type_for(["Credential", "Competency"]) == ENTITY_CREDENTIAL
    assert entity_type_for(["Course", "Competency"]) == ENTITY_COURSE


# --- one reading, three platforms ---------------------------------------------


DRUPAL = PAGE.format(
    title="AELP060 &lt; Example College",
    body="""
<main><article class="node node--type-class node--view-mode-full">
  <h1>AELP060: Elementary I Academic English</h1>
  <div class="field field--name-field-credits">
    <div class="field__label">Credits</div><div class="field__item">6</div>
  </div>
  <div class="field field--name-field-lecture-hours">
    <div class="field__label">Lecture Hours</div>
    <div class="field__item">6</div>
  </div>
  <div class="field field--name-field-description">
    <div class="field__item">Beginning-level course for new students.</div>
  </div>
  <div class="field field--name-field-pr">
    <div class="field__label">Prerequisites</div>
    <div class="field__item">Placement Test score</div>
  </div>
</article></main>""",
)

COURSEDOG = PAGE.format(
    title="ENG-102 | Example College Catalog",
    body="""
<div id="main-content" role="main">
  <h1>ENG-102</h1>
  <div class="field-row">
    <div class="field"><h3 class="field-label">Subject code</h3>
      <div class="field-value">ENG</div></div>
    <div class="field"><h3 class="field-label">Course Number</h3>
      <div class="field-value">102</div></div>
    <div class="field"><h3 class="field-label">Credit Hours</h3>
      <div class="field-value">3</div></div>
  </div>
  <div class="field"><h3 class="field-label">Description</h3>
    <div class="field-value">Expository writing and close reading.</div></div>
</div>""",
)

COURSELEAF = PAGE.format(
    title="Brewing Science (BREW) &lt; Example University",
    body="""
<main><h1>Brewing Science (BREW)</h1>
<div class="courseblock">
  <p class="courseblocktitle"><strong>BREW 55703.  Production Design and
  Analysis of Beer.  3 Hours.</strong></p>
  <p class="courseblockdesc">Production design and sensory evaluation of
  barley, malt, hops, water, yeast and beer.</p>
</div></main>""",
)


def test_a_drupal_course_is_read_from_the_fields_it_marks_up() -> None:
    found = values(extract_fields(ENTITY_COURSE, DRUPAL))
    assert found["course_credits"] == 6
    assert found["course_credits_unit"] == "Credits"
    assert found["course_lecture_hours"] == 6
    assert found["course_prerequisites"] == "Placement Test score"
    assert found["course_description"].startswith("Beginning-level course")


def test_a_coursedog_course_is_read_by_the_same_code() -> None:
    """Different class names, same shape: a label and a value beside it.

    The three fields in one `field-row` matter: a reading that took the
    row for one field found the subject code and lost the two after it.
    """
    found = values(extract_fields(ENTITY_COURSE, COURSEDOG))
    assert found["course_subject_code"] == "ENG"
    assert found["course_number"] == "102"
    assert found["course_credits"] == 3
    assert found["course_credits_unit"] == "Credit Hours"
    assert found["course_description"].startswith("Expository writing")


def test_a_courseleaf_course_is_read_from_its_block_title() -> None:
    """CourseLeaf labels nothing: the title line carries all three."""
    found = values(extract_fields(ENTITY_COURSE, COURSELEAF))
    assert found["course_id"] == "BREW 55703"
    assert found["course_name"] == "Production Design and Analysis of Beer"
    assert found["course_credits"] == 3
    assert found["course_credits_unit"] == "Hours"
    assert found["course_description"].startswith("Production design")


COURSELEAF_DETAIL = PAGE.format(
    title="Agriculture Engr (AGEG) &lt; Example University",
    body="""
<main><h1>Agriculture Engr/Mechanization (AGEG)</h1>
<div class="sc_sccoursedescs"><div class="courseblock">
  <div class="cols noindent">
    <span class="text detail-code"><strong>AGEG 3203</strong></span>
    <span class="text detail-title"><strong>Soil and Water
      Conservation</strong></span>
  </div>
  <div class="noindent"><span class="text detail-prerequisites">
    <span class="label">Prerequisite:</span> Junior standing.</span></div>
  <div class="courseblockextra noindent">Causes and control of soil and
    water losses.</div>
</div></div></main>""",
)


def test_the_newer_courseleaf_theme_names_each_part_of_the_block() -> None:
    """Same platform, a theme that labels the parts instead of one line.

    Read as one line the block has no code in it, and the record came out
    holding the subject's name and nothing else.
    """
    found = values(extract_fields(ENTITY_COURSE, COURSELEAF_DETAIL))
    assert found["course_id"] == "AGEG 3203"
    assert found["course_name"] == "Soil and Water Conservation"
    # The label is not part of the value.
    assert found["course_prerequisites"] == "Junior standing."
    assert found["course_description"].startswith("Causes and control")


def test_the_course_name_comes_from_the_block_not_the_page() -> None:
    """The h1 of a CourseLeaf subject page names the subject, not a course."""
    found = values(extract_fields(ENTITY_COURSE, COURSELEAF))
    assert found["course_name"] != "Brewing Science (BREW)"


def test_a_numeric_field_is_a_number_and_the_rest_are_text() -> None:
    found = values(extract_fields(ENTITY_COURSE, DRUPAL))
    assert isinstance(found["course_credits"], int)
    assert isinstance(found["course_prerequisites"], str)


def test_every_field_says_where_it_came_from() -> None:
    for draft in extract_fields(ENTITY_COURSE, DRUPAL):
        assert draft.locator_strategy == "dom_path"
        assert draft.locator_value
        assert draft.excerpt


# --- eLumen: a heading group instead of labelled fields -----------------------


ELUMEN = PAGE.format(
    title="ELEC 150 - Electrical Maintenance",
    body="""
<div id="nav"><a href="/course/elec110">ELEC 110 - Basic Electricity</a></div>
<main id="landmark-main" role="main">
  <h1 class="u-visuallyhidden">2026-27 Catalog</h1>
  <div id="mainContent">
    <header class="header l-body">
      <h2>Electrical Maintenance</h2>
      <h3>ELEC 150:</h3>
      <p class="header-x-meta">4.0 Units</p>
    </header>
    <div class="l-body">
      <div class="introtext l-introtext"><p>Prerequisite: Completion of or
      concurrent enrollment in ELEC 110. Students will progress from basic
      electrical theory to the maintenance of industrial systems.</p></div>
      <h4>Units and Hours</h4>
      <h5>Minimum Credit Units</h5><div class="text"><p>4.0</p></div>
      <h5>Total Course Lecture Hours</h5><div class="text">54.0</div>
      <h5>Total Course Lab Hours</h5><div class="text">54.0</div>
    </div>
  </div>
</main>""",
)

# A second theme: the name in a <p>, the code in the h1, the units two
# wrappers below, and its hours as an h3 over a <p>.
ELUMEN_OTHER_THEME = PAGE.format(
    title="FIRE B71A - Seasonal Firefighter Basic Training 1",
    body="""
<main role="main">
  <h1 class="u-visuallyhidden">2026 - 2027 Catalog</h1>
  <div id="mainContent"><div class="l-body">
    <header class="header-course l-body">
      <p class="header-course-name">Seasonal Firefighter Basic Training 1</p>
      <h1>FIRE B71A</h1>
    </header>
    <div><div class="units"><p><strong>2.0 UNITS</strong></p></div>
      <div class="print-icon-container"><a href="#">Print</a></div></div>
    <div class="text-format"><p id="description">All of the federal fire
      agencies recognize this course as the foundation of all later
      wildland fire training, and it covers the NWCG L180 material.</p></div>
    <h3 class="introtext course-label">Total Lecture Hours:</h3>
    <p class="course-content">27.0</p>
    <h3 class="introtext course-label">Total Lab Hours:</h3>
    <p class="course-content">27.0</p>
  </div></div>
</main>""",
)


def test_an_elumen_course_is_read_from_its_heading_group() -> None:
    """None of the course's code, name or units is labelled.

    Read as a page, the course was named after the hidden banner h1 and
    had no code, units or hours.
    """
    found = values(extract_fields(ENTITY_COURSE, ELUMEN))
    assert found["course_id"] == "ELEC 150"
    assert found["course_name"] == "Electrical Maintenance"
    assert found["course_credits"] == 4.0
    assert found["course_credits_unit"] == "Units"
    assert found["course_lecture_hours"] == 54.0
    assert found["course_lab_hours"] == 54.0
    assert found["course_description"].startswith("Prerequisite: Completion")
    assert found["course_prerequisites"] == (
        "Completion of or concurrent enrollment in ELEC 110."
    )


def test_the_other_elumen_theme_prints_the_code_in_the_h1() -> None:
    found = values(extract_fields(ENTITY_COURSE, ELUMEN_OTHER_THEME))
    assert found["course_id"] == "FIRE B71A"
    assert found["course_name"] == "Seasonal Firefighter Basic Training 1"
    assert found["course_credits"] == 2.0
    # As printed: the unit is what the page says, not a spelling of it.
    assert found["course_credits_unit"] == "UNITS"
    assert found["course_lecture_hours"] == 27.0
    assert found["course_lab_hours"] == 27.0


def test_a_variable_unit_course_keeps_its_range() -> None:
    """A range printed "1.0 - 4.0 Units" is kept as "1.0-4.0"."""
    page = PAGE.format(
        title="COMM 80SB - Special Studies II",
        body=(
            "<main><header class='header'><h2>Special Studies II</h2>"
            "<h3>COMM 80SB:</h3><p class='header-x-meta'>1.0 - 4.0 Units</p>"
            "</header><p>Independent study in communication studies under "
            "the direction of a faculty member.</p></main>"
        ),
    )
    found = values(extract_fields(ENTITY_COURSE, page))
    assert found["course_credits"] == "1.0-4.0"
    assert found["course_credits_unit"] == "Units"


def test_a_code_heading_outside_a_heading_group_names_no_course(
    fixture_html_dir: Path,
) -> None:
    """Clean Catalog prints its vendor credit just above <h1>ENGL101:</h1>.

    Only what a heading group prints beside the code is the course's name;
    anything else beside a bare code is whatever the page put there.
    """
    html = (fixture_html_dir / "course-clean-catalog.html").read_text(
        encoding="utf-8"
    )
    found = values(extract_fields(ENTITY_COURSE, html))
    assert found["course_id"] == "ENGL101"
    assert found["course_name"] != "Course Catalog Software by Clean Catalog"


def test_a_heading_over_a_word_is_not_a_number(fixture_html_dir: Path) -> None:
    """Coursedog prints "Credit Hours" over "Min", then the number."""
    html = (fixture_html_dir / "course-coursedog-credit-hours.html").read_text(
        encoding="utf-8"
    )
    found = values(extract_fields(ENTITY_COURSE, html))
    assert found.get("course_credits") != "Min"
    assert "course_credits_unit" not in found


def test_a_credits_heading_over_its_value_is_read() -> None:
    """SmartCatalog prints <h3>Credits</h3> over the number, unlabelled."""
    page = PAGE.format(
        title="AIR 2002 Development of Air Power II",
        body=(
            "<div id='main'><h1>AIR 2002 Development of Air Power II</h1>"
            "<div class='desc'><p>A continuation of AIR 2001, on the "
            "doctrine and the history of air power.</p></div>"
            "<div class='sc_credits'><h3>Credits</h3>"
            "<div class='credits'>1</div></div></div>"
        ),
    )
    found = values(extract_fields(ENTITY_COURSE, page))
    assert found["course_credits"] == 1
    assert found["course_credits_unit"] == "Credits"


def test_a_description_is_not_cut_at_six_hundred_characters() -> None:
    """Cut at the length the award rules read, a long description stopped
    mid-sentence."""
    description = "Covers cost terminology and cost behavior. " * 20
    page = PAGE.format(
        title="ACCT 1B - Managerial Accounting",
        body=(
            "<main><header class='header'><h2>Managerial Accounting</h2>"
            "<h3>ACCT 1B:</h3><p class='header-x-meta'>4.0 Units</p>"
            f"</header><p>{description}</p></main>"
        ),
    )
    found = values(extract_fields(ENTITY_COURSE, page))
    assert found["course_description"] == description.strip()


# --- the unit the credits are counted in --------------------------------------


def drafts_by_label(drafts) -> dict:
    return {draft.canonical_label: draft for draft in drafts}


def test_the_unit_is_read_from_the_line_that_prints_the_credits() -> None:
    """A reviewer finds the number and its unit in one place."""
    found = drafts_by_label(extract_fields(ENTITY_COURSE, ELUMEN))
    unit, credits = found["course_credits_unit"], found["course_credits"]
    assert unit.value == "Units"
    assert unit.excerpt == "4.0 Units"
    assert unit.locator_value == credits.locator_value


def test_a_label_gives_its_unit_without_its_qualifier() -> None:
    """The label "CREDIT HOURS MIN:" counts in credit hours; MIN is a bound."""
    page = PAGE.format(
        title="ACC 101 - Accounting I",
        body=(
            "<main><h1>ACC 101 Accounting I</h1>"
            "<dl><dt>CREDIT HOURS MIN:</dt><dd>3</dd></dl></main>"
        ),
    )
    found = drafts_by_label(extract_fields(ENTITY_COURSE, page))
    assert found["course_credits"].value == 3
    assert found["course_credits_unit"].value == "CREDIT HOURS"
    assert found["course_credits_unit"].excerpt == "CREDIT HOURS MIN:"


def test_a_value_that_prints_its_unit_is_a_number_and_a_unit() -> None:
    """Read as one value, "3 Units" was a string where a number belongs."""
    page = PAGE.format(
        title="ACC 101 - Accounting I",
        body=(
            "<main><h1>ACC 101 Accounting I</h1>"
            "<dl><dt>Credits</dt><dd>3 Units</dd></dl></main>"
        ),
    )
    found = values(extract_fields(ENTITY_COURSE, page))
    assert found["course_credits"] == 3
    assert found["course_credits_unit"] == "Units"


# A Drupal credits field with no label over it: only its class names it.
UNLABELLED_CREDITS = (
    "<div class='field field--name-field-credits'>"
    "<div class='field__item'>{credits}</div></div>"
)


def test_a_field_known_only_by_its_class_prints_no_unit() -> None:
    """The class says the field is credits; nothing printed says in what."""
    page = PAGE.format(
        title="AELP060",
        body=(
            "<main><h1>AELP060: Elementary I Academic English</h1>"
            + UNLABELLED_CREDITS.format(credits=6)
            + "</main>"
        ),
    )
    found = values(extract_fields(ENTITY_COURSE, page))
    assert found["course_credits"] == 6
    assert "course_credits_unit" not in found


def test_the_unit_comes_from_the_reading_whose_credits_are_kept() -> None:
    """A labelled field outranks the eLumen header, and so does its silence.

    The header's "Units" belongs to the header's number. Lent to the
    field's, the record would pair a number and a unit that no element on
    the page prints together.
    """
    page = PAGE.format(
        title="ELEC 150 - Electrical Maintenance",
        body=(
            "<main><header class='header'><h2>Electrical Maintenance</h2>"
            "<h3>ELEC 150:</h3><p class='header-x-meta'>4.0 Units</p>"
            "</header>" + UNLABELLED_CREDITS.format(credits=4) + "</main>"
        ),
    )
    found = values(extract_fields(ENTITY_COURSE, page))
    assert found["course_credits"] == 4
    assert "course_credits_unit" not in found


def test_a_unit_does_not_make_a_record_of_one_field() -> None:
    """The unit only ever comes with the credits, so it adds no field."""
    page = PAGE.format(title="", body="<dl><dt>Credits</dt><dd>3</dd></dl>")
    with pytest.raises(NothingToExtract):
        extract_fields(ENTITY_COURSE, page)


# --- the prerequisite a course names ------------------------------------------


def prerequisite(body: str, title: str = "ENGL 102") -> object:
    found = drafts_by_label(
        extract_fields(ENTITY_COURSE, PAGE.format(title=title, body=body))
    )
    draft = found.get("course_prerequisites")
    return draft.value if draft is not None else None


ACALOG = (
    "<table><tr><td class='block_content'>"
    "<h1>ARCH 171 - Graphic Communications II</h1><hr>3 units<br>"
    "2 hours lecture, 4 hours lab<br><strong>Prerequisite:</strong> "
    "<a href='#'>ARCH 170</a><span>&nbsp;</span>&nbsp; with a minimum grade "
    "C<br>Credit, degree applicable<br>Transfer CSU<br><br>This course "
    "teaches drawing with an emphasis on design ideas.</td></tr></table>"
)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        pytest.param(ACALOG, "ARCH 170 with a minimum grade C", id="acalog"),
        pytest.param(
            "<table><tr><td class='block_content'><h1>CSC 2000</h1>"
            "<strong>Credit(s):</strong> <strong>4</strong><br>"
            "<strong>Prerequisite(s):</strong> CSC 1061<br>Formerly CSC 225 "
            "Covers how a computer operates.</td></tr></table>",
            "CSC 1061",
            id="acalog-ends-at-its-line-break",
        ),
        pytest.param(
            "<main><h1>Behavioral Health (BEH)</h1><div class='courseblock'>"
            "<p class='courseblocktitle'><strong>BEH 2001 | Crisis</strong>"
            "</p><p class='courseblockdesc'>Covers a wide range of skills.</p>"
            "<p class='courseblockreqs'><strong>Prerequisite:</strong> "
            "<a href='#'>BEH 1001</a> with a grade of C or better<br/></p>"
            "</div></main>",
            "BEH 1001 with a grade of C or better",
            id="courseleaf-requirements",
        ),
        pytest.param(
            "<main><h1>ALAN 0300</h1><div class='courseblock'>"
            "<p class='courseblockdesc'>Advanced language.</p>"
            "<p class='courseblockextra noindent'>Prerequisite: ALAN 0200</p>"
            "</div></main>",
            "ALAN 0200",
            id="courseleaf-extra",
        ),
        pytest.param(
            "<main><h1>ASL 051</h1><p>Second semester ASL.</p><div>"
            "<span class='course-Requisite-value'><b>Prerequisite:</b> "
            "ASL 050 or ASL 050B </span></div></main>",
            "ASL 050 or ASL 050B",
            id="curriqunet-bold",
        ),
        pytest.param(
            "<main><h1>PE 29B</h1><p>Swimming.</p><div>"
            "<span class='course-requisites'>Prerequisite: PE 29A or "
            "demonstration of exit skills</span></div></main>",
            "PE 29A or demonstration of exit skills",
            id="curriqunet-plain",
        ),
        pytest.param(
            "<main><h1>CSL 2069</h1><p>Counseling.</p>"
            "<p class='wp-block-paragraph'><strong>Prerequisite(s):</strong> "
            "CSL 2068</p></main>",
            "CSL 2068",
            id="wordpress",
        ),
    ],
)
def test_a_label_on_the_line_of_its_value_gives_the_rest_of_the_line(
    body: str, expected: str
) -> None:
    """Acalog, CourseLeaf, CurriQunet and WordPress print it one way."""
    assert prerequisite(body) == expected


def test_a_label_cell_gives_the_cell_beside_it() -> None:
    """The label is in one cell and the value in the next."""
    body = (
        "<main><h1>AATA 101A</h1><p>Nondestructive testing.</p><table><tr>"
        "<td class='cor_heading'><strong>Prerequisite:</strong></td>"
        "<td class='cor_value'>MATH 105<br>or<br>MATH 105H</td></tr></table>"
        "</main>"
    )
    assert prerequisite(body) == "MATH 105 or MATH 105H"


DRUPAL_HEADING = (
    "<main><h1>AAA 0090</h1><div class='degree-class-details'>"
    "<div class='field field--name-field-description field--label-hidden "
    "field__item'>Develops personalized approaches to learn.</div>"
    "<div><h3>Prerequisites</h3><div class='field field--name-field-pr "
    "field--label-hidden field__item'>{value}</div></div>"
    "<span class='field field--name-field-lecture-hours'>"
    "<span class='field__label'>Lecture Hours</span>"
    "<span class='field__item'>45</span></span></div></main>"
)


def test_a_heading_gives_what_its_own_wrapper_prints_under_it() -> None:
    """The heading and its value share a wrapper; the hours are outside."""
    found = values(
        extract_fields(
            ENTITY_COURSE,
            PAGE.format(
                title="AAA 0090", body=DRUPAL_HEADING.format(value="MAT 105")
            ),
        )
    )
    assert found["course_prerequisites"] == "MAT 105"
    assert found["course_lecture_hours"] == 45


def test_a_heading_over_a_course_link_gives_the_course() -> None:
    """SmartCatalog prints <h2>Prerequisite</h2> over a bare link."""
    body = (
        "<div id='main'><h1><span>AEC 1232</span> Construction Drawing</h1>"
        "<div class='desc'><p>Examines architectural drawings.</p></div>"
        "<div class='sc_prereqs'><h2> Prerequisite </h2>"
        "<a class='sc-courselink' href='#'>CAD 2220</a></div>"
        "<div class='sc_coreqs'><h2> Corequisite </h2>"
        "<a href='#'>AEC 1231</a></div></div>"
    )
    assert prerequisite(body) == "CAD 2220"


SIDEBAR = (
    "<main class='main-content'><article class='course-full'>"
    "<h1>ACC 122 Accounting Principles II</h1><div class='course-full__body'>"
    "<p>Continues the study of accounting principles with an emphasis on "
    "corporations, partnerships and financial statement analysis.</p></div>"
    "<aside class='course-full__aside'><ul><li>"
    "<span class='course-full__aside__label'>credits | </span>"
    "<div class='field_credits'>4</div></li><li><div class='prerequisites'>"
    "<div class='prerequisites__text'><h4>prerequisites</h4>"
    "<div class='field_prerequisite_text'><p>ACC 121 with a grade of "
    "\"C\" or better</p></div></div><div class='prerequisites__references'>"
    "<h5>referenced courses</h5><div><a href='#'>ACC 121 </a></div></div>"
    "</div></li></ul></aside></article></main>"
)


def test_a_sidebar_inside_the_page_is_the_pages_own() -> None:
    """The prerequisite is printed in an <aside> inside <main>."""
    assert prerequisite(SIDEBAR) == 'ACC 121 with a grade of "C" or better'


def test_a_sidebar_beside_the_page_is_still_the_sites() -> None:
    """With no main container of its own, an <aside> is site furniture."""
    body = (
        "<aside><h4>Prerequisites</h4><p>ENGL 101</p></aside>"
        "<h1>ENGL 102</h1><p>Composition and research writing for students "
        "who plan to transfer to a four-year college.</p>"
    )
    assert prerequisite(body) is None


REQUISITES_CARD = (
    "<main><h1>ACCT 463</h1><p>Bookkeeping for small business.</p>"
    "<div class='infocard'><h5>Requisites:</h5><div class='text'>{list}"
    "</div></div><div class='infocard'>"
    "<h5>Additional Requisite Information:</h5><div class='text'>"
    "<p>None</p></div></div></main>"
)


def requisite(label: str, course: str) -> str:
    return f"<p><strong>{label}</strong></p><p><a href='#'> {course} </a></p>"


def test_requisites_a_list_joins_with_or_are_one_prerequisite() -> None:
    """Each alternative is printed under a label of its own."""
    listed = "<br><p><strong>OR</strong></p><br>".join(
        [
            requisite("Prerequisite", "ACCT451A - Bookkeeping Concepts"),
            requisite("Prerequisite", "ACCT151A - Bookkeeping Concepts"),
            requisite("Prerequisite", "ACCT1A - Financial Accounting"),
        ]
    )
    assert prerequisite(REQUISITES_CARD.format(list=listed)) == (
        "ACCT451A - Bookkeeping Concepts OR ACCT151A - Bookkeeping Concepts "
        "OR ACCT1A - Financial Accounting"
    )


def test_an_and_joining_a_corequisite_is_not_part_of_the_prerequisite() -> None:
    listed = (
        requisite("Co-Requisite", "ART51L - Museum Viewing Lab")
        + "<p><strong>AND</strong></p>"
        + requisite("Prerequisite", "ART495A - Digital Fabrication")
        + "<br><p><strong>OR</strong></p><br>"
        + requisite("Prerequisite", "ART95A - Digital Fabrication")
    )
    assert prerequisite(REQUISITES_CARD.format(list=listed)) == (
        "ART495A - Digital Fabrication OR ART95A - Digital Fabrication"
    )


def test_a_bold_course_under_the_label_is_its_value_not_a_label() -> None:
    """The prerequisite course is printed in bold, under an h3."""
    body = (
        "<main><h1>ARTB55</h1><p>Design.</p><div><br/>"
        "<h3 class='introtext course-label'>Requisites</h3><br/>"
        "<h3 class='introtext course-label'>Prerequisite</h3><br/>"
        "<p><a href='#'><strong>ARTB40 - Digital Illustration</strong></a>"
        "</p><p class='text-format'>Successful completion of ART B40 with a "
        "grade of C or better.</p><p>OR</p>"
        "<h3 class='introtext course-label'>Prerequisite</h3><br/>"
        "<p><a href='#'><strong>ARTB41 - Advertising Design</strong></a></p>"
        "<p class='text-format'>Successful completion of ART B41.</p></div>"
        "<br/><h3 class='introtext course-label'>Materials Fees:</h3>"
        "<p class='course-content'>None</p></main>"
    )
    assert prerequisite(body) == (
        "ARTB40 - Digital Illustration Successful completion of ART B40 with "
        "a grade of C or better. OR ARTB41 - Advertising Design Successful "
        "completion of ART B41."
    )


REQUISITES_IN_DESCRIPTION = PAGE.format(
    title="AFMT 320",
    body=(
        "<main><h1>AFMT 320</h1><div class='introtext'><p>Limitation on "
        "Enrollment: Must be selected as part of the AFMT BS Degree cohort "
        "to take this course. Prerequisite: Completion of AFAB 210, ENGL "
        "315, and PSY 301. Corequisite: Concurrent enrollment in AFMT 330."
        "<br/> This course focuses on Lean principles.</p></div></main>"
    ),
)


def test_a_prerequisite_in_a_description_is_copied_out_and_left_there() -> None:
    """The description opens with the course's requisites."""
    found = values(extract_fields(ENTITY_COURSE, REQUISITES_IN_DESCRIPTION))
    assert found["course_prerequisites"] == (
        "Completion of AFAB 210, ENGL 315, and PSY 301."
    )
    assert found["course_description"].startswith("Limitation on Enrollment:")
    assert "Prerequisite: Completion of AFAB 210" in found["course_description"]


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        (
            "Prerequisite: Completion of ART 113. Instructional materials "
            "fee required.",
            "Completion of ART 113.",
        ),
        (
            "Prerequisite: Completion of AM 135A. Students supply tools.",
            "Completion of AM 135A.",
        ),
        (
            "Prerequisite: Proof of U.S. citizenship. Seats are limited.",
            "Proof of U.S. citizenship.",
        ),
    ],
)
def test_a_prerequisite_in_a_paragraph_ends_with_its_sentence(
    sentence: str, expected: str
) -> None:
    body = f"<main><h1>ART 213</h1><p>{sentence}<br/> A course.</p></main>"
    assert prerequisite(body) == expected


@pytest.mark.parametrize(
    "label", ["Prerequisite(s):", "Pre-requisite(s)", "Prereqs"]
)
def test_a_field_label_in_any_spelling_gives_the_prerequisite(
    label: str,
) -> None:
    body = (
        f"<main><h1>ENG 102</h1><dl><dt>{label}</dt><dd>ENG 101</dd></dl>"
        "</main>"
    )
    assert prerequisite(body) == "ENG 101"


CLEAN_CATALOG = (
    "<main><h1>PSYC 303</h1><p>Abnormal psychology.</p>"
    "<div class='degree-class-details'><div class='field'>"
    "<div class='field__label'>Prerequisite Courses</div>"
    "<div class='field__items'>{items}</div></div>{statement}</div></main>"
)


def course_item(name: str) -> str:
    return f"<div class='field__item'><a href='#'>{name}</a></div>"


def test_the_printed_statement_wins_over_the_list_of_courses_it_names() -> None:
    """The list is printed first and the fuller statement after."""
    body = CLEAN_CATALOG.format(
        items=course_item("CRIM101: Introduction to Criminal Justice"),
        statement=(
            "<div class='field'><div class='field__label'>Prerequisites</div>"
            "<div class='field__item'>CRIM101 with a grade of C or better."
            "</div></div>"
        ),
    )
    assert prerequisite(body) == "CRIM101 with a grade of C or better."


def test_the_list_of_courses_stands_in_when_no_statement_is_printed() -> None:
    body = CLEAN_CATALOG.format(
        items=course_item("PSYC101: General Psychology")
        + course_item("MATH220: Statistical Methods"),
        statement="",
    )
    assert prerequisite(body) == (
        "PSYC101: General Psychology; MATH220: Statistical Methods"
    )


def test_a_listing_of_courses_gives_its_first_prerequisite() -> None:
    """A subject page taken for one course must not mix two courses' own."""

    def block(code: str, required: str) -> str:
        return (
            "<div class='courseblock'><p class='courseblocktitle'><strong>"
            f"{code} | A Course</strong></p><p class='courseblockdesc'>Skills."
            "</p><p class='courseblockreqs'><strong>Prerequisite:</strong> "
            f"{required} with a grade of C or better</p></div>"
        )

    body = (
        "<main><h1>Behavioral Health (BEH)</h1>"
        + block("BEH 2001", "BEH 1001")
        + block("BEH 2040", "BEH 2030")
        + "</main>"
    )
    assert prerequisite(body) == "BEH 1001 with a grade of C or better"


def test_a_prerequisite_says_where_it_was_printed() -> None:
    """A reviewer finds the label and the value in one place."""
    listed = requisite("Prerequisite", "ACCT1A - Financial Accounting")
    under = drafts_by_label(
        extract_fields(
            ENTITY_COURSE,
            PAGE.format(title="", body=REQUISITES_CARD.format(list=listed)),
        )
    )["course_prerequisites"]
    assert under.excerpt == "Prerequisite ACCT1A - Financial Accounting"
    assert under.locator_value.endswith("div.text")
    inline = drafts_by_label(
        extract_fields(ENTITY_COURSE, REQUISITES_IN_DESCRIPTION)
    )
    line = inline["course_prerequisites"]
    assert line.excerpt == (
        "Prerequisite: Completion of AFAB 210, ENGL 315, and PSY 301."
    )
    assert line.locator_value.startswith("content line")


def test_a_prerequisite_is_a_field_toward_the_two_a_record_needs() -> None:
    """Unlike the unit, it is printed on its own, so it counts."""
    named = "<main><h1>Composition II</h1>{line}</main>"
    page = PAGE.format(
        title="", body=named.format(line="<p>Prerequisite: ENGL 101</p>")
    )
    assert values(extract_fields(ENTITY_COURSE, page)) == {
        "course_name": "Composition II",
        "course_prerequisites": "ENGL 101",
    }
    with pytest.raises(NothingToExtract):
        extract_fields(
            ENTITY_COURSE, PAGE.format(title="", body=named.format(line=""))
        )


def test_a_heading_without_a_wrapper_gives_only_the_block_under_it() -> None:
    """Under a page's own heading, the next paragraph is not the value too."""
    body = (
        "<h1>ENGL 102</h1><h3>Prerequisites</h3><p>ENGL 101</p>"
        "<p>Students will write research papers.</p>"
    )
    assert prerequisite(body) == "ENGL 101"


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            "<main><h1>ENGL 1A</h1><p>Composition.</p><div>"
            "<i class='course-Requisite-value'>Prerequisite: None.</i></div>"
            "</main>",
            id="curriqunet",
        ),
        pytest.param(DRUPAL_HEADING.format(value="None"), id="drupal-heading"),
        pytest.param(
            "<main><h1>ENG 102</h1><p>Writing.</p><dl><dt>Prerequisites</dt>"
            "<dd>N/A</dd></dl></main>",
            id="field-pair",
        ),
        pytest.param(
            "<main><h1>ENG 102</h1><p>Writing.</p>"
            "<p>Prerequisite: No prerequisites</p></main>",
            id="line",
        ),
    ],
)
def test_a_prerequisite_printed_as_none_is_left_out(body: str) -> None:
    assert prerequisite(body) is None


def test_none_followed_by_a_note_is_still_no_prerequisite() -> None:
    """Under one heading: "None", then a note."""
    body = DRUPAL_HEADING.format(
        value="None</div><div class='field__item'>Each student is "
        "responsible for completing and passing a background check."
    )
    assert prerequisite(body) is None


PRE_WRAP_DESCRIPTION = (
    "<main><header class='header l-body'><h2>Applications of Robotics</h2>"
    "<h3>ENGR 955:</h3><p class='header-x-meta'>0.0 Units</p></header>"
    "<div class='l-body'><div class='introtext l-introtext' "
    "style='white-space: pre-wrap;'><p>{paragraph}</p></div></div></main>"
)


@pytest.mark.parametrize(
    ("paragraph", "expected"),
    [
        pytest.param(
            "Prerequisite: Completion of ENGR 905\n\nBuilding upon the "
            "foundational knowledge established in the introductory course, "
            "this course offers a deeper exploration of robotics.",
            "Completion of ENGR 905",
            id="blank-line",
        ),
        pytest.param(
            "Prerequisite: Completion of DM 101\nThis course will focus on "
            "the fundamentals of video production and editing.",
            "Completion of DM 101",
            id="newline",
        ),
        pytest.param(
            "Prerequisite: Completion of Intermediate Algebra or placement by "
            "multiple measures&nbsp;\nThis course is primarily for students "
            "who plan to study calculus.",
            "Completion of Intermediate Algebra or placement by multiple "
            "measures",
            id="no-course-code",
        ),
    ],
)
def test_a_line_break_a_pre_wrap_description_shows_ends_the_prerequisite(
    paragraph: str, expected: str
) -> None:
    """In a white-space: pre-wrap description, the newline after the
    prerequisite is a line break on screen. Read as one paragraph, the
    prerequisite ran on into the description's first sentence.
    """
    page = PAGE.format(
        title="ENGR 955", body=PRE_WRAP_DESCRIPTION.format(paragraph=paragraph)
    )
    found = values(extract_fields(ENTITY_COURSE, page))
    assert found["course_prerequisites"] == expected
    # The description is read as it always was.
    assert found["course_description"].startswith("Prerequisite: Completion")


def test_a_prerequisite_run_into_the_description_is_not_read() -> None:
    """A page may print nothing at all between the two.

    No full stop and no line break then says where the prerequisite ends,
    and read to the end of the paragraph it is the whole description; the
    description itself is read as printed.
    """
    paragraph = (
        "Prerequisite: Completion of Intermediate Algebra or higher or "
        "placement by multiple measures A college-level course in algebra "
        "for non-STEM or liberal arts majors covering the properties and "
        "graphs of polynomial, rational, radical, absolute value, and "
        "exponential and logarithmic functions; solutions and applications "
        "of equations and systems of equations and inequalities from these "
        "functions; linear programming; and introduction to matrices and "
        "determinants in solving linear systems (C-ID: MATH 150) "
        "(UC, CSU)"
    )
    page = PAGE.format(
        title="MATH 128",
        body=f"<main><h1>MATH 128</h1><div class='introtext'><p>{paragraph}"
        "</p></div><dl><dt>Units</dt><dd>3</dd></dl></main>",
    )
    found = values(extract_fields(ENTITY_COURSE, page))
    assert "course_prerequisites" not in found
    assert found["course_description"] == paragraph


def test_a_prerequisite_that_opens_the_page_is_read_when_it_is_short() -> None:
    """Printed before the description, the prerequisite can be the page's
    first long line."""
    statement = (
        "College Readiness in English and College Readiness in Quantitative "
        "Literacy Math"
    )
    body = (
        "<table><tr><td class='block_content'><h1>CIS 2002 - Automated "
        f"Project Management</h1><strong>Prerequisite(s):</strong> {statement}"
        "<br><br>Covers the tools of project management.</td></tr></table>"
    )
    assert prerequisite(body) == statement


def test_a_long_prerequisite_on_its_own_line_is_read_whole() -> None:
    """A prerequisite can list every placement score that admits."""
    statement = " or ".join(
        f"Accuplacer Next Gen Writing with a score of {score}"
        for score in range(240, 260)
    )
    body = (
        "<main><h1>ENG 1021</h1><p>English Composition I emphasizes the "
        "planning, writing, and revising of compositions.</p>"
        f"<p><strong>Prerequisite(s):</strong> {statement}</p></main>"
    )
    assert prerequisite(body) == statement


def test_a_first_prerequisite_of_none_decides_there_is_none() -> None:
    """The first statement is the course's, the way one reading is the
    unit's; a later line naming a course belongs to some other course."""
    body = DRUPAL_HEADING.format(value="None").replace(
        "</main>", "<p>Prerequisite: ENGL 101</p></main>"
    )
    assert prerequisite(body) is None


@pytest.mark.parametrize(
    "label",
    [
        "Prerequisite/Corequisite",
        "Prerequisite and/or Corequisite",
        "Pre/Corequisite",
        "Prerequisite or Corequisite",
    ],
)
@pytest.mark.parametrize("printed_as", ["heading", "inline"])
def test_a_label_naming_both_relations_gives_no_prerequisite(
    label: str, printed_as: str
) -> None:
    """Taken before or alongside: not a prerequisite on its own."""
    shape = (
        "<h3>{label}</h3><p>ACC 1001</p>"
        if printed_as == "heading"
        else "<p><strong>{label}:</strong> ACC 1001</p>"
    )
    body = (
        "<main><h1>ACC 2001</h1><p>Intermediate accounting.</p>"
        + shape.format(label=label)
        + "</main>"
    )
    assert prerequisite(body) is None


def test_the_combined_fixture_gives_no_prerequisite(
    fixture_html_dir: Path,
) -> None:
    html = (fixture_html_dir / "course-prereq-coreq-combined.html").read_text(
        encoding="utf-8"
    )
    assert "course_prerequisites" not in values(
        extract_fields(ENTITY_COURSE, html)
    )


def test_a_value_that_names_both_relations_gives_no_prerequisite() -> None:
    """A plain heading over a combined statement."""
    body = (
        "<div id='main'><h1><span>ASE 1042</span> Brakes</h1>"
        "<div class='desc'><p>Brake systems.</p></div>"
        "<div class='sc_prereqs'><h2>Prerequisite</h2>Prerequisite/"
        "Corequisite: ASE 1041 . This course and ASE 1041 may be taken at "
        "the same time.</div></div>"
    )
    assert prerequisite(body) is None


@pytest.mark.parametrize(
    "line",
    [
        "Recommended Prerequisite: MATH 50",
        "Recommended Preparation: ARCH 121",
        "Advisory: ENGL 1A",
        "Corequisite: AEC 1231",
        "Limitation on Enrollment: Must be selected for the cohort.",
    ],
)
def test_a_recommendation_an_advisory_or_a_corequisite_is_no_prerequisite(
    line: str,
) -> None:
    body = f"<main><h1>ART 213</h1><p>A course.</p><p>{line}</p></main>"
    assert prerequisite(body) is None


def test_a_sentence_that_mentions_prerequisites_names_none() -> None:
    body = (
        "<main><h1>CHEM 101</h1><p>Satisfies the chemistry prerequisite or "
        "requirement for nursing. Covers any prerequisite skills needed by "
        "the student, with a minimum grade of C in prerequisite.</p></main>"
    )
    assert prerequisite(body) is None


# --- the entities the templates never could read ------------------------------


def test_a_credential_page_gives_a_credential_its_name_and_description(
    fixture_html_dir: Path,
) -> None:
    html = (fixture_html_dir / "program.html").read_text(encoding="utf-8")
    found = values(extract_fields(ENTITY_CREDENTIAL, html))
    assert found["credential_name"] == (
        "Associate in Science, Business Administration"
    )
    assert found["credential_description"]


def test_a_learning_opportunity_gives_a_learning_program(
    fixture_html_dir: Path,
) -> None:
    html = (fixture_html_dir / "minor-requirements.html").read_text(
        encoding="utf-8"
    )
    found = values(extract_fields(ENTITY_PROGRAM, html))
    assert found["learning_program_name"] == "Jewish Studies (JWST)"
    assert "minor" in found["learning_program_description"]


def test_a_competency_page_gives_one_competency_per_outcome(
    fixture_html_dir: Path,
) -> None:
    html = (fixture_html_dir / "outcomes-only.html").read_text(encoding="utf-8")
    drafts = extract_fields(ENTITY_COMPETENCY, html)
    texts = [
        draft.value
        for draft in drafts
        if draft.canonical_label == "competency_text"
    ]
    names = [
        draft.value
        for draft in drafts
        if draft.canonical_label == "competency_framework_name"
    ]
    assert len(texts) >= 2
    assert names == ["Institutional Learning Outcomes"]


# --- failing closed -----------------------------------------------------------


def test_a_page_printing_nothing_readable_raises() -> None:
    with pytest.raises(NothingToExtract):
        extract_fields(ENTITY_COURSE, "<html><body>unrelated</body></html>")


def test_a_page_with_only_a_name_is_not_a_record() -> None:
    """Every page has a name. A record holding only that was never read."""
    page = PAGE.format(
        title="Something", body="<main><h1>Something</h1></main>"
    )
    with pytest.raises(NothingToExtract):
        extract_fields(ENTITY_CREDENTIAL, page)


def test_a_page_listing_no_outcome_is_not_a_competency() -> None:
    with pytest.raises(NothingToExtract):
        extract_fields(ENTITY_COMPETENCY, DRUPAL)


def test_a_description_is_the_pages_prose_not_its_contact_block(
    fixture_html_dir: Path,
) -> None:
    """A bulletin opens with who to ring, which is not a description."""
    html = (
        fixture_html_dir / "program-bare-requirements-heading.html"
    ).read_text(encoding="utf-8")
    found = values(extract_fields(ENTITY_PROGRAM, html))
    assert found["learning_program_description"].startswith("Dental hygienists")
    assert "450-3194" not in found["learning_program_description"]
