// Compare (spec §7.4, screens 08-compare*): is ruleset version B better than A?
// Top: From / To only. Left: the rules that changed. Right: summary line, why, Jared's earlier verdicts, signals
// before → after (expandable into the records that lost / gained them), a sample of other changed records.
// Every record links to the Rules tab ("See on page →"); Compare has no page pane.
import { useEffect, useState, type KeyboardEvent, type ReactNode } from "react";
import { api } from "../api/client";
import type { BriefRow, DiffPart } from "../api/types";
import { go, href } from "../shell/router";
import type { TabProps } from "../shell/tabProps";
import { fmt, Ico, useKeyHints } from "../shell/ui";
import { compactDiff, delta, outcomeLabel, unchanged } from "./diff";
import type { AnnotatedRowX, CompareResponseX, RuleCardX, SignalDeltaX } from "./types";
import "./compare.css";

const VERDICT_LABEL = { correct: "Correct", wrong: "Wrong" } as const;
const num = (v: string | null) => (v && /^\d+$/.test(v) ? Number(v) : undefined);

export default function CompareTab({ catalog, route }: TabProps) {
  const short = catalog.short;
  const a = num(route.params.get("a")), b = num(route.params.get("b"));
  const rule = route.params.get("rule") || undefined;
  const [data, setData] = useState<CompareResponseX | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    setLoading(true);
    api.compare(short, { a, b, rule }).then(
      (d) => { if (live) { setData(d as unknown as CompareResponseX); setError(null); setLoading(false); } },
      (e) => { if (live) { setError(String(e.message ?? e)); setLoading(false); } });
    return () => { live = false; };
  }, [short, a, b, rule]);

  useKeyHints(<span>The same numbers <span className="mono">golden-datasets rule try</span> prints</span>, []);

  const nav = (p: { a?: number; b?: number; rule?: string | null }) => {
    const next = { a: p.a ?? data?.a ?? a, b: p.b ?? data?.b ?? b, rule: p.rule === undefined ? rule : p.rule };
    go(href(short, "compare", null, next));
  };

  if (error && !data) return <div className="cmp-layout"><div /><section className="doc"><div className="doc-in">
    <h1>Compare ruleset versions</h1><p className="muted cmp-empty">{error}</p></div></section></div>;
  if (!data) return <div className="cmp-layout"><aside className="col" /><section className="doc"><div className="doc-in">
    <h1>Compare ruleset versions</h1><p className="muted cmp-empty">Loading…</p></div></section></div>;

  return (
    <div className={"cmp-layout" + (loading ? " loading" : "")}>
      <RuleColumn data={data} rule={rule} onPick={(r) => nav({ rule: r })} />
      <section className="doc">
        <div className="doc-in">
          <div className="cmp-head">
            <h1>Compare ruleset versions</h1>
            <div className="ctl">
              <label>From <VersionSelect data={data} value={data.a} onChange={(v) => nav({ a: v })} name="from" /></label>
              <span className="faint">→</span>
              <label>To <VersionSelect data={data} value={data.b} onChange={(v) => nav({ b: v })} name="to" /></label>
            </div>
          </div>
          {error && <p className="cmp-error">{error}</p>}
          <Body data={data} short={short} rule={rule} />
        </div>
      </section>
    </div>
  );
}

function VersionSelect({ data, value, onChange, name }:
  { data: CompareResponseX; value: number; onChange: (v: number) => void; name: string }) {
  return (
    <select className="vsel" aria-label={name} value={value} onChange={(e) => onChange(Number(e.target.value))}>
      {data.versions.map((v) => <option key={v.version} value={v.version} title={v.note ?? ""}>ruleset v{v.version}</option>)}
    </select>
  );
}

const ver = (v: number | null) => (v == null ? "none" : `v${v}`);

function RuleColumn({ data, rule, onPick }: { data: CompareResponseX; rule?: string; onPick: (r: string | null) => void }) {
  const items = [...data.changed_rules];
  // A link to a rule that didn't change still shows it, with 0.
  const extra = rule && !items.some((r) => r.rule_id === rule) ? data.rules.find((c) => c.rule_id === rule) : undefined;
  if (extra) items.push({ ...extra, records_changed: 0 });
  const total = data.changed_rules.reduce((t, r) => t + r.records_changed, 0);
  const pick = (r: string | null) => () => onPick(r);
  const key = (r: string | null) => (e: KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(r); } };
  return (
    <aside className="col">
      <div className="rule-list">
        <div className="group-h"><span className="panel-title">Rules that changed</span></div>
        <div className={"rule-item" + (!rule ? " on" : "")} role="button" tabIndex={0} onClick={pick(null)} onKeyDown={key(null)}>
          <div /><div><div className="nm">All changed rules</div></div><div className="meta"><span>{fmt(total)}</span></div>
        </div>
        {items.map((r) => (
          <div key={r.rule_id} className={"rule-item" + (rule === r.rule_id ? " on" : "")} role="button" tabIndex={0}
               onClick={pick(r.rule_id)} onKeyDown={key(r.rule_id)} data-rule={r.rule_id}>
            <div />
            <div style={{ minWidth: 0 }}>
              <div className={"nm" + (r.ctdl_property ? " mono-t" : "")}>{r.ctdl_property ?? r.title}</div>
              <div className="id plain">{r.title} · {ver(r.a_version)} → {ver(r.b_version)}</div>
            </div>
            <div className="meta"><span>{fmt(r.records_changed)}</span></div>
          </div>
        ))}
        {items.length > 0 && <div className="faint cmp-foot">Counts are records whose value changed.</div>}
      </div>
    </aside>
  );
}

function Body({ data, short, rule }: { data: CompareResponseX; short: string; rule?: string }) {
  if (data.versions.length < 2) return <p className="muted cmp-empty">
    Only one ruleset version so far (v{data.b}), so there is nothing to compare. Publishing a rule makes the next one.</p>;
  if (data.a === data.b) return <p className="muted cmp-empty">From and To are the same version. Pick two different ones.</p>;
  if (data.rules.length === 0) return <p className="muted cmp-empty">No rule changed between v{data.a} and v{data.b}.</p>;

  const cards = data.rules;
  const many = cards.length > 1 && !rule;
  const t = data.totals;
  const verdicts = cards.flatMap((c) => c.annotated_rows.map((r) => ({ r, c })));
  const authors = [...new Set(verdicts.map((v) => v.r.author))];
  const sampleTotal = cards.reduce((s, c) => s + (c.sample_total ?? c.sample.length), 0);
  const sample = roundRobin(cards.map((c) => c.sample.map((r) => ({ r, c }))), 12);
  const added = cards.flatMap((c) => c.new_rows.map((r) => ({ r, c })));
  const gone = cards.flatMap((c) => c.vanished_rows.map((r) => ({ r, c })));
  const addedN = cards.reduce((s, c) => s + c.values.new, 0), goneN = cards.reduce((s, c) => s + c.values.vanished, 0);

  return (
    <>
      <div className="sumline" data-testid="sumline">
        <Num n={data.records_changed} label="records changed" />
        <Dot /><Num n={t.fixed} label="fixed" cls="good" />
        <Dot /><Num n={t.still_wrong} label="still wrong" cls="bad" />
        <Dot /><Num n={t.newly_wrong} label="newly wrong" cls="bad" />
      </div>
      {cards.map((c) => (
        <details key={c.rule_id} className="why1">
          <summary>Why this version{many && <> of <span className="mono">{c.ctdl_property ?? c.title}</span></>}</summary>
          <p>{c.why || "No reason given."}</p>
        </details>
      ))}

      <h2>{authors.length === 1 ? `${authors[0]}'s earlier verdicts` : "Earlier verdicts"}
        <span className="c">{fmt(verdicts.length)} records</span></h2>
      {verdicts.length ? (
        <div className="clist">
          {verdicts.map(({ r, c }) => <VerdictRow key={c.rule_id + r.key} r={r} card={c} short={short} many={many} />)}
        </div>
      ) : <p className="muted cmp-none">No verdicts on these rules yet.</p>}

      <h2>Signals <span className="c">click a signal to see the records that lost or gained it</span></h2>
      {cards.some((c) => c.signals.length)
        ? <div className="sigt">{cards.flatMap((c) => c.signals.map((s) =>
            <SignalRow key={c.rule_id + s.signal} s={s} card={c} short={short} many={many} />))}</div>
        : <p className="muted cmp-none">No signals on these rules.</p>}

      {addedN > 0 && <>
        <h2>New in v{data.b} <span className="c">{fmt(addedN)} records{addedN > added.length ? `, first ${added.length}` : ""}</span></h2>
        <div className="clist">{added.map(({ r, c }) => <RecLine key={c.rule_id + r.key} r={r} card={c} short={short} many={many} />)}</div>
      </>}
      {goneN > 0 && <>
        <h2>Gone in v{data.b} <span className="c">{fmt(goneN)} records{goneN > gone.length ? `, first ${gone.length}` : ""}</span></h2>
        <div className="clist">{gone.map(({ r, c }) => <RecLine key={c.rule_id + r.key} r={r} card={c} short={short} many={many} />)}</div>
      </>}

      <h2>Sample of other changed records <span className="c">{sample.length} of {fmt(sampleTotal)}, random</span></h2>
      {sample.length
        ? <div className="clist">{sample.map(({ r, c }) => <RecLine key={c.rule_id + r.key} r={r} card={c} short={short} many={many} />)}</div>
        : <p className="muted cmp-none">No other record changed.</p>}
    </>
  );
}

function roundRobin<T>(lists: T[][], n: number): T[] {
  const out: T[] = [];
  for (let i = 0; out.length < n && lists.some((l) => i < l.length); i++)
    for (const l of lists) if (i < l.length && out.length < n) out.push(l[i]);
  return out;
}

const Dot = () => <span className="dot">·</span>;
function Num({ n, label, cls = "" }: { n: number; label: string; cls?: string }) {
  return <span className={n ? cls : "zero"}><b>{fmt(n)}</b> {label}</span>;
}

/** Old → new with a word diff: removed text struck through in red, added text in green. */
export function Diff({ parts, value }: { parts: DiffPart[]; value?: string | null }) {
  if (unchanged(parts)) {
    const text = parts.map((p) => p.text).join("") || value || "";
    return <div className="diff faint one">unchanged · {text.slice(0, 200)}</div>;
  }
  return (
    <div className="diff">
      {compactDiff(parts).map((p, i) =>
        p.op === "del" ? <del key={i}>{p.text}</del>
        : p.op === "add" ? <ins key={i}>{p.text}</ins>
        : p.op === "gap" ? <span key={i} className="gap">{p.text}</span>
        : <span key={i}>{p.text}</span>)}
    </div>
  );
}

function See({ r, card, short }: { r: BriefRow; card: RuleCardX; short: string }) {
  return <a className="see" href={href(short, "rules", card.rule_id, { row: r.key })}>See on page →</a>;
}

function Ck({ r, card, many }: { r: BriefRow; card: RuleCardX; many: boolean }) {
  return <span className="ck">{r.course_key ?? "—"}{many && <span className="rtag">{card.ctdl_property ?? card.title}</span>}</span>;
}

function RecLine({ r, card, short, many, children }:
  { r: BriefRow; card: RuleCardX; short: string; many: boolean; children?: ReactNode }) {
  return (
    <div className="crec">
      <Ck r={r} card={card} many={many} />
      <div className="cbody"><Diff parts={r.diff} value={r.b_value ?? r.a_value} />{children}</div>
      <See r={r} card={card} short={short} />
    </div>
  );
}

function VerdictRow({ r, card, short, many }: { r: AnnotatedRowX; card: RuleCardX; short: string; many: boolean }) {
  const o = outcomeLabel(r);
  return (
    <div className="crec cv" data-outcome={r.outcome}>
      <span className="vb">
        <span className={`verdict ${r.verdict}`}><Ico name={r.verdict} />{VERDICT_LABEL[r.verdict]}</span>
        <span className="arr">→</span>
        <span className={`outcome ${o.cls}`}>{o.label}</span>
      </span>
      <Ck r={r} card={card} many={many} />
      <div className="cbody">
        <Diff parts={r.diff} value={r.b_value} />
        {r.note && <div className="cnote">{r.author}: “{r.note}”</div>}
        {r.verdict === "wrong" && r.outcome !== "fixed" && r.expected != null &&
          <div className="cnote">Expected: “{r.expected.length > 160 ? r.expected.slice(0, 160) + "…" : r.expected}”</div>}
      </div>
      <See r={r} card={card} short={short} />
    </div>
  );
}

function SignalRow({ s, card, short, many }: { s: SignalDeltaX; card: RuleCardX; short: string; many: boolean }) {
  const [open, setOpen] = useState(false);
  const lostN = s.lost_total ?? s.lost.length, gainedN = s.gained_total ?? s.gained.length;
  const d = s.b - s.a;
  const toggle = () => setOpen((o) => !o);
  return (
    <>
      <div className={"sigrow" + (open ? " open" : "")} role="button" tabIndex={0} aria-expanded={open} onClick={toggle}
           onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } }}>
        <span className="tw">▸</span>
        <span className="sname">{many && <span className="rtag-i">{card.ctdl_property ?? card.title} · </span>}{s.signal}</span>
        <span className="num">{fmt(s.a)}</span>
        <span className="arrow">→</span>
        <span className="num">{fmt(s.b)}</span>
        <span className={"num " + (d < 0 ? "delta-down" : d > 0 ? "delta-up" : "faint")}>{delta(s.a, s.b)}</span>
      </div>
      {open && (
        <div className="sigdrill">
          {lostN > 0 && <>
            <div className="dh good">− {fmt(lostN)} lost it{lostN > s.lost.length ? ` (first ${s.lost.length})` : ""}</div>
            <div className="clist">{s.lost.map((r) => <RecLine key={r.key} r={r} card={card} short={short} many={false} />)}</div>
          </>}
          {gainedN > 0 && <>
            <div className="dh bad">+ {fmt(gainedN)} gained it{gainedN > s.gained.length ? ` (first ${s.gained.length})` : ""}</div>
            <div className="clist">{s.gained.map((r) => <RecLine key={r.key} r={r} card={card} short={short} many={false} />)}</div>
          </>}
          {lostN === 0 && gainedN === 0 &&
            <div className="muted cmp-none">No record lost or gained it.</div>}
        </div>
      )}
    </>
  );
}
