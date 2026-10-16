import { createContext, useContext, type ReactNode } from 'react'

// Teaching text uses two marks: `like this` is code, and [[Like this]] opens the glossary.
export const GlossaryContext = createContext<(term: string) => void>(() => {})

export function Rich({ text }: { text: string }): ReactNode {
  const open = useContext(GlossaryContext)
  const parts = text.split(/(`[^`]+`|\[\[[^\]]+\]\])/g)
  return parts.map((part, i) => {
    if (part.startsWith('`')) return <code key={i}>{part.slice(1, -1)}</code>
    if (part.startsWith('[[')) {
      const term = part.slice(2, -2)
      return (
        <button key={i} className="gloss" onClick={(e) => (e.stopPropagation(), open(term))} title="What is this?">
          {term}
        </button>
      )
    }
    return part
  })
}

export function Badge({ n }: { n: number }) {
  return <span className={`n n${((n - 1) % 3) + 1}`}>{n}</span>
}

export function Segmented<T extends string>({ value, options, onChange, small }: { value: T; options: [T, ReactNode][]; onChange: (v: T) => void; small?: boolean }) {
  return (
    <span className={'seg' + (small ? ' small' : '')} role="tablist">
      {options.map(([v, label]) => (
        <button key={v} role="tab" aria-selected={v === value} className={v === value ? 'on' : ''} onClick={() => onChange(v)}>
          {label}
        </button>
      ))}
    </span>
  )
}

/** Small line icons, so that actions are icons with a tooltip and not labelled buttons (PD5). */
const PATHS: Record<string, string> = {
  copy: 'M9 9h10v11H9zM5 15V4h10',
  check: 'M4 12.5l5 5L20 6.5',
  edit: 'M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4',
  menu: 'M4 7h16M4 12h16M4 17h16',
  info: 'M12 11v6M12 7.5v.5M12 3a9 9 0 100 18 9 9 0 000-18z',
  unfold: 'M8 9l4-4 4 4M8 15l4 4 4-4',
  left: 'M14 6l-6 6 6 6',
  right: 'M10 6l6 6-6 6',
  close: 'M6 6l12 12M18 6L6 18',
  undo: 'M9 7L4 12l5 5M4 12h10a6 6 0 010 12',
  code: 'M9 7l-5 5 5 5M15 7l5 5-5 5',
  cards: 'M4 5h16v6H4zM4 14h16v5H4z',
  comment: 'M4 5h16v11h-9l-4 4v-4H4z',
  page: 'M6 3h9l4 4v14H6zM14 3v5h5',
  out: 'M10 5H5v14h14v-5M13 4h7v7M20 4l-9 9',
  down: 'M12 4v12M7 11l5 5 5-5M5 20h14',
  plus: 'M12 5v14M5 12h14',
  sidebar: 'M4 5h16v14H4zM9.5 5v14',
  warn: 'M12 4l9.5 16h-19zM12 10v4.5M12 17.2v.3',
  spark: 'M12 3l2.2 6.8L21 12l-6.8 2.2L12 21l-2.2-6.8L3 12l6.8-2.2z',
}
export function Icon({ name, size = 16 }: { name: keyof typeof PATHS | string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={PATHS[name]} />
    </svg>
  )
}
/** An action shown as an icon. Rest the pointer on it for a second and it says what it does and, where
 *  it has one, shows its key. The key is written at the end of the title, in brackets: "Accept (A)". */
export function IconButton({ name, title, onClick, on, disabled }: { name: string; title: string; onClick: () => void; on?: boolean; disabled?: boolean }) {
  const found = title.match(/^(.*?)\s*\(([A-Z]|(?:Shift\+)?Enter|Esc)\)\.?$/)
  const label = (found ? found[1] : title).replace(/\.$/, '')
  return (
    <button className={'ico' + (on ? ' on' : '')} aria-label={title} disabled={disabled} onClick={(e) => (e.stopPropagation(), onClick())}>
      <Icon name={name} />
      <span className="tip" role="tooltip">
        <Icon name={name} size={13} />
        <span>{label}</span>
        {found && <kbd>{found[2].replace('Shift+', '⇧ ')}</kbd>}
      </span>
    </button>
  )
}

/** The two marks that ask for attention: a caution, and "a language model proposed this". */
export function Sign({ kind, title }: { kind: 'warn' | 'lm'; title?: string }) {
  return (
    <span className={'sign ' + kind} title={title ?? (kind === 'lm' ? 'Proposed by the language model' : 'Something to know about this value')}>
      <Icon name={kind === 'lm' ? 'spark' : 'warn'} size={13} />
    </span>
  )
}
