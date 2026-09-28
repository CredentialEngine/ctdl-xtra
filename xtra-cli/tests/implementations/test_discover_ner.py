"""What the entity reader has to get right, kind by kind.

Every page shape here is one a real catalog prints. The occupation tests
carry the most weight: a job title is the one kind with no vocabulary
already proven by the labels, and the whole design rests on needing two
signals rather than a head noun on its own.
"""

from __future__ import annotations

from implementations.discover_dom import read_markup
from implementations.discover_ner import (
    entities_by_kind,
    read_entities,
)
from implementations.discover_rules import (
    ENTITY_AWARD,
    ENTITY_COURSE_CODE,
    ENTITY_CREDITS,
    ENTITY_OCCUPATION,
    ENTITY_ORGANIZATION,
    ENTITY_TERM,
    credit_amounts,
    occupation_titles,
    occupation_value,
    organization_names,
    term_values,
)

PAGE = """
<html><head><title>{title}</title>{meta}</head>
<body>{body}</body></html>
"""


def page(body: str, *, title: str = "Example", meta: str = "") -> str:
    return PAGE.format(title=title, body=body, meta=meta)


def found(body: str, *, title: str = "Example", meta: str = "") -> dict:
    return entities_by_kind(
        read_entities(read_markup(page(body, title=title, meta=meta)))
    )


def values(body: str, kind: str, **kwargs) -> list[str]:
    return found(body, **kwargs).get(kind, [])


# --- the award ----------------------------------------------------------------


def test_the_marked_up_award_field_is_read() -> None:
    """Clean Catalog badges a program with the award and prints no noun.

    "Professional Series" carries no award word at all, so a reading of
    the prose finds nothing. The class naming the field is the answer.
    """
    body = (
        "<main><h1>Bookkeeper Credentials</h1>"
        "<div class='field--name-field-degree-type field__item'>"
        "Professional Series</div></main>"
    )
    assert "Professional Series" in values(body, ENTITY_AWARD)


def test_the_menus_award_words_are_not_the_pages_award() -> None:
    """ "Degrees and Certificates" is what the main menu is called.

    Both words name an award, in the plural, so both read as one until
    the plural and the generic are dropped. A page whose award list is
    the menu names no award.
    """
    body = (
        "<main><h1>Attendance</h1>"
        "<p>Degrees and Certificates are listed elsewhere.</p></main>"
    )
    assert values(body, ENTITY_AWARD) == []


def test_a_level_with_no_field_after_it_is_not_an_award() -> None:
    """ "Associate in" says a level, not which award."""
    body = "<main><h1>Transfer</h1><p>Associate in or bachelor.</p></main>"
    assert values(body, ENTITY_AWARD) == []


def test_an_award_the_page_says_it_is_not_does_not_count() -> None:
    body = (
        "<main><h1>English Language Studies</h1>"
        "<p>This is a program (not a degree).</p></main>"
    )
    assert values(body, ENTITY_AWARD) == []


# --- credits ------------------------------------------------------------------


def test_a_marked_up_credits_field_is_read_with_its_number() -> None:
    body = (
        "<main><h1>ACCT130</h1>"
        "<div class='field--name-field-credits'>"
        "<div class='field__label'>Credits</div>"
        "<div class='field__item'>4</div></div></main>"
    )
    assert "4" in values(body, ENTITY_CREDITS)


def test_a_range_of_credits_keeps_both_ends() -> None:
    assert credit_amounts("1-3 credits") == ("1", "3")
    assert credit_amounts("3 credits") == ("3", "3")
    assert credit_amounts("Credit Hours Min: 3") == ("3", "3")
    assert credit_amounts("credits") == ("", "")


def test_a_printed_range_is_one_value() -> None:
    body = "<main><h1>ART 101</h1><p>1-3 credits</p></main>"
    assert "1-3" in values(body, ENTITY_CREDITS)


# --- course codes -------------------------------------------------------------


def test_a_marked_up_course_block_names_its_course() -> None:
    body = (
        "<main><div class='courseblock'>"
        "<p class='courseblocktitle'>ENGL 101. Composition I. 3 Hours.</p>"
        "<p class='courseblockdesc'>An introduction.</p></div></main>"
    )
    assert "ENGL101" in values(body, ENTITY_COURSE_CODE)


def test_a_code_in_a_requirement_table_is_marked_a_reference() -> None:
    """A program's requirement list points at courses it does not describe.

    The label rules already turn on that difference, so the entity has to
    carry it too or a reader cannot tell the two apart.
    """
    body = (
        "<main><h1>Nursing A.A.S.</h1>"
        "<table class='sc_courselist'>"
        "<tr class='even'><td class='codecol'>BIOL 1543</td>"
        "<td>Anatomy</td><td class='hourscol'>4</td></tr>"
        "</table></main>"
    )
    entities = read_entities(read_markup(page(body)))
    codes = [e for e in entities if e.kind == ENTITY_COURSE_CODE]
    assert codes and all(e.source == "reference" for e in codes)


# --- terms --------------------------------------------------------------------


def test_a_plan_of_studys_term_headings_are_terms() -> None:
    body = (
        "<main><h1>Computer Systems Support</h1>"
        "<h2>First Semester</h2><h2>Second Semester</h2></main>"
    )
    assert values(body, ENTITY_TERM) == ["First Semester", "Second Semester"]


def test_a_season_needs_a_term_noun_or_a_year() -> None:
    """ "Students who fall below a 2.0" is not a term.

    Every refund schedule prints the word, which is why a season counts
    only with a noun or a year after it.
    """
    assert term_values("students who fall below a 2.0") == []
    assert term_values("offered Fall 2026") == ["Fall 2026"]
    assert term_values("in the fall semester") == ["fall semester"]


def test_the_catalog_year_is_a_term() -> None:
    body = "<main><h1>Nursing</h1><p>Requirements.</p></main>"
    assert "2026-2027" in values(
        body, ENTITY_TERM, title="2026-2027 Catalog | Example College"
    )


# --- organizations ------------------------------------------------------------


def test_an_organization_is_named_by_its_proper_name() -> None:
    body = (
        "<main><h1>Medical Laboratory Technology</h1>"
        "<p>Offered with Mercer County Community College.</p></main>"
    )
    assert "Mercer County Community College" in values(
        body, ENTITY_ORGANIZATION
    )


def test_a_course_title_is_not_an_organization() -> None:
    """ "PHYS125 College Physics I" is a row of a plan of study.

    On its shape alone it reads as an organization called "PHYS125
    College", and a plan of study prints a dozen of them.
    """
    assert organization_names("PHYS125 College Physics I 4") == []


def test_the_lowercase_word_college_is_not_a_name() -> None:
    assert organization_names("transfer to the college of your choice") == []


def test_two_organizations_in_a_row_are_two_names() -> None:
    """An articulation page lists them one after another.

    The pattern reaches six words back, so read whole the two ran
    together into one organization that does not exist.
    """
    assert organization_names(
        "articulation with Rutgers University and Stockton University"
    ) == ["Rutgers University", "Stockton University"]


def test_a_name_stops_where_its_sentence_does() -> None:
    """An initialism keeps its dots; a full stop ends the name."""
    assert organization_names(
        "contact the U.S. Department of Education. FERPA rights apply"
    ) == ["U.S. Department of Education"]
    assert organization_names("N.J. Department of Higher Education rules") == [
        "N.J. Department of Higher Education"
    ]


def test_a_name_keeps_the_of_phrase_that_belongs_to_it() -> None:
    assert organization_names(
        "Rutgers University-Edward J. Bloustein School of Planning"
    ) == ["Rutgers University-Edward J. Bloustein School of Planning"]


# --- occupations --------------------------------------------------------------


def test_a_job_named_in_a_career_sentence_is_read() -> None:
    body = (
        "<main><h1>Computer Systems Support</h1>"
        "<p>Career options include Computer Server Administrator, "
        "Help Desk Technician.</p></main>"
    )
    assert values(body, ENTITY_OCCUPATION) == [
        "Computer Server Administrator",
        "Help Desk Technician",
    ]


def test_a_job_listed_under_a_career_heading_is_read() -> None:
    """The items under "Career Opportunities" carry no cue of their own."""
    body = (
        "<main><h1>Welding</h1><h2>Career Opportunities</h2>"
        "<ul><li>Welder</li><li>Pipefitter</li>"
        "<li>Fabrication Technician</li></ul></main>"
    )
    assert "Welder" in values(body, ENTITY_OCCUPATION)
    assert "Fabrication Technician" in values(body, ENTITY_OCCUPATION)


def test_a_head_noun_with_no_cue_is_not_an_occupation() -> None:
    """This is the whole reason two signals are required.

    "Nurse Education" is a department and "Engineer" is half a course
    title. Read on the head noun alone, every catalog page names jobs.
    """
    body = (
        "<main><h1>Nurse Education</h1>"
        "<p>The Nurse Education department offers ENGR 101 "
        "Introduction to the Engineer.</p></main>"
    )
    assert values(body, ENTITY_OCCUPATION) == []


def test_a_contact_blocks_title_is_not_an_occupation() -> None:
    """ "Program Coordinator" names who to email, not the work."""
    body = (
        "<main><h1>Nursing</h1>"
        "<p>Graduates may contact the Program Coordinator.</p></main>"
    )
    assert values(body, ENTITY_OCCUPATION) == []


def test_a_sentences_own_words_are_not_part_of_the_title() -> None:
    assert occupation_value("As Medical Laboratory Technician") == (
        "Medical Laboratory Technician"
    )
    assert occupation_value("include Computer Server Administrator") == (
        "Computer Server Administrator"
    )
    assert occupation_value("such as a Registered Nurse") == (
        "Registered Nurse"
    )


def test_a_plural_job_title_is_the_same_occupation() -> None:
    assert occupation_value("Registered Nurses") == "Registered Nurse"
    assert occupation_value("Emergency Medical Services Technicians") == (
        "Emergency Medical Services Technician"
    )


def test_a_sentence_around_a_head_noun_is_not_the_title() -> None:
    """The words in front of the noun are taken only when they belong.

    Matching them with the title pattern read whole sentences as jobs,
    because `[A-Z]` under re.IGNORECASE matches any word at all. Every
    line here is one this catalog prints.
    """

    def read(line: str) -> list[str]:
        return [occupation_value(t) for t in occupation_titles(line)]

    assert read("Graduates earn a Commercial Pilot certificate") == [
        "Commercial Pilot"
    ]
    assert read("Their FAA Remote Pilot certificate is required") == [
        "FAA Remote Pilot"
    ]
    assert read("Students may also apply to technician programs") == [
        "Technician"
    ]


def test_a_lowercase_job_title_keeps_the_words_that_describe_it() -> None:
    """A sentence prints one without capitals and it is still the job."""
    assert [
        occupation_value(t)
        for t in occupation_titles("may work as a licensed practical nurse")
    ] == ["Licensed Practical Nurse"]


def test_a_comma_ends_a_job_title() -> None:
    """Two jobs in a list are two titles, not one running across them."""
    assert [
        occupation_value(t)
        for t in occupation_titles("Welder, Fabrication Technician")
    ] == ["Welder", "Fabrication Technician"]


def test_a_college_referred_to_is_not_a_college_named() -> None:
    """A page writes these about a college it has already named."""
    assert organization_names("the College requires a 2.0 GPA") == []
    assert organization_names("Other Colleges may accept these") == []
    assert organization_names("students from High School may enroll") == []


def test_the_download_link_above_the_name_is_not_part_of_it() -> None:
    """Clean Catalog prints "Download as PDF" directly above the name."""
    assert organization_names(
        "Download as PDF Atlantic Cape Community College"
    ) == ["Atlantic Cape Community College"]


# --- the collection itself ----------------------------------------------------


def test_one_value_is_kept_once_per_kind() -> None:
    body = (
        "<main><h1>Nursing</h1>"
        "<p>Careers as a Registered Nurse. Employment as a "
        "registered nurse is expected to grow.</p></main>"
    )
    assert values(body, ENTITY_OCCUPATION) == ["Registered Nurse"]


def test_the_markups_reading_keeps_its_place() -> None:
    """A field-sourced value wins over the same value found in the prose."""
    body = (
        "<main><h1>Nursing</h1>"
        "<div class='field--name-field-degree-type field__item'>"
        "Associate in Applied Science</div>"
        "<p>The Associate in Applied Science prepares students.</p></main>"
    )
    awards = [
        e
        for e in read_entities(read_markup(page(body)))
        if e.kind == ENTITY_AWARD
    ]
    assert [e.source for e in awards] == ["field"]


def test_an_empty_page_names_nothing() -> None:
    assert entities_by_kind(read_entities(read_markup(page("")))) == {}
