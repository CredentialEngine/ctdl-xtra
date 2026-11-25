// The Evals tab's URL query, read once per route, and the navigation that changes part of it.
import type { ScoreBasis, ScoreOutcome, WrongKey } from "../api/types";

export type NavChange = Record<string, string | number | null>;
export type Nav = (change: NavChange, keepRow?: boolean) => void;

export interface EvalsQuery {
  basis: ScoreBasis; goldenParam: string | null; outputParam: string | null; col: string | null; subj: string | null;
  outcome: ScoreOutcome | null; grp: string | null; offset: number; rowKey: string | null; wk: WrongKey;
}

export function readQuery(params: URLSearchParams): EvalsQuery {
  return { basis: basisOf(params), goldenParam: params.get("g"), outputParam: params.get("x"),
    col: params.get("col"), subj: params.get("subj"), outcome: params.get("o") as ScoreOutcome | null, grp: params.get("grp"),
    offset: +(params.get("off") || 0), rowKey: params.get("row"), wk: wrongKeyOf(params.get("wk")) };
}

/** The current query as URL parameters, the open value kept only when `keepRow`. */
export function queryParams(q: EvalsQuery, keepRow: boolean): NavChange {
  return { b: q.basis === "rule" ? "rule" : null, g: q.goldenParam, x: q.outputParam, col: q.col, subj: q.subj,
    o: q.outcome, grp: q.grp, off: q.offset || null, row: keepRow ? q.rowKey : null, wk: q.wk === "auto" ? null : q.wk };
}

export function basisOf(params: URLSearchParams): ScoreBasis {
  return params.get("b") === "rule" ? "rule" : "human";
}

function wrongKeyOf(param: string | null): WrongKey {
  return param === "label" || param === "shape" || param === "diff" || param === "subject" ? param : "auto";
}
