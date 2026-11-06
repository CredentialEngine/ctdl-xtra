from review_ui.runs import PageRef
from review_ui.sample import pick_sample

BASE = "https://ccsf.curricunet.com/catalog/iq"


def ref(path, n):
    return PageRef(f"s{n}", f"{BASE}/{path}", "", f"p/s{n}.html")


def catalog():
    pages = [ref(f"courses/3/{n}", n) for n in range(60)]
    pages += [ref(f"programs/area{n % 5}/{n}/{n}", 100 + n) for n in range(30)]
    pages += [ref(f"programs/area{n}", 200 + n) for n in range(5)]
    pages += [ref(f"{1700 + n}", 300 + n) for n in range(12)]
    return pages


def html_of(page):
    """Fake saved html whose features follow the stem number, in CurricUNET markup."""
    n = int(page.stem[1:])
    blocks = ('course-summary-wrapper"' if n < 100 else 'course-entry"') * (
        40 if n % 7 == 0 else 5
    )
    flags = ""
    if n % 4 == 0:
        flags += 'course-unit-range">(1.0-3.0)'
    if n % 5 == 0:
        flags += 'course-Type">Noncredit'
    if n == 33:
        flags += 'course-catalog-description"></span>'
    return blocks + flags


def size_of(entry):
    return html_of(PageRef(entry["stem"], entry["url"], "", "")).count('"') // 1


def types_of(picked):
    counts = {}
    for entry in picked:
        counts[entry["page_type"]] = counts.get(entry["page_type"], 0) + 1
    return counts


def sample(ruleset, **kw):
    return pick_sample(
        catalog(), ruleset["sample"], ruleset["page_types"], html_of, **kw
    )


def test_sample_mixes_page_types_by_the_rulesets_quotas(ruleset):
    picked = sample(ruleset)
    assert types_of(picked) == ruleset["sample"]["quotas"] and len(picked) == 30


def test_course_pages_cover_the_rulesets_odd_cases(ruleset):
    reasons = {e["reason"] for e in sample(ruleset) if e["page_type"] == "course"}
    assert reasons == {
        "course, empty description",
        "course, range",
        "course, noncredit",
        "course, plain",
    }


def test_small_pages_are_preferred(ruleset):
    picked = sample(ruleset)
    big = [
        e
        for e in picked
        if e["page_type"] in ("course", "program")
        and "40"
        and size_of(e)
        and html_of(PageRef(e["stem"], "", "", "")).count("course-") > 12
    ]
    assert big == []


def test_programs_are_spread_across_areas(ruleset):
    areas = {
        e["url"].split("/programs/")[1].split("/")[0]
        for e in sample(ruleset)
        if e["page_type"] == "program"
    }
    assert len(areas) == 5


def test_sample_is_deterministic_and_has_no_duplicates(ruleset):
    first = sample(ruleset)
    assert first == pick_sample(
        list(reversed(catalog())), ruleset["sample"], ruleset["page_types"], html_of
    )
    assert len({e["stem"] for e in first}) == len(first)


def test_sample_size_scales_the_page_type_mix(ruleset):
    picked = sample(ruleset, target=10)
    counts = types_of(picked)
    assert len(picked) == 10 and counts["course"] == 4 and counts["program"] == 3


def test_pages_matching_no_page_type_still_fill_the_sample(ruleset):
    pages = [
        PageRef(f"s{n}", f"https://other.edu/page{n}", "", f"p/s{n}.html")
        for n in range(50)
    ]
    picked = pick_sample(pages, ruleset["sample"], ruleset["page_types"], html_of)
    assert len(picked) == 30 and {e["reason"] for e in picked} <= {"info", "top-up"}


def test_a_ruleset_with_no_sample_config_gets_a_default_size_sample():
    pages = [
        PageRef(f"s{n}", f"https://other.edu/page{n}", "", f"p/s{n}.html")
        for n in range(50)
    ]
    picked = pick_sample(pages, {}, [], html_of)
    assert len(picked) == 30 and {e["reason"] for e in picked} == {"top-up"}


def test_html_is_only_read_when_a_stratum_or_size_pattern_needs_it():
    calls = []
    config = {"quotas": {"course": 3}}
    pick_sample(
        catalog(),
        config,
        [{"type": "course", "url_regex": "/courses/"}],
        lambda p: calls.append(p) or "",
    )
    assert calls == []


def test_a_stratum_without_a_pattern_takes_whatever_is_left():
    types = [{"type": "course", "url_regex": "/courses/"}]
    config = {
        "quotas": {"course": 4},
        "strata": {
            "course": [
                {"name": "noncredit", "quota": 1, "pattern": "Noncredit"},
                {"name": "rest", "quota": 3},
            ]
        },
    }
    picked = pick_sample(catalog(), config, types, html_of, target=4)
    reasons = sorted(e["reason"] for e in picked)
    assert reasons == [
        "course, noncredit",
        "course, rest",
        "course, rest",
        "course, rest",
    ]
    assert len({e["stem"] for e in picked}) == 4
