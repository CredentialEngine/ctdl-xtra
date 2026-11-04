// sme-fixes §5 and §6: what a row's value says when the rule found none, the "Why wrong?" flags, and the
// list-of-objects helpers (Estimated Duration). Kept out of logic.ts so the Rules and Records tabs share it.
import type { CapturedSelection } from "../pagepane";
import type { EventBrief, NewEvent, ObjectField, RowItem } from "../api/types";

/** A rule ends one of three ways on a course (§6): a value; its claim "not on the page" (`absent`); or nothing found,
 * which claims nothing. A property with no rule yet says so. */
export function statusWords(status: string, value: string | null): string {
  if (status === "found") return value ?? "";
  if (status === "absent") return "Not on the page (rule's claim)";
  if (status === "none") return "no rule yet";
  return "Nothing found · the rule made no claim; check the page";
}

/** The page pane's banner line for a row with no value. */
export function statusHint(status: string): string {
  if (status === "absent") return "the rule looked in the dashed box and claims this property isn't on the page.";
  if (status === "none") return "no rule yet.";
  return "this rule found nothing here and makes no claim: check the page.";
}

/** "Why wrong?" flags, shown after ✕ (§6). Only one for now. */
export const REASONS: { id: string; label: string; tip: string }[] = [
  { id: "not_on_page", label: "Not on the page", tip: "This course's page doesn't state this property anywhere." },
];

export const reasonLabel = (id: string) => REASONS.find((r) => r.id === id)?.label ?? id;

// --- lists of objects (§5) ---------------------------------------------------------------------------------------
/** A profile rule's fields (in order) and its key field, from its definition. */
export function profileOf(definition: Record<string, unknown> | null | undefined): { fields: string[]; key: string } | null {
  const p = definition?.profile as { fields?: Record<string, unknown>; key?: string } | undefined;
  if (!p?.fields) return null;
  const fields = Object.keys(p.fields);
  return fields.length ? { fields, key: p.key ?? fields[0] } : null;
}

/** `ceterms:timeRequired` → `timeRequired` (field names on the row and the label buttons). */
export const fieldWord = (f: string) => f.replace(/^[a-z]+:/, "");

/** An item's object: its fields' words, from `fields` (else its JSON value). */
export function objectOf(it: Pick<RowItem, "value" | "fields">): Record<string, string> {
  if (it.fields) return Object.fromEntries(Object.entries(it.fields).map(([k, f]) => [k, f.text]));
  try {
    const o = JSON.parse(it.value) as unknown;
    return o && typeof o === "object" ? (o as Record<string, string>) : {};
  } catch { return {}; }
}

/** An object being added: the selections labelled so far, and the one waiting for a label. */
export interface ObjectAdd { pending: CapturedSelection | null; fields: Record<string, CapturedSelection> }

export const emptyAdd = (): ObjectAdd => ({ pending: null, fields: {} });

/** Label the waiting selection as one field. */
export function labelField(a: ObjectAdd, field: string): ObjectAdd {
  return a.pending ? { pending: null, fields: { ...a.fields, [field]: a.pending } } : a;
}

/** Saved once every field is labelled; savable by hand once the key field is. */
export const addComplete = (a: ObjectAdd, fields: string[]) => fields.every((f) => !!a.fields[f]);
export const addSavable = (a: ObjectAdd, key: string) => !!a.fields[key];

const placed = (c: CapturedSelection): ObjectField => ({ text: c.text.trim(), css_path: c.css_path, char_start: c.char_start, char_end: c.char_end });

/** The `missing` item verdict that adds an object (`expected.objects[]`; the server sets `expected.text`). */
export function objectEvent(author: string, ruleId: string, occurrenceKey: string | null, a: ObjectAdd, fields: string[]): NewEvent {
  const fs = Object.fromEntries(fields.filter((f) => a.fields[f]).map((f) => [f, placed(a.fields[f])]));
  const first = a.fields[fields.find((f) => a.fields[f]) ?? ""];
  return { type: "verdict", author, verdict: "missing", note: null,
           expected: { text: "", css_path: first?.css_path ?? null, char_start: first?.char_start ?? null, char_end: first?.char_end ?? null,
                       located_by: "labelled in the Studio", objects: [{ fields: fs }] },
           target: { kind: "match", rule_id: ruleId, occurrence_key: occurrenceKey, item: true } };
}

/** An added object's fields' words, from its `missing` verdict. */
export function addedObject(e: EventBrief): Record<string, string> {
  const fs = e.expected?.objects?.[0]?.fields ?? {};
  return Object.fromEntries(Object.entries(fs).map(([k, f]) => [k, f.text]));
}
