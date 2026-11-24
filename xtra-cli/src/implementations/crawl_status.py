from __future__ import annotations

import csv
import io
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

from common.keys import (
    PAGES_FAILED,
    PAGES_SKIPPED,
    crawl_key,
    manifest_key,
    pages_prefix,
)

GROUP_SAVED = "saved"
GROUP_FAILED = "failed"
GROUP_SKIPPED = "skipped"
GROUPS = (GROUP_SAVED, GROUP_FAILED, GROUP_SKIPPED)

COLUMNS = ("result", "http_status", "attempts", "bytes", "at", "url", "detail")
ERROR_WIDTH = 60
READ_BATCH = 100


@dataclass(frozen=True)
class RunFiles:
    by_group: dict[str, list[str]]

    def counts(self) -> dict[str, int]:
        return {
            group: len(keys)
            for group, keys in sorted(self.by_group.items())
            if keys
        }

    def total(self) -> int:
        return sum(len(keys) for keys in self.by_group.values())


def list_run_files(store: Any, catalog_folder: str, run_id: str) -> RunFiles:
    prefix = pages_prefix(catalog_folder, run_id)
    by_group: dict[str, list[str]] = {group: [] for group in GROUPS}
    folders = {PAGES_FAILED: GROUP_FAILED, PAGES_SKIPPED: GROUP_SKIPPED}
    for key in store.list_keys(under=prefix):
        if not key.endswith(".meta.json"):
            continue
        parts = key[len(prefix) + 1 :].split("/")
        if len(parts) == 1:
            by_group[GROUP_SAVED].append(key)
        elif len(parts) == 2 and parts[0] in folders:
            by_group[folders[parts[0]]].append(key)
    return RunFiles(by_group=by_group)


def read_report(
    store: Any, catalog_folder: str, run_id: str
) -> dict[str, Any] | None:
    key = crawl_key(catalog_folder, run_id)
    if not store.exists(key):
        return None
    try:
        loaded = store.get_json(key)
    except ValueError:
        return None
    return loaded if isinstance(loaded, dict) else None


def run_started(store: Any, catalog_folder: str, run_id: str) -> bool:
    return bool(store.exists(manifest_key(catalog_folder, run_id)))


def totals_line(
    files: RunFiles, report: dict[str, Any] | None, *, started: bool = False
) -> str:
    parts = [f"{group}={count}" for group, count in files.counts().items()]
    parts.append(f"urls={files.total()}")
    if report is None:
        if started or files.total():
            parts.append("run=running (crawl.json is written when it ends)")
        else:
            parts.append("run=unknown (no such run yet)")
        return "TOTAL " + " ".join(parts)
    if report.get("pages_copied") is not None:
        parts.append(f"copied={report.get('pages_copied')}")
        parts.append(f"fetched={report.get('pages_fetched')}")
    if report.get("from_run_id"):
        parts.append(f"from_run={report.get('from_run_id')}")
    parts.append(f"run={report.get('status')}")
    parts.append(f"frontier_remaining={report.get('frontier_remaining')}")
    parts.append(f"updated_at={report.get('updated_at')}")
    return "TOTAL " + " ".join(parts)


@dataclass(frozen=True)
class StatusRow:
    result: str
    url: str
    http_status: int | None
    attempts: int | None
    bytes: int | None
    at: str
    detail: str

    @classmethod
    def from_meta(cls, group: str, meta: dict[str, Any]) -> StatusRow:
        if group == GROUP_SAVED:
            copied = meta.get("copied_from_run")
            return cls(
                result=GROUP_SAVED,
                url=str(meta.get("requested_url") or ""),
                http_status=meta.get("http_status"),
                attempts=meta.get("attempts"),
                bytes=meta.get("bytes"),
                at=str(meta.get("retrieved_at") or ""),
                detail=f"copied from {copied}" if copied else "",
            )
        if group == GROUP_SKIPPED:
            reason = str(meta.get("reason") or "")
            detail = reason
            if meta.get("final_url"):
                detail = f"{reason} -> {meta['final_url']}".strip()
            return cls(
                result=f"skipped-{reason}" if reason else GROUP_SKIPPED,
                url=str(meta.get("url") or ""),
                http_status=meta.get("http_status"),
                attempts=None,
                bytes=None,
                at=str(meta.get("at") or ""),
                detail=detail,
            )
        return cls(
            result=str(meta.get("result") or GROUP_FAILED),
            url=str(meta.get("url") or ""),
            http_status=meta.get("http_status"),
            attempts=meta.get("attempts"),
            bytes=None,
            at=str(meta.get("at") or ""),
            detail=str(meta.get("error") or ""),
        )

    def cells(self) -> list[str]:
        return [
            self.result,
            "" if self.http_status is None else str(self.http_status),
            "" if self.attempts is None else str(self.attempts),
            "" if self.bytes is None else str(self.bytes),
            self.at,
            self.url,
            self.detail,
        ]


def read_rows(store: Any, files: RunFiles, groups: set[str]) -> list[StatusRow]:
    rows: list[StatusRow] = []
    for group in GROUPS:
        if groups and group not in groups:
            continue
        keys = sorted(files.by_group.get(group, []))
        for start in range(0, len(keys), READ_BATCH):
            for body in store.get_many(keys[start : start + READ_BATCH]):
                try:
                    meta = json.loads(body.decode("utf-8"))
                except ValueError:
                    continue
                if isinstance(meta, dict):
                    rows.append(StatusRow.from_meta(group, meta))
    rows.sort(key=lambda row: (row.at, row.url))
    return rows


def row_counts(rows: list[StatusRow]) -> dict[str, int]:
    return dict(sorted(Counter(row.result for row in rows).items()))


def render_table(rows: list[StatusRow]) -> str:
    header = [name.upper() for name in COLUMNS]
    body = []
    for row in rows:
        cells = row.cells()
        if len(cells[-1]) > ERROR_WIDTH:
            cells[-1] = cells[-1][: ERROR_WIDTH - 3] + "..."
        body.append(cells)
    widths = [
        max(len(cells[i]) for cells in [header, *body])
        for i in range(len(header))
    ]
    lines = [
        "  ".join(
            cell.ljust(width) for cell, width in zip(cells, widths, strict=True)
        ).rstrip()
        for cells in [header, *body]
    ]
    return "\n".join(lines)


def render_csv(rows: list[StatusRow]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow(row.cells())
    return out.getvalue()
