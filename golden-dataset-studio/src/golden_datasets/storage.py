"""Storage roots: a local folder or an Azure Blob prefix, behind one interface (spec §4.5, §10).

    root = open_root("/path/to/folder")
    root = open_root("azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output/zz-scratch-review-ui-v3")
    root = open_root("azure://http://127.0.0.1:10000/devstoreaccount1/container/prefix")   # Azurite

Paths are POSIX strings relative to the root, without a leading slash. The rules of spec §10 live here:

- nothing is found by listing at run time (`list` exists for `init` and `sync` only);
- immutable files are downloaded once into a disk cache (`local_path`), so their second read costs nothing;
- the annotation log is append-only and is read incrementally from a byte offset (`append`, `read_from`);
- small mutable files (the manifest) are written with optimistic concurrency (`write_bytes(if_match=etag)`).

Azure credentials come from `AZURE_STORAGE_CONNECTION_STRING` (or `UseDevelopmentStorage=true` for Azurite); when it
isn't set, from the signed-in Azure CLI (`az login`): `az storage account show-connection-string -n <account>`.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .errors import ConflictError, UserError

AZURITE_CONNECTION = (
    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)


APPEND_BLOCK = 4 * 1024 * 1024


def cache_home() -> Path:
    return Path(os.environ.get("GOLDEN_DATASETS_CACHE", Path.home() / ".cache" / "golden-datasets"))


@dataclass(frozen=True)
class Stat:
    etag: str
    size: int


def _clean(path: str) -> str:
    path = path.strip("/")
    if any(part in ("..", "") for part in path.split("/")) and path:
        raise ValueError(f"bad storage path: {path!r}")
    return path


class Root:
    """Interface shared by LocalRoot and AzureRoot."""

    uri: str

    # -- reads ------------------------------------------------------------------------------------------
    def read_bytes(self, path: str) -> bytes:
        raise NotImplementedError

    def read_text(self, path: str) -> str:
        return self.read_bytes(path).decode("utf-8")

    def read_json(self, path: str):
        return json.loads(self.read_bytes(path))

    def stat(self, path: str) -> Stat | None:
        raise NotImplementedError

    def exists(self, path: str) -> bool:
        return self.stat(path) is not None

    def read_from(self, path: str, offset: int) -> bytes:
        """Bytes from `offset` to the end (b"" if the file is missing or has nothing new)."""
        raise NotImplementedError

    def list(self, prefix: str) -> list[str]:
        """Every file below `prefix` (relative to the root). Setup commands only: never at run time."""
        raise NotImplementedError

    def list_dirs(self, prefix: str) -> list[str]:
        """Names of the immediate sub-folders of `prefix`. Setup commands only."""
        raise NotImplementedError

    def sizes(self, prefix: str) -> dict[str, int]:
        """{path: size} of every file below `prefix`, in one listing. Setup commands only."""
        return {p: self.stat(p).size for p in self.list(prefix)}

    def local_path(self, path: str, mutable: bool = False) -> Path:
        """A local file with this path's content. Immutable files are fetched once and cached on disk;
        mutable ones are revalidated by ETag."""
        raise NotImplementedError

    # -- writes -----------------------------------------------------------------------------------------
    def write_bytes(self, path: str, data: bytes, *, if_match: str | None = None,
                    if_none_match: bool = False) -> str:
        """Write and return the new ETag. `if_match`: only if the current ETag is this one.
        `if_none_match`: only if nothing exists yet (immutable files). Raises ConflictError otherwise."""
        raise NotImplementedError

    def write_text(self, path: str, text: str, **kw) -> str:
        return self.write_bytes(path, text.encode("utf-8"), **kw)

    def write_json(self, path: str, obj, **kw) -> str:
        return self.write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n", **kw)

    def write_file(self, path: str, local: Path, *, if_none_match: bool = False) -> str:
        return self.write_bytes(path, Path(local).read_bytes(), if_none_match=if_none_match)

    def append(self, path: str, data: bytes) -> int:
        """Append to an append-only file (created when missing). Returns the new size."""
        raise NotImplementedError

    def delete(self, path: str) -> None:
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.uri!r})"


# =====================================================================================================
# Local folder
# =====================================================================================================
class LocalRoot(Root):
    def __init__(self, folder: str | Path):
        self.base = Path(folder).expanduser().resolve()
        self.uri = str(self.base)

    def _p(self, path: str) -> Path:
        return self.base / _clean(path)

    @staticmethod
    def _etag(st: os.stat_result) -> str:
        return f"{st.st_mtime_ns:x}-{st.st_size:x}"

    def read_bytes(self, path: str) -> bytes:
        try:
            return self._p(path).read_bytes()
        except FileNotFoundError:
            raise FileNotFoundError(f"{self.uri}/{path}") from None

    def stat(self, path: str) -> Stat | None:
        try:
            st = self._p(path).stat()
        except FileNotFoundError:
            return None
        return Stat(self._etag(st), st.st_size) if not self._p(path).is_dir() else None

    def read_from(self, path: str, offset: int) -> bytes:
        try:
            with open(self._p(path), "rb") as fh:
                fh.seek(offset)
                return fh.read()
        except FileNotFoundError:
            return b""

    def list(self, prefix: str) -> list[str]:
        start = self._p(prefix) if prefix else self.base
        if not start.exists():
            return []
        out = []
        for dirpath, _dirs, files in os.walk(start, followlinks=True):
            for name in files:
                if name.startswith("."):  # lock and temp files
                    continue
                out.append(str((Path(dirpath) / name).relative_to(self.base)))
        return sorted(out)

    def list_dirs(self, prefix: str) -> list[str]:
        start = self._p(prefix) if prefix else self.base
        return sorted(p.name for p in start.iterdir() if p.is_dir()) if start.is_dir() else []

    def local_path(self, path: str, mutable: bool = False) -> Path:
        p = self._p(path)
        if not p.exists():
            raise FileNotFoundError(f"{self.uri}/{path}")
        return p

    @contextlib.contextmanager
    def _lock(self, p: Path):
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p.parent / f".{p.name}.lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lk, fcntl.LOCK_UN)

    def write_bytes(self, path: str, data: bytes, *, if_match: str | None = None,
                    if_none_match: bool = False) -> str:
        p = self._p(path)
        with self._lock(p):
            current = self.stat(path)
            if if_none_match and current is not None:
                raise ConflictError(f"{path} already exists")
            if if_match is not None and (current is None or current.etag != if_match):
                raise ConflictError(f"{path} changed since it was read")
            fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.")
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, p)
            return self._etag(p.stat())

    def write_file(self, path: str, local: Path, *, if_none_match: bool = False) -> str:
        p = self._p(path)
        with self._lock(p):
            if if_none_match and p.exists():
                raise ConflictError(f"{path} already exists")
            fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.")
            os.close(fd)
            shutil.copyfile(local, tmp)
            os.replace(tmp, p)
            return self._etag(p.stat())

    def append(self, path: str, data: bytes) -> int:
        p = self._p(path)
        with self._lock(p):
            with open(p, "ab") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
                return fh.tell()

    def delete(self, path: str) -> None:
        with contextlib.suppress(FileNotFoundError):
            self._p(path).unlink()

    def symlink(self, path: str, target: Path) -> None:
        """Local → local `sync --pages link`: the crawl stays where xtra-cli put it."""
        p = self._p(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.is_symlink() or p.exists():
            return
        p.symlink_to(target)


# =====================================================================================================
# Azure Blob prefix
# =====================================================================================================
_AZ_CONN: dict[str, str] = {}


def _az_connection_string(account: str) -> str:
    """The account's connection string from the signed-in Azure CLI, once per process (never printed or saved)."""
    if account not in _AZ_CONN:
        cmd = ["az", "storage", "account", "show-connection-string", "-n", account,
               "--query", "connectionString", "-o", "tsv"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except FileNotFoundError:
            raise UserError("AZURE_STORAGE_CONNECTION_STRING is not set and the Azure CLI (`az`) is not installed: "
                            "install it (https://aka.ms/InstallAzureCLI) and run `az login`") from None
        if r.returncode != 0 or not r.stdout.strip():
            why = (r.stderr.strip().splitlines() or ["no output"])[-1]
            raise UserError(f"AZURE_STORAGE_CONNECTION_STRING is not set and `az` couldn't read the key of storage "
                            f"account {account!r} ({why}). Run `az login` with an account that can read it.")
        _AZ_CONN[account] = r.stdout.strip()
    return _AZ_CONN[account]


class AzureRoot(Root):
    def __init__(self, uri: str):
        from azure.storage.blob import BlobServiceClient

        self.uri = uri.rstrip("/")
        url = urlparse(uri[len("azure://"):])
        parts = [p for p in url.path.split("/") if p]
        if url.hostname in ("127.0.0.1", "localhost"):  # Azurite: /<account>/<container>/<prefix>
            account, parts = parts[0], parts[1:]
            conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING") or AZURITE_CONNECTION
            if "devstoreaccount1" not in conn and account == "devstoreaccount1":
                conn = AZURITE_CONNECTION
        else:
            account = url.hostname.split(".")[0]
            conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING") or _az_connection_string(account)
        if not parts:
            raise UserError(f"{uri}: no container in the URI")
        self.account = account
        self.container_name, self.prefix = parts[0], "/".join(parts[1:])
        self.service = BlobServiceClient.from_connection_string(conn)
        self.container = self.service.get_container_client(self.container_name)
        self.cache = cache_home() / hashlib.sha256(self.uri.encode()).hexdigest()[:16]
        self._dl_locks: dict[str, threading.Lock] = {}
        self._dl_guard = threading.Lock()

    def _name(self, path: str) -> str:
        path = _clean(path)
        return f"{self.prefix}/{path}" if self.prefix else path

    def _blob(self, path: str):
        return self.container.get_blob_client(self._name(path))

    def read_bytes(self, path: str) -> bytes:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self._blob(path).download_blob(max_concurrency=4).readall()
        except ResourceNotFoundError:
            raise FileNotFoundError(f"{self.uri}/{path}") from None

    def stat(self, path: str) -> Stat | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            props = self._blob(path).get_blob_properties()
        except ResourceNotFoundError:
            return None
        return Stat(props.etag, props.size)

    def read_from(self, path: str, offset: int) -> bytes:
        from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

        try:
            return self._blob(path).download_blob(offset=offset).readall()
        except ResourceNotFoundError:
            return b""
        except HttpResponseError as exc:  # 416: offset at (or past) the end
            if exc.status_code == 416:
                return b""
            raise

    def list(self, prefix: str) -> list[str]:
        start = self._name(prefix) if prefix else self.prefix
        start = (start.rstrip("/") + "/") if start else ""
        cut = len(self.prefix) + 1 if self.prefix else 0
        return sorted(b.name[cut:] for b in self.container.list_blobs(name_starts_with=start))

    def list_dirs(self, prefix: str) -> list[str]:
        start = self._name(prefix) if prefix else self.prefix
        start = (start.rstrip("/") + "/") if start else ""
        return sorted(item.name[len(start):].rstrip("/") for item in self.container.walk_blobs(start, delimiter="/")
                      if item.name.endswith("/"))

    def sizes(self, prefix: str) -> dict[str, int]:
        start = self._name(prefix) if prefix else self.prefix
        start = (start.rstrip("/") + "/") if start else ""
        cut = len(self.prefix) + 1 if self.prefix else 0
        return {b.name[cut:]: b.size for b in self.container.list_blobs(name_starts_with=start)}

    def local_path(self, path: str, mutable: bool = False) -> Path:
        dest = self.cache / _clean(path)
        etag_file = dest.with_name(dest.name + ".etag")
        with self._dl_guard:
            lock = self._dl_locks.setdefault(path, threading.Lock())
        with lock:
            if dest.exists() and not mutable:
                return dest
            if dest.exists() and mutable:
                st = self.stat(path)
                if st is None:
                    raise FileNotFoundError(f"{self.uri}/{path}")
                if etag_file.exists() and etag_file.read_text() == st.etag:
                    return dest
            from azure.core.exceptions import ResourceNotFoundError

            dest.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.")
            try:
                with os.fdopen(fd, "wb") as fh:
                    downloader = self._blob(path).download_blob(max_concurrency=4)
                    downloader.readinto(fh)
                os.replace(tmp, dest)
            except ResourceNotFoundError:
                os.unlink(tmp)
                raise FileNotFoundError(f"{self.uri}/{path}") from None
            etag_file.write_text(downloader.properties.etag)
            return dest

    def write_bytes(self, path: str, data: bytes, *, if_match: str | None = None,
                    if_none_match: bool = False) -> str:
        from azure.core import MatchConditions
        from azure.core.exceptions import ResourceExistsError, ResourceModifiedError
        from azure.storage.blob import ContentSettings

        kw: dict = {"overwrite": True, "content_settings": ContentSettings(content_type=_content_type(path))}
        if if_none_match:
            kw.update(overwrite=False)
        elif if_match is not None:
            kw.update(etag=if_match, match_condition=MatchConditions.IfNotModified)
        try:
            resp = self._blob(path).upload_blob(data, **kw)
        except (ResourceExistsError, ResourceModifiedError) as exc:
            raise ConflictError(f"{path}: {type(exc).__name__}") from None
        except Exception as exc:  # if_match on a missing blob → 404 / 412
            if getattr(exc, "status_code", None) in (404, 409, 412):
                raise ConflictError(f"{path}: {exc}") from None
            raise
        return resp["etag"]

    def write_file(self, path: str, local: Path, *, if_none_match: bool = False) -> str:
        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import ContentSettings

        with open(local, "rb") as fh:
            try:
                resp = self._blob(path).upload_blob(
                    fh, overwrite=not if_none_match, max_concurrency=4,
                    content_settings=ContentSettings(content_type=_content_type(path)))
            except ResourceExistsError:
                raise ConflictError(f"{path} already exists") from None
        return resp["etag"]

    def append(self, path: str, data: bytes) -> int:
        size = 0
        for i in range(0, max(len(data), 1), APPEND_BLOCK):  # an append block holds at most 4 MiB
            size = self._append_block(path, data[i:i + APPEND_BLOCK])
        return size

    def _append_block(self, path: str, data: bytes) -> int:
        from azure.core.exceptions import HttpResponseError, ResourceExistsError, ResourceNotFoundError

        blob = self._blob(path)
        try:
            resp = blob.append_block(data)
        except ResourceNotFoundError:
            with contextlib.suppress(ResourceExistsError):
                blob.create_append_blob(if_none_match="*")
            resp = blob.append_block(data)
        except HttpResponseError as exc:
            if "InvalidBlobType" not in str(exc):
                raise
            # A block blob (e.g. copied by a tool that doesn't know about append blobs): convert it once.
            old = blob.download_blob().readall()
            etag = blob.get_blob_properties().etag
            from azure.core import MatchConditions

            blob.delete_blob(etag=etag, match_condition=MatchConditions.IfNotModified)
            blob.create_append_blob()
            if old:
                blob.append_block(old)
            resp = blob.append_block(data)
        return int(resp["blob_append_offset"]) + len(data)

    def delete(self, path: str) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        with contextlib.suppress(ResourceNotFoundError):
            self._blob(path).delete_blob()

    def blob_url_with_sas(self, path: str, hours: int = 2) -> str:
        """A read-only URL for server-side copies between containers of the same account."""
        from datetime import UTC, datetime, timedelta

        from azure.storage.blob import BlobSasPermissions, generate_blob_sas

        cred = self.service.credential
        sas = generate_blob_sas(
            account_name=cred.account_name, container_name=self.container_name, blob_name=self._name(path),
            account_key=cred.account_key, permission=BlobSasPermissions(read=True),
            expiry=datetime.now(UTC) + timedelta(hours=hours))
        return f"{self._blob(path).url}?{sas}"

    def copy_from_url(self, path: str, url: str) -> None:
        """Server-side copy (no download, no upload)."""
        self._blob(path).upload_blob_from_url(url, overwrite=True)


def _content_type(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    return {"json": "application/json", "jsonl": "application/x-ndjson", "html": "text/html; charset=utf-8",
            "parquet": "application/vnd.apache.parquet", "css": "text/css", "md": "text/markdown"}.get(
        ext, "application/octet-stream")


def open_root(uri: str | Path | Root) -> Root:
    if isinstance(uri, Root):
        return uri
    uri = str(uri)
    if uri.startswith("azure://"):
        return AzureRoot(uri)
    return LocalRoot(uri)
