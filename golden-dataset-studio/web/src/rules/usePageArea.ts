// The Rules tab's page pane: its tabs, a locator's course boxes, what a selection on the page does, and the highlights.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { Overlay } from "../api/types";
import type { BarAction, CapturedSelection } from "../pagepane";
import type { RowX } from "./api";
import { answerBarActions } from "./answerBar";
import { pageHighlights } from "./highlights";
import { addCapture, markPiece, newDraft, paneTabs, shortTitle, type Draft, type Piece, type TabRef } from "./logic";
import { focusStem, useFocusPage } from "./NotHere";
import type { Loaded } from "./useRulesTab";

export function usePageArea(t: Loaded) {
  const tabs = usePaneTabs(t);
  const ov = useOverlay(t, tabs.active);
  const selection = useAnswerSelection({ ...t, ...tabs });
  const { row, rows, detail, draft, missing, listRule, objAdd, objFix, onPage } = t;
  const { active } = tabs;
  const { captures } = selection;
  const marks = useMemo(() => pageHighlights({ row, rows, detail, active, ov, captures, draft, missing, listRule, objAdd, objFix, onPage }),
    [row, rows, detail, active, ov, captures, draft, missing, listRule, objAdd, objFix, onPage]);
  return { ...tabs, ov, ...selection, ...marks };
}

export type Paned = Loaded & ReturnType<typeof usePageArea>;

/** The pane's tabs: the row's page, its other pages, then the last few viewed; the linked row's page when it isn't here. */
function usePaneTabs({ cat, notHere, focus, row, extraTab, recent, activeStem }: Loaded) {
  const focusTab = useFocusPage(cat, notHere ? focusStem(focus) : null);
  const curTab: TabRef | null = row ? { stem: row.page_stem, url: row.url, title: row.page_title ?? row.page_stem } : focusTab;
  const tabs = useMemo(() => paneTabs(curTab, otherTabs(extraTab, row), recent)
    .map((t, i) => ({ ...t, title: shortTitle(t.title), badge: i + 1 })),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [row?.key, extraTab, recent, focusTab]);
  return { tabs, active: activeStem ?? row?.page_stem ?? curTab?.stem ?? null };
}

/** The course boxes and marks of a page for a record locator or page rule, each asked for once. */
function useOverlay({ cat, detail, ext }: Loaded, active: string | null): Overlay | null {
  const [overlay, setOverlay] = useState<{ key: string; data: Overlay } | null>(null);
  const overlays = useRef(new Map<string, Overlay>());
  useEffect(() => {
    if (!detail || detail.kind === "property" || !active) return;
    const key = overlayKey(detail.rule_id, active, ext);
    const hit = overlays.current.get(key);
    if (hit) { setOverlay({ key, data: hit }); return; }
    api.overlay(cat, active, detail.rule_id, ext).then((data) => { overlays.current.set(key, data); setOverlay({ key, data }); }, () => {});
  }, [cat, detail, active, ext]);
  return detail && active && overlay?.key === overlayKey(detail.rule_id, active, ext) ? overlay.data : null;
}

type WithTabs = Loaded & ReturnType<typeof usePaneTabs>;

/** A property rule's row: selecting text on its page shows the highlight bar (sme-fixes §1): comment on it, ✓ it is
 * in the right answer, ✕ it is not (both open the ✗ draft with it). Once the ✗ draft is open, a selection is a piece
 * of the answer at once, as before the bar (Jared, 2026-11-05: answers dragged after ✗ were lost when the bar was
 * dismissed), and the bar only offers ✕ Not in answer. Only on the row's own page: the expected text is located there. */
function useAnswerSelection(t: WithTabs) {
  const { draft, missed, itemAdd, objAdd, row, active, listRule, kind } = t;
  const captures: Piece[] = draft?.captures.length ? draft.captures : missed?.capture ? [missed.capture] : itemAdd?.capture ? [itemAdd.capture] : [];
  const onRowPage = !!row && active === row.page_stem;
  // a list's row answers only while a missing item is being selected (its items have their own ✓ and ✕)
  const selectAnswer = listRule ? onRowPage && (!!itemAdd || !!objAdd)
    : kind === "property" ? onRowPage && !missed && draft?.mode !== "comment" : draft?.mode === "wrong";
  const onAnswer = useOnAnswer(t);
  const captureFirst = kind === "property" && !listRule && draft?.mode === "wrong";
  const barActions = useAnswerBar({ ...t, onRowPage, onAnswer, captureFirst });
  const removePiece = useRemovePiece(t.setDraft);
  return { captures, onRowPage, selectAnswer, onAnswer, captureFirst, barActions, removePiece };
}

function useOnAnswer({ kind, draft, row, listRule, itemAdd, objAdd, setObjAdd, setItemAdd, setMissed, setDraft }: WithTabs) {
  return useCallback((c: Piece) => {
    if (listRule && objAdd) { setObjAdd((a) => (a ? { ...a, pending: c } : a)); return; }  // then: which field is it?
    if (listRule && itemAdd) { setItemAdd({ capture: c }); return; }
    setMissed(null);
    setDraft((d) => withAnswerPiece(d, c, row));
  }, [kind, draft, row, listRule, itemAdd, objAdd]);  // eslint-disable-line react-hooks/exhaustive-deps
}

/** Several drags add pieces of one answer; one over an existing piece replaces it. A comment already pinned with the
 * bubble stays with the ✗: the comment goes with either answer. */
function withAnswerPiece(d: Draft | null, c: Piece, row: RowX | null): Draft | null {
  if (d && d.mode === "wrong") return { ...d, captures: addCapture(d.captures, c) };
  if (!row) return d;
  return { ...newDraft("wrong", row.verdict, row.state), captures: [c], ...(d?.mode === "comment" ? { anchor: d.anchor, note: d.note } : {}) };
}

function useAnswerBar(t: WithTabs & { onRowPage: boolean; onAnswer: (c: Piece) => void; captureFirst: boolean }) {
  const { kind, listRule, onRowPage, missed, itemAdd, row, onAnswer, captureFirst, setDraft, setMissed } = t;
  return useMemo<BarAction[] | null>(() => {
    if (kind !== "property" || listRule || !onRowPage || missed || itemAdd || !row) return null;
    // after ✗ the drag is already a piece of the answer (captureFirst): ✓ keeps it in, ✕ marks it out
    const mark = (polarity: "in" | "out") => (c: CapturedSelection) => (captureFirst
      ? setDraft((d) => (d ? { ...d, captures: markPiece(d.captures, c, polarity) } : d))
      : onAnswer({ ...c, polarity }));
    return answerBarActions(row, mark, setMissed, setDraft);
  }, [kind, listRule, onRowPage, missed, itemAdd, row, onAnswer, captureFirst]);  // eslint-disable-line react-hooks/exhaustive-deps
}

function useRemovePiece(setDraft: Loaded["setDraft"]) {
  return useCallback((id: string) => {
    const i = Number(id.replace(/^capture-/, ""));
    setDraft((d) => (d ? { ...d, captures: d.captures.filter((_, j) => j !== i) } : d));
  }, [setDraft]);
}

const otherTabs = (extraTab: TabRef | null, row: RowX | null): TabRef[] =>
  [...(extraTab ? [extraTab] : []), ...(row?.other_pages ?? []).map((p) => ({ stem: p.page_stem, url: p.url, title: p.title ?? p.page_stem }))];

const overlayKey = (ruleId: string, stem: string, ext: string | null) => `${ruleId}|${stem}|${ext ?? ""}`;
