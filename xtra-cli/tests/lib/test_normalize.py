"""HTML to normalized text: the text every offset and template runs on.

Discovery and extraction share this normalizer, so a change in what it
prints moves every stored evidence offset. The fixture outputs below are
pinned on purpose.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from normalize import normalize_html, sha256_bytes, sha256_text
from template_texts import lines

D10 = (
    "D10: a <head> with no </head>, which HTML5 allows, hides the whole "
    "body: the skip counter at normalize.py:31-33 never comes back down"
)

ENGL101_TEXT = lines(
    "Course Catalog Software by Clean Catalog",
    "ENGL101:",
    "Composition I",
    "Credits",
    "3",
    "Lecture Hours",
    "3",
    "An introduction to college writing.",
)


def test_the_engl101_fixture_gives_one_line_per_block(
    engl101_html: str,
) -> None:
    assert normalize_html(engl101_html) == ENGL101_TEXT


def test_source_line_breaks_inside_a_paragraph_become_lines(
    fixture_html_dir: Path,
) -> None:
    """A browser shows one paragraph; the templates read lines."""
    html = (fixture_html_dir / "course-clean-catalog.html").read_text(
        encoding="utf-8"
    )
    assert normalize_html(html) == ENGL101_TEXT + lines(
        "This description is published by the college for the current catalog and",
        "is reviewed each year by the academic department that offers it. Students",
        "should speak with an advisor before registering, since availability varies by",
        "term and by campus. The wording below is used for the print edition and the",
        "web edition alike, so the two stay identical. Questions about the text itself",
        "should go to the office that maintains the catalog rather than to the",
        "department.",
    )


@pytest.mark.parametrize(
    ("html", "text"),
    [
        pytest.param(
            "<head><title>T</title><style>p{}</style></head><body><p>A</p>"
            "<script>x()</script><noscript>n</noscript><svg><text>s</text>"
            "</svg><iframe>i</iframe><p>B</p></body>",
            "A\nB\n",
            id="hidden-content-dropped",
        ),
        pytest.param("<p>a<svg/>b</p>", "ab\n", id="self-closing-svg"),
        pytest.param(
            "<div>Name</div><span>4 units</span>",
            "Name4 units\n",
            id="inline-tags-glue-text",
        ),
        pytest.param("<p>a \t  b</p>", "a b\n", id="spaces-and-tabs-collapse"),
        pytest.param(
            "<p>  a  </p><p>   </p><p>b</p>", "a\nb\n", id="blank-lines-dropped"
        ),
        pytest.param("a<br>b<br/>c", "a\nb\nc\n", id="br-breaks-lines"),
        pytest.param(
            "<h2>Head</h2><li>one</li><tr>row</tr><section>s</section>",
            "Head\none\nrow\ns\n",
            id="block-tags-break-lines",
        ),
        pytest.param(
            "<p>ENG 101&nbsp;-&nbsp;Composition</p>",
            "ENG 101\xa0-\xa0Composition\n",
            id="nbsp-kept-inside-a-line",
        ),
        pytest.param(
            "<p>&nbsp;x&nbsp;</p><p>&nbsp;</p>",
            "x\n",
            id="nbsp-stripped-at-line-edges",
        ),
        pytest.param(
            "<p>R&amp;D &#8211; 3</p>",
            "R&D – 3\n",
            id="character-references-decoded",
        ),
        pytest.param("", "\n", id="empty-page"),
    ],
)
def test_normalize_html(html: str, text: str) -> None:
    assert normalize_html(html) == text


def test_normalizing_twice_gives_the_same_text(engl101_html: str) -> None:
    assert normalize_html(engl101_html) == normalize_html(engl101_html)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=D10)
def test_a_page_that_leaves_out_the_head_end_tag_keeps_its_body() -> None:
    html = "<html><head><title>T</title><body><p>Body text</p></body></html>"
    assert normalize_html(html) == "Body text\n"


def test_hashes_are_sha256_hex_of_the_utf8_bytes() -> None:
    assert sha256_bytes(b"ENGL101") == hashlib.sha256(b"ENGL101").hexdigest()
    text = "Café\xa0101"
    assert sha256_text(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert sha256_text("") == sha256_bytes(b"")
