from __future__ import annotations

import logging

import pytest
from crawl_doubles import LIST_LOADING, button_row, list_site_page

from implementations.crawl_list_pages import (
    MAX_LIST_PAGES,
    PROBLEM_CAPPED,
    PROBLEM_LOADING,
    PROBLEM_NO_CURRENT_PAGE,
    PROBLEM_PAGE_IGNORED,
    asked_page,
    page_url,
    queue_list_pages,
    read_bar,
    read_list_pages,
)

COURSES = "https://catalog.example.edu/courses"
PROGRAMS = "https://catalog.example.edu/programs"

# A row copied from a saved catalog page, page 1 of 137, svg paths cut short.
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
    bar = read_bar(list_site_page(REAL_ROW))
    assert bar is not None
    assert (bar.current, bar.last) == (1, 137)


def test_the_first_page_of_a_list_queues_its_second_page_only() -> None:
    """One page is enough to learn whether the list opens by number."""
    pages = read_list_pages(list_site_page(REAL_ROW), COURSES)
    assert pages is not None
    assert pages.urls == (f"{COURSES}?page=2",)
    assert (pages.asked, pages.current, pages.last) == (1, 1, 137)
    assert pages.problem is None


def test_a_page_that_opened_as_asked_queues_every_page_after_it() -> None:
    pages = read_list_pages(
        list_site_page(button_row(2, 6)), f"{COURSES}?page=2"
    )
    assert pages is not None
    assert pages.urls == tuple(f"{COURSES}?page={n}" for n in (3, 4, 5, 6))
    assert pages.problem is None


def test_a_later_page_queues_only_the_pages_after_it() -> None:
    pages = read_list_pages(
        list_site_page(button_row(4, 6)), f"{COURSES}?page=4"
    )
    assert pages is not None
    assert pages.urls == (f"{COURSES}?page=5", f"{COURSES}?page=6")


def test_the_last_page_and_a_one_page_list_queue_nothing() -> None:
    last = read_list_pages(
        list_site_page(button_row(6, 6)), f"{COURSES}?page=6"
    )
    assert last is not None
    assert last.urls == ()
    assert last.problem is None
    alone = read_list_pages(list_site_page(button_row(1, 1)), COURSES)
    assert alone is not None
    assert alone.urls == ()
    assert alone.problem is None


def test_a_list_that_ignores_the_page_in_its_address_queues_nothing_more() -> (
    None
):
    """Asked for page 2 and showing page 1: the address does not page it."""
    pages = read_list_pages(
        list_site_page(button_row(1, 195)), f"{PROGRAMS}?page=2"
    )
    assert pages is not None
    assert pages.urls == ()
    assert pages.problem == PROBLEM_PAGE_IGNORED
    assert (pages.asked, pages.current, pages.last) == (2, 1, 195)


def test_a_list_saved_before_it_loaded_says_so() -> None:
    pages = read_list_pages(list_site_page(LIST_LOADING), COURSES)
    assert pages is not None
    assert pages.urls == ()
    assert pages.problem == PROBLEM_LOADING


def test_a_row_that_marks_no_page_as_on_screen_says_so() -> None:
    plain = (
        button_row(2, 6)
        .replace("btn-primary", "btn-secondary")
        .replace(' disabled=""', "")
    )
    pages = read_list_pages(list_site_page(plain), f"{COURSES}?page=2")
    assert pages is not None
    assert pages.urls == ()
    assert pages.problem == PROBLEM_NO_CURRENT_PAGE


def test_the_disabled_button_marks_the_page_when_none_is_highlighted() -> None:
    """The "..." gap is disabled too, but it carries no page number."""
    uncoloured = button_row(2, 9).replace("btn-primary", "btn-secondary")
    bar = read_bar(list_site_page(uncoloured))
    assert bar is not None
    assert (bar.current, bar.last) == (2, 9)


def test_the_row_ends_where_its_own_element_ends() -> None:
    """A wrapper closing inside the row does not end it; a button after does
    not join it."""
    row = button_row(1, 9).replace(
        'mt-4">', 'mt-4"><div class="spacer"></div>', 1
    )
    after = (
        '<button class="btn btn-primary mx-1" type="button" disabled="" '
        'number="999">999</button>'
    )
    bar = read_bar(list_site_page(row, after))
    assert bar is not None
    assert (bar.current, bar.last) == (1, 9)


@pytest.mark.parametrize(
    "html",
    [
        # A course page: only the stylesheet every page carries names the row.
        list_site_page("<h1>ENGL121</h1><p>Course Description</p>"),
        # Two lists on one page: which row pages which list is unknown.
        list_site_page(button_row(1, 9), button_row(1, 4)),
        # A row that numbers no page.
        list_site_page(
            '<div class="base-pagination"><button>Next</button></div>'
        ),
        "",
    ],
    ids=["course-page", "two-rows", "no-numbers", "empty"],
)
def test_a_page_that_is_not_one_list_is_left_alone(html: str) -> None:
    assert read_list_pages(html, COURSES) is None


def test_loading_text_without_the_row_class_is_left_alone() -> None:
    page = f"<html><body>{LIST_LOADING}</body></html>"
    assert read_list_pages(page, COURSES) is None


def test_a_class_that_only_contains_the_row_name_is_not_the_row() -> None:
    row = button_row(1, 9).replace("base-pagination", "my-base-pagination")
    assert read_list_pages(list_site_page(row), COURSES) is None


def test_an_address_with_no_usable_page_number_is_left_alone() -> None:
    page = list_site_page(button_row(1, 9))
    assert read_list_pages(page, f"{COURSES}?page=abc") is None


def test_the_cap_bounds_what_one_list_can_queue() -> None:
    last = MAX_LIST_PAGES + 50
    pages = read_list_pages(
        list_site_page(button_row(2, last)), f"{COURSES}?page=2"
    )
    assert pages is not None
    assert pages.problem == PROBLEM_CAPPED
    assert len(pages.urls) == MAX_LIST_PAGES - 2
    assert pages.urls[-1] == f"{COURSES}?page={MAX_LIST_PAGES}"


def test_the_first_page_of_a_long_list_is_not_reported_as_capped() -> None:
    """Page 1 queues page 2 only, so there is nothing to cap yet."""
    page = list_site_page(button_row(1, MAX_LIST_PAGES + 50))
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


class FakeQueue:
    """Stands in for Crawler.enqueue: records each URL, says if it was new."""

    def __init__(self, seen: tuple[str, ...] = ()) -> None:
        self.seen = set(seen)
        self.asked: list[str] = []

    def __call__(self, url: str) -> bool:
        self.asked.append(url)
        if url in self.seen:
            return False
        self.seen.add(url)
        return True


def list_messages(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("LIST ")
    ]


def test_the_pages_go_to_enqueue_and_only_the_new_ones_are_counted(
    caplog,
) -> None:
    queue = FakeQueue(seen=(f"{COURSES}?page=4",))
    with caplog.at_level(logging.INFO):
        queued = queue_list_pages(
            list_site_page(button_row(2, 5)),
            f"{COURSES}?page=2",
            enqueue=queue,
        )
    assert queue.asked == [f"{COURSES}?page={n}" for n in (3, 4, 5)]
    assert queued == 2
    assert list_messages(caplog) == [
        f"LIST {COURSES}?page=2 opened as page 2 of 5; queued 2 more "
        "page(s) of the list"
    ]


def test_a_list_already_queued_is_read_again_without_a_word(caplog) -> None:
    """What a resume does with every list page it reads back."""
    queue = FakeQueue(seen=(f"{COURSES}?page=2",))
    with caplog.at_level(logging.INFO):
        queued = queue_list_pages(
            list_site_page(button_row(1, 9)), COURSES, enqueue=queue
        )
    assert queued == 0
    assert list_messages(caplog) == []


def test_a_page_that_is_not_a_list_never_reaches_enqueue() -> None:
    queue = FakeQueue()
    page = "<html><body>no list</body></html>"
    assert queue_list_pages(page, COURSES, enqueue=queue) == 0
    assert queue.asked == []


def test_a_list_that_cannot_be_paged_is_warned_about(caplog) -> None:
    queue = FakeQueue()
    with caplog.at_level(logging.WARNING):
        queued = queue_list_pages(
            list_site_page(LIST_LOADING), COURSES, enqueue=queue
        )
    assert queued == 0
    assert queue.asked == []
    assert list_messages(caplog) == [
        f"LIST {COURSES} was saved before its list loaded (Loading "
        "results...), so the pages after it are not known"
    ]
