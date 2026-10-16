import { useEffect, useRef, useState } from 'react'

type Props = {
  mode: 'reject' | 'comment'
  label: string
  text: string
  rejected: boolean // already rejected: the comment is its reason and cannot be emptied
  onSave: (text: string) => void
  onCancel: () => void
  onUndo: () => void
}

/** Where a reviewer writes about a field: the reason for rejecting it, or a comment left in passing.
 *  The cursor is already in the box. A rejection is not recorded until it has a reason. */
export function NoteBox({ mode, label, text: initial, rejected, onSave, onCancel, onUndo }: Props) {
  const [text, setText] = useState(initial)
  const box = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    box.current?.focus()
    box.current?.setSelectionRange(initial.length, initial.length)
  }, [initial])
  const reject = mode === 'reject'
  const needed = (reject || rejected) && !text.trim()
  const save = () => (needed ? box.current?.focus() : onSave(text.trim()))
  return (
    <div className={'pop note' + (reject ? ' reject' : '')} onClick={(e) => e.stopPropagation()}>
      <div className="reject-head">
        {reject ? <><span className="x">✗</span> Reject <b>{label}</b></> : <>Comment on <b>{label}</b></>}
      </div>
      <textarea
        ref={box}
        className="in"
        rows={3}
        placeholder={reject ? 'Why is xTRA’s value wrong? A rejection needs a reason.' : 'Anything the next reader should know about this field'}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          // Keys typed here stay here: saving closes the box, and the same Enter must not then open the next course.
          e.stopPropagation()
          if (e.key === 'Enter' && !e.shiftKey) (e.preventDefault(), save())
          else if (e.key === 'Escape') (e.preventDefault(), onCancel())
        }}
      />
      <div className="reject-foot">
        <span className="faint">
          <kbd>Enter</kbd> {reject ? 'reject' : 'save'} · <kbd>⇧ Enter</kbd> new line · <kbd>Esc</kbd> cancel
          {!reject && !rejected && ' · a comment counts as having looked at the field'}
        </span>
        <span className="sp" />
        {rejected && <button className="linkish" onClick={onUndo}>Undo rejection</button>}
        <button className="btn primary" disabled={needed} title={needed ? 'A rejection needs a reason' : undefined} onClick={save}>{reject && !rejected ? 'Reject' : 'Save'}</button>
      </div>
    </div>
  )
}
