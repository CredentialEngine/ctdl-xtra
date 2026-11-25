// The Rules tab's keys (spec §7.2): Tab / Shift+Tab move between rows, 1 2 3 (A W C) mark the selected row, H selects
// text, Enter saves what is under way, Esc cancels it. On a page of courses (sme-fixes §3), Enter goes into the page and
// Esc back up to it.
import { useEffect, useRef } from "react";
import { isField, keyAction, moveIn, rowKeysBlocked, type KeyAction } from "./logic";
import type { RulesTabState } from "./useRulesTab";

export function useRuleKeys(t: RulesTabState) {
  const keys = useRef<(e: KeyboardEvent) => void>(() => {});
  keys.current = (e: KeyboardEvent) => handleRuleKey(t, e);
  useEffect(() => {
    const on = (e: KeyboardEvent) => keys.current(e);
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);
}

function handleRuleKey(t: RulesTabState, e: KeyboardEvent) {
  const a = keyAction(e, isField(e.target));
  if (!a || !t.row || rowKeysBlocked()) return;
  if (a === "save") { saveByKey(t, e); return; }
  if (a === "cancel") { cancelByKey(t, e); return; }
  e.preventDefault();
  moveOrMark(t, a);
}

function saveByKey(t: RulesTabState, e: KeyboardEvent) {
  const { missed, itemAdd, objAdd, profile, objFix, draft, onPage, sel } = t;
  if (missed) { e.preventDefault(); void t.saveMissed(); }
  else if (itemAdd?.capture) { e.preventDefault(); void t.saveAddItem(); }
  else if (objAdd && profile && objAdd.fields[profile.key]) { e.preventDefault(); void t.saveObject(objAdd); }
  else if (objFix && Object.keys(objFix.fields).length) { e.preventDefault(); void t.saveFix(); }
  else if (draft) { e.preventDefault(); void t.saveRow(sel, { draft }); }
  else if (onPage && !isField(e.target)) { e.preventDefault(); t.selectRow(sel, "course"); }  // into the page's courses
}

function cancelByKey(t: RulesTabState, e: KeyboardEvent) {
  if (isField(e.target)) (e.target as HTMLElement).blur();
  // Esc on a course of a page, with nothing to cancel: back up to the page row (sme-fixes §3)
  if (t.perPage && t.level === "course" && !t.draft && !t.missed && !t.itemAdd) moveBy(t, "up");
  t.setDraft(null); t.setMissed(null); t.setExtraTab(null); t.setItemAdd(null); t.setObjAdd(null); t.setObjFix(null);
}

function moveOrMark(t: RulesTabState, a: NonNullable<KeyAction>) {
  const { sel } = t;
  if (t.perPage && (a === "next" || a === "prev")) moveBy(t, a);
  else if (t.onPage) markPageByKey(t, a);
  else if (a === "next") t.selectRow(sel + 1);
  else if (a === "prev") t.selectRow(sel - 1);
  else if (t.listRule) markListByKey(t, a);
  else if (a === "correct") t.pick(sel, "correct");
  else if (a === "wrong" || a === "select") t.pick(sel, "wrong");
  else if (a === "comment") t.pick(sel, "comment");
}

function moveBy(t: RulesTabState, a: "next" | "prev" | "up") {
  const m = moveIn(t.groups, t.sel, t.level, a);
  t.selectRow(m.sel, m.level);
}

/** On a page row: 1 accepts every course on it. */
function markPageByKey(t: RulesTabState, a: NonNullable<KeyAction>) {
  if (a === "correct") void t.acceptPage(t.sel);
  else if (a === "wrong" || a === "comment") t.pick(t.sel, a);
}

/** On a list's row: H adds a missing item; 1 / 2 mark every item of the row. */
function markListByKey(t: RulesTabState, a: NonNullable<KeyAction>) {
  if (a === "select") (t.profile ? t.startAddObject : t.startAddItem)();
  else if (a === "comment") t.pick(t.sel, "comment");
  else if (a === "correct" || a === "wrong") void t.markAll(a);
}
