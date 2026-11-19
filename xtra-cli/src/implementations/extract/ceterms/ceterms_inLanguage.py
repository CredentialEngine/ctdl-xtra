"""ceterms:inLanguage, read from a ceterms:Course: the language the course
is taught in, by its English name ("English", "Spanish").

https://credreg.net/ctdl/terms/inLanguage, "The primary language or
languages of the entity, even if it makes use of other languages; e.g., a
course offered in English to teach Spanish would have an inLanguage of
English, while a credential in Quebec could have an inLanguage of both
French and English."

Catalogs rarely say it, so it is looked for in this order, first one found
wins:

1. `stated`: the course says so itself: "The course will be conducted
   entirely in French.", "Course taught in Japanese.", "This course is
   taught in ASL only." A course about a language is not in that language
   unless it says so: "Japanese Anime & Manga. Taught in English."
2. `markup_lang`: the language the markup declares for the course: the
   `lang` of the course's element or the nearest one around it, which on
   most pages is <html lang="en">.
3. `content_language`: a <meta http-equiv="Content-Language"> header.

Never guessed: a course on a page that declares no language has none.
"""

from __future__ import annotations

import re

from bs4 import Comment, NavigableString, Tag

from implementations.discover_rules import collapse
from implementations.extract_run import (
    REASON_NO_CANDIDATE,
    UNPRINTED,
    Occurrence,
    Page,
    Reading,
)

PROPERTY = "ceterms:inLanguage"
# The classes it is read from, each a CTDL class the command knows.
CLASS = ("ceterms:Course",)

STRATEGY_STATED = "stated"
STRATEGY_MARKUP_LANG = "markup_lang"
STRATEGY_CONTENT_LANGUAGE = "content_language"

# A language tag's primary subtag (BCP 47, ISO 639-1) and its English name.
LANGUAGE_NAMES: dict[str, str] = {
    "ar": "Arabic",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "fa": "Persian",
    "fil": "Filipino",
    "fr": "French",
    "he": "Hebrew",
    "hi": "Hindi",
    "hy": "Armenian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "la": "Latin",
    "nl": "Dutch",
    "pl": "Polish",
    "pt": "Portuguese",
    "ru": "Russian",
    "sw": "Swahili",
    "tl": "Tagalog",
    "uk": "Ukrainian",
    "vi": "Vietnamese",
    "zh": "Chinese",
}

# Names a catalog prints for a language other than the one above.
LANGUAGE_ALIASES: dict[str, str] = {
    "american sign language": "American Sign Language",
    "asl": "American Sign Language",
    "cantonese": "Cantonese",
    "farsi": "Persian",
    "mandarin": "Mandarin Chinese",
    "pilipino": "Filipino",
}

_PRINTED_NAMES: dict[str, str] = {
    **{name.lower(): name for name in LANGUAGE_NAMES.values()},
    **LANGUAGE_ALIASES,
}

# "conducted entirely in French", "taught in ASL only", "Course taught
# primarily in Spanish". The verb has to be one that says how the course
# is given, so "readings in Spanish" or "oral practice in Spanish" don't
# count: the course can still be taught in English.
_STATED_RE = re.compile(
    r"\b(?:taught|conducted|offered|delivered|instructed)\s+"
    r"(?:(?:entirely|primarily|mainly|mostly|exclusively|solely|fully|"
    r"completely|only)\s+)?"
    r"in\s+(?P<language>"
    + "|".join(
        re.escape(name)
        for name in sorted(_PRINTED_NAMES, key=len, reverse=True)
    )
    + r")\b",
    re.IGNORECASE,
)


def _words(element: Tag) -> str:
    """The element's printed text with a space between its strings.

    A course's title and its description are elements side by side, and
    joined as printed they run together: "Advanced SpanishConducted in
    Italian." hides the sentence's first word.
    """
    return collapse(
        " ".join(
            str(node)
            for node in element.descendants
            if isinstance(node, NavigableString)
            and not isinstance(node, Comment)
            and not any(parent.name in UNPRINTED for parent in node.parents)
        )
    )


def tag_language(tag: str) -> str | None:
    """A language tag's English name: "en-US" is English. A tag of a
    language not in the table is kept as written; an empty one is None."""
    tag = tag.strip()
    if not tag:
        return None
    primary = re.split(r"[-_]", tag, maxsplit=1)[0].lower()
    return LANGUAGE_NAMES.get(primary, tag)


def _markup_lang(element: Tag) -> str | None:
    """The `lang` the element has, or the nearest element around it."""
    for tag in (element, *element.parents):
        if not isinstance(tag, Tag):
            continue
        declared = tag.get("lang") or tag.get("xml:lang")
        if isinstance(declared, str) and declared.strip():
            return declared
    return None


def _content_language(page: Page) -> str | None:
    meta = page.soup.find(
        "meta",
        attrs={"http-equiv": re.compile(r"^content-language$", re.I)},
    )
    content = meta.get("content") if isinstance(meta, Tag) else None
    if not isinstance(content, str):
        return None
    # A header may list several; the first is the primary one.
    return content.split(",")[0]


def read(occurrence: Occurrence, page: Page) -> Reading:
    """The course's language, read from inside one occurrence, else from
    what the page's markup declares."""
    match = _STATED_RE.search(_words(occurrence.element))
    if match is not None:
        return Reading(
            value=_PRINTED_NAMES[match.group("language").lower()],
            raw_text=match.group(0),
            strategy=STRATEGY_STATED,
            css_path=occurrence.css_path,
        )
    for strategy, declared in (
        (STRATEGY_MARKUP_LANG, _markup_lang(occurrence.element)),
        (STRATEGY_CONTENT_LANGUAGE, _content_language(page)),
    ):
        name = tag_language(declared or "")
        if name is not None:
            return Reading(
                value=name,
                raw_text=declared,
                strategy=strategy,
                css_path=occurrence.css_path,
            )
    return Reading(
        value=None,
        raw_text=None,
        strategy="",
        css_path=occurrence.css_path,
        reason=REASON_NO_CANDIDATE,
    )
