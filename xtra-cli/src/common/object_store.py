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
        rows = self.provider.load_batch(
            keys=[self._load_key(key)], errors=errors
        )
        if not rows:
            rows = self.provider.load_batch(keys=[key], errors=errors)
        if not rows:
            raise FileNotFoundError(key)
        content = rows[0].content
        return (
            content if isinstance(content, bytes) else content.encode("utf-8")
        )

    def get_many(self, keys: list[str]) -> list[bytes]:
        """Several objects in one provider batch, in the order asked for."""
        if not keys:
            return []
        errors: list[str] = []
        load_key = {key: self._load_key(key) for key in keys}
        found = {
            row.key: row.content
            for row in self.provider.load_batch(
                keys=[load_key[key] for key in keys], errors=errors
            )
        }
        # Like get_bytes, a bare key is tried when the prefixed one is missing.
        retry = [
            key
            for key in keys
            if load_key[key] not in found and load_key[key] != key
        ]
        if retry:
            for row in self.provider.load_batch(keys=retry, errors=errors):
                found[row.key] = row.content
        contents: list[bytes] = []
        missing: list[str] = []
        for key in keys:
            content = found.get(load_key[key], found.get(key))
            if content is None:
                missing.append(key)
            elif isinstance(content, bytes):
                contents.append(content)
            else:
                contents.append(content.encode("utf-8"))
        if missing:
            detail = f" ({errors[0]})" if errors else ""
            raise FileNotFoundError(
                f"{len(missing)} of {len(keys)} objects could not be read, "
                f"first {missing[0]}{detail}"
            )
        return contents

    def delete(self, keys: list[str]) -> None:
        errors: list[str] = []
        self.writer.delete_batch(keys=keys, errors=errors)
        if errors:
            raise RuntimeError("; ".join(errors))

    def get_text(self, key: str) -> str:
        return self.get_bytes(key).decode("utf-8")

    def get_json(self, key: str) -> object:
        return json.loads(self.get_text(key))

    def exists(self, key: str) -> bool:
        """True when the object is stored, without downloading it.

        A crawl asks this once per frontier URL on resume, so reading the
        whole page to answer it was both slow and wrong: it turned a
        credential or network fault into "not saved yet" and refetched a
        page the run already had.
        """
        return bool(self.provider.exists(self._load_key(key)))

    def list_keys(self, under: str = "") -> list[str]:
        prefix = getattr(self.provider, "prefix_path", "") or ""
        needle = under.strip("/")
        start = self._load_key(needle) if needle else prefix
        out: list[str] = []
        for name in self.provider.iter_keys(name_starts_with=start):
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
