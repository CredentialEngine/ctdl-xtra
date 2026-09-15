"""Relative-key façade over ceops-style storage providers and writers."""

from __future__ import annotations

import json
from dataclasses import dataclass

from common.storage_provider_factory import create_storage_provider
from common.storage_writer_factory import create_storage_writer


@dataclass
class ObjectStore:
    provider: object
    writer: object

    def _load_key(self, key: str) -> str:
        prefix = getattr(self.provider, "prefix_path", "") or ""
        if prefix:
            return f"{prefix.rstrip('/')}/{key.lstrip('/')}"
        return key

    def put_bytes(
        self,
        key: str,
        data: bytes | str,
        content_type: str = "application/octet-stream",
    ) -> str:
        errors: list[str] = []
        uploaded = self.writer.upload_batch(
            key_contents={key: data},
            content_type=content_type,
            errors=errors,
        )
        if errors:
            raise RuntimeError("; ".join(errors))
        return uploaded[0] if uploaded else key

    def put_text(
        self,
        key: str,
        text: str,
        content_type: str = "text/plain; charset=utf-8",
    ) -> str:
        return self.put_bytes(key, text, content_type)

    def put_json(self, key: str, payload: object) -> str:
        body = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        return self.put_text(key, body, "application/json")

    def get_bytes(self, key: str) -> bytes:
        errors: list[str] = []
        rows = self.provider.load_batch(keys=[self._load_key(key)], errors=errors)
        if not rows:
            rows = self.provider.load_batch(keys=[key], errors=errors)
        if not rows:
            raise FileNotFoundError(key)
        content = rows[0].content
        return content if isinstance(content, bytes) else content.encode("utf-8")

    def get_text(self, key: str) -> str:
        return self.get_bytes(key).decode("utf-8")

    def get_json(self, key: str) -> object:
        return json.loads(self.get_text(key))

    def exists(self, key: str) -> bool:
        try:
            self.get_bytes(key)
            return True
        except FileNotFoundError:
            return False

    def list_keys(self, under: str = "") -> list[str]:
        prefix = getattr(self.provider, "prefix_path", "") or ""
        needle = under.strip("/")
        out: list[str] = []
        for name in self.provider.iter_keys():
            rel = name
            if prefix and (
                name == prefix or name.startswith(prefix.rstrip("/") + "/")
            ):
                rel = name[len(prefix.rstrip("/")) + 1 :]
            if needle and rel != needle and not rel.startswith(needle + "/"):
                continue
            out.append(rel)
        return sorted(out)

    def describe_location(self) -> str:
        return self.writer.describe_location()


def open_store(
    uri: str,
    *,
    azure_storage_connection_string: str | None = None,
    concurrency: int = 1,
) -> ObjectStore:
    writer = create_storage_writer(
        target_uri=uri,
        write_concurrency=concurrency,
        azure_storage_connection_string=azure_storage_connection_string,
    )
    provider = create_storage_provider(
        source_uri=uri,
        batch_size=100,
        read_concurrency=concurrency,
        azure_storage_connection_string=azure_storage_connection_string,
    )
    return ObjectStore(provider=provider, writer=writer)
