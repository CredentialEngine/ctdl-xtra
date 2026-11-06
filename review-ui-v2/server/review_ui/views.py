"""Read model over one extraction: what a reviewer sees for a page."""

from __future__ import annotations

from .merge import label_id
from .store import Store


class ExtractionView:
    def __init__(self, store: Store, run_key: str, extraction_id: str):
        self.store = store
        self.run_key = run_key
        self.extraction_id = extraction_id
        self.base = f"{run_key}/extractions/{extraction_id}"
        self._pages: dict[str, dict] | None = None
        self._records: dict[str, dict] = {}

    @property
    def pages(self) -> dict[str, dict]:
        if self._pages is None:
            self._pages = {
                row["stem"]: row
                for row in self.store.read_jsonl(f"{self.base}/pages.jsonl")
            }
        return self._pages

    def report(self) -> dict:
        return self.store.read_json(f"{self.base}/report.json")

    def ruleset(self) -> dict:
        return self.store.read_json(f"{self.base}/rules.json")

    def sample(self) -> list[dict]:
        key = f"{self.base}/sample.json"
        return self.store.read_json(key)["pages"] if self.store.exists(key) else []

    def record(self, record_id: str) -> dict:
        if record_id not in self._records:
            self._records[record_id] = self.store.read_json(
                f"{self.base}/records/{record_id}.json"
            )
        return self._records[record_id]

    def page(self, stem: str) -> dict:
        """Labels and the fields extracted *from this page*, grouped by record."""
        row = self.pages[stem]
        url = row["url"]
        records = []
        for rid in row["record_ids"]:
            record = self.record(rid)
            fields = [
                f for f in record["source_expected"]["fields"] if f["source_url"] == url
            ]
            if fields:
                records.append(
                    {
                        "record_id": rid,
                        "conflicts": record["conflicts"],
                        "source_urls": record["source_urls"],
                        "fields": fields,
                    }
                )
        return {
            "stem": stem,
            "url": url,
            "page_type": row["page_type"],
            "labels": [
                {
                    "key": label_id(url, entry["label"], entry["rule_id"]),
                    "label": entry["label"],
                    "rule_id": entry["rule_id"],
                }
                for entry in row["labels"]
            ],
            "records": records,
        }

    def item_keys(self, stems: list[str]) -> list[str]:
        """Keys of every reviewable item (labels and present/absent fields)."""
        keys: list[str] = []
        for stem in stems:
            view = self.page(stem)
            keys += [label["key"] for label in view["labels"]]
            keys += [
                f["field_id"] for record in view["records"] for f in record["fields"]
            ]
        return keys
