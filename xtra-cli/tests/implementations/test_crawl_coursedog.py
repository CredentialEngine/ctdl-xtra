from __future__ import annotations

import pytest
from crawl_doubles import (
    COURSEDOG_LOADING,
    coursedog_page,
    coursedog_row,
)

from implementations.crawl_coursedog import (
    MAX_LIST_PAGES,
    PROBLEM_CAPPED,
    PROBLEM_LOADING,
    PROBLEM_NO_CURRENT_PAGE,
    PROBLEM_PAGE_IGNORED,
    asked_page,
    page_url,
    read_bar,
    read_list_pages,
)

COURSES = "https://catalog.example.edu/courses"
PROGRAMS = "https://catalog.example.edu/programs"

# The row Commonwealth University's Coursedog catalog drew on 2026-10-21 for
# page 1 of its 2,733 courses, as the crawler saved it, svg paths cut short.
# Brookdale's catalog runs the same Coursedog build.
REAL_ROW = (
    '<div data-v-6c735c42="" class="flex ml-2 px-0 text-xs ui-font '
    'base-pagination mt-4"><button class="btn btn-secondary mx-1" '
    'type="button" disabled="" aria-label="Previous page"><svg '
    'class="svg-inline--fa fa-chevron-left fa-w-10" aria-hidden="true" '
    'focusable="false" data-prefix="fas" data-icon="chevron-left" '
    'role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 512">'
    '<path class="" fill="currentColor" d="M34.52 239.03"></path></svg>'
    '</button><button class="btn btn-primary mx-1" type="button" '
    'disabled="" aria-label="Go to page 1" aria-hidden="false" '
    'number="1">1</button><button class="btn btn-secondary mx-1" '
    'type="button" aria-label="Go to page 2" aria-hidden="false" '
    'number="2">2</button><button class="btn btn-secondary mx-1" '
    'type="button" disabled="" aria-label="Go to page ..." '
    'aria-hidden="true" number="...">...</button><button '
    'class="btn btn-secondary mx-1" type="button" aria-label="Go to page '
    '137" aria-hidden="false" number="137">137</button><button '
    'class="btn btn-secondary mx-1" type="button" aria-label="Next page">'
    '<svg class="svg-inline--fa fa-chevron-right fa-w-10" '
    'aria-hidden="true" focusable="false" data-prefix="fas" '
    'data-icon="chevron-right" role="img" '
    'xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 512"><path '
    'class="" fill="currentColor" d="M285.48 272.97"></path></svg></button>'
    "</div>"
)


def test_the_real_row_reads_as_page_1_of_137() -> None:
    bar = read_bar(coursedog_page(REAL_ROW))
    assert bar is not None
    assert (bar.current, bar.last) == (1, 137)


def test_the_first_page_of_a_list_queues_its_second_page_only() -> None:
    """One page is enough to learn whether the list opens by number."""
    pages = read_list_pages(coursedog_page(REAL_ROW), COURSES)
    assert pages is not None
    assert pages.urls == (f"{COURSES}?page=2",)
    assert (pages.asked, pages.current, pages.last) == (1, 1, 137)
    assert pages.problem is None


def test_a_page_that_opened_as_asked_queues_every_page_after_it() -> None:
    pages = read_list_pages(
        coursedog_page(coursedog_row(2, 6)), f"{COURSES}?page=2"
    )
    assert pages is not None
    assert pages.urls == tuple(f"{COURSES}?page={n}" for n in (3, 4, 5, 6))
    assert pages.problem is None


def test_a_later_page_queues_only_the_pages_after_it() -> None:
    pages = read_list_pages(
        coursedog_page(coursedog_row(4, 6)), f"{COURSES}?page=4"
    )
    assert pages is not None
    assert pages.urls == (f"{COURSES}?page=5", f"{COURSES}?page=6")


def test_the_last_page_and_a_one_page_list_queue_nothing() -> None:
    last = read_list_pages(
        coursedog_page(coursedog_row(6, 6)), f"{COURSES}?page=6"
    )
    assert last is not None
    assert last.urls == ()
    assert last.problem is None
    alone = read_list_pages(coursedog_page(coursedog_row(1, 1)), COURSES)
    assert alone is not None
    assert alone.urls == ()
    assert alone.problem is None


def test_a_list_that_ignores_the_page_in_its_address_queues_nothing_more() -> (
    None
):
    """Asked for page 2 and showing page 1: the address does not page it."""
    pages = read_list_pages(
        coursedog_page(coursedog_row(1, 195)), f"{PROGRAMS}?page=2"
    )
    assert pages is not None
    assert pages.urls == ()
    assert pages.problem == PROBLEM_PAGE_IGNORED
    assert (pages.asked, pages.current, pages.last) == (2, 1, 195)


def test_a_list_saved_before_it_loaded_says_so() -> None:
    pages = read_list_pages(coursedog_page(COURSEDOG_LOADING), COURSES)
    assert pages is not None
    assert pages.urls == ()
    assert pages.problem == PROBLEM_LOADING


def test_a_row_that_marks_no_page_as_on_screen_says_so() -> None:
    plain = (
        coursedog_row(2, 6)
        .replace("btn-primary", "btn-secondary")
        .replace(' disabled=""', "")
    )
    pages = read_list_pages(coursedog_page(plain), f"{COURSES}?page=2")
    assert pages is not None
    assert pages.urls == ()
    assert pages.problem == PROBLEM_NO_CURRENT_PAGE


def test_the_disabled_button_marks_the_page_when_none_is_highlighted() -> None:
    """The "..." gap is disabled too, but it carries no page number."""
    uncoloured = coursedog_row(2, 9).replace("btn-primary", "btn-secondary")
    bar = read_bar(coursedog_page(uncoloured))
    assert bar is not None
    assert (bar.current, bar.last) == (2, 9)


def test_the_row_ends_where_its_own_element_ends() -> None:
    """A wrapper closing inside the row does not end it; a button after does
    not join it."""
    row = coursedog_row(1, 9).replace(
        'mt-4">', 'mt-4"><div class="spacer"></div>', 1
    )
    after = (
        '<button class="btn btn-primary mx-1" type="button" disabled="" '
        'number="999">999</button>'
    )
    bar = read_bar(coursedog_page(row, after))
    assert bar is not None
    assert (bar.current, bar.last) == (1, 9)


@pytest.mark.parametrize(
    "html",
    [
        # A course page: only the stylesheet every page carries names the row.
        coursedog_page("<h1>ENGL121</h1><p>Course Description</p>"),
        # A row like Coursedog's on a catalog that is not Coursedog.
        "<html><body>" + coursedog_row(1, 9) + "</body></html>",
        # Two lists on one page: which row pages which list is unknown.
        coursedog_page(coursedog_row(1, 9), coursedog_row(1, 4)),
        # A row that numbers no page.
        coursedog_page(
            '<div class="base-pagination"><button>Next</button></div>'
        ),
        "",
    ],
    ids=["course-page", "not-coursedog", "two-rows", "no-numbers", "empty"],
)
def test_a_page_that_is_not_one_coursedog_list_is_left_alone(html: str) -> None:
    assert read_list_pages(html, COURSES) is None


def test_a_class_that_only_contains_the_row_name_is_not_the_row() -> None:
    row = coursedog_row(1, 9).replace("base-pagination", "my-base-pagination")
    assert read_list_pages(coursedog_page(row), COURSES) is None


def test_an_address_with_no_usable_page_number_is_left_alone() -> None:
    page = coursedog_page(coursedog_row(1, 9))
    assert read_list_pages(page, f"{COURSES}?page=abc") is None


def test_the_cap_bounds_what_one_list_can_queue() -> None:
    last = MAX_LIST_PAGES + 50
    pages = read_list_pages(
        coursedog_page(coursedog_row(2, last)), f"{COURSES}?page=2"
    )
    assert pages is not None
    assert pages.problem == PROBLEM_CAPPED
    assert len(pages.urls) == MAX_LIST_PAGES - 2
    assert pages.urls[-1] == f"{COURSES}?page={MAX_LIST_PAGES}"


def test_the_first_page_of_a_long_list_is_not_reported_as_capped() -> None:
    """Page 1 queues page 2 only, so there is nothing to cap yet."""
    page = coursedog_page(coursedog_row(1, MAX_LIST_PAGES + 50))
    pages = read_list_pages(page, COURSES)
    assert pages is not None
    assert pages.problem is None
    assert pages.urls == (f"{COURSES}?page=2",)


@pytest.mark.parametrize(
    ("url", "asked"),
    [
        (COURSES, 1),
        (f"{COURSES}?page=1&cq=", 1),
        (f"{COURSES}?page=7", 7),
        (f"{COURSES}?cq=&page=12", 12),
        (f"{COURSES}?page=abc", None),
        (f"{COURSES}?page=", None),
        (f"{COURSES}?page=1&page=2", None),
        (f"{COURSES}?page=²", None),
    ],
)
def test_asked_page(url: str, asked: int | None) -> None:
    assert asked_page(url) == asked


@pytest.mark.parametrize(
    ("url", "number", "expected"),
    [
        (COURSES, 2, f"{COURSES}?page=2"),
        # Where the site rewrites /courses to, and what its own pages link
        # to: both lead to the one page 2.
        (f"{COURSES}?page=1&cq=", 2, f"{COURSES}?page=2"),
        (
            f"{COURSES}?page=2&cq=&department=ACCT",
            3,
            f"{COURSES}?page=3&department=ACCT",
        ),
        (
            f"{COURSES}?cq=ENGL%20101&page=2",
            3,
            f"{COURSES}?page=3&cq=ENGL%20101",
        ),
        (f"{COURSES}?page=2#results", 3, f"{COURSES}?page=3"),
        (f"{PROGRAMS}?flag&page=2", 3, f"{PROGRAMS}?page=3&flag"),
    ],
)
def test_page_url(url: str, number: int, expected: str) -> None:
    assert page_url(url, number) == expected
