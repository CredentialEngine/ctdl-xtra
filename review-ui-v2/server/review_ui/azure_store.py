"""Azure Blob Storage backend for the Store interface (needs the ``azure`` extra).

Root form, the same as ``xtra-cli``'s:

    azure://https://<account>.blob.core.windows.net/<container>[/<prefix>]
    azure://http://127.0.0.1:10000/devstoreaccount1/<container>[/<prefix>]   (Azurite)

Credentials: ``AZURE_STORAGE_CONNECTION_STRING`` if set, else Azurite's well-known
development account for a local emulator, else ``DefaultAzureCredential`` (a managed
identity in Azure, ``az login`` on a laptop). No secret is ever stored in the app.
"""

from __future__ import annotations

import json
import os
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse

from azure.core import MatchConditions
from azure.core.exceptions import (
    AzureError,
    ClientAuthenticationError,
    HttpResponseError,
    ResourceExistsError,
    ResourceModifiedError,
    ResourceNotFoundError,
)
from azure.storage.blob import ContainerClient, ContentSettings

from .store import SKIP_DIRS

_APPEND_BLOCK = 4 * 1024 * 1024  # an Append Block holds at most 4 MiB

CONNECTION_STRING_ENV = "AZURE_STORAGE_CONNECTION_STRING"
# Azurite's published development account; not a secret.
_AZURITE_KEY = "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="


def azurite_connection_string(
    blob_endpoint: str = "http://127.0.0.1:10000/devstoreaccount1",
) -> str:
    """Azurite's development account, pointed at wherever the emulator is reachable."""
    return (
        "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
        f"AccountKey={_AZURITE_KEY};BlobEndpoint={blob_endpoint};"
    )


AZURITE_CONNECTION_STRING = azurite_connection_string()
_EMULATOR_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "host.containers.internal",
    "host.docker.internal",
    "azurite",
}
_UPDATE_ATTEMPTS = 12


@dataclass(frozen=True)
class AzureUri:
    account_url: str
    container: str
    prefix: str  # "" or "a/b/" (always ends with a slash when set)
    emulator: bool


def parse_azure_uri(uri: str) -> AzureUri:
    if not uri.lower().startswith("azure://"):
        raise ValueError(f"Expected azure:// URI: {uri}")
    parsed = urlparse(uri[len("azure://") :])
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(
            "azure URI must wrap a full http(s) URL, for example "
            f"azure://https://<account>.blob.core.windows.net/<container>: {uri}"
        )
    segments = [unquote(s) for s in parsed.path.split("/") if s]
    emulator = (parsed.hostname or "").lower() in _EMULATOR_HOSTS
    account_path = ""
    if emulator:  # the account name is the first path segment, not part of the host
        if len(segments) < 2:
            raise ValueError(
                "emulator URI must be azure://http://127.0.0.1:10000/<account>/<container>"
                f"[/<prefix>]: {uri}"
            )
        account_path, segments = "/" + segments[0], segments[1:]
    if not segments:
        raise ValueError(f"azure URI must name a container: {uri}")
    prefix = "/".join(segments[1:])
    return AzureUri(
        account_url=f"{parsed.scheme}://{parsed.netloc}{account_path}",
        container=segments[0],
        prefix=f"{prefix}/" if prefix else "",
        emulator=emulator,
    )


def _create_emulator_container(connection: str, name: str) -> None:
    """Azurite starts empty, so create the container if it is missing. Only ever for an
    emulator URI, never real Azure; failure (emulator not up yet) is ignored, because a
    real request will say so more clearly."""
    try:
        ContainerClient.from_connection_string(
            connection, name, retry_total=0, connection_timeout=1
        ).create_container()
    except ResourceExistsError:
        pass
    except AzureError:
        pass


def _content_type(key: str) -> str:
    return "application/json" if key.endswith((".json", ".jsonl")) else "text/plain"


class AzureBlobStore:
    def __init__(
        self, container: ContainerClient, prefix: str = "", base_uri: str = ""
    ):
        self._container = container
        self._prefix = prefix
        self._base_uri = base_uri.rstrip("/")

    @classmethod
    def from_uri(cls, uri: str) -> AzureBlobStore:
        parsed = parse_azure_uri(uri)
        connection = os.environ.get(CONNECTION_STRING_ENV) or (
            azurite_connection_string(parsed.account_url) if parsed.emulator else None
        )
        if connection:
            container = ContainerClient.from_connection_string(
                connection, parsed.container
            )
        else:
            from azure.identity import DefaultAzureCredential

            container = ContainerClient(
                parsed.account_url,
                parsed.container,
                credential=DefaultAzureCredential(),
            )
        if parsed.emulator and connection:
            _create_emulator_container(connection, parsed.container)
        base = f"{parsed.account_url}/{parsed.container}/{parsed.prefix}"
        return cls(container, parsed.prefix, base)

    # -- helpers ------------------------------------------------------------
    def _name(self, key: str) -> str:
        if ".." in key.split("/") or key.startswith("/"):
            raise ValueError(f"key escapes storage root: {key!r}")
        return f"{self._prefix}{key}"

    def _download(self, key: str) -> bytes:
        try:
            return self._container.download_blob(self._name(key)).readall()
        except ResourceNotFoundError as exc:
            raise FileNotFoundError(key) from exc

    def _settings(self, key: str) -> ContentSettings:
        return ContentSettings(content_type=_content_type(key))

    # -- Store --------------------------------------------------------------
    def read_text(self, key: str) -> str:
        return self._download(key).decode("utf-8")

    def write_text(self, key: str, text: str) -> None:
        # A blob upload replaces the whole blob atomically; readers never see half a file.
        self._container.upload_blob(
            self._name(key),
            text.encode("utf-8"),
            overwrite=True,
            content_settings=self._settings(key),
        )

    def read_json(self, key: str) -> Any:
        return json.loads(self.read_text(key))

    def write_json(self, key: str, value: Any) -> None:
        self.write_text(key, json.dumps(value, indent=2, ensure_ascii=False) + "\n")

    def append_jsonl(self, key: str, value: Any) -> None:
        """One Append Block per event: atomic, and concurrent appenders never clobber."""
        blob = self._container.get_blob_client(self._name(key))
        data = (json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            blob.append_block(data)
        except ResourceNotFoundError:
            try:  # create only if missing, so a racing writer's events are never wiped
                blob.create_append_blob(
                    content_settings=self._settings(key),
                    match_condition=MatchConditions.IfMissing,
                )
            except ResourceExistsError:
                pass
            blob.append_block(data)
        except HttpResponseError as exc:
            if getattr(exc, "error_code", None) != "InvalidBlobType":
                raise
            self._convert_to_append_blob(key)  # an uploaded copy is a block blob
            blob.append_block(data)

    def _convert_to_append_blob(self, key: str) -> None:
        """Turn a block blob (what az/azcopy/portal uploads create) into an append blob with
        the same content. Azure cannot change a blob's type in place, so the block blob is
        deleted and recreated; the delete only happens if the blob has not changed since it
        was read, so no write is lost. If another process converted it first this does
        nothing."""
        blob = self._container.get_blob_client(self._name(key))
        downloader = blob.download_blob()
        etag, content = downloader.properties.etag, downloader.readall()
        try:
            blob.delete_blob(etag=etag, match_condition=MatchConditions.IfNotModified)
        except (ResourceModifiedError, ResourceNotFoundError):
            return  # someone else changed or converted it first
        try:
            blob.create_append_blob(
                content_settings=self._settings(key),
                match_condition=MatchConditions.IfMissing,
            )
        except ResourceExistsError:
            pass  # a racing appender already recreated it
        for start in range(0, len(content), _APPEND_BLOCK):
            blob.append_block(content[start : start + _APPEND_BLOCK])

    def read_jsonl(self, key: str) -> list[Any]:
        try:
            text = self._download(key).decode("utf-8")
        except FileNotFoundError:
            return []
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def exists(self, key: str) -> bool:
        return self._container.get_blob_client(self._name(key)).exists()

    def list_dir(self, key: str) -> list[str]:
        prefix = self._name(key + "/") if key else self._prefix
        names = {
            item.name[len(prefix) :].rstrip("/")
            for item in self._container.walk_blobs(
                name_starts_with=prefix or None, delimiter="/"
            )
        }
        return sorted(n for n in names if n)

    def find_files(self, name: str, max_depth: int = 4) -> list[str]:
        """Breadth-first by folder level. A delimiter listing returns a sub-folder as a
        single prefix, so a run's thousands of page blobs are never enumerated."""
        found: list[str] = []
        level = [""]
        for depth in range(max_depth + 1):
            next_level: list[str] = []
            for folder in level:
                prefix = self._name(f"{folder}/") if folder else self._prefix
                subfolders: list[str] = []
                files: set[str] = set()
                for item in self._container.walk_blobs(
                    name_starts_with=prefix or None, delimiter="/"
                ):
                    relative = item.name[len(prefix) :]
                    if relative.endswith("/"):
                        subfolders.append(relative.rstrip("/"))
                    else:
                        files.add(relative)
                if name in files:
                    found.append(folder)
                elif depth < max_depth:
                    next_level += [
                        f"{folder}/{d}" if folder else d
                        for d in subfolders
                        if d not in SKIP_DIRS
                    ]
            level = next_level
        return sorted(found)

    def update_json(
        self, key: str, update: Callable[[Any], Any], default: Any = None
    ) -> Any:
        """Read, change, write back only if nobody else wrote in between (ETag), else retry."""
        blob = self._container.get_blob_client(self._name(key))
        for attempt in range(_UPDATE_ATTEMPTS):
            try:
                download = blob.download_blob()
                etag, current = download.properties.etag, json.loads(download.readall())
            except ResourceNotFoundError:
                etag, current = None, default
            new = update(current)
            data = (json.dumps(new, indent=2, ensure_ascii=False) + "\n").encode(
                "utf-8"
            )
            try:
                if etag:
                    blob.upload_blob(
                        data,
                        overwrite=True,
                        etag=etag,
                        match_condition=MatchConditions.IfNotModified,
                        content_settings=self._settings(key),
                    )
                else:  # it did not exist: create it only if still missing
                    blob.upload_blob(
                        data, overwrite=False, content_settings=self._settings(key)
                    )
                return new
            except (ResourceModifiedError, ResourceExistsError):
                time.sleep(random.uniform(0.005, 0.05) * (attempt + 1))
        raise RuntimeError(f"could not update {key!r}: too many concurrent writers")

    def location(self, key: str) -> str:
        return f"azure://{self._base_uri}/{key}"


def explain_azure_error(exc: Exception, root: str = "") -> str | None:
    """A plain-language message for the Azure errors people actually hit (no role, wrong
    sign-in, firewall, wrong container), or None for anything else."""
    where = f" ({root})" if root else ""
    code = getattr(exc, "error_code", None) or ""
    status = getattr(exc, "status_code", None)
    request_id = ""
    response = getattr(exc, "response", None)
    if response is not None:
        rid = response.headers.get("x-ms-request-id")
        request_id = f"\nAzure request id for an administrator: {rid}" if rid else ""

    if isinstance(exc, ClientAuthenticationError) or "DefaultAzureCredential" in str(
        exc
    ):
        return (
            f"Not signed in to Azure{where}. Run `az login` (or set "
            f"{CONNECTION_STRING_ENV}), then try again."
        )
    if not isinstance(exc, HttpResponseError):
        return None
    if code == "AuthorizationPermissionMismatch":
        return (
            f"Azure refused access{where}: you are signed in, but your account has no "
            "blob data role there (AuthorizationPermissionMismatch).\n"
            "  - Ask an administrator for 'Storage Blob Data Contributor' (read and write) "
            "or 'Storage Blob Data Reader' (read only) on the container or storage account. "
            "Roles like Owner or Contributor on the subscription do not include blob data.\n"
            "  - Or, if your team uses the account key, set "
            f"{CONNECTION_STRING_ENV} (the app prefers it over your sign-in).\n"
            "  - Check you are on the right account: `az account show`." + request_id
        )
    if code in ("AuthorizationFailure", "AuthorizationFailureOrFirewall") or (
        status == 403 and "firewall" in str(exc).lower()
    ):
        return (
            f"Azure blocked the request{where}. The storage account's firewall or private "
            "endpoint probably does not allow this machine: connect to the VPN, or ask for "
            "your IP to be allowed." + request_id
        )
    if code in ("AuthenticationFailed", "InvalidAuthenticationInfo") or status == 401:
        return (
            f"Azure did not accept your credentials{where}. Run `az login` again (an "
            f"expired sign-in or a wrong {CONNECTION_STRING_ENV} causes this)."
            + request_id
        )
    if (
        code in ("ContainerNotFound", "AccountNotFound", "ResourceNotFound")
        and status == 404
    ):
        return (
            f"Azure could not find the container or account{where}. Check the root: "
            "azure://https://<account>.blob.core.windows.net/<container>[/prefix]."
            + request_id
        )
    return None
