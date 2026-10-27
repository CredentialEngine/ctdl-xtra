// Talk about rules as a whole (Rules tab sidebar): a thread per rule (e.g. questioning whether a rule is needed)
// and one for the ruleset (suggesting new rules, such as a domain expert's heuristic like "every course in this
// catalog is in English", or other approaches). Stored as comments in the annotation log (target kind "rule" /
// "ruleset", with a topic) and sent to Claude in the prompt.
import { useState } from "react";
import type { TalkItem, Topic } from "../api/types";
import { Ico } from "../shell/icons";
import "./discussion.css";

export const TOPIC_LABEL: Record<Topic, string> = {
  "new-rule": "Suggests a new rule", approach: "Suggests an approach", "question-rule": "Questions this rule", other: "Comment",
};
const when = (at: string) => at.slice(0, 10);

export function Thread({ items }: { items: TalkItem[] }) {
  if (!items.length) return null;
  return (
    <ul className="talk-list">
      {items.map((e) => (
        <li key={e.annotation_id} className={"talk-item" + (e.topic === "question-rule" ? " q" : "")}>
          <div className="talk-meta"><b>{e.author}</b> · {when(e.at)}
            {e.topic && e.topic !== "other" && <span className={`talk-topic t-${e.topic}`}>{TOPIC_LABEL[e.topic]}</span>}
            {e.rule_version_seen != null && <span className="faint"> · on v{e.rule_version_seen}</span>}</div>
          <div className="talk-note">{e.note}</div>
        </li>
      ))}
    </ul>
  );
}

/** A note and Post; `topics` (if more than one) are offered as a choice, `question` as a checkbox. */
export function Composer({ placeholder, topics, question, onPost }: {
  placeholder: string; topics?: Topic[]; question?: boolean;
  onPost: (note: string, topic: Topic) => Promise<boolean>;
}) {
  const [note, setNote] = useState("");
  const [topic, setTopic] = useState<Topic>(topics?.[0] ?? "other");
  const [asks, setAsks] = useState(false);
  const [busy, setBusy] = useState(false);
  const post = async () => {
    if (!note.trim() || busy) return;
    setBusy(true);
    const ok = await onPost(note.trim(), question ? (asks ? "question-rule" : "other") : topic);
    setBusy(false);
    if (ok) { setNote(""); setAsks(false); }
  };
  return (
    <div className="talk-composer" onClick={(e) => e.stopPropagation()}>
      {topics && topics.length > 1 && (
        <div className="seg talk-topics" role="group" aria-label="About">
          {topics.map((t) => <button key={t} className={t === topic ? "on" : ""} onClick={() => setTopic(t)}>{TOPIC_LABEL[t]}</button>)}
        </div>
      )}
      <textarea className="talk-input" rows={3} value={note} placeholder={topics && topic === "new-rule"
        ? "e.g. Every course in this catalog is in English: set ceterms:inLanguage to English for all of them." : placeholder}
        onChange={(e) => setNote(e.target.value)}
        onKeyDown={(e) => { e.stopPropagation(); if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void post(); }} />
      <div className="talk-actions">
        {question && <label className="talk-q"><input type="checkbox" checked={asks} onChange={(e) => setAsks(e.target.checked)} />
          Question whether this rule is needed</label>}
        <button className="btn primary sm" disabled={!note.trim() || busy} onClick={() => void post()}>Post</button>
      </div>
    </div>
  );
}

/** The ruleset's thread, at the top of the rule list: collapsed to one line until opened. */
export function RulesetTalk({ items, onPost }: { items: TalkItem[]; onPost: (note: string, topic: Topic) => Promise<boolean> }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={"talk-ruleset" + (open ? " open" : "")} data-testid="ruleset-talk">
      <button className="talk-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="tw">{open ? "▾" : "▸"}</span><Ico name="bubble" />
        <span className="talk-title">Discuss the ruleset</span>
        {items.length > 0 && <span className="talk-n">{items.length}</span>}
      </button>
      {open && <>
        <p className="talk-d">New rules (a domain expert's heuristic counts), other approaches, whether a rule is needed. Claude
          reads these in the prompt.</p>
        <Thread items={items} />
        <Composer placeholder="A thought about the catalog's rules as a whole…" topics={["new-rule", "approach", "other"]} onPost={onPost} />
      </>}
    </div>
  );
}
