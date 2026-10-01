from __future__ import annotations

from pathlib import Path

import pytest
from discovery_doubles import fixture_url

from implementations.discover_page import (
    field_labels_of,
    page_type_of,
    parse_structure,
    profile_page,
    read_program_evidence,
)

# What each hand-written fixture is meant to demonstrate. When a rule in
# discover_rules changes, this table is the thing that has to still hold.
EXPECTED = {
    "course-single.html": {
        "page_type": "Course",
        "labels": ["Course"],
        "markers": {"catalog_year", "prerequisite"},
        "field_labels": {"credits", "department", "prerequisite"},
    },
    "course-prereq-coreq-combined.html": {
        "page_type": "Course",
        "labels": ["Course"],
        "markers": {
            "catalog_year",
            "prerequisite",
            "corequisite",
            "prerequisite_corequisite_combined",
        },
        "field_labels": {"credits", "department"},
    },
    "course-lecture-lab-credit.html": {
        "page_type": "Course",
        "labels": ["Course"],
        "markers": {
            "catalog_year",
            "lecture_lab_credit_numbers",
            "lab_clinical_field_study_hours",
            "printed_zero_hours",
        },
        "field_labels": {"credits", "lab hours", "clinical hours"},
    },
    "course-with-outcomes.html": {
        "page_type": "Multiple",
        "labels": ["Course", "Competency"],
        "markers": {"catalog_year", "learning_outcomes"},
        "field_labels": {"credits", "department"},
    },
    # The h1 is "Associate in Science, Business Administration", so the page
    # names the award it grants. In CTDL that award is the entity worth
    # publishing, which makes this a Credential page and not the program
    # that leads to it.
    "program.html": {
        "page_type": "Credential",
        "labels": ["Credential"],
        "markers": {"catalog_year", "credential_award", "program_markers"},
        "field_labels": set(),
    },
    # The same shape with no award anywhere: a non-credit training program
    # that prints its requirements and never says degree or certificate.
    "learning-program.html": {
        "page_type": "LearningOpportunity",
        "labels": ["LearningOpportunity"],
        "markers": {"catalog_year", "program_markers"},
        "field_labels": set(),
    },
    # A vendor certification. No course codes, no program vocabulary, and
    # nothing but the heading to say what the page is.
    "credential-certification.html": {
        "page_type": "Credential",
        "labels": ["Credential"],
        "markers": {"credential_award"},
        "field_labels": set(),
    },
    # Acalog and Coursedog put a qualifier between the noun and the value.
    # Reading "CREDIT HOURS MIN: 3" as no value left four live Ivy Tech
    # course pages with no course block and no label at all.
    "course-credit-hours-min.html": {
        "page_type": "Course",
        "labels": ["Course"],
        "markers": {"lab_clinical_field_study_hours"},
        "field_labels": set(),
    },
    # Non-breaking spaces inside the codes, and a catalog that encodes the
    # credit count in the course number instead of printing one. Zero
    # course blocks, and still a page of course descriptions.
    "course-list-no-credits.html": {
        "page_type": "Course",
        "labels": ["Course"],
        "markers": set(),
        "field_labels": set(),
    },
    # A bot wall answers 200 with prose. Without a rule for it, a page that
    # was never fetched profiles as a real one and can enter the sample.
    "blocked-page.html": {
        "page_type": "Unknown",
        "labels": [],
        "markers": {"empty_or_error_page"},
        "field_labels": set(),
    },
    "outcomes-only.html": {
        "page_type": "Competency",
        "labels": ["Competency"],
        "markers": {"catalog_year", "learning_outcomes"},
        "field_labels": set(),
    },
    "multi-course.html": {
        "page_type": "Course",
        "labels": ["Course"],
        "markers": {"catalog_year", "multi_course_page"},
        "field_labels": set(),
    },
    "policy-course-numbering.html": {
        "page_type": "Unknown",
        "labels": [],
        "markers": {"catalog_year", "policy_or_definition_page"},
        "field_labels": set(),
    },
    "error-page.html": {
        "page_type": "Unknown",
        "labels": [],
        "markers": {"empty_or_error_page"},
        "field_labels": set(),
    },
    "course-title-in-h2.html": {
        "page_type": "Course",
        "labels": ["Course"],
        "markers": {"catalog_year"},
        "field_labels": {"credits", "department"},
    },
    # A real Clean Catalog course page: the breadcrumb prints the code and
    # the heading prints it again, and the main menu is called "Degrees &
    # Certificates". Neither makes this two courses or a credential.
    "course-breadcrumb-repeats-code.html": {
        "page_type": "Course",
        "labels": ["Course"],
        "markers": {"lab_clinical_field_study_hours", "printed_zero_hours"},
        "field_labels": set(),
    },
    # A Clean Catalog program page. The h1 is only "Biology"; the award is
    # the badge printed above it. On the real site the nav menu's
    # "Degrees" was the only award these pages were ever credited with, and
    # the outcome list every one of them prints was never found.
    "program-award-badge.html": {
        "page_type": "Multiple",
        "labels": ["Credential", "Competency"],
        "markers": {
            "credential_award",
            "learning_outcomes",
            "program_markers",
            "published_as",
        },
        "field_labels": {"course #", "credits", "title"},
    },
    # The same page shape badged "Program (not a degree)", and an intro
    # that mentions a certificate as a goal of the students it serves.
    "program-not-a-degree.html": {
        "page_type": "LearningOpportunity",
        "labels": ["LearningOpportunity"],
        "markers": {"program_markers", "published_as"},
        "field_labels": {"course #", "credits", "title"},
    },
    # A graduation policy under a menu called "Degrees & Certificates" and a
    # sidebar linking "Degree Requirements", with "degree requirements" and
    # "spring semester" in its prose. The real page was labelled a
    # Credential, and 39 pages like it LearningOpportunity.
    "policy-with-menus.html": {
        "page_type": "Unknown",
        "labels": [],
        "markers": set(),
        "field_labels": set(),
    },
    # CourseLeaf names the award in a section heading, never in the h1.
    "program-award-in-heading.html": {
        "page_type": "Credential",
        "labels": ["Credential"],
        "markers": {
            "course_requirement_list",
            "credential_award",
            "multi_course_page",
            "program_markers",
        },
        "field_labels": set(),
    },
    # A minor prints its requirements and earns no award of its own.
    "minor-requirements.html": {
        "page_type": "LearningOpportunity",
        "labels": ["LearningOpportunity"],
        "markers": {"course_requirement_list", "program_markers"},
        "field_labels": set(),
    },
    # A school offering four degrees, with its sections numbered. It
    # prints requirements and names awards, for every programme it runs
    # at once, so it is nobody's credential page. Read as one, every
    # school and college in a bulletin became a Credential.
    "department-several-awards.html": {
        "page_type": "Unknown",
        "labels": [],
        "markers": {"course_requirement_list"},
        "field_labels": set(),
    },
    # The same shape under a name that is not an organisation's. It keeps
    # the Credential label and says out loud that there are several, the
    # way a page of several courses does.
    "department-multi-credential.html": {
        "page_type": "Credential",
        "labels": ["Credential"],
        "markers": {
            "course_requirement_list",
            "credential_award",
            "multi_credential_page",
            "program_markers",
        },
        "field_labels": set(),
    },
    # A bulletin that numbers every heading. Every heading rule is
    # anchored at the start of the line, so "[2] Baccalaureate Degree:
    # Bachelor of Science" matched none of them and the whole bulletin's
    # programs were Unknown.
    "program-numbered-headings.html": {
        "page_type": "Credential",
        "labels": ["Credential"],
        "markers": {"credential_award", "multi_course_page", "program_markers"},
        "field_labels": set(),
    },
    # A pre-professional programme headed just "Requirements" over the
    # courses it asks for, and naming no award because it grants none.
    # Nine of them at Central Arkansas were read as course pages or as
    # nothing at all.
    "program-bare-requirements-heading.html": {
        "page_type": "LearningOpportunity",
        "labels": ["LearningOpportunity"],
        "markers": {"prerequisite", "program_markers"},
        "field_labels": {"be completed here"},
    },
    # A page of course descriptions whose prerequisites read "and 45 total
    # credit hours completed". Read as the page's own credit total, that
    # clause made a run of film courses a learning opportunity.
    "course-list-prose-total.html": {
        "page_type": "Course",
        "labels": ["Course"],
        "markers": {"multi_course_page", "prerequisite"},
        "field_labels": set(),
    },
    # A graduate course listing under a sidebar linking "Degree
    # Requirements". The link kept 92 real listings from being course pages.
    "course-listing-with-sidebar.html": {
        "page_type": "Course",
        "labels": ["Course"],
        "markers": {"multi_course_page"},
        "field_labels": set(),
    },
}

# Enough text to clear EMPTY_PAGE_CHARS, so a hand-written page is not an
# empty one.
FILLER = (
    "<p>This description is published by the college for the current "
    "catalog and is reviewed each year by the academic department that "
    "offers it. Students should speak with an advisor before registering, "
    "since availability varies by term and by campus. The wording below is "
    "used for the print edition and the web edition alike, so the two stay "
    "identical. Questions about the text itself should go to the office "
    "that maintains the catalog rather than to the department.</p>"
)


def profile_fixture(fixture_html_dir: Path, name: str):
    return profile_page(
        url=fixture_url(Path(name).stem),
        html=(fixture_html_dir / name).read_text(encoding="utf-8"),
        stem=Path(name).stem,
    )


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_fixture_profiles_as_intended(
    fixture_html_dir: Path, name: str
) -> None:
    expected = EXPECTED[name]
    profile = profile_fixture(fixture_html_dir, name)
    assert profile.page_type == expected["page_type"]
    assert profile.labels == expected["labels"]
    assert set(profile.markers) == expected["markers"]
    assert set(profile.field_labels) == expected["field_labels"]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_marker_carries_its_evidence(
    fixture_html_dir: Path, name: str
) -> None:
    profile = profile_fixture(fixture_html_dir, name)
    for marker, quote in profile.markers.items():
        assert quote, f"{marker} fired with no evidence"
        assert len(quote) <= 80


def test_a_course_title_in_a_heading_never_becomes_a_field_label(
    fixture_html_dir: Path,
) -> None:
    """Headings carry course titles, so they stay out of the vocabulary."""
    profile = profile_fixture(fixture_html_dir, "course-title-in-h2.html")
    assert "ACCT 101 Principles of Accounting" in profile.headings
    for label in profile.field_labels:
        assert "acct" not in label
        assert "principles of accounting" not in label


def test_a_heading_is_never_a_label_even_without_a_course_code() -> None:
    html = "<h2>Description of the Course Content</h2><dt>Credits</dt>"
    structure = parse_structure(html)
    labels = field_labels_of(structure, "")
    assert labels == ["credits"]
    assert structure.headings == ["Description of the Course Content"]


def test_a_bold_run_is_a_label_only_when_something_follows_it() -> None:
    """`<strong>Credits</strong> 3` is a label. A bold title is not."""
    html = (
        "<p><strong>Credits</strong> 3</p>"
        "<p><strong>Prerequisite:</strong></p>"
        "<p><strong>Introduction to Welding</strong></p>"
    )
    labels = field_labels_of(parse_structure(html), "")
    assert labels == ["credits", "prerequisite"]


def test_a_short_line_ending_in_a_colon_is_a_label() -> None:
    text = "Credits:\n3\nThis sentence is far too long to be a key and ends:\n"
    labels = field_labels_of(parse_structure(""), text)
    assert labels == ["credits"]


def test_digits_in_a_label_collapse_so_terms_group() -> None:
    html = "<dt>Semester 1</dt><dt>Semester 2</dt>"
    assert field_labels_of(parse_structure(html), "") == ["semester #"]


def test_outcomes_need_a_heading_and_two_items() -> None:
    one_item = (
        "<h3>Learning Outcomes</h3><ul><li>Apply the nursing process.</li></ul>"
    )
    assert not parse_structure(one_item).outcomes_evidence
    two_items = (
        "<h3>Learning Outcomes</h3><ul><li>Apply the nursing process.</li>"
        "<li>Document patient care.</li></ul>"
    )
    assert parse_structure(two_items).outcomes_evidence == "Learning Outcomes"


def test_a_list_under_an_unrelated_heading_is_not_an_outcome_list() -> None:
    html = (
        "<h3>Learning Outcomes</h3><h3>Course Fees</h3>"
        "<ul><li>Laboratory fee of forty dollars</li>"
        "<li>Clinical uniform and badge</li></ul>"
    )
    assert not parse_structure(html).outcomes_evidence


def test_an_outcome_list_is_found_whatever_element_leads_it_in() -> None:
    """Clean Catalog's lead-in is a <div>, and every Atlantic Cape program has one.

    Only headings, labels and bold runs could lead a list in, so all 85 of
    the college's outcome lists were missed.
    """
    structure = parse_structure(
        "<main><div class='field__label'>Upon completion of this program "
        "students will be able to:</div><div class='field__item'><ul>"
        "<li>Correctly explain and apply the scientific method;</li>"
        "<li>Demonstrate safe laboratory practices;</li></ul></div></main>"
    )
    assert structure.outcomes_evidence == (
        "Upon completion of this program students will be able to:"
    )


def test_an_outcome_does_not_have_to_be_a_list_item() -> None:
    """Coursedog prints each outcome in a <div> of its own."""
    structure = parse_structure(
        "<main><label>Learning Outcomes:</label>"
        "<div><div class='field-value'>Use the writing process to compose "
        "analytical essays</div></div>"
        "<div><div class='field-value'>Employ active reading strategies to "
        "interpret complicated texts</div></div></main>"
    )
    assert structure.outcomes_evidence == "Learning Outcomes:"


@pytest.mark.parametrize(
    "html",
    [
        # A course title with the word in it, over a course description.
        (
            "<main><p><strong>PSYC 62103. Psychotherapy Outcomes. 3 Hours.</strong>"
            "</p><p>Review of research on the outcomes of psychotherapy.</p>"
            "<p><strong>PSYC 62203. Research Methods. 3 Hours.</strong></p></main>"
        ),
        # The same title in a requirements table, with its credits.
        (
            "<main><table><tr><td>PSYC 62103</td><td>Psychotherapy Outcomes</td>"
            "<td>3</td></tr><tr><td>PSYC 62203</td><td>Research Methods</td>"
            "<td>3</td></tr></table></main>"
        ),
        # A college's mission, whose bullets read like outcomes.
        (
            "<main><h2>Mission and Objectives</h2><ul>"
            "<li>Advance impactful research in education and health.</li>"
            "<li>Expand service to the state through partnerships.</li></ul></main>"
        ),
        # What a program does, not what its students learn.
        (
            "<main><p>The major objectives of the program are as follows:</p><ul>"
            "<li>To provide a broad flexible program for public service careers</li>"
            "<li>To prepare scholars for further graduate study</li></ul></main>"
        ),
        # Admission standards, not outcomes.
        (
            "<main><p>The following abilities and expectations must be met by all "
            "students admitted to the program:</p><ul>"
            "<li>The mental capacity to assimilate and analyze concepts</li>"
            "<li>Sufficient motor coordination to use equipment</li></ul></main>"
        ),
        # A general education category, followed by the courses in it.
        (
            "<main><h3>Technological Competency (IT) - 3 credits</h3><ul>"
            "<li>CISM 125 Computer Concepts</li><li>CISM 130 Spreadsheets</li>"
            "</ul></main>"
        ),
    ],
)
def test_a_list_that_only_mentions_outcomes_is_not_a_competency_list(
    html: str,
) -> None:
    """Every one of these was a Competency page at the University of Arkansas
    or Brookdale, most of them because the lead-in counted every <li> after
    it, the footer's included."""
    assert not parse_structure(html).outcomes_evidence


def test_the_footer_s_links_are_not_outcomes() -> None:
    structure = parse_structure(
        "<main><h2>Institutional learning outcomes</h2>"
        "<p>The outcomes are shown in the chart below.</p>"
        "<img src='outcomes.jpg' alt='Chart'></main>"
        "<footer><h2>Connect with us!</h2><ul><li>Instagram feed</li>"
        "<li>Facebook page</li><li>YouTube channel</li></ul></footer>"
    )
    assert not structure.outcomes_evidence


def test_tabs_are_noticed_by_role_or_by_class() -> None:
    assert parse_structure('<div role="tab">A</div>').tabs_evidence
    assert parse_structure('<ul class="nav tabs">x</ul>').tabs_evidence
    assert not parse_structure(
        '<div class="tabular-data">x</div>'
    ).tabs_evidence


def test_script_and_style_text_is_not_page_content() -> None:
    html = (
        "<style>.x{}</style><script>var credits = 3;</script><dt>Credits</dt>"
    )
    assert field_labels_of(parse_structure(html), "") == ["credits"]


def test_page_type_names_the_single_label_or_says_how_many() -> None:
    assert page_type_of([]) == "Unknown"
    assert page_type_of(["Course"]) == "Course"
    assert page_type_of(["Course", "Competency"]) == "Multiple"


def test_the_same_page_always_profiles_the_same_way(
    fixture_html_dir: Path,
) -> None:
    first = profile_fixture(fixture_html_dir, "course-single.html")
    second = profile_fixture(fixture_html_dir, "course-single.html")
    assert first.as_dict() == second.as_dict()


def test_a_repeated_course_code_still_counts_as_one_course(
    fixture_html_dir: Path,
) -> None:
    profile = profile_fixture(fixture_html_dir, "course-single.html")
    assert profile.course_code_count == 1
    assert profile.course_block_count == 1


def test_rules_fired_records_why_each_label_applied(
    fixture_html_dir: Path,
) -> None:
    profile = profile_fixture(fixture_html_dir, "course-with-outcomes.html")
    assert set(profile.rules_fired) == {"Course", "Competency"}
    assert "course block" in profile.rules_fired["Course"]


def test_the_profile_records_the_url_template_with_digits_removed() -> None:
    profile = profile_page(
        url="https://catalog.example.edu/content.php?catoid=13&navoid=664",
        html="<h1>x</h1>",
        stem="stem",
    )
    assert profile.url_template == "/content.php?catoid={n}&navoid={n}"


def test_nothing_normalized_is_written_into_the_profile(
    fixture_html_dir: Path,
) -> None:
    """Normalized text is read in memory; only its hash is kept."""
    profile = profile_fixture(fixture_html_dir, "course-single.html")
    payload = profile.as_dict()
    assert len(payload["text_sha256"]) == 64
    assert "text" not in payload
    assert "normalized" not in payload


def test_a_repeated_code_and_a_navigation_menu_do_not_change_what_a_page_is(
    fixture_html_dir: Path,
) -> None:
    """The two false positives a live Clean Catalog crawl produced.

    Every course page carried multi_course_page, because the breadcrumb
    repeats the code above the heading, and program_markers, because the
    menu is called "Degrees & Certificates". The first made extraction skip
    every course; the second put a marker on all of them, which tells a
    reviewer nothing.
    """
    profile = profile_fixture(
        fixture_html_dir, "course-breadcrumb-repeats-code.html"
    )
    assert profile.course_code_count == 1
    assert profile.course_block_count == 1
    assert "multi_course_page" not in profile.markers
    assert "program_markers" not in profile.markers
    assert profile.page_type == "Course"


def test_a_page_that_prints_credential_content_still_carries_the_marker(
    fixture_html_dir: Path,
) -> None:
    """The marker has to keep working where it is true."""
    profile = profile_fixture(fixture_html_dir, "program.html")
    assert "program_markers" in profile.markers
    assert profile.page_type == "Credential"


def test_a_program_is_a_credential_only_once_it_names_the_award() -> None:
    """The one line between the two program labels.

    Both pages print the same requirements. One says which award finishing
    them earns and the other does not, and that is the whole difference:
    the award is the entity that gets published, the program is not.
    """
    body = (
        "<h2>Program Requirements</h2><p>Total Credits: 60</p>"
        f"<h3>Course Sequence</h3><p>Two years of full-time study.</p>{FILLER}"
    )
    named = profile_page(
        url="https://catalog.example.edu/programs/business",
        html=f"<title>Business</title><h1>Business, Associate in Science</h1>{body}",
        stem="named",
    )
    unnamed = profile_page(
        url="https://catalog.example.edu/programs/business",
        html=f"<title>Business</title><h1>Business Career Training</h1>{body}",
        stem="unnamed",
    )
    assert named.labels == ["Credential"]
    assert named.rules_fired["Credential"] == "award in the name: Associate in"
    assert unnamed.labels == ["LearningOpportunity"]


def test_a_course_page_is_not_a_credential_because_of_its_own_menu() -> None:
    """Every page of a catalog links to "Degrees & Certificates".

    55 of the 70 pages in the reference crawl carry an award word
    somewhere in their furniture, so the award only counts where the page
    names itself: the title and the h1.
    """
    profile = profile_page(
        url="https://catalog.example.edu/courses/engl101",
        html=(
            "<title>ENGL 101 Composition I</title>"
            "<nav><a href='/degrees'>Degrees &amp; Certificates</a></nav>"
            "<h1>ENGL 101 Composition I</h1><p>Credits 3</p>"
        ),
        stem="engl101",
    )
    assert profile.labels == ["Course"]
    assert "credential_award" not in profile.markers


INTRO = (
    "<p>The school contributes to the three purposes of the university, "
    "education, research and service, and its faculty teach in every "
    "program listed below.</p>"
)


def page(html: str, url: str = "https://catalog.example.edu/page"):
    """A hand-written page long enough that no rule can skip it as empty."""
    profile = profile_page(url=url, html=f"{html}{FILLER}", stem="page")
    assert "empty_or_error_page" not in profile.markers
    return profile


def test_the_page_is_read_without_its_menus_sidebars_and_footer() -> None:
    """Furniture is dropped; a program's own header is not furniture.

    Clean Catalog prints the site banner as a <header role="banner"> and a
    program's h1 and award badge inside a <header> of the program's own,
    within <main>. Only the first is the site's.
    """
    structure = parse_structure(
        "<header role='banner'><p>College Catalog</p></header>"
        "<nav><a href='/degrees'>Degrees &amp; Certificates</a></nav>"
        "<aside><a href='/req'>Degree Requirements</a></aside>"
        "<main><header><div>Associate in Science</div><h1>Biology</h1>"
        "</header><p>Program text.</p></main>"
        "<footer><p>Staff Login</p></footer>"
    )
    assert structure.content_text.splitlines() == [
        "Associate in Science",
        "Biology",
        "Program text.",
    ]
    assert structure.h1 == "Biology"


def test_the_h1_is_the_page_s_own_not_the_one_in_the_sidebar() -> None:
    """Coursedog prints the college's name as an h1 in the sidebar."""
    structure = parse_structure(
        "<aside><h1>Example Community College</h1></aside>"
        "<main><h1>Graduation Requirements</h1><h2>Overview</h2></main>"
    )
    assert structure.h1 == "Graduation Requirements"
    assert structure.content_headings == ["Overview"]


def test_a_paragraph_wrapped_across_source_lines_is_one_line() -> None:
    structure = parse_structure(
        "<main><p>One sentence\nwrapped\nthree times.</p></main>"
    )
    assert structure.content_text == "One sentence wrapped three times."


def test_a_listing_of_programs_is_not_a_credential() -> None:
    """The "Degrees and Certificates" page names every award there is."""
    profile = page(
        "<main><h1>Degrees and Certificates</h1><ul>"
        "<li>Biology, Associate in Science</li>"
        "<li>Culinary Arts I, Certificate</li>"
        "<li>Commercial Pilot, Professional Series</li></ul></main>"
    )
    assert profile.labels == []


def test_a_listing_under_an_award_url_is_still_a_listing() -> None:
    """The URL says credential; the name says list, and the name is right."""
    listing = page(
        f"<main><h1>Degrees and Certificates</h1>{INTRO}</main>",
        url="https://catalog.example.edu/degrees/all",
    )
    one = page(
        f"<main><h1>Nursing</h1>{INTRO}</main>",
        url="https://catalog.example.edu/degrees/nursing",
    )
    assert listing.labels == []
    assert one.labels == ["Credential"]
    assert one.rules_fired["Credential"] == "url template /degrees/nursing"


def test_a_stub_named_after_an_award_type_is_not_a_credential() -> None:
    """Atlantic Cape keeps a near-empty page per award type.

    /associate-in-applied-science is 303 characters: the award type's name
    and a PDF link. Its name alone made it a Credential. Either reason is
    enough on its own: the page is empty, and the name is an award type.
    """
    stub = profile_page(
        url="https://catalog.example.edu/associate-in-applied-science",
        html="<main><h1>Associate in Applied Science</h1><p>Download as PDF</p></main>",
        stem="aas",
    )
    assert "empty_or_error_page" in stub.markers
    assert stub.labels == []
    described = page(
        f"<main><h1>Associate in Applied Science</h1>{INTRO}</main>"
    )
    assert described.labels == []


def test_a_college_overview_is_neither_a_program_nor_a_credential() -> None:
    """A college prints requirements and names awards for all its programs."""
    profile = page(
        "<main><h1>College of Engineering</h1>"
        "<h2>Degree Requirements</h2><p>Total Hours: 120</p>"
        "<h2>Degrees Offered</h2><p>The college offers the B.S. in six fields.</p>"
        "</main>"
    )
    assert profile.labels == []
    assert "program_markers" not in profile.markers


def test_a_school_printing_one_degree_s_requirements_is_a_credential() -> None:
    """A school's name does not hide the degree whose requirements it prints."""
    profile = page(
        f"<main><h1>Eleanor Example School of Nursing (NURS)</h1>{INTRO}"
        "<h2>Requirements for B.S.N. in Nursing</h2><p>Total Hours: 120</p></main>"
    )
    assert profile.labels == ["Credential"]
    assert profile.rules_fired["Credential"] == "award in a heading: B.S.N."


def test_a_heading_listing_several_awards_is_a_rule_for_all_of_them() -> None:
    """The real page is a college's, and the heading does not make it a program's."""
    profile = page(
        f"<main><h1>College of Education and Health Professions</h1>{INTRO}"
        "<h2>Minimum Requirements for the B.S.E. or B.S. or B.S.N. Degree</h2>"
        "<p>Total Hours: 120</p></main>"
    )
    assert profile.labels == []


def test_a_glossary_term_is_not_a_section_of_the_page() -> None:
    """A bold term is a definition, not a heading over requirements."""
    profile = page(
        "<main><h1>Glossary</h1>"
        "<p><strong>Certification/Licensure Requirements.</strong> The "
        "conditions a student must meet to sit for a license exam.</p>"
        "<p><strong>Curriculum.</strong> The set of courses a program requires, "
        "listed by term with a total.</p></main>"
    )
    assert profile.labels == []


def test_a_course_title_that_mentions_a_degree_is_not_a_heading() -> None:
    """ "FREN 30603. Ph.D. Reading Requirement I." is a course, not a Ph.D.

    Read as a heading it named an award and said "requirement", which is
    the strongest evidence a program page prints, and the course listing it
    sits on became a Credential.
    """
    structure = parse_structure(
        "<main><h1>French (FREN)</h1>"
        "<h3>FREN 30603. Ph.D. Reading Requirement I. 3 Hours.</h3>"
        "<p>Reading knowledge of French for doctoral students.</p></main>"
    )
    program = read_program_evidence(structure, "/coursesofinstruction/fren/")
    assert program.award_requirements_heading == ""
    assert program.heading_award is None
    assert not program.prints_requirements


def test_a_contact_block_beside_the_name_names_no_award(
    fixture_html_dir: Path,
) -> None:
    """CourseLeaf lists the program's staff under its name.

    Read for a badge, those lines gave "Ph.D." (the director's), "J.B."
    (a building) and "J.D." (a professor's initials) as the award of the
    programs they run.
    """
    profile = profile_fixture(fixture_html_dir, "program-award-in-heading.html")
    assert profile.rules_fired["Credential"] == "award in a heading: B.S."


def test_the_award_can_sit_one_line_under_the_name() -> None:
    """CourseLeaf graduate certificates: the h1 names the subject only."""
    profile = page(
        "<main><h1>Analytics for Operations Management (OMOA)</h1>"
        "<p>Graduate Microcertificate in Analytics for Operations Management</p>"
        "<p>Required Courses (6 hours)</p><p>Total Hours 6</p></main>"
    )
    assert profile.labels == ["Credential"]
    assert profile.rules_fired["Credential"] == (
        "award beside the name: Microcertificate"
    )


def test_a_declaration_names_the_awards_a_page_confers() -> None:
    """ "Degrees Conferred:" says what the page is, and which awards."""
    profile = page(
        f"<main><h1>Electrical Engineering (ELEG)</h1>{INTRO}"
        "<h2>Program Overview</h2><p>Degrees Conferred:</p>"
        "<p>M.S.E.E. (ELEGMS), Ph.D. (ELEGPH)</p></main>"
    )
    assert profile.labels == ["Credential"]
    assert profile.rules_fired["Credential"] == "award declared: M.S.E.E."


def test_the_url_and_one_named_award_together_make_a_credential() -> None:
    """Neither alone is enough: a program URL and "The Master of ..." are."""
    html = (
        "<main><h1>Clinton School of Public Service (UACS)</h1>"
        "<p>The Master of Public Service degree is offered at the Clinton "
        "School in collaboration with three other campuses of the "
        "university system, with coursework in Little Rock.</p></main>"
    )
    under_programs = page(
        html, url="https://catalog.example.edu/programsofstudy/clintonschool/"
    )
    elsewhere = page(
        html, url="https://catalog.example.edu/about/clintonschool/"
    )
    assert under_programs.labels == ["Credential"]
    assert elsewhere.labels == []


def test_a_word_in_the_url_slug_is_not_a_program() -> None:
    """Atlantic Cape's /honors-program and /credit-amnesty-program are policies."""
    profile = page(
        "<main><h1>Honors Program</h1><p>Students with a 3.5 average may apply.</p></main>",
        url="https://catalog.example.edu/2026-2027-catalog/honors-program",
    )
    assert profile.labels == []
