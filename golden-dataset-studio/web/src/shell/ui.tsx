// Small shared pieces: the footer key-hint line, toasts, icons, number/date formatting.
import { createContext, useContext, useEffect, type ReactNode } from "react";

export const fmt = (n: number | null | undefined) => (n ?? 0).toLocaleString("en-US");
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2026-10-12T20-59-13Z" → "12 Oct 2026" */
export const fmtDate = (crawl: string) => `${+crawl.slice(8, 10)} ${MONTHS[+crawl.slice(5, 7) - 1]} ${crawl.slice(0, 4)}`;
export const termUrl = (t: string | null | undefined) => (t ? `https://credreg.net/ctdl/terms/${t.split(":")[1]}` : null);

type SetKeys = (hint: ReactNode) => void;
export const KeysContext = createContext<SetKeys>(() => {});
/** Show a key-hint line in the footer while the calling component is mounted. */
export function useKeyHints(hint: ReactNode, deps: unknown[] = []): void {
  const set = useContext(KeysContext);
  useEffect(() => {
    set(hint);
    return () => set(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

export function toast(msg: string): void {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 1800);
}

export { Ico, ICON } from "./icons";
