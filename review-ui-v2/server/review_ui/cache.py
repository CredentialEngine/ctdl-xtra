"""A read-through disk cache for crawled pages, so each page is downloaded from Azure once.

Only a crawl's own files are cached: ``<run>/pages/<page>.html`` and ``.meta.json``. A crawl
is written once and a recrawl goes into a new run folder, so those files never change under
the same name and nothing needs invalidating. Everything that does change (review events,
decisions, flags, the index, rulesets, the template, extractions) always goes to storage.

Entries are gzipped (pages compress about tenfold), written to a temporary file and renamed
into place, so several worker processes can share one cache folder. When the folder passes
its size limit the least recently used entries are deleted first.

    REVIEW_UI_CACHE_DIR      folder (default: $XDG_CACHE_HOME/review-ui or ~/.cache/review-ui)
    REVIEW_UI_CACHE_MAX_GB   size limit across the whole folder (default 10)
    REVIEW_UI_CACHE=0        turn the cache off (also `--no-cache`)
"""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .store import Store

CACHE_DIR_ENV = "REVIEW_UI_CACHE_DIR"
CACHE_MAX_GB_ENV = "REVIEW_UI_CACHE_MAX_GB"
CACHE_SWITCH_ENV = "REVIEW_UI_CACHE"
DEFAULT_MAX_GB = 10.0
_OFF = {"0", "off", "false", "no"}
_PAGE_FILE = re.compile(r"(^|/)pages/[^/]+\.(html|meta\.json)$")
_EVICT_TO = 0.9  # when over the limit, delete down to this share of it


def is_cacheable(key: str) -> bool:
    """A crawled page or its metadata: the only files that never change."""
    return bool(_PAGE_FILE.search(key))


def cache_enabled() -> bool:
    return os.environ.get(CACHE_SWITCH_ENV, "1").strip().lower() not in _OFF


def cache_root() -> Path:
    configured = os.environ.get(CACHE_DIR_ENV)
    if configured:
        return Path(configured).expanduser()
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "review-ui"


def cache_max_bytes() -> int:
    try:
        gigabytes = float(os.environ.get(CACHE_MAX_GB_ENV, DEFAULT_MAX_GB))
    except ValueError:
        gigabytes = DEFAULT_MAX_GB
    return int(gigabytes * 1024**3)


def namespace_of(location: str) -> str:
    """A folder name for one storage root, so two containers never share entries."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", location.removeprefix("azure://"))
    return cleaned.strip("_")[:120] or "root"


@dataclass(frozen=True)
class CacheStats:
    files: int
    bytes: int


class DiskCache:
    """Gzipped entries under ``<root>/<namespace>/<key>.gz``; the size limit covers ``root``."""

    def __init__(self, root: Path, namespace: str, max_bytes: int):
        self.root = Path(root)
        self.namespace = namespace
        self.dir = self.root / namespace
        self.max_bytes = max_bytes
        self._lock = threading.Lock()
        self._estimate: int | None = None  # bytes in the whole cache, kept roughly

    # -- entries ------------------------------------------------------------
    def _path(self, key: str) -> Path:
        if ".." in key.split("/") or key.startswith("/"):
            raise ValueError(f"key escapes the cache: {key!r}")
        return self.dir / f"{key}.gz"

    def has(self, key: str) -> bool:
        return self._path(key).exists()

    def get(self, key: str) -> bytes | None:
        path = self._path(key)
        try:
            data = gzip.decompress(path.read_bytes())
        except FileNotFoundError:
            return None
        except (OSError, EOFError):  # a damaged entry: drop it and fetch again
            path.unlink(missing_ok=True)
            return None
        try:
            os.utime(path, None)  # "used just now", for least-recently-used eviction
        except OSError:
            pass
        return data

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        packed = gzip.compress(data, compresslevel=5)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_bytes(packed)
        os.replace(tmp, path)  # atomic: a reader sees the old file or the whole new one
        self._added(len(packed))

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    # -- size ---------------------------------------------------------------
    def _entries(self, under: Path | None = None) -> list[tuple[Path, int, float]]:
        entries = []
        for path in (under or self.root).rglob("*.gz"):
            try:
                info = path.stat()
            except FileNotFoundError:  # another process evicted it meanwhile
                continue
            entries.append((path, info.st_size, info.st_mtime))
        return entries

    def stats(self, namespace_only: bool = True) -> CacheStats:
        entries = self._entries(self.dir if namespace_only else None)
        return CacheStats(len(entries), sum(size for _, size, _ in entries))

    def _added(self, size: int) -> None:
        with self._lock:
            if self._estimate is None:
                self._estimate = self.stats(namespace_only=False).bytes
            else:
                self._estimate += size
            if self._estimate > self.max_bytes:
                self._estimate = self._evict()

    def _evict(self) -> int:
        """Delete least recently used entries until under the limit; returns the new size."""
        entries = sorted(self._entries(), key=lambda e: e[2])  # oldest use first
        total = sum(size for _, size, _ in entries)
        target = int(self.max_bytes * _EVICT_TO)
        for path, size, _ in entries:
            if total <= target:
                break
            path.unlink(missing_ok=True)
            total -= size
        return total

    def clear(self, prefix: str = "") -> int:
        """Delete this root's entries (or those under a key prefix); returns how many."""
        target = self.dir / prefix if prefix else self.dir
        count = len(self._entries(target)) if target.exists() else 0
        shutil.rmtree(target, ignore_errors=True)
        with self._lock:
            self._estimate = None
        return count


class CachedStore:
    """A Store that serves crawled pages from a DiskCache and passes everything else through."""

    def __init__(self, inner: Store, cache: DiskCache):
        self.inner = inner
        self.cache = cache

    def read_text(self, key: str) -> str:
        if not is_cacheable(key):
            return self.inner.read_text(key)
        data = self.cache.get(key)
        if data is None:
            text = self.inner.read_text(key)  # a missing page raises and is not cached
            self.cache.put(key, text.encode("utf-8"))
            return text
        return data.decode("utf-8")

    def read_json(self, key: str) -> Any:
        if not is_cacheable(key):
            return self.inner.read_json(key)
        return json.loads(self.read_text(key))

    def exists(self, key: str) -> bool:
        return (is_cacheable(key) and self.cache.has(key)) or self.inner.exists(key)

    def write_text(self, key: str, text: str) -> None:
        self.inner.write_text(key, text)
        if is_cacheable(key):
            self.cache.delete(key)  # never serve a stale copy of something just written

    def write_json(self, key: str, value: Any) -> None:
        self.inner.write_json(key, value)
        if is_cacheable(key):
            self.cache.delete(key)

    def append_jsonl(self, key: str, value: Any) -> None:
        self.inner.append_jsonl(key, value)

    def read_jsonl(self, key: str) -> list[Any]:
        return self.inner.read_jsonl(key)

    def list_dir(self, key: str) -> list[str]:
        return self.inner.list_dir(key)

    def find_files(self, name: str, max_depth: int = 4) -> list[str]:
        return self.inner.find_files(name, max_depth)

    def update_json(
        self, key: str, update: Callable[[Any], Any], default: Any = None
    ) -> Any:
        return self.inner.update_json(key, update, default)

    def location(self, key: str) -> str:
        return self.inner.location(key)


def cached(inner: Store, enabled: bool | None = None) -> Store:
    """``inner`` wrapped in the disk cache, unless caching is switched off."""
    if not (cache_enabled() if enabled is None else enabled):
        return inner
    cache = DiskCache(cache_root(), namespace_of(inner.location("")), cache_max_bytes())
    return CachedStore(inner, cache)


@dataclass(frozen=True)
class WarmResult:
    fetched: int
    already_cached: int
    failed: int


def warm(
    store: CachedStore,
    run_key: str,
    threads: int = 16,
    progress: Callable[[int, int], None] | None = None,
) -> WarmResult:
    """Download every page of a run into the cache with many parallel connections."""
    keys = [
        f"{run_key}/pages/{name}"
        for name in store.list_dir(f"{run_key}/pages")
        if is_cacheable(f"pages/{name}")
    ]
    todo = [k for k in keys if not store.cache.has(k)]
    done = 0
    lock = threading.Lock()
    failed = 0

    def fetch(key: str) -> None:
        nonlocal done, failed
        try:
            store.read_text(key)
        except (
            FileNotFoundError
        ):  # listed but gone: count it; real errors (auth, network) propagate
            with lock:
                failed += 1
        with lock:
            done += 1
            if progress:
                progress(done, len(todo))

    with ThreadPoolExecutor(max_workers=threads) as pool:
        list(pool.map(fetch, todo))
    return WarmResult(len(todo) - failed, len(keys) - len(todo), failed)
