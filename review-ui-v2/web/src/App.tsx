import { useCallback, useEffect, useMemo, useState } from "react";
import { apiBase, getBoot, getPage, openReview, postEvent, startReview } from "./api";
import type { Actions, ItemRef } from "./actions";
import LabelSection from "./components/LabelSection";
import NotesDrawer from "./components/NotesDrawer";
import PageList from "./components/PageList";
import PagePane from "./components/PagePane";
import PageFlag from "./components/PageFlag";
import RecordGroup from "./components/RecordGroup";
import SaveGolden from "./components/SaveGolden";
import type { DecideExtra } from "./components/ItemCard";
import { buildHash, parseHash } from "./route";
import { addedKey, flagTotals, foldDecision, foldFlag, foldNote, manualLabelKey, pageFlagKey } from "./review";
import type { Author, Boot, Decision, DecisionEvent, Flag, FlagEvent, Note, NoteEvent, NoteScope, PageView } from "./types";

type SaveState = "idle" | "saving" | "saved" | "error";

const readAuthor = (): Author => {
  try {
    return localStorage.getItem("xtra-author") === "Jared" ? "Jared" : "Seth";
  } catch {
    return "Seth";
  }
};

/** Everything on the page that has no decision yet and is not waiting on an expert. */
function undecidedItems(
  page: PageView,
  decisions: Record<string, Decision>,
  flags: Record<string, Flag>,
): ItemRef[] {
  const open = (key: string) => !decisions[key] && !flags[key];
  const labels = page.labels
    .filter((l) => open(l.key))
    .map((l): ItemRef => ({
      kind: "label",
      key: l.key,
      canonical_label: l.label,
      source_url: page.url,
      rule_id: l.rule_id,
      value: l.label,
    }));
  const fields = page.records.flatMap((r) =>
    r.fields
      .filter((f) => open(f.field_id))
      .map((f): ItemRef => ({
        kind: "field",
        key: f.field_id,
        canonical_label: f.canonical_label,
        source_url: f.source_url,
        record_id: r.record_id,
        rule_id: f.rule_id,
        value: f.value,
      })),
  );
  return [...labels, ...fields];
}

export default function App({ cid }: { cid: string }) {
  const [boot, setBoot] = useState<Boot | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [notes, setNotes] = useState<Note[]>([]);
  const [flags, setFlags] = useState<Record<string, Flag>>({});
  const [golden, setGolden] = useState<Set<string>>(new Set());
  const [stem, setStem] = useState<string | null>(null);
  const [page, setPage] = useState<PageView | null>(null);
  const [author, setAuthor] = useState<Author>(readAuthor);
  const [save, setSave] = useState<SaveState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<string[]>([]);
  const [drawer, setDrawer] = useState(false);

  const adopt = useCallback((b: Boot) => {
    setBoot(b);
    setDecisions(b.review.decisions);
    setNotes(b.review.notes);
    setFlags(b.review.flags ?? {});
    setGolden(new Set(b.golden ?? []));
    setStem((current) => {
      const fromHash = parseHash(location.hash).stem ?? "";
      const keep = current && b.pages.some((p) => p.stem === current) ? current : null;
      const first = b.pages.find((p) => p.keys.some((k) => !b.review.decisions[k])) ?? b.pages[0];
      return keep ?? (b.pages.some((p) => p.stem === fromHash) ? fromHash : first?.stem ?? null);
    });
  }, []);

  useEffect(() => {
    getBoot().then(adopt).catch((e) => setError(String(e)));
  }, [adopt]);

  useEffect(() => {
    if (!stem) return;
    setPage(null);
    setSelectedKey(null);
    setHighlight([]);
    location.hash = buildHash(cid, stem);
    getPage(stem).then(setPage).catch((e) => setError(String(e)));
  }, [stem]);

  const send = useCallback(
    async (event: DecisionEvent | NoteEvent | FlagEvent) => {
      setSave("saving");
      try {
        const saved = await postEvent({ ...event, author });
        if (event.type === "decision") setDecisions((d) => foldDecision(d, saved.event));
        else if (event.type === "flag") setFlags((f) => foldFlag(f, saved.event));
        else setNotes((n) => foldNote(n, saved.event));
        setSave("saved");
        setError(null);
      } catch (e) {
        setSave("error");
        setError(`Not saved: ${e}. Do not close this window; retry the last action.`);
      }
    },
    [author],
  );

  const actions: Actions = useMemo(
    () => ({
      decide: (item: ItemRef, status, extra?: DecideExtra) => {
        void send({
          type: "decision",
          kind: item.kind,
          key: item.key,
          status,
          canonical_label: item.canonical_label,
          source_url: item.source_url,
          record_id: item.record_id,
          rule_id: item.rule_id,
          value: item.value,
          expected_value: extra?.expected,
          reasons: extra?.reasons ?? [],
        });
        if (extra?.note) {
          void send({ type: "note", scope: "field", target: item.key, text: extra.note });
        }
      },
      note: (scope: NoteScope, target, text, id) =>
        void send({ type: "note", scope, target, text, id }),
      addMissing: (recordId, label, url, expected, note) => {
        const key = addedKey(recordId, label, url);
        void send({
          type: "decision",
          kind: "field",
          key,
          status: "missing",
          canonical_label: label,
          source_url: url,
          record_id: recordId,
          expected_value: expected,
          reasons: ["missed"],
        });
        if (note) void send({ type: "note", scope: "field", target: key, text: note });
      },
      flag: (target, on, note) =>
        void send({
          type: "flag",
          scope: target.scope,
          target: target.key,
          stem: target.stem,
          source_url: target.source_url,
          canonical_label: target.canonical_label,
          record_id: target.record_id,
          flagged: on,
          note,
        }),
      addLabel: (url, label, note) => {
        const key = manualLabelKey(url, label);
        void send({
          type: "decision",
          kind: "label",
          key,
          status: "missing",
          canonical_label: label,
          source_url: url,
          expected_value: label,
          reasons: ["missed"],
        });
        if (note) void send({ type: "note", scope: "field", target: key, text: note });
      },
    }),
    [send],
  );

  const index = boot && stem ? boot.pages.findIndex((p) => p.stem === stem) : -1;
  const go = useCallback(
    (delta: number) => {
      if (!boot || index < 0) return;
      const next = boot.pages[index + delta];
      if (next) setStem(next.stem);
    },
    [boot, index],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "Enter" && !(e.target as HTMLElement).closest("button")) go(1);
      else if (e.key === "]") go(1);
      else if (e.key === "[") go(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);

  const chooseAuthor = (a: Author) => {
    setAuthor(a);
    try {
      localStorage.setItem("xtra-author", a);
    } catch {
      /* private window: author just resets on reload */
    }
  };

  if (!boot) return <div className="loading">{error ?? "Loading…"}</div>;

  const values = Object.values(decisions);
  const accepted = values.filter((d) => d.status === "accepted").length;
  const rejected = values.filter((d) => d.status === "rejected").length;
  const total = boot.review.counts.total;
  const current = boot.pages[index];
  const flagCount = flagTotals(flags);
  const remaining = page ? undecidedItems(page, decisions, flags) : [];

  return (
    <div className="app">
      <header className="topbar">
        <strong className="brand">xTRA Review</strong>
        <button className="link" title="Back to the list of rulesets" onClick={() => (location.hash = "")}>
          ⇄ Change ruleset
        </button>
        <div className="pager">
          <button onClick={() => go(-1)} disabled={index <= 0} aria-label="Previous page">‹</button>
          <span className="page-title">{current?.title ?? ""}</span>
          <button onClick={() => go(1)} disabled={index >= boot.pages.length - 1} aria-label="Next page">›</button>
          <span className="muted">{index + 1} of {boot.pages.length}</span>
        </div>
        <div className="spacer" />
        <div className="seg" role="group" aria-label="Who is recording">
          <span className="muted">Recording as</span>
          {(["Seth", "Jared"] as Author[]).map((a) => (
            <button key={a} className={author === a ? "on" : ""} onClick={() => chooseAuthor(a)}>{a}</button>
          ))}
        </div>
        <span className={`save ${save}`} role="status">
          {save === "saving" ? "Saving…" : save === "saved" ? "✓ Saved to disk" : save === "error" ? "⚠ NOT SAVED" : ""}
        </span>
        <button onClick={() => setDrawer(!drawer)}>Notes ({notes.length})</button>
        <details className="menu">
          <summary>Download</summary>
          <div className="menu-body">
            {stem && <a href={`${apiBase()}/export/golden/${stem}.json`} download>Golden sample · this page</a>}
            {stem && <a href={`${apiBase()}/export/labels/${stem}.json`} download>Labels · this page</a>}
            <a href={`${apiBase()}/export/golden.zip`} download>Golden sample · all {boot.pages.length} pages (zip)</a>
            <a href={`${apiBase()}/export/labels.json`} download>Labels · all pages</a>
            <a href={`${apiBase()}/export/flagged.md`} download>⚑ Flagged for review (.md, for experts)</a>
            <a href={`${apiBase()}/export/feedback.md`} download>Feedback for Claude (.md)</a>
          </div>
        </details>
      </header>

      {error && <div className="banner error" role="alert">{error}</div>}

      <div className="main">
        <PageList
          pages={boot.pages}
          decisions={decisions}
          flags={flags}
          current={stem}
          onPick={setStem}
        />

        <section className="pane middle" aria-label="Extracted values">
          <div className="middle-head">
            <span className="muted">EXTRACTED VALUES</span>
            {page && (
              <a href={page.url} target="_blank" rel="noreferrer" className="url" title={page.url}>
                {page.url.replace(/^https?:\/\//, "")}
              </a>
            )}
          </div>
          {page && (
            <div className="page-tools">
              <PageFlag
                flag={flags[pageFlagKey(page.stem)]}
                onFlag={(on, note) =>
                  actions.flag(
                    { scope: "page", key: pageFlagKey(page.stem), stem: page.stem, source_url: page.url },
                    on,
                    note,
                  )
                }
              />
              <SaveGolden
                key={page.stem}
                stem={page.stem}
                saved={golden.has(page.stem)}
                onSaved={(saved) => setGolden((current) => new Set(current).add(saved))}
              />
              {remaining.length > 0 && (
                <button
                  className="act accept"
                  title="Flagged items are skipped"
                  onClick={() => remaining.forEach((item) => actions.decide(item, "accepted"))}
                >
                  ✓ Accept all remaining on this page ({remaining.length})
                </button>
              )}
            </div>
          )}
          <div className="middle-scroll">
            {!page && <div className="loading">Loading page…</div>}
            {page && (
              <>
                <LabelSection
                  stem={page.stem}
                  flags={flags}
                  pageUrl={page.url}
                  labels={page.labels}
                  vocabulary={boot.label_vocabulary}
                  decisions={decisions}
                  notes={notes}
                  reasons={boot.reasons}
                  selectedKey={selectedKey}
                  onSelect={(key) => {
                    setSelectedKey(key);
                    setHighlight([]);
                  }}
                  actions={actions}
                />
                {page.records.map((record) => (
                  <RecordGroup
                    key={record.record_id}
                    stem={page.stem}
                    flags={flags}
                    record={record}
                    pageUrl={page.url}
                    decisions={decisions}
                    notes={notes}
                    properties={boot.properties}
                    reasons={boot.reasons}
                    selectedKey={selectedKey}
                    onSelect={(key, path) => {
                      setSelectedKey(key);
                      setHighlight(path ? [path] : []);
                    }}
                    actions={actions}
                  />
                ))}
                {page.records.length === 0 && (
                  <div className="card empty-card">No values were extracted from this page.</div>
                )}
              </>
            )}
          </div>
          {drawer && (
            <NotesDrawer
              notes={notes}
              flags={Object.values(flags)}
              onClose={() => setDrawer(false)}
              onSave={(text, id) => actions.note("general", null, text, id)}
            />
          )}
        </section>

        {page && <PagePane stem={page.stem} url={page.url} highlight={highlight} />}
      </div>

      <footer className="bottombar">
        <span>
          <strong>Accepted {accepted} of {total}</strong>
          {rejected > 0 && <span className="bad"> · rejected {rejected}</span>}
          {(flagCount.pages > 0 || flagCount.items > 0) && (
            <span className="flag-mark">
              {" "}· ⚑ flagged {flagCount.pages} page{flagCount.pages === 1 ? "" : "s"}, {flagCount.items} item
              {flagCount.items === 1 ? "" : "s"}
            </span>
          )}
          <span className="muted"> · review {boot.review.session.review_id} · ruleset v{boot.extraction.ruleset.version}</span>
        </span>
        <span className="keys muted">
          <kbd>Tab</kbd> next value · <kbd>A</kbd> accept · <kbd>R</kbd> reject · <kbd>C</kbd> note · <kbd>F</kbd> flag ·{" "}
          <kbd>E</kbd> edit · <kbd>Enter</kbd> next page
        </span>
        <span className="spacer" />
        <select
          aria-label="Review session"
          value={boot.review.session.review_id}
          onChange={(e) => openReview(e.target.value).then(adopt).catch((err) => setError(String(err)))}
        >
          {boot.reviews.map((r) => (
            <option key={r}>{r}</option>
          ))}
        </select>
        <button
          onClick={() => {
            if (confirm("Start a new review session? Accepted values that did not change are carried over."))
              startReview().then(adopt).catch((err) => setError(String(err)));
          }}
        >
          New review
        </button>
      </footer>
    </div>
  );
}
