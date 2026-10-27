// The prototype's icon set (docs/qrspi/prototype/ui/static/app.js), as inline SVG strings.
// Use <Ico name="approved" /> ; the status icons of the rule list are "approved" / "needs work" / "in review".
export const ICON: Record<string, string> = {
  approved: '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="7.5" fill="#12805c"/><path d="m4.8 8.2 2.2 2.2 4.2-4.6" stroke="#fff" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  "needs work": '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="7.5" fill="#d92d20"/><path d="m5.6 5.6 4.8 4.8m0-4.8-4.8 4.8" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/></svg>',
  "in review": '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.6" fill="#fff" stroke="#98a2b3" stroke-width="1.6"/><circle cx="8" cy="8" r="2" fill="#98a2b3"/></svg>',
  signal: '<svg viewBox="0 0 16 16" fill="none"><path d="M8 2.2 14.3 13H1.7L8 2.2Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M8 6.5v3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="8" cy="11.2" r=".8" fill="currentColor"/></svg>',
  open: '<svg viewBox="0 0 16 16" fill="none"><path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2v-7Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>',
  correct: '<svg viewBox="0 0 16 16" fill="none"><path d="m3.5 8.5 3 3 6-7" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  wrong: '<svg viewBox="0 0 16 16" fill="none"><path d="m4.5 4.5 7 7m0-7-7 7" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
  missing: '<svg viewBox="0 0 16 16" fill="none"><path d="M8 3.5v9M3.5 8h9" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
  question: '<svg viewBox="0 0 16 16" fill="none"><path d="M6 6.2a2.1 2.1 0 1 1 3 1.9c-.6.3-1 .8-1 1.5v.4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><circle cx="8" cy="12.2" r=".9" fill="currentColor"/></svg>',
  highlight: '<svg viewBox="0 0 16 16" fill="none"><path d="m9.5 2.5 4 4-6 6H3.5v-4l6-6Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M2 14.5h12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  ext: '<svg viewBox="0 0 16 16" fill="none"><path d="M9 2.5h4.5V7M13.5 2.5 7 9M12 9.5v3.5H3V4h3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  copy: '<svg viewBox="0 0 16 16" fill="none"><rect x="5" y="5" width="8.5" height="8.5" rx="1.5" stroke="currentColor" stroke-width="1.5"/><path d="M11 3V2.5h-8.5V11H3" stroke="currentColor" stroke-width="1.5"/></svg>',
  download: '<svg viewBox="0 0 16 16" fill="none"><path d="M8 2.5v8m0 0L4.8 7.3M8 10.5l3.2-3.2M2.5 13.5h11" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  lock: '<svg viewBox="0 0 20 20" fill="none"><rect x="4" y="9" width="12" height="8.5" rx="2" stroke="currentColor" stroke-width="1.6"/><path d="M7 9V6.5a3 3 0 0 1 6 0V9" stroke="currentColor" stroke-width="1.6"/></svg>',
  bubble: '<svg viewBox="0 0 16 16" fill="none"><path d="M3 3.2h10a1 1 0 0 1 1 1v6.1a1 1 0 0 1-1 1H8.2L5 13.8v-2.5H3a1 1 0 0 1-1-1V4.2a1 1 0 0 1 1-1Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M5 6.4h6M5 8.6h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  dots: '<svg viewBox="0 0 16 16" fill="currentColor"><circle cx="3.5" cy="8" r="1.4"/><circle cx="8" cy="8" r="1.4"/><circle cx="12.5" cy="8" r="1.4"/></svg>',
  spark: '<svg viewBox="0 0 16 16" fill="none"><path d="M8 1.8 9.5 6.5 14.2 8 9.5 9.5 8 14.2 6.5 9.5 1.8 8 6.5 6.5 8 1.8Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  inst: '<svg viewBox="0 0 16 16" fill="none"><path d="M2 6.2 8 2.8l6 3.4M3 6.6h10M4 7v5M6.7 7v5M9.3 7v5M12 7v5M2.5 13.4h11" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  expert: '<svg viewBox="0 0 16 16" fill="none"><circle cx="8" cy="5.5" r="2.7" stroke="currentColor" stroke-width="1.5"/><path d="M2.8 14c.6-2.6 2.7-4.2 5.2-4.2s4.6 1.6 5.2 4.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
};

export function Ico({ name, className }: { name: string; className?: string }) {
  return <span className={"ico " + (className ?? "")} aria-hidden="true" dangerouslySetInnerHTML={{ __html: ICON[name] ?? "" }} />;
}
