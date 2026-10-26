"""Storage for review-ui files.

Everything is addressed by a posix key relative to the storage root. LocalStore keeps
files on disk; AzureBlobStore (``azure_store.py``) keeps them in an Azure Blob
Storage container. ``open_store`` picks one from a root: a folder path, or an
``azure://https://<account>.blob.core.windows.net/<container>[/prefix]`` URI.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

# Folders never searched for crawl runs: tooling, and review-ui-index (the review index
# plus the shared rulesets and field template).
SKIP_DIRS = frozenset({".git", "node_modules", "review-ui-index", ".venv"})


class Store(Protocol):
    def read_text(self, key: str) -> str: ...
    def write_text(self, key: str, text: str) -> None: ...
    def read_json(self, key: str) -> Any: ...
    def write_json(self, key: str, value: Any) -> None: ...
    def append_jsonl(self, key: str, value: Any) -> None: ...
    def read_jsonl(self, key: str) -> list[Any]: ...
    def exists(self, key: str) -> bool: ...
    def list_dir(self, key: str) -> list[str]: ...

    def find_files(self, name: str, max_depth: int = 4) -> list[str]:
        """Keys of the folders (up to ``max_depth`` below the root) that directly contain a
        file called ``name``; folders that do are not searched further."""
        ...

    def update_json(
        self, key: str, update: Callable[[Any], Any], default: Any = None
    ) -> Any:
        """Atomically replace a JSON file with ``update(current)`` (``default`` if it does
        not exist yet), even with several writers. Returns the new value."""
        ...

    def location(self, key: str) -> str:
        """Where ``key`` really lives (a path or an azure:// URI), for messages."""
        ...


class LocalStore:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError(f"key escapes storage root: {key!r}")
        return path

    def read_text(self, key: str) -> str:
        return self._path(key).read_text(encoding="utf-8")

    def write_text(self, key: str, text: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename so a crash never leaves a half-written file.
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def read_json(self, key: str) -> Any:
        return json.loads(self.read_text(key))

    def write_json(self, key: str, value: Any) -> None:
        self.write_text(key, json.dumps(value, indent=2, ensure_ascii=False) + "\n")

    def append_jsonl(self, key: str, value: Any) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(value, ensure_ascii=False) + "\n"
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def read_jsonl(self, key: str) -> list[Any]:
        path = self._path(key)
        if not path.exists():
            return []
        with open(path, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def list_dir(self, key: str) -> list[str]:
        path = self._path(key)
        if not path.is_dir():
            return []
        return sorted(child.name for child in path.iterdir())

    def find_files(self, name: str, max_depth: int = 4) -> list[str]:
        found: list[str] = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            here = Path(dirpath).relative_to(self.root)
            if name in filenames:
                found.append(here.as_posix() if here.parts else "")
                dirnames[:] = []
            elif len(here.parts) >= max_depth:
                dirnames[:] = []
        return sorted(found)

    def update_json(
        self, key: str, update: Callable[[Any], Any], default: Any = None
    ) -> Any:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # A lock file makes the read-modify-write safe between processes (two apps
        # sharing one index file), not just between threads.
        with open(path.with_name(f".{path.name}.lock"), "a") as lock:
            try:
                import fcntl

                fcntl.flock(lock, fcntl.LOCK_EX)
            except ImportError:  # not POSIX: fall back to unlocked
                pass
            current = self.read_json(key) if path.exists() else default
            new = update(current)
            self.write_json(key, new)
            return new

    def location(self, key: str) -> str:
        return str(self._path(key))


def open_store(spec: Store | Path | str, cache: bool | None = None) -> Store:
    """A Store for a root: an existing Store is returned as is; an ``azure://`` URI opens
    Azure Blob Storage (needs the ``azure`` extra), fronted by the page cache unless
    ``cache`` is False or REVIEW_UI_CACHE=0; anything else is a local folder, never cached."""
    if isinstance(spec, (str, Path)):
        text = str(spec)
        if text.startswith("azure://"):
            from .azure_store import AzureBlobStore  # optional dependency
            from .cache import cached

            return cached(AzureBlobStore.from_uri(text), cache)
        return LocalStore(text)
    return spec
