"""URL stems and pack-relative paths. A stem names every cached file, so a
change to slug_url orphans everything already cached."""

from __future__ import annotations

from pathlib import Path

import pytest
from html_text import SCRIPT_STYLE, pack_join, slug_url


@pytest.mark.parametrize(
    ("url", "stem"),
    [
        (
            "https://catalog.example.edu/english/engl101",
            "catalog-example-edu-english-engl101",
        ),
        (
            "http://catalog.example.edu/preview_course_nopop.php"
            "?catoid=8&coid=1234",
            "catalog-example-edu-preview-course-nopop-php-catoid-8-coid-1234",
        ),
        (
            "https://catalog.example.edu/courses/ENGL121/",
            "catalog-example-edu-courses-ENGL121",
        ),
        (
            "https://a.example.edu/r?next=https://b.example.edu",
            "a-example-edu-r-next-b-example-edu",
        ),
    ],
)
def test_slug_url_gives_the_stem_cached_files_are_named_by(
    url: str, stem: str
) -> None:
    assert slug_url(url) == stem


def test_slug_url_stops_at_120_characters() -> None:
    url = "https://catalog.example.edu/" + "x" * 200
    assert slug_url(url) == ("catalog-example-edu-" + "x" * 200)[:120]


def test_pack_join_splits_posix_and_windows_separators(tmp_path: Path) -> None:
    expected = tmp_path.joinpath("cache", "2026-10-21", "x.html")
    assert pack_join(tmp_path, "cache/2026-10-21/x.html") == expected
    assert pack_join(tmp_path, "cache\\2026-10-21\\x.html") == expected


@pytest.mark.parametrize("rel", ["", None])
def test_pack_join_of_nothing_is_the_pack_itself(
    tmp_path: Path, rel: str | None
) -> None:
    assert pack_join(tmp_path, rel) == tmp_path


def test_script_style_removes_each_hidden_block_in_any_case() -> None:
    html = (
        '<p>a</p><SCRIPT type="x">if (a < b) {}\n</SCRIPT>'
        "<style>p{}</style><noscript><p>n</p></noscript><p>b</p>"
    )
    assert SCRIPT_STYLE.sub("", html) == "<p>a</p><p>b</p>"
