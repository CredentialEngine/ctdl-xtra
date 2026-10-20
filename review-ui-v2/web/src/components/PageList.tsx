import { useEffect, useMemo, useRef, useState } from "react";
import { pageFlags, pageProgress } from "../review";
import type { Decision, Flag, PageSummary } from "../types";

interface Props {
  pages: PageSummary[];
  decisions: Record<string, Decision>;
  flags: Record<string, Flag>;
  current: string | null;
  onPick: (stem: string) => void;
}

export default function PageList({ pages, decisions, flags, current, onPick }: Props) {
  const [query, setQuery] = useState("");
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const flaggedPages = useMemo(
    () => pages.filter((p) => pageFlags(p.stem, flags).any).length,
    [pages, flags],
  );
  const currentRow = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    currentRow.current?.scrollIntoView({ block: "nearest" });
  }, [current]);
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matching = q ? pages.filter((p) => `${p.title} ${p.page_type}`.toLowerCase().includes(q)) : pages;
    return flaggedOnly ? matching.filter((p) => pageFlags(p.stem, flags).any) : matching;
  }, [pages, query, flaggedOnly, flags]);

  return (
    <nav className="pane list" aria-label="Pages">
      <input className="search" placeholder="Find a page" value={query} onChange={(e) => setQuery(e.target.value)} />
      <div className="list-head">PAGES <span>{pages.length}</span></div>
      <label className={`only-flagged ${flaggedOnly ? "on" : ""}`}>
        <input type="checkbox" checked={flaggedOnly} onChange={(e) => setFlaggedOnly(e.target.checked)} />
        <span className="flag-mark">⚑</span> Flagged only ({flaggedPages})
      </label>
      <ul>
        {shown.map((page) => {
          const { decided, total, rejected } = pageProgress(page, decisions);
          const done = decided === total;
          const flagged = pageFlags(page.stem, flags);
          return (
            <li key={page.stem}>
              <button
                ref={page.stem === current ? currentRow : undefined}
                className={`row ${page.stem === current ? "current" : ""} ${done ? "done" : ""} ${flagged.any ? "flagged" : ""}`}
                style={{ ["--fill" as string]: total ? `${(decided / total) * 100}%` : "100%" }}
                onClick={() => onPick(page.stem)}
              >
                <span className="row-top">
                  <span className="row-title">{page.title}</span>
                  <span className="row-count">
                    {flagged.any && (
                      <b
                        className="flag-mark"
                        title={`${flagged.page ? "page flagged" : ""}${flagged.page && flagged.items ? ", " : ""}${flagged.items ? `${flagged.items} flagged item(s)` : ""}`}
                      >
                        ⚑{flagged.items > 0 ? flagged.items : ""}{" "}
                      </b>
                    )}
                    {rejected > 0 && <b className="bad">✕{rejected} </b>}
                    {total === 0 ? "–" : done ? "✓" : `${decided}/${total}`}
                  </span>
                </span>
                <span className="row-sub">
                  <span className="chip type">{page.page_type}</span>
                  {page.labels.map((l) => (
                    <span className="chip label" key={l}>{l}</span>
                  ))}
                  {page.labels.length === 0 && <span className="chip none">no label</span>}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
