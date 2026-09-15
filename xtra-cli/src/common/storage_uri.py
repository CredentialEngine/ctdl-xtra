from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class ParsedFileStorageUri:
    local_path: str


@dataclass(frozen=True)
class ParsedAzureStorageUri:
    container_name: str
    prefix_path: str


def _non_empty_path_segments(path: str) -> list[str]:
    return [unquote(segment) for segment in path.split("/") if segment]


def parse_file_storage_uri(uri: str) -> ParsedFileStorageUri:
    parsed = urlparse(uri)

    if parsed.scheme != "file":
        raise ValueError(f"Expected file:// URI: {uri}")

    if parsed.netloc:
        raise ValueError(f"file URI must use file:///absolute/path form: {uri}")

    local_path = unquote(parsed.path)

    if not local_path:
        raise ValueError(f"file URI must include an absolute path: {uri}")

    if (
        local_path.startswith("/")
        and len(local_path) > 3
        and local_path[2] == ":"
        and local_path[1].isalpha()
    ):
        local_path = local_path[1:]

    return ParsedFileStorageUri(local_path=local_path)


def _parse_wrapped_http_url(uri: str, scheme: str):
    prefix = f"{scheme}://"

    if not uri.lower().startswith(prefix):
        raise ValueError(f"Expected {scheme}:// URI: {uri}")

    inner_url = uri[len(prefix) :]
    parsed = urlparse(inner_url)

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(
            f"{scheme} URI must wrap a full http(s) URL, for example "
            f"{scheme}://https://host/container/path: {uri}"
        )

    return parsed


def parse_azure_storage_uri(uri: str) -> ParsedAzureStorageUri:
    """Parse ceops-style azure://https://... or Azurite azure://http://127.0.0.1:10000/... URIs."""
    parsed = _parse_wrapped_http_url(uri, "azure")
    segments = _non_empty_path_segments(parsed.path)

    host = (parsed.hostname or "").lower()
    is_local_emulator = host in {"localhost", "127.0.0.1", "::1"}

    if is_local_emulator:
        if len(segments) < 2:
            raise ValueError(
                "Azurite azure URI must be "
                "azure://http://127.0.0.1:10000/<account>/<container>/<path>"
            )
        container_name = segments[1]
        prefix_segments = segments[2:]
    else:
        if not segments:
            raise ValueError(
                "Azure URI must be "
                "azure://https://<account>.blob.core.windows.net/<container>/<path>"
            )
        container_name = segments[0]
        prefix_segments = segments[1:]

    if not container_name:
        raise ValueError(f"Azure URI must include a container name: {uri}")

    return ParsedAzureStorageUri(
        container_name=container_name,
        prefix_path="/".join(prefix_segments),
    )


def parse_local_path_if_supported(uri: str) -> str | None:
    parsed = urlparse(uri)
    scheme = (parsed.scheme or "").lower()
    if scheme in {"s3", "azure", "file", "http", "https"}:
        return None
    if len(scheme) == 1 and scheme.isalpha():
        return str(Path(uri).expanduser())
    path = Path(uri).expanduser()
    return str(path)


def join_storage_uri(base: str, *parts: str) -> str:
    extra = "/".join(part.strip("/") for part in parts if part)
    if not extra:
        return base
    return base.rstrip("/") + "/" + extra
