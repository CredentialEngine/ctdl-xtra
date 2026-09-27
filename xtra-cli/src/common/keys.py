"""Object keys for a catalog run. No zip, no pack directory.

One converter turns a catalog URL into the folder that holds its runs, so a
crawl is recognisable from the storage path alone.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit

from common.clock import run_id_for_path

_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")
_NOT_ALNUM_RE = re.compile(r"[^a-z0-9]+")

# 80 + "-" + 10 hex keeps a Windows run path well under the 260 character
# limit, and the digest keeps two long URLs apart when the slug truncates.
STEM_SLUG_LIMIT = 80
STEM_DIGEST_LENGTH = 10

_DEFAULT_PORTS = {"http": 80, "https": 443}


def hyphenate(value: str) -> str:
    """Lowercase, then every run of non a-z0-9 becomes one hyphen."""
    return _NOT_ALNUM_RE.sub("-", value.lower()).strip("-")


def catalog_folder_name(url: str) -> str:
    """Folder that holds every run of one catalog, from the URL as typed.

    https://catalog.bergen.edu/content.php?catoid=13&navoid=664
      -> catalog-bergen-edu-content-php-catoid-13-navoid-664
    """
    without_fragment = url.split("#", 1)[0]
    without_scheme = _SCHEME_RE.sub("", without_fragment)
    return hyphenate(without_scheme.rstrip("/"))


def dedupe_key(url: str) -> str:
    """Identity of one page: lowercased host, path and query, no fragment.

    http and https are the same page, so the scheme is dropped. A port is
    kept only when it is not the default for its scheme, so a catalog served
    on a spare port cannot collide with the same path on 443.
    """
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    port = parsed.port
    scheme = (parsed.scheme or "").lower()
    suffix = ""
    if port is not None and port != _DEFAULT_PORTS.get(scheme, port):
        suffix = f":{port}"
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{host}{suffix}{path}{query}"


def page_stem(url: str) -> str:
    """File name for one saved page: readable slug plus a collision guard."""
    key = dedupe_key(url)
    slug = hyphenate(key)[:STEM_SLUG_LIMIT].rstrip("-")
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[
        :STEM_DIGEST_LENGTH
    ]
    return f"{slug}-{digest}" if slug else digest


def run_prefix(catalog_folder: str, run_id: str) -> str:
    return f"{catalog_folder.strip('/')}/{run_id_for_path(run_id)}"


def crawl_key(catalog_folder: str, run_id: str) -> str:
    return f"{run_prefix(catalog_folder, run_id)}/crawl.json"


def state_key(catalog_folder: str, run_id: str) -> str:
    return f"{run_prefix(catalog_folder, run_id)}/state.json"


def failed_key(catalog_folder: str, run_id: str) -> str:
    return f"{run_prefix(catalog_folder, run_id)}/failed.jsonl"


def page_html_key(catalog_folder: str, run_id: str, stem: str) -> str:
    return f"{run_prefix(catalog_folder, run_id)}/pages/{stem}.html"


def page_meta_key(catalog_folder: str, run_id: str, stem: str) -> str:
    return f"{run_prefix(catalog_folder, run_id)}/pages/{stem}.meta.json"


def discovery_root(catalog_folder: str, run_id: str) -> str:
    """Where every discovery run of one crawl run lives, side by side."""
    return f"{run_prefix(catalog_folder, run_id)}/discovery"


def discovery_prefix(
    catalog_folder: str, run_id: str, discovery_run_id: str
) -> str:
    return (
        f"{discovery_root(catalog_folder, run_id)}/"
        f"{run_id_for_path(discovery_run_id)}"
    )


def discovery_key(
    catalog_folder: str, run_id: str, discovery_run_id: str, name: str
) -> str:
    return (
        f"{discovery_prefix(catalog_folder, run_id, discovery_run_id)}/{name}"
    )


def extract_report_key(catalog_folder: str, run_id: str) -> str:
    """Skipped pages live beside records/, never inside it.

    transform reads every JSON file under records/, so a report stored there
    would be transformed as if it were a course.
    """
    return f"{run_prefix(catalog_folder, run_id)}/extract-report.json"


def record_key(catalog_folder: str, run_id: str, record_id: str) -> str:
    return f"{run_prefix(catalog_folder, run_id)}/records/{record_id}.json"


def jsonld_key(catalog_folder: str, run_id: str, record_id: str) -> str:
    return f"{run_prefix(catalog_folder, run_id)}/jsonld/{record_id}.json"


def expected_key(catalog_folder: str, run_id: str, record_id: str) -> str:
    return f"{run_prefix(catalog_folder, run_id)}/expected/{record_id}.json"
