from __future__ import annotations

import pytest

from implementations.discover_rules import (
    AWARD_DECLARATION_RE,
    COURSE_TITLE_RE,
    COURSE_URL_RE,
    CREDIT_VALUE_RE,
    EMPTY_OR_ERROR_RE,
    LABEL_CREDENTIAL,
    LABEL_LEARNING_OPPORTUNITY,
    LECTURE_LAB_CREDIT_RE,
    MARKER_MEANING,
    MARKER_NAMES,
    PREREQ_COREQ_COMBINED_RE,
    REQUIREMENTS_HEADING_RE,
    TOTAL_CREDITS_RE,
    award_in_heading,
    award_in_intro,
    award_in_name,
    award_in_name_line,
    catalog_year_value,
    course_block_count,
    course_codes,
    credential_award,
    distinct_awards,
    evidence,
    has_program_structure,
    heading_body,
    is_contact_line,
    is_outcome_statement,
    is_outcomes_lead_in,
    names_a_listing,
    names_an_organization_or_policy,
    normalize_course_code,
    normalize_field_label,
    program_structure_terms,
    program_terms,
    singular_award,
    specific_award,
    total_credits_line,
    url_label,
    url_template,
)


@pytest.mark.parametrize(
    ("url", "template"),
    [
        ("https://x.edu/courses/engl101", "/courses/engl{n}"),
        (
            "https://x.edu/content.php?catoid=13&navoid=664",
            "/content.php?catoid={n}&navoid={n}",
        ),
        ("https://x.edu", "/"),
        ("https://x.edu/2026-2027/a", "/{n}-{n}/a"),
    ],
)
def test_url_template_folds_digits(url: str, template: str) -> None:
    assert url_template(url) == template


@pytest.mark.parametrize(
    ("raw", "label"),
    [
        ("Credits:", "credits"),
        ("  Lab   Hours  ", "lab hours"),
        ("Semester 1", "semester #"),
        ("PREREQUISITE", "prerequisite"),
        ("Total Credits.", "total credits"),
    ],
)
def test_normalize_field_label(raw: str, label: str) -> None:
    assert normalize_field_label(raw) == label


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        ":",
        "ENGL 101 Composition I",
        "A label far longer than any key a catalog would ever print on a page",
    ],
)
def test_text_that_is_not_a_label_is_dropped(raw: str) -> None:
    assert normalize_field_label(raw) is None


def test_a_credits_value_is_read_in_either_order() -> None:
    assert CREDIT_VALUE_RE.search("3 credits")
    assert CREDIT_VALUE_RE.search("Credits: 3")
    assert CREDIT_VALUE_RE.search("Credits\n3")
    assert CREDIT_VALUE_RE.search("1-3 credit hours")
    assert CREDIT_VALUE_RE.search("4.0 units")


def test_a_credit_word_inside_another_word_is_not_a_value() -> None:
    """Without the boundary, every accredited college prints credits."""
    assert not CREDIT_VALUE_RE.search("accredited by 3 agencies")
    assert not CREDIT_VALUE_RE.search("3 crop science degrees")


@pytest.mark.parametrize(
    "printed",
    [
        "CREDIT HOURS MIN: 3",
        "Credit Hours Min 3",
        "Credit Hours Max: 4",
        "Credit Hour(s): 3",
        "Minimum Credits: 3",
        "1 Course Unit",
        "3 semester hours",
    ],
)
def test_a_qualifier_between_the_noun_and_the_value_is_still_a_value(
    printed: str,
) -> None:
    """Coursedog and Acalog never print the noun on its own.

    Reading "CREDIT HOURS MIN: 3" as no value at all gave four live Ivy
    Tech course pages zero course blocks, so none of them was labelled a
    Course and none could be sampled.
    """
    assert CREDIT_VALUE_RE.search(printed), printed


def test_a_course_block_needs_a_code_and_a_value_near_it() -> None:
    assert course_block_count("ENGL 101 Composition I\nCredits\n3") == 1
    assert course_block_count("See ENGL 101 for details.") == 0
    assert course_block_count("ENGL 101\nCredits 3\nENGL 102\nCredits 3") == 2


def test_a_value_too_far_from_the_code_is_a_different_course() -> None:
    far = "ENGL 101" + ("x" * 500) + " 3 credits"
    assert course_block_count(far) == 0


def test_three_numbers_in_a_row_are_lecture_lab_and_credit() -> None:
    assert LECTURE_LAB_CREDIT_RE.search("2-3-3")
    assert LECTURE_LAB_CREDIT_RE.search("3/2/4")
    assert not LECTURE_LAB_CREDIT_RE.search("2026-2027")


def test_a_combined_heading_is_recognised_in_its_usual_spellings() -> None:
    for heading in (
        "Prerequisite/Corequisite",
        "Prerequisites and Corequisites",
        "Pre-requisite or Co-requisite",
    ):
        assert PREREQ_COREQ_COMBINED_RE.search(heading), heading


def test_the_word_as_is_not_a_degree() -> None:
    """Matching bare abbreviations made every page a credential."""
    assert program_terms("this page is as plain as it gets") == []
    assert "degree" in program_terms("Associate in Science")
    assert "degree" in program_terms("awarded the A.A.S. degree")


def test_program_terms_are_reported_by_name() -> None:
    text = "Associate in Science. Program Requirements. Total Credits: 60."
    assert program_terms(text) == [
        "degree",
        "program_requirements",
        "total_credits",
    ]


@pytest.mark.parametrize(
    ("text", "year"),
    [
        ("Example College Catalog 2026-2027", "2026-2027"),
        ("Catalog 2026/2027", "2026-2027"),
        ("Catalog 2026-27", "2026-2027"),
        ("Example College Catalog", None),
    ],
)
def test_catalog_year_is_written_out_in_full(
    text: str, year: str | None
) -> None:
    assert catalog_year_value(text) == year


def test_evidence_is_short_enough_to_read() -> None:
    quote = evidence("word " * 200)
    assert len(quote) <= 80
    assert "\n" not in evidence("a\nb")


def test_every_marker_has_a_line_on_why_it_matters() -> None:
    """patterns.md is a demo document, so no marker may be unexplained."""
    assert set(MARKER_NAMES) == set(MARKER_MEANING)
    for name, meaning in MARKER_MEANING.items():
        assert meaning.strip(), name


def test_a_phone_number_is_not_an_error_page() -> None:
    """A college address carrying (404) marked a real page empty."""
    assert not EMPTY_OR_ERROR_RE.search("Atlanta, GA 30326 (404) 975-5000")
    assert not EMPTY_OR_ERROR_RE.search("call 404-975-5000 for details")


def test_a_real_error_page_still_reads_as_one() -> None:
    for text in (
        "Page Not Found",
        "404 Error",
        "Error 404",
        "Access Denied",
        "Please log in to continue",
    ):
        assert EMPTY_OR_ERROR_RE.search(text), text


def test_a_navigation_menu_is_not_program_structure() -> None:
    """Every page of a catalog links to Degrees and Certificates."""
    assert not has_program_structure(["certificate", "degree"])
    assert has_program_structure(["degree", "program_requirements"])


def test_one_course_printed_twice_is_still_one_block() -> None:
    """A breadcrumb above a heading repeats the code. It is one course.

    Counting both occurrences made every single-course page on a live Clean
    Catalog site report two blocks, which marked it multi_course_page and
    made extraction skip it as a page holding several courses.
    """
    breadcrumb_then_heading = (
        "Home\nAccounting\nACCT130\nACCT130: Financial Accounting\n"
        "Credits 4\nLab/Clinical/Field Study Hours 0"
    )
    assert course_block_count(breadcrumb_then_heading) == 1
    assert course_block_count("ENGL 101\nCredits 3\nENGL101\nCredits 3") == 1
    assert course_block_count("ENGL 101\nCredits 3\nENGL 102\nCredits 3") == 2


def test_the_same_code_spelled_three_ways_is_one_course() -> None:
    spellings = {
        normalize_course_code(code)
        for code in ("ENGL 101", "ENGL-101", "ENGL101", "ENGL 101")
    }
    assert spellings == {"ENGL101"}


@pytest.mark.parametrize(
    "printed",
    [
        "ENGL 101",  # the plain form
        "ENGL-101",  # hyphenated
        "ENGL101",  # glued
        "ALAN 0100",  # Acalog and CourseLeaf print a non-breaking space
        "AFRCNA 1415",  # Pitt spells the subject out in six letters
        "ACCT A101",  # a letter in front of the number
        "ACTG 1A",  # De Anza and Foothill number courses from 1
        "CIS114DE",  # a two-letter suffix, glued
    ],
)
def test_a_course_code_is_read_in_every_shape_a_catalog_prints(
    printed: str,
) -> None:
    assert course_codes(printed) == [printed], printed


@pytest.mark.parametrize(
    "printed",
    ["GOAL 1", "SLO 3", "OSHA 10", "LEVEL 1", "PK-12", "BC3", "COVID 19"],
)
def test_a_number_beside_a_word_is_not_a_course_code(printed: str) -> None:
    """The short-number shape has to end in a letter.

    Without that, a page of six learning outcomes numbered SLO 1 to SLO 6
    counted six courses, and the college's own name read as a code.
    """
    assert course_codes(printed) == [], printed


def test_an_award_is_read_from_the_words_a_catalog_actually_prints() -> None:
    for printed in (
        "Bookkeeping (Certificate)",
        "Accounting (A.A.S.)",
        "Medical Assistant, Certificate",
        "Automotive Technology, Associate of Applied Science",
        "Example Cloud Certified: Network Administrator Associate",
        "Master of Accountancy",
        "Online Bachelor of Science in Engineering",
    ):
        assert credential_award(printed) is not None, printed


def test_a_bare_abbreviation_that_is_a_word_is_not_an_award() -> None:
    """The same trap the degree term already had, one level down.

    Case-insensitively a bare A.S. is "as" and a bare M.A. is "ma", so
    only the dotted spellings are matched, and only the undotted
    abbreviations that are not English words.
    """
    for printed in (
        "this page is as plain as it gets",
        "the ma and pa store",
        "BS in the sense of nonsense",
        "a master syllabus for the course",
        "the associate dean of instruction",
    ):
        assert credential_award(printed) is None, printed


def test_a_term_sequence_alone_does_not_make_a_page_a_program() -> None:
    """A course description that says "offered Fall semester" prints one.

    So does a refund schedule. The term names counted toward a program
    once, and with the menu's "Degrees" always present that was enough to
    label 39 Atlantic Cape policy pages LearningOpportunity.
    """
    assert not has_program_structure(["certificate", "degree", "term_sequence"])
    assert has_program_structure(["degree", "total_credits"])


@pytest.mark.parametrize(
    "line",
    [
        # The heading that names the list.
        "Student Learning Outcomes",
        "Learning Outcomes:",
        "Course Objectives",
        "Program Competencies",
        "Goals and Objectives",
        "School of Law Learning Outcomes",
        "Program Goals and Student Learning Objectives for the Master of Science",
        "Skills measured",
        "What you'll learn",
        # The sentence that introduces it.
        "Upon completion of this program students will be able to:",
        "Upon completion of the program, graduates will be able to:",
        (
            "Completion of the degree requirements provides graduates with the "
            "following learning outcomes:"
        ),
        (
            "The faculty has adopted the following learning outcomes for our J.D. "
            "program:"
        ),
        (
            "All programs leading to an associate degree include the following "
            "competencies:"
        ),
    ],
)
def test_a_competency_list_is_led_in_the_ways_catalogs_print(line: str) -> None:
    assert is_outcomes_lead_in(line), line


@pytest.mark.parametrize(
    "line",
    [
        # A course title, with and without its code.
        "PSYC 62103. Psychotherapy Outcomes. 3 Hours.",
        "Core Competencies and Clinical Care I",
        # A general education category and the tag every course carries.
        "Technological Competency (IT)",
        "ENGL 1013 Composition I (Satisfies General Education Outcome 1.1)",
        # What a college, a program, or a center does.
        "Mission and Objectives",
        "Program Educational Objectives",
        "The major objectives of the program are as follows:",
        "The main objectives of the center are to:",
        # Rules and standards.
        "Objectives and Regulations",
        (
            "The following abilities and expectations must be met by all students "
            "admitted to the program:"
        ),
        # A mention, not a lead-in.
        "Students will be able to",
        "Upon successful completion",
    ],
)
def test_a_line_that_only_mentions_outcomes_leads_in_nothing(line: str) -> None:
    """Each of these was a lead-in once, and most were Competency pages."""
    assert not is_outcomes_lead_in(line), line


@pytest.mark.parametrize(
    "line",
    [
        "Demonstrate safe laboratory practices and correct use of equipment;",
        "Correctly explain and apply the scientific method;",
        "Use the writing process to compose analytical essays",
        "CE1. An ability to identify, formulate, and solve engineering problems.",
        "an ability to communicate effectively with a range of audiences,",
        "Our graduates will have an understanding of their ethical duties.",
        "Thesis: Students will gain an understanding of their research field.",
        "2) Analyze data from laboratory experiments.",
    ],
)
def test_an_outcome_reads_as_one(line: str) -> None:
    assert is_outcome_statement(line), line


@pytest.mark.parametrize(
    "line",
    [
        "Examines the theories and methods of educational measurement.",
        "Review",
        "PSYC 62103. Psychotherapy Outcomes. 3 Hours.",
        "Students will be able to:",
        "Required Program Courses",
        "To provide a broad flexible program for public service careers",
    ],
)
def test_a_description_heading_course_or_purpose_is_not_an_outcome(
    line: str,
) -> None:
    """A course description opens in the third person, not the base form."""
    assert not is_outcome_statement(line), line


@pytest.mark.parametrize(
    ("line", "award"),
    [
        ("Associate in Science", "Associate in"),
        ("Certificate", "Certificate"),
        ("Professional Series", "Professional Series"),
        ("Graduate Microcertificate in Regression", "Microcertificate"),
        ("Master of Science in Environmental Resiliency (ENREMS)", "Master of"),
        ("M.S., Ph.D. (CSES)", "M.S."),
        ("Human Resources Management B.S.B.A.", "B.S.B.A."),
    ],
)
def test_a_badge_is_a_line_that_is_only_an_award(line: str, award: str) -> None:
    assert award_in_name_line(line) == award


@pytest.mark.parametrize(
    "line",
    [
        "Ph.D. Program Director",
        "Director, Master of Social Work Program",
        "Executive Director of M.B.A. Programs",
        "504 J.B. Hunt Building",
        "J.D. Willson",
        "Christopher Nelson, Ph.D.",
        "Master of Applied Business Analytics Website",
        "Program (not a degree)",
    ],
)
def test_a_contact_line_is_not_a_badge(line: str) -> None:
    """CourseLeaf prints its contacts where Clean Catalog prints its badge."""
    assert award_in_name_line(line) is None, line


def test_initials_are_not_a_law_degree() -> None:
    """Only J.D. and the LL. degrees start with those letters."""
    assert specific_award("JBHT 504 J.B. Hunt Center") is None
    assert specific_award("J.D. Admissions and Courses") == "J.D."
    assert specific_award("LL.M. in Agricultural and Food Law") == "LL.M."


def test_a_curly_apostrophe_is_an_apostrophe() -> None:
    assert specific_award("a master’s degree in nursing") == "master’s degree"


def test_an_award_in_the_plural_is_a_list_of_them() -> None:
    assert (
        singular_award("Graduate Certificates and Microcertificates Offered")
        is None
    )
    assert singular_award("Degrees Conferred: M.S.E.E., Ph.D.") == "M.S.E.E."
    assert award_in_name("Graduate Microcertificates") is None
    for name in (
        "Graduate Certificates",
        "Fields of Study",
        "Associate in Applied Science",
    ):
        assert names_a_listing(name), name
    assert not names_a_listing("Bookkeeping (Certificate)")


def test_the_award_is_read_from_the_first_sentence_s_subject() -> None:
    """The award before the verb is the program's; after it, a goal."""
    assert (
        award_in_intro(
            "The graduate microcertificate in Regression provides a framework.",
            "x",
        )
        == "microcertificate"
    )
    assert (
        award_in_intro(
            "Program Description: The post master’s Advanced School-Based "
            "Speech-Language Pathology Certificate is designed for clinicians.",
            "x",
        )
        == "Certificate"
    )
    assert (
        award_in_intro("The degree requirements are listed below.", "x") is None
    )


def test_the_url_rules_read_a_path_and_say_which_kind_it_is() -> None:
    """The last resort, for a page whose text says nothing."""
    credential, program = LABEL_CREDENTIAL, LABEL_LEARNING_OPPORTUNITY
    assert url_label("/en-us/credentials/certifications/x") == credential
    assert url_label("/degrees-certificates/nursing") == credential
    assert url_label("/preview_program.php?catoid={n}") == program
    assert url_label("/catalog/majors/arts/arts/") == program
    assert url_label("/graduatecatalog/programsofstudy/libs/") == program
    assert COURSE_URL_RE.search("/course-descriptions/phys/")
    assert not COURSE_URL_RE.search("/catalog/majors/arts/arts/")


@pytest.mark.parametrize(
    "template",
    [
        "/{n}-catalog/honors-program",
        "/student-handbook/credit-amnesty-program",
        "/{n}-catalog/academic-degrees",
        "/programs",
        "/degrees",
        "/degree-completion-agreements/transfer",
    ],
)
def test_a_word_in_a_slug_or_the_listing_itself_is_not_a_url_kind(
    template: str,
) -> None:
    """A segment counts only whole, and only with a page under it.

    Read anywhere in the path, "program" made Atlantic Cape's honors,
    credit amnesty and student-support pages programs. /programs is the
    list of programs, not one of them.
    """
    assert url_label(template) is None


def test_a_wall_and_a_soft_404_are_not_pages() -> None:
    """Both answer 200 with prose, so only the words give them away.

    A Cloudflare block page profiled as a real course page, and a themed
    "that page has moved" stayed in the run as a live program.
    """
    for text in (
        "Sorry, you have been blocked",
        "You are unable to access deanza.edu",
        "Cloudflare Ray ID: a30a2f7d6a3aedc9",
        "Oops! That page has moved.",
        "The page you are looking for may have been moved or renamed",
    ):
        assert EMPTY_OR_ERROR_RE.search(text), text


@pytest.mark.parametrize(
    ("printed", "award"),
    [
        ("Human Resource Development B.H.R.D.", "B.H.R.D."),
        ("Requirements for M.Ed. in Adult and Lifelong Learning", "M.Ed."),
        ("LL.M. in Agricultural and Food Law", "LL.M."),
        ("Chemical Engineering B.S.Ch.E.", "B.S.Ch.E."),
        ("Degrees Conferred: M.S.E.E., Ph.D.", "M.S.E.E."),
        ("Graduate Microcertificate in Regression", "Microcertificate"),
        ("Professional Series", "Professional Series"),
    ],
)
def test_the_awards_a_university_catalog_prints_are_read(
    printed: str, award: str
) -> None:
    """CourseLeaf dots every degree and writes microcertificate as one word.

    A fixed list of dotted degrees missed B.H.R.D., M.Ed. and LL.M., and
    the boundary in front of "certificate" missed every microcertificate.
    """
    assert specific_award(printed) == award


def test_a_time_a_place_or_an_abbreviation_is_not_a_dotted_degree() -> None:
    for printed in (
        "Classes meet at 9:00 A.M. daily",
        "an internship in Washington, D.C.",
        "e.g. a laboratory course",
        "U.S. History",
    ):
        assert credential_award(printed) is None, printed


def test_a_generic_or_negated_award_names_no_award() -> None:
    """ "Degree" says an award exists; "not a degree" says the opposite."""
    assert specific_award("the degree requirements") is None
    assert specific_award("Initial Teacher Licensure") is None
    assert specific_award("Program (not a degree)") is None
    assert specific_award("Non-Degree Certificate") == "Certificate"


@pytest.mark.parametrize(
    "name",
    [
        "Associate in Science, Business Administration",
        "Accounting (A.A.S.)",
        "Bookkeeping (Certificate)",
        "Bachelor of Science in Nursing (BSN)",
        "LL.M. in Agricultural and Food Law",
        "Example Cloud Certified: Network Administrator Associate",
        "Human Resource Development B.H.R.D.",
    ],
)
def test_a_name_that_names_one_credential(name: str) -> None:
    assert award_in_name(name), name


@pytest.mark.parametrize(
    "name",
    [
        # Lists: the plural is the name of a menu or a listing page.
        "Degrees and Certificates",
        "Academic Degrees",
        "General Education Courses at Atlantic Cape",
        "3+1 Programs, Dual Admissions, and Degree Completion Agreements",
        # Rules: the page is a policy, whatever award it mentions.
        "New Jersey Commission on Higher Education Degree Program Criteria",
        "Associate Degree and Certificate Requirements",
        "Graduation Requirements",
        # The award type's own page, which lists its programs.
        "Associate in Applied Science",
        "Certificate",
        # The award the page says it is not.
        "Program (not a degree)",
    ],
)
def test_a_name_that_lists_or_rules_or_is_an_award_type_is_not_a_credential(
    name: str,
) -> None:
    """Every one of these was a Credential page, from its name alone."""
    assert award_in_name(name) is None, name


def test_a_heading_names_one_award_or_is_about_all_of_them() -> None:
    assert award_in_heading("Requirements for B.S. in Chemical Engineering")
    assert award_in_heading(
        "Requirements for the Master of Science (M.S.) Degree"
    )
    assert award_in_heading(
        "Bachelor of Science in Nursing R.N. to B.S.N. Option"
    )
    for heading in (
        "Minimum Requirements for the B.S.E. or B.S. or B.S.N. Degree",
        "Master of Arts, Master of Science",
        "Certificates and Microcertificates",
        "Degree Requirements",
    ):
        assert award_in_heading(heading) is None, heading


def test_the_first_paragraph_names_the_program_s_own_award() -> None:
    name = "Building-Level Administration (PSBL)"
    assert award_in_intro(
        "This degree can lead to a baccalaureate degree.", "Biology"
    )
    assert award_in_intro(
        "The Practical Nursing Certificate program is designed to prepare nurses.",
        "Practical Nursing",
    )
    assert award_in_intro(
        "Program Description: A graduate certificate in teaching English is "
        "recognized worldwide.",
        "TESL",
    )
    assert award_in_intro(
        "Prerequisites for Acceptance to the Graduate Certificate Program in "
        "Building-Level Administration: applicants must hold a master's.",
        name,
    )
    assert award_in_intro(
        "Special Education Transition Services Graduate Certificate is "
        "designed for school-based professionals.",
        "Special Education Transition Services",
    )


def test_an_award_the_students_are_after_is_not_the_program_s() -> None:
    """Atlantic Cape's English language program is "not a degree"."""
    assert (
        award_in_intro(
            "The Academic English Language program is designed for students "
            "whose native language is not English, and who want to study at "
            "the college to earn a certificate or degree.",
            "Academic English Language Program",
        )
        is None
    )


@pytest.mark.parametrize(
    "printed",
    [
        "Total Credits: 60",
        "Total Hours\n18",
        "60 total credits",
        "Credits Required: 64",
    ],
)
def test_a_program_total_is_a_total_with_its_number(printed: str) -> None:
    assert TOTAL_CREDITS_RE.search(printed), printed


def test_a_sentence_about_totals_is_not_a_program_total() -> None:
    assert not TOTAL_CREDITS_RE.search(
        "the total credits a student has attempted are counted"
    )


@pytest.mark.parametrize(
    "heading",
    [
        "Program Requirements",
        "Requirements for a Minor in Statistics:",
        "Required Courses (6 hours)",
        "Eight-Semester Plan",
        "Plan of Study",
    ],
)
def test_a_requirements_heading_is_the_whole_line(heading: str) -> None:
    assert REQUIREMENTS_HEADING_RE.match(heading), heading


@pytest.mark.parametrize(
    "line",
    [
        "Admission Requirements",
        "Graduation Requirements",
        "Curriculum Instruction Education Internship Fee",
        "Students must complete the program requirements in two years.",
    ],
)
def test_a_line_that_merely_starts_like_one_is_not_a_requirements_heading(
    line: str,
) -> None:
    """The fee table row was read as a curriculum heading."""
    assert not REQUIREMENTS_HEADING_RE.match(line), line


def test_a_declaration_is_a_label_not_a_sentence() -> None:
    assert AWARD_DECLARATION_RE.match("Degrees Conferred:")
    assert AWARD_DECLARATION_RE.match("Degree Offered")
    assert AWARD_DECLARATION_RE.match("Award Type: Certificate")
    assert not AWARD_DECLARATION_RE.match(
        "Degrees offered by the college include"
    )


def test_a_heading_that_opens_with_a_course_code_is_a_course_title() -> None:
    assert COURSE_TITLE_RE.match(
        "FREN 30603. Ph.D. Reading Requirement I. 3 Hours."
    )
    assert COURSE_TITLE_RE.match("ACCT 2013. Accounting Principles I. 3 Hours.")
    assert not COURSE_TITLE_RE.match(
        "Requirements for B.S. in Chemical Engineering"
    )


def test_an_organization_or_a_rule_is_not_a_program() -> None:
    for name in (
        "College of Engineering",
        "Sam M. Walton College of Business",
        "Honors College",
        "Objectives and Regulations",
        "Graduation Requirements",
    ):
        assert names_an_organization_or_policy(name), name
    for name in (
        "Nursing",
        "Chemical Engineering (CHEG)",
        "Childhood Education (CHED)",
    ):
        assert not names_an_organization_or_policy(name), name


def test_an_outline_number_is_not_part_of_the_heading() -> None:
    """A bulletin that numbers its headings still has headings.

    Every heading rule is anchored at the start of the line, so "[2.2]
    Biology Track" matched none of them and a whole bulletin's programs
    went unlabelled.
    """
    assert heading_body("[2] Baccalaureate Degree") == "Baccalaureate Degree"
    assert heading_body("[2.2] Biology Track (50 hours)") == (
        "Biology Track (50 hours)"
    )
    assert heading_body("3. Program Requirements") == "Program Requirements"
    assert heading_body("1) Core Courses") == "Core Courses"
    # A year is not an outline number, and a letter is the start of an
    # award, so neither is stripped.
    assert heading_body("2026 Catalog") == "2026 Catalog"
    assert heading_body("B. S. in Nursing") == "B. S. in Nursing"


def test_a_credit_total_is_a_line_not_a_clause() -> None:
    """A total is printed as its own line or a table row, never in prose."""
    assert total_credits_line(["Total Credits 60"]) == "Total Credits 60"
    # Clean Catalog prints the label and the number as two paragraphs.
    assert total_credits_line(["Total Credits", "12"]) == "Total Credits 12"
    # The clause that turned a page of film courses into a program.
    assert (
        total_credits_line(
            [
                (
                    "FILM 4V70 Advanced Film Production 3 Credits. Individual "
                    "projects. Prerequisites: FILM 2310 and 45 total credit "
                    "hours completed."
                )
            ]
        )
        == ""
    )


def test_a_structure_term_counts_only_where_a_heading_could_be() -> None:
    assert program_structure_terms(["Program Requirements"]) == [
        "program_requirements"
    ]
    assert (
        program_structure_terms(
            [
                (
                    "Students who transfer must have completed the degree "
                    "requirements of the sending institution before applying."
                )
            ]
        )
        == []
    )


def test_one_award_written_two_ways_is_one_award() -> None:
    """The Eleanor Mann School of Nursing heads B.S.N. and Bachelor."""
    assert distinct_awards(["B.S.N.", "Bachelor"]) == ["B.S.N."]
    assert distinct_awards(["M.S.", "MS"]) == ["M.S."]
    # Two real awards, whichever way they are written.
    assert distinct_awards(["B.A.", "B.F.A.", "Bachelor"]) == ["B.A.", "B.F.A."]
    assert distinct_awards(["Certificate", "Microcertificate"]) == [
        "Certificate",
        "Microcertificate",
    ]
    # Nothing specific to keep: the bare levels are all there is.
    assert distinct_awards(["Bachelor", "Master of"]) == [
        "Bachelor",
        "Master of",
    ]


def test_a_page_that_calls_itself_a_listing_names_no_credential() -> None:
    for name in (
        "Accelerated Bachelor to Master Program Listing",
        "Degree Index",
        "Certificate Directory",
    ):
        assert names_a_listing(name), name


def test_a_heading_that_is_only_the_word_requirements_is_one() -> None:
    """A page headed just "Requirements" is printing its own.

    The words that make the longer spellings unsafe - admission,
    graduation - are absent by definition when there is none in front.
    """
    assert REQUIREMENTS_HEADING_RE.match("Requirements")
    assert REQUIREMENTS_HEADING_RE.match("Requirement")
    assert REQUIREMENTS_HEADING_RE.match("Requirements:")
    assert not REQUIREMENTS_HEADING_RE.match("Admission Requirements")
    assert not REQUIREMENTS_HEADING_RE.match("Graduation Requirements")
    assert not REQUIREMENTS_HEADING_RE.match(
        "Requirements are set by the professional schools"
    )


def test_a_url_segment_counts_by_its_words_when_it_is_a_phrase() -> None:
    """ "programs-by-program" is the section holding many of them.

    Only the plural counts. "academic-english-language-program" is one
    programme's own folder, with its course pages underneath it, and
    reading that as a programme listing would relabel every course in it.
    """
    assert (
        url_label("/{n}-bulletin/programs-by-program/preprofessional/law/")
        == LABEL_LEARNING_OPPORTUNITY
    )
    assert url_label("/catalog/academic-programs/nursing") == (
        LABEL_LEARNING_OPPORTUNITY
    )
    assert url_label("/all-degrees/nursing") == LABEL_CREDENTIAL
    assert url_label("/academic-english-language-program/aelp{n}") is None
    assert url_label("/computer-programming/course") is None
    assert url_label("/honors-program/apply") is None


def test_a_contact_line_names_a_role_and_how_to_reach_them() -> None:
    """Both halves matter, or the rule eats the page's own prose.

    A bulletin opens with its contact block, which is long enough to read
    as the first paragraph and is not one. A sentence that mentions an
    advisor is the page talking.
    """
    assert is_contact_line(
        "Dr. David Welky, Chair, Department of History, Irby 105B, "
        "(501) 450-5624"
    )
    assert is_contact_line(
        "Program Coordinator: Jake Held, PhD, Assistant Provost, jmheld@uca.edu"
    )
    assert not is_contact_line(
        "Students should speak with an advisor before registering, since "
        "availability varies by term."
    )
    # A role with no way to reach them, and a number with no role.
    assert not is_contact_line("Director and Professor of Philosophy")
    assert not is_contact_line("Call (501) 450-5624 for the class schedule")
