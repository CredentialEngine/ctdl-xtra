"""Harvest course detail URLs from a college catalog homepage. HTML proof only."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from catalog import (
    ACALOG_COURSE,
    CLEAN_COURSE_PATH,
    COURSEDOG_COURSE_PATH,
    abs_url,
    college_slug,
    detect_family,
    institution_from_html,
    is_course_detail_url,
    normalize_course_url,
    origin_of,
    sample_urls,
)
from slots import Slot
from catalog import page_id_for, record_id_for

HREF = re.compile(r"""href=["']([^"'#]+)["']""", re.I)
COURSE_CODE = re.compile(r"^[A-Za-z]{2,8}[-_]?[A-Za-z]?\d{2,4}[A-Za-z]?$")


def iter_json_codes(obj, acc: list[str]) -> None:
    if isinstance(obj, dict):
        for key in ("code", "id", "courseId", "displayName"):
            val = obj.get(key)
            if isinstance(val, str) and COURSE_CODE.match(val.strip()):
                acc.append(val.strip())
        for val in obj.values():
            iter_json_codes(val, acc)
    elif isinstance(obj, list):
        for item in obj:
            iter_json_codes(item, acc)


def hrefs_from_html(html: str, base: str) -> list[str]:
    out = []
    for href in HREF.findall(html):
        if href.startswith("javascript:") or href.startswith("mailto:"):
            continue
        out.append(abs_url(base, href))
    return out


def acalog_listing_url(html: str, page_url: str) -> str | None:
    origin = origin_of(page_url)
    best = None
    for href in HREF.findall(html):
        full = abs_url(page_url, href)
        if "content.php" not in full or "catoid=" not in full:
            continue
        low = href.lower()
        parent = html[max(0, html.lower().find(href.lower()) - 120) : html.lower().find(href.lower()) + 160].lower()
        if "courses (a-z)" in parent or "courses a-z" in parent or ">courses<" in parent:
            if "discipline" in parent:
                continue
            best = full
            if "a-z" in parent:
                return full
    if best:
        return best
    m = re.search(
        r'href="([^"]*content\.php\?catoid=\d+&amp;navoid=\d+)"[^>]*>\s*Courses',
        html,
        re.I,
    )
    if m:
        return abs_url(page_url, m.group(1).replace("&amp;", "&"))
    parsed = urlparse(page_url)
    qs = parse_qs(parsed.query)
    if "catoid" in qs and "navoid" in qs:
        return page_url
    return None


def acalog_course_urls(html: str, page_url: str) -> list[str]:
    found = []
    for raw in ACALOG_COURSE.findall(html):
        found.append(normalize_course_url(abs_url(page_url, raw.replace("&amp;", "&"))))
    return list(dict.fromkeys(found))


def acalog_max_page(html: str) -> int:
    nums = [int(n) for n in re.findall(r"filter(?:\[|%5B)cpage(?:\]|%5D)=(\d+)", html)]
    nums += [int(n) for n in re.findall(r"Page\s+\d+\s+of\s+(\d+)", html, re.I)]
    return max(nums) if nums else 1


def clean_course_urls(html: str, page_url: str) -> list[str]:
    origin = origin_of(page_url)
    found = []
    for href in hrefs_from_html(html, page_url):
        if urlparse(href).netloc != urlparse(origin).netloc:
            continue
        if CLEAN_COURSE_PATH.match(urlparse(href).path):
            found.append(normalize_course_url(href))
    return list(dict.fromkeys(found))


def clean_subject_urls(html: str, page_url: str) -> list[str]:
    origin = origin_of(page_url)
    skip = {
        "login",
        "search",
        "degrees",
        "certificates",
        "archived",
        "handbook",
        "about",
        "admissions",
        "home",
        "catalog",
        "courses",
        "programs",
    }
    found = []
    for href in hrefs_from_html(html, page_url):
        p = urlparse(href)
        if p.netloc != urlparse(origin).netloc:
            continue
        parts = [x for x in p.path.split("/") if x]
        if len(parts) == 1 and re.fullmatch(r"[a-z][a-z0-9-]{2,40}", parts[0]) and parts[0] not in skip:
            found.append(f"{origin}/{parts[0]}")
    return list(dict.fromkeys(found))


def coursedog_course_urls(html: str, page_url: str) -> list[str]:
    origin = origin_of(page_url)
    found = []
    for href in hrefs_from_html(html, page_url):
        if urlparse(href).netloc != urlparse(origin).netloc:
            continue
        if COURSEDOG_COURSE_PATH.match(urlparse(href).path):
            found.append(normalize_course_url(href))
    return list(dict.fromkeys(found))


def make_slot(
    url: str,
    *,
    institution: str,
    family: str,
    template_id: str,
) -> Slot:
    slug = college_slug(url)
    rid = record_id_for(slug, url)
    return Slot(
        rid,
        "Course",
        url,
        institution,
        family,
        template_id or family,
        "1",
        page_id_for(rid),
        None,
        None,
    )


def harvest_with_playwright(
    seed_url: str,
    *,
    want: int,
    fetch_all: bool,
) -> dict:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    buffer = 10_000 if fetch_all else max(want * 4, 40)
    origin = origin_of(seed_url)
    json_codes: list[str] = []

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, channel="chrome")
        except Exception:
            browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1400, "height": 1800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            ignore_https_errors=True,
        )
        page = context.new_page()
        page.set_default_timeout(60000)

        def on_response(resp) -> None:
            try:
                ct = (resp.headers or {}).get("content-type") or ""
                if "json" not in ct:
                    return
                data = resp.json()
                iter_json_codes(data, json_codes)
            except Exception:
                return

        page.on("response", on_response)

        def goto(url: str) -> str:
            try:
                page.goto(url, wait_until="load", timeout=60000)
            except PlaywrightTimeout:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1200)
            return page.content()

        html = goto(seed_url)
        family = detect_family(html, seed_url)
        institution = institution_from_html(html, college_slug(seed_url).replace("-", " ").title())
        urls: list[str] = []

        if is_course_detail_url(seed_url, family):
            urls = [normalize_course_url(seed_url)]
        elif family == "acalog":
            listing = acalog_listing_url(html, seed_url) or seed_url
            listing_html = goto(listing) if listing != seed_url else html
            urls.extend(acalog_course_urls(listing_html, listing))
            max_page = acalog_max_page(listing_html)
            parsed = urlparse(listing)
            qs = parse_qs(parsed.query)
            catoid = (qs.get("catoid") or [None])[0]
            navoid = (qs.get("navoid") or [None])[0]
            if catoid and navoid:
                last = max_page if fetch_all else min(max_page, 8)
                for n in range(1, last + 1):
                    page_url = (
                        f"{origin}/content.php?catoid={catoid}&navoid={navoid}&filter[cpage]={n}"
                    )
                    ph = goto(page_url)
                    urls.extend(acalog_course_urls(ph, page_url))
                    if len(dict.fromkeys(urls)) >= buffer:
                        break
        elif family == "coursedog":
            courses_home = f"{origin}/courses"
            ch = goto(courses_home)
            urls.extend(coursedog_course_urls(ch, courses_home))
            for code in json_codes:
                urls.append(normalize_course_url(f"{origin}/courses/{code}"))
            for _ in range(25 if fetch_all else 8):
                moved = False
                loc = page.locator(
                    'a:has-text("Next"), button:has-text("Next"), [aria-label="Next page"], [aria-label="Next"]'
                )
                if loc.count() > 0:
                    try:
                        loc.first.click(timeout=2000)
                        page.wait_for_timeout(900)
                        moved = True
                    except Exception:
                        moved = False
                if not moved:
                    page.mouse.wheel(0, 3500)
                    page.wait_for_timeout(700)
                html_now = page.content()
                urls.extend(coursedog_course_urls(html_now, courses_home))
                for code in json_codes:
                    urls.append(normalize_course_url(f"{origin}/courses/{code}"))
                if len(dict.fromkeys(urls)) >= buffer:
                    break
        elif family == "custom_html":
            urls.extend(clean_course_urls(html, seed_url))
            for subject in clean_subject_urls(html, seed_url):
                sh = goto(subject)
                urls.extend(clean_course_urls(sh, subject))
                if len(dict.fromkeys(urls)) >= buffer:
                    break
        else:
            urls.extend(coursedog_course_urls(html, seed_url))
            urls.extend(clean_course_urls(html, seed_url))
            urls.extend(acalog_course_urls(html, seed_url))

        browser.close()

    urls = [normalize_course_url(u) for u in urls if is_course_detail_url(u, family if family != "unknown" else None)]
    urls = list(dict.fromkeys(urls))
    chosen = urls if fetch_all else sample_urls(urls, want)
    family_out = family if family != "unknown" else detect_family("", chosen[0] if chosen else seed_url)
    slots = [
        make_slot(u, institution=institution, family=family_out, template_id=family_out)
        for u in chosen
    ]
    return {
        "seed_url": seed_url,
        "family": family_out,
        "institution_name": institution,
        "discovered": len(urls),
        "kept": len(slots),
        "slots": slots,
        "sample": not fetch_all,
    }
