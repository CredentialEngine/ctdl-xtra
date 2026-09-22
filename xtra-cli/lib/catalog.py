"""Family and URL helpers for catalog course discovery. No LLM."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse


CLEAN_COURSE_PATH = re.compile(r"^/([a-z0-9-]+)/([a-z]{2,6}\d{2,4}[a-z]?)/?$", re.I)
# Catalog codes like ENGL121 / ENG101. Not Coursedog document ids (LJdUL84T, JDbDH653).
COURSEDOG_COURSE_CODE = re.compile(
    r"^(?:[A-Z]{2,8}|[a-z]{2,8})[-_]?\d{3,4}[A-Za-z]?$"
)
COURSEDOG_COURSE_PATH = re.compile(
    r"^/courses/((?:[A-Z]{2,8}|[a-z]{2,8})[-_]?\d{3,4}[A-Za-z]?)/?$"
)
ACALOG_COURSE = re.compile(
    r"preview_course(?:_nopop)?\.php\?[^'\"\s<>]*catoid=\d+[^'\"\s<>]*coid=\d+",
    re.I,
)


def college_slug(url: str) -> str:
    host = (urlparse(url).hostname or "catalog").lower()
    for prefix in ("catalog.", "www.", "coursecatalog.", "bulletin."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    if host.endswith(".edu"):
        host = host[:-4]
    elif host.endswith(".org"):
        host = host[:-4]
    slug = re.sub(r"[^a-z0-9]+", "-", host).strip("-")
    return slug or "college"


def origin_of(url: str) -> str:
    p = urlparse(url)
    return urlunparse((p.scheme or "https", p.netloc, "", "", "", ""))


def abs_url(base: str, href: str) -> str:
    return urljoin(base, href.split("#", 1)[0])


def detect_family(html: str, url: str = "") -> str:
    """CMS family from distinctive markers. Coursedog and Acalog before Clean Catalog."""
    blob = f"{html}\n{url}".lower()
    path = urlparse(url).path.lower()
    if "coursedog" in blob:
        return "coursedog"
    if path.startswith("/courses/") and path.count("/") >= 2:
        return "coursedog"
    if (
        "acalog" in blob
        or "preview_course" in blob
        or "catoid=" in blob
        or "modern campus catalog" in blob
    ):
        return "acalog"
    if "preview_course" in path or "catoid=" in url.lower():
        return "acalog"
    if "cleancatalog.com" in blob:
        return "custom_html"
    return "unknown"


def is_course_detail_url(url: str, family: str | None = None) -> bool:
    path = urlparse(url).path
    fam = family or detect_family("", url)
    if fam == "coursedog" or COURSEDOG_COURSE_PATH.match(path):
        return bool(COURSEDOG_COURSE_PATH.match(path))
    if fam == "acalog" or "preview_course" in path:
        qs = parse_qs(urlparse(url).query)
        return "catoid" in qs and "coid" in qs
    if fam in {"custom_html", "clean_catalog"}:
        return bool(CLEAN_COURSE_PATH.match(path))
    return bool(
        COURSEDOG_COURSE_PATH.match(path)
        or CLEAN_COURSE_PATH.match(path)
        or ("preview_course" in path and "coid=" in url)
    )


def normalize_course_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path
    if "preview_course.php" in path and "preview_course_nopop" not in path:
        path = path.replace("preview_course.php", "preview_course_nopop.php")
        qs = parse_qs(parsed.query)
        catoid = (qs.get("catoid") or [""])[0]
        coid = (qs.get("coid") or [""])[0]
        if catoid and coid:
            return urlunparse(
                (parsed.scheme, parsed.netloc, path, "", f"catoid={catoid}&coid={coid}", "")
            )
    if COURSEDOG_COURSE_PATH.match(path) or CLEAN_COURSE_PATH.match(path):
        return urlunparse((parsed.scheme, parsed.netloc, path.rstrip("/") or path, "", "", ""))
    return url.split("#", 1)[0]


def record_id_for(college: str, url: str, code_hint: str | None = None) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if qs.get("coid"):
        token = f"coid-{qs['coid'][0]}"
    elif code_hint:
        token = code_hint
    else:
        token = parsed.path.rstrip("/").split("/")[-1]
    slug = re.sub(r"[^a-z0-9]+", "-", token.lower()).strip("-")
    return f"{college}-{slug}-course"


def page_id_for(record_id: str) -> str:
    if record_id.endswith("-course"):
        return record_id[: -len("-course")]
    return record_id


def institution_from_html(html: str, fallback: str) -> str:
    m = re.search(r'property="og:site_name"\s+content="([^"]+)"', html, re.I)
    if m:
        return _clean_inst(m.group(1))
    m = re.search(r'<meta[^>]+name="og:site_name"[^>]+content="([^"]+)"', html, re.I)
    if m:
        return _clean_inst(m.group(1))
    m = re.search(r"<title>([^<]+)</title>", html, re.I)
    if m:
        title = re.split(r"\s+[|\-–]\s+", m.group(1).strip())[0]
        title = re.sub(r"\s+Catalog.*$", "", title, flags=re.I).strip()
        if title and title.lower() not in {"courses", "catalog", "home"}:
            return _clean_inst(title)
    return fallback


def _clean_inst(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip()


def subject_key(url: str) -> str:
    path = urlparse(url).path.strip("/")
    qs = parse_qs(urlparse(url).query)
    if qs.get("coid"):
        return "acalog"
    parts = path.split("/")
    if not parts:
        return "other"
    token = parts[-1]
    m = re.match(r"([A-Za-z]{2,8})", token)
    return (m.group(1) if m else token[:8]).lower()


def sample_urls(urls: list[str], limit: int) -> list[str]:
    """Round-robin by subject prefix so a 30-pack is not 30 ENGL courses."""
    if limit <= 0 or len(urls) <= limit:
        return list(urls)
    buckets: dict[str, list[str]] = {}
    order: list[str] = []
    for url in urls:
        key = subject_key(url)
        if key not in buckets:
            order.append(key)
            buckets[key] = []
        buckets[key].append(url)
    if order == ["acalog"]:
        step = len(urls) / limit
        return [urls[min(len(urls) - 1, int(i * step))] for i in range(limit)]
    out: list[str] = []
    idx = 0
    while len(out) < limit:
        progressed = False
        for key in order:
            bucket = buckets[key]
            if idx < len(bucket):
                out.append(bucket[idx])
                progressed = True
                if len(out) >= limit:
                    break
        if not progressed:
            break
        idx += 1
    return out
