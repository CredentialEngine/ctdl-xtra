import type { DecideExtra } from "./components/ItemCard";
import type { FlagScope, NoteScope } from "./types";

export interface ItemRef {
  kind: "field" | "label";
  key: string;
  canonical_label: string;
  source_url: string;
  record_id?: string;
  rule_id?: string | null;
  value: string | null;
}

export interface FlagTarget {
  scope: FlagScope;
  key: string;
  stem: string;
  source_url: string;
  canonical_label?: string;
  record_id?: string;
}

export interface Actions {
  decide: (item: ItemRef, status: "accepted" | "rejected" | "pending", extra?: DecideExtra) => void;
  note: (scope: NoteScope, target: string | null, text: string, id?: string) => void;
  addMissing: (recordId: string, label: string, url: string, expected: string, note?: string) => void;
  addLabel: (url: string, label: string, note?: string) => void;
  flag: (target: FlagTarget, on: boolean, note?: string) => void;
}
