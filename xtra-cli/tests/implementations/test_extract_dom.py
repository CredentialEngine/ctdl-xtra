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
    assert found["course_description"].startswith("Expository writing")


def test_a_courseleaf_course_is_read_from_its_block_title() -> None:
    """CourseLeaf labels nothing: the title line carries all three."""
    found = values(extract_fields(ENTITY_COURSE, COURSELEAF))
    assert found["course_id"] == "BREW 55703"
    assert found["course_name"] == "Production Design and Analysis of Beer"
    assert found["course_credits"] == 3
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

# Bakersfield's theme: the name in a <p>, the code in the h1, the units two
# wrappers below, and its hours as an h3 over a <p>.
ELUMEN_BAKERSFIELD = PAGE.format(
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
    """eLumen labels none of a course's code, name or units.

    Read as a page, every eLumen course was named after the catalog's
    hidden banner h1, "2026-27 Catalog", and carried its description and
    nothing else: no code, no units, no hours.
    """
    found = values(extract_fields(ENTITY_COURSE, ELUMEN))
    assert found["course_id"] == "ELEC 150"
    assert found["course_name"] == "Electrical Maintenance"
    assert found["course_credits"] == 4.0
    assert found["course_lecture_hours"] == 54.0
    assert found["course_lab_hours"] == 54.0
    assert found["course_description"].startswith("Prerequisite: Completion")


def test_the_other_elumen_theme_prints_the_code_in_the_h1() -> None:
    found = values(extract_fields(ENTITY_COURSE, ELUMEN_BAKERSFIELD))
    assert found["course_id"] == "FIRE B71A"
    assert found["course_name"] == "Seasonal Firefighter Basic Training 1"
    assert found["course_credits"] == 2.0
    assert found["course_lecture_hours"] == 27.0
    assert found["course_lab_hours"] == 27.0


def test_a_variable_unit_course_keeps_its_range() -> None:
    """Cabrillo prints "1.0 - 4.0 Units", written the way CourseLeaf's is."""
    page = PAGE.format(
        title="COMM 80SB - Special Studies II",
        body=(
            "<main><header class='header'><h2>Special Studies II</h2>"
            "<h3>COMM 80SB:</h3><p class='header-x-meta'>1.0 - 4.0 Units</p>"
            "</header><p>Independent study in communication studies under "
            "the direction of a faculty member.</p></main>"
        ),
    )
    assert values(extract_fields(ENTITY_COURSE, page))["course_credits"] == (
        "1.0-4.0"
    )


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
    html = (fixture_html_dir / "course-coursedog-brookdale.html").read_text(
        encoding="utf-8"
    )
    found = values(extract_fields(ENTITY_COURSE, html))
    assert found.get("course_credits") != "Min"


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
    assert values(extract_fields(ENTITY_COURSE, page))["course_credits"] == 1


def test_a_description_is_not_cut_at_six_hundred_characters() -> None:
    """Cut at the length the award rules read, every Cabrillo course
    description stopped mid-sentence."""
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
