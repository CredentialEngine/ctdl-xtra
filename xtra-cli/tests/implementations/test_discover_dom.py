"""What the tree reading has to get right, page shape by page shape.

Each test here is a shape a real catalog prints, and most of them are a
page that was read wrong before discovery parsed markup as markup.
"""

from __future__ import annotations

from implementations.discover_dom import (
    element_lines,
    element_text,
    find_main,
    is_chrome,
    lines_after,
    parse,
    printed_text,
    read_cms_page_type,
    read_course_blocks,
    read_declarations,
    read_fingerprint,
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


def test_main_text_keeps_the_pages_own_aside_not_the_sites_menu() -> None:
    """Two readings of one container, for two different questions.

    content_text drops an <aside> inside <main> as furniture. Arapahoe
    prints a course's code and credits there, so main_text keeps it: it
    is what the page prints, as against the catalog menu eLumen prints
    beside <main> on every page.
    """
    markup = read_markup(
        page(
            "<div id='nav'><a>CHEM 110 - General Chemistry</a></div>"
            "<main><h1>Payroll Accounting</h1>"
            "<aside class='course-full__aside'><p>ACC 115</p>"
            "<p>Credits 3</p></aside></main>"
        )
    )
    assert "ACC 115" not in markup.content_text
    assert markup.main_text.splitlines() == [
        "Payroll Accounting",
        "ACC 115",
        "Credits 3",
    ]


def test_a_page_without_a_main_container_has_no_main_text() -> None:
    """Nothing tells the page from the site there, so nothing is the site."""
    markup = read_markup(page("<div><p>ENGL 101 Composition I</p></div>"))
    assert markup.main_text == ""


def test_main_text_keeps_a_code_split_across_two_strings_whole() -> None:
    """CurriQunet prints "APP-" and "450" as two strings.

    Read with a space between every pair, as `get_text(" ")` reads them,
    the code becomes "APP- 450", which is no course code, and the page's
    own course would look printed outside its container.
    """
    markup = read_markup(
        page("<main><h2><span>APP-</span><span>450</span></h2></main>")
    )
    assert markup.main_text == "APP-450"


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


def test_an_elements_lines_break_where_the_content_text_breaks() -> None:
    """A cell printing three lines is three lines, not one glued string."""
    soup = parse(
        page("<table><tr><td>MATH 105<br>or<br>MATH 105H</td></tr></table>")
    )
    cell = soup.find("td")
    assert element_lines(cell) == ["MATH 105", "or", "MATH 105H"]
    assert element_text(cell) == "MATH 105orMATH 105H"


def test_what_follows_a_label_is_read_one_block_at_a_time() -> None:
    """A bare link after a heading is a run of its own; a block is a block."""
    soup = parse(
        page(
            "<div><h2>Prerequisite</h2><a href='#'>CAD 2220</a> or "
            "<a href='#'>CAD 2221</a><p>Taken first.</p><br>"
            "<script>var x;</script><!-- a note --></div>"
        )
    )
    entries = lines_after(soup.find("h2"))
    assert [lines for _, lines in entries] == [
        ["CAD 2220 or CAD 2221"],
        ["Taken first."],
    ]
    assert entries[0][0] is None
    assert entries[1][0].name == "p"


def test_printed_text_keeps_the_line_breaks_a_pre_wrap_element_shows() -> None:
    """Antelope Valley sets the prerequisite on a line of its own this way.

    Discovery reads the page as it always has: there a newline is a space.
    """
    html = page(
        "<main><div style='white-space: pre-wrap;'><p>Prerequisite: "
        "Completion of ENGR 905\n\nBuilding upon the basics.</p></div>"
        "<p>Two\nwords</p></main>"
    )
    assert printed_text(parse(html)).splitlines() == [
        "Prerequisite: Completion of ENGR 905",
        "Building upon the basics.",
        "Two words",
    ]
    assert read_markup(html).content_text.splitlines() == [
        "Prerequisite: Completion of ENGR 905 Building upon the basics.",
        "Two words",
    ]


def test_a_pre_keeps_its_lines_and_a_style_of_its_own_wins() -> None:
    """white-space is inherited unless an element sets its own."""
    html = page(
        "<main><pre>one\ntwo</pre><div style='white-space: pre-wrap'>"
        "<p style='white-space: normal'>three\nfour</p></div></main>"
    )
    assert printed_text(parse(html)).splitlines() == [
        "one",
        "two",
        "three four",
    ]


def test_an_elements_lines_inherit_the_white_space_around_it() -> None:
    soup = parse(
        page(
            "<div style='white-space: pre-wrap'><p>ENGR 905\nENGR 910</p></div>"
        )
    )
    assert element_lines(soup.find("p")) == ["ENGR 905", "ENGR 910"]


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


def fingerprint(body: str = "", *, title: str = "Example", meta: str = ""):
    return read_fingerprint(parse(page(body, title=title, meta=meta)))


def test_courseleaf_is_named_by_its_script_and_its_container() -> None:
    found = fingerprint(
        '<div id="textcontainer"></div>',
        meta='<script src="/js/courseleaf.js"></script>',
    )
    assert found.platform == "courseleaf"
    assert "script /js/courseleaf.js" in found.evidence


def test_acalog_is_named_by_its_gateway_assets() -> None:
    found = fingerprint(
        meta=(
            '<script src="//acalog-clients.s3.amazonaws.com/global/js/'
            'gateway-javascript.js"></script>'
        )
    )
    assert found.platform == "acalog"


def test_a_single_page_app_shell_is_named_before_it_draws_anything() -> None:
    """Coursedog and eLumen print nothing but assets until script runs."""
    coursedog = fingerprint(
        meta=(
            '<script src="https://static.catalog.prod.coursedog.com/x/_nuxt/'
            'a.js"></script>'
        )
    )
    elumen = fingerprint(
        "<script>loadContent('https://api-prod.elumenapp.com:443/c');</script>"
    )
    assert coursedog.platform == "coursedog"
    assert elumen.platform == "elumen"


def test_curriqunet_is_named_by_its_title_alone() -> None:
    found = fingerprint(title="View - CurriQunet META")
    assert found.platform == "curriqunet"


def test_kuali_is_named_even_inside_a_wordpress_page() -> None:
    """UCF embeds its Kuali catalog in WordPress; the catalog is the answer."""
    found = fingerprint(
        '<div id="kuali-catalog"></div>',
        meta=(
            '<link href="/wp-content/themes/x/style.css" rel="stylesheet"/>'
            '<script src="https://ucf.kuali.co/catalog/build/catalog.js">'
            "</script>"
        ),
    )
    assert found.platform == "kuali"


def test_smartcatalog_is_named_by_its_credit_and_its_tenant_paths() -> None:
    found = fingerprint(
        '<div id="footerSC">Powered by SmartCatalog IQ</div>',
        meta='<link href="/Institutions/Linn/styles/a.css" rel="stylesheet"/>',
    )
    assert found.platform == "smartcatalog"


def test_wordpress_is_named_when_nothing_more_specific_is() -> None:
    found = fingerprint(
        meta='<meta name="generator" content="WordPress 6.5" />'
    )
    assert found.platform == "wordpress"


def test_clean_catalog_beats_the_drupal_it_runs_on() -> None:
    found = fingerprint(
        '<article class="node node--type-degree"></article>'
        "<p>Course Catalog Software by Clean Catalog</p>"
    )
    assert found.platform == "clean_catalog"


def test_drupal_alone_is_named_drupal() -> None:
    found = fingerprint('<article class="node node--type-degree"></article>')
    assert found.platform == "drupal"


def test_a_page_that_names_no_platform_reads_as_none() -> None:
    found = fingerprint("<main><p>Hello.</p></main>")
    assert found.platform == ""
    assert found.evidence == []


def test_a_repeated_marker_is_one_hit_not_many() -> None:
    """Twenty Drupal-looking classes must not outvote one platform script."""
    drupal = "".join(
        f'<div class="field--name-f{index}"></div>' for index in range(20)
    )
    found = fingerprint(
        drupal, meta='<script src="/js/courseleaf.js"></script>'
    )
    assert found.platform == "courseleaf"


def test_evidence_is_capped_at_a_few_quotes() -> None:
    found = fingerprint(
        '<div id="textcontainer" class="sc_courselist sc_plangrid"></div>',
        meta=(
            '<link href="/css/courseleaf.css" rel="stylesheet"/>'
            '<script src="/js/courseleaf.js"></script>'
        ),
    )
    assert found.platform == "courseleaf"
    assert len(found.evidence) == 3


def test_script_text_is_not_read_as_printed_text() -> None:
    """A script that mentions a credit line is not the page printing it."""
    found = fingerprint(
        "<script>var s = 'Course Catalog Software by Clean Catalog';</script>"
    )
    assert found.platform == ""


def test_read_markup_carries_the_fingerprint() -> None:
    markup = read_markup(
        page("<main></main>", meta='<script src="/js/courseleaf.js"></script>')
    )
    assert markup.fingerprint.platform == "courseleaf"


def test_json_ld_survives_the_removal_of_script_tags() -> None:
    """read_markup removes every script, so declarations are read first."""
    markup = read_markup(
        page(
            "<main><h1>Accounting</h1></main>",
            meta=(
                '<script type="application/ld+json">'
                '{"@type": "Course", "name": "Accounting"}</script>'
            ),
        )
    )
    declaration = markup.declaration()
    assert declaration is not None
    assert declaration.source == "json-ld"
