"""What the tree reading has to get right, page shape by page shape.

Each test here is a shape a real catalog prints, and most of them are a
page that was read wrong before discovery parsed markup as markup.
"""

from __future__ import annotations

from implementations.discover_dom import (
    element_text,
    find_main,
    is_chrome,
    parse,
    read_cms_page_type,
    read_course_blocks,
    read_declarations,
    read_markup,
    read_requirement_lists,
)

PAGE = """
<html><head><title>{title}</title>{meta}</head>
<body>{body}</body></html>
"""


def page(body: str, *, title: str = "Example", meta: str = "") -> str:
    return PAGE.format(title=title, body=body, meta=meta)


# --- the page's own name ------------------------------------------------------


def test_an_h1_in_the_menu_is_not_the_pages_name() -> None:
    """Coursedog prints the college's name as the only h1 on every page.

    It sits in the sidebar `<nav>`. A fallback that reaches for it when the
    content has no h1 of its own names all 62 pages of a catalog after the
    college, and every rule that reads the page's name then reads the
    college's instead.
    """
    markup = read_markup(
        page(
            "<aside><nav><h1>Hudson County Community College</h1></nav></aside>"
            "<div role='main'><p>Attendance is taken each week.</p></div>",
            title="Attendance | Hudson County Community College Catalog",
        )
    )
    assert markup.h1 == ""


def test_the_pages_own_h1_wins_over_one_outside_the_main_container() -> None:
    markup = read_markup(
        page(
            "<header><h1>Example College</h1></header>"
            "<main><h1>Nursing A.A.S.</h1><p>Requirements.</p></main>"
        )
    )
    assert markup.h1 == "Nursing A.A.S."


def test_an_h1_that_is_only_the_sites_name_is_not_the_pages_name() -> None:
    markup = read_markup(
        page(
            "<main><h1>Brookdale Community College Catalog</h1>"
            "<p>Student services.</p></main>",
            meta="<meta property='og:site_name' "
            "content='Brookdale Community College Catalog'>",
        )
    )
    assert markup.h1 == ""


def test_an_h1_of_punctuation_is_a_divider_not_a_name() -> None:
    """Acalog rules its catalog landing page off with an h1 of underscores."""
    markup = read_markup(
        page(
            "<main><h1>______________________</h1>"
            "<p>Select a catalog.</p></main>"
        )
    )
    assert markup.h1 == ""


# --- the page's own content ---------------------------------------------------


def test_the_main_container_is_found_by_id_when_nothing_says_main() -> None:
    """Coursedog writes <div id="main-content">, with no <main> anywhere."""
    soup = parse(
        page(
            "<div id='main-content'><p>The program admits each fall.</p></div>"
        )
    )
    main = find_main(soup)
    assert main is not None
    assert main.get("id") == "main-content"


def test_an_empty_main_is_no_main_at_all() -> None:
    """A <main> filled in by script after load is not where the page is."""
    soup = parse(page("<main></main><div><p>Printed server side.</p></div>"))
    assert find_main(soup) is None


def test_a_breadcrumb_is_furniture_even_though_it_is_not_a_nav() -> None:
    """The breadcrumb repeats the course code one line above the heading.

    Counted as content it makes a single-course page look like a page
    holding two courses, which marks it multi_course_page and makes
    extraction skip it.
    """
    markup = read_markup(
        page(
            "<main><ol class='breadcrumb'><li>Home</li><li>ENGL 101</li></ol>"
            "<h1>ENGL 101 Composition I</h1></main>"
        )
    )
    assert "Home" not in markup.content_text
    assert markup.content_text.startswith("ENGL 101 Composition I")


def test_a_class_named_content_is_not_a_breadcrumb() -> None:
    """The furniture test reads one class at a time, so it cannot overreach."""
    soup = parse(page("<div class='course-breadcrumb-free'>x</div>"))
    assert not is_chrome(soup.find("div"))


def test_an_unclosed_tag_in_the_menu_does_not_swallow_the_page() -> None:
    """The reason this is a real parser and not a tag-name stack.

    A `<nav>` holding an unclosed `<div>` is most catalog pages. A parser
    that pops elements by searching backwards for a matching name never
    leaves the menu, so every heading after it counts as site furniture.
    """
    markup = read_markup(
        page(
            "<nav><div><a href='/'>Degrees &amp; Certificates</a></nav>"
            "<main><h2>Program Requirements</h2>"
            "<p>Sixty credits are required.</p></main>"
        )
    )
    assert markup.content_headings == ["Program Requirements"]
    assert "Degrees" not in markup.content_text


def test_an_element_reads_the_way_the_content_lines_read() -> None:
    """One stray space and a list item no longer matches its own line.

    The outcome rules compare the two, so `get_text(" ")` - which puts a
    space between every pair of strings - dropped a competency list.
    """
    soup = parse(page("<li>Apply the <em>nursing</em> process;</li>"))
    assert element_text(soup.find("li")) == "Apply the nursing process;"


# --- course descriptions and requirement lists --------------------------------


COURSEBLOCK = (
    "<div class='courseblock'><p class='courseblocktitle'><strong>"
    "ASTR 50303.  Astrophysics I.  3 Hours.</strong></p>"
    "<p class='courseblockdesc'>An introduction to astrophysics. "
    "This course is cross-listed with "
    "<a class='bubblelink code'>SPAC 50303</a>.</p></div>"
)


def test_a_marked_up_course_description_is_counted_as_one() -> None:
    blocks = read_course_blocks(parse(page(COURSEBLOCK)))
    assert [block.code for block in blocks] == ["ASTR50303"]


def test_the_same_course_marked_up_twice_is_still_one_course() -> None:
    blocks = read_course_blocks(parse(page(COURSEBLOCK + COURSEBLOCK)))
    assert len(blocks) == 1


def test_a_cross_reference_inside_a_description_is_not_a_second_course() -> (
    None
):
    """CourseLeaf links a cross-listed course as `a.bubblelink.code`."""
    _, references = read_requirement_lists(parse(page(COURSEBLOCK)))
    assert "SPAC50303" in references


REQUIREMENTS = (
    "<table class='sc_courselist'>"
    "<colgroup><col class='codecol'><col class='titlecol'>"
    "<col class='hourscol'></colgroup>"
    "<tr><td class='codecol'>ISYS 50103</td><td>Data and Cybersecurity</td>"
    "<td class='hourscol'>3</td></tr></table>"
)
EQUIVALENCIES = (
    "<table class='sc_courselist'>"
    "<colgroup><col class='codecol'><col class='titlecol'></colgroup>"
    "<tr><td>ANTH 2013</td><td>ANTH 10203</td></tr></table>"
)


def test_a_course_list_with_an_hours_column_is_a_requirement_list() -> None:
    quotes, references = read_requirement_lists(parse(page(REQUIREMENTS)))
    assert quotes and "ISYS 50103" in quotes[0]
    assert references == {"ISYS50103"}


def test_a_course_list_with_no_hours_column_is_not_requirements() -> None:
    """A transfer equivalency table is two columns of codes and nothing else.

    Read as a program's own requirements it made a transfer-of-credit
    policy page a LearningOpportunity with 167 courses in it. Its codes
    are still references: those courses are described on their own pages.
    """
    quotes, references = read_requirement_lists(parse(page(EQUIVALENCIES)))
    assert quotes == []
    assert references == {"ANTH2013", "ANTH10203"}


def test_a_list_whose_class_names_requirements_needs_no_hours_column() -> None:
    quotes, _ = read_requirement_lists(
        parse(
            page(
                "<div class='program-requirements'>"
                "<p>NURS 101 Foundations</p></div>"
            )
        )
    )
    assert quotes and "NURS 101" in quotes[0]


# --- what the publisher declares ----------------------------------------------


def test_json_ld_saying_the_page_is_a_course_is_read() -> None:
    soup = parse(
        page(
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"Course",'
            '"name":"Composition I"}</script>'
        )
    )
    declared = read_declarations(soup)
    assert [found.label for found in declared] == ["Course"]
    assert declared[0].source == "json-ld"


def test_a_declared_program_carries_the_award_it_names() -> None:
    """schema.org has one type for programs, so the award decides which."""
    soup = parse(
        page(
            '<script type="application/ld+json">{"@graph":[{'
            '"@type":"EducationalOccupationalProgram",'
            '"educationalCredentialAwarded":"Associate in Science"}]}</script>'
        )
    )
    declared = read_declarations(soup)
    assert declared[0].label == "LearningOpportunity"
    assert declared[0].award == "Associate in Science"


def test_a_declaration_that_says_nothing_about_the_entity_is_ignored() -> None:
    """Every catalog declares a WebPage and a BreadcrumbList."""
    soup = parse(
        page(
            '<script type="application/ld+json">'
            '{"@type":"BreadcrumbList","itemListElement":[]}</script>'
        )
    )
    assert read_declarations(soup) == []


def test_broken_json_ld_is_not_an_error() -> None:
    soup = parse(page('<script type="application/ld+json">{oops</script>'))
    assert read_declarations(soup) == []


def test_microdata_is_read_the_same_way() -> None:
    soup = parse(
        page("<div itemtype='https://schema.org/Course' itemscope>x</div>")
    )
    declared = read_declarations(soup)
    assert declared[0].label == "Course"
    assert declared[0].source == "microdata"


def test_the_cms_type_comes_from_the_node_the_page_rendered() -> None:
    markup = read_markup(
        page(
            "<article class='node node--type-degree node--view-mode-full'>"
            "<h1>Biology</h1></article>"
        )
    )
    assert markup.cms_page_type == "degree"


def test_a_teaser_does_not_give_the_page_its_type() -> None:
    """A department hub carries a teaser for every degree under it."""
    soup = parse(
        page(
            "<div class='node node--type-degree node--view-mode-teaser'>"
            "Biology</div>"
        )
    )
    assert read_cms_page_type(soup) == ""


# --- labels and headings ------------------------------------------------------


def test_a_bold_run_is_a_label_only_when_something_follows_it() -> None:
    markup = read_markup(
        page(
            "<p><strong>Credits</strong> 3</p>"
            "<p><strong>Prerequisite:</strong></p>"
            "<p><strong>Introduction to Welding</strong></p>"
        )
    )
    assert markup.label_texts == ["Credits", "Prerequisite:"]


def test_script_and_style_never_reach_the_text() -> None:
    markup = read_markup(
        page(
            "<main><script>var x = 'Degrees';</script>"
            "<style>.a{color:red}</style><p>Real text.</p></main>"
        )
    )
    assert markup.content_text == "Real text."


def test_an_empty_document_reads_as_an_empty_page() -> None:
    markup = read_markup("")
    assert markup.content_text == ""
    assert markup.h1 == ""
    assert markup.described_course_count == 0
