/** Shared shapes of the design: the card, its header, the small chips. */

import { useEffect, useState, type ReactNode } from 'react'

export function Section({
  id,
  step,
  title,
  hint,
  scope,
  dimmed,
  children,
}: {
  id: string
  step: number
  title: ReactNode
  /** One sentence: what the operator does on this screen and why. */
  hint?: string
  scope?: string
  dimmed?: boolean
  children: ReactNode
}) {
  return (
    <section
      id={id}
      className={`rounded-lg border border-line bg-surface px-7 py-6 max-mid:px-3.5 max-mid:py-4 ${dimmed ? 'opacity-60' : ''}`}
    >
      <div className="mb-1.5 flex flex-wrap items-baseline gap-2.5">
        <span className="rounded-sm bg-line-2 px-1.5 py-0.5 text-[10.5px] font-semibold text-ink-2">
          Paso {step} de 5
        </span>
        <h2 className="m-0 text-[17px] font-semibold max-narrow:text-[15px]">{title}</h2>
        {scope ? (
          <span className="rounded-sm bg-[#eef0f2] px-1.75 py-0.5 text-[10.5px] font-medium text-ink-2">
            {scope}
          </span>
        ) : null}
      </div>
      {hint ? <p className="m-0 mb-4 text-[13px] leading-[1.55] text-ink-3">{hint}</p> : null}
      {children}
    </section>
  )
}

/** A quiet explanatory line under a control — never an error, never a status. */
export function Hint({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <p className={`m-0 text-[11.5px] leading-normal text-ink-4 ${className}`}>{children}</p>
}

export function Caps({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`label-caps ${className}`}>{children}</div>
}

export function Mono({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <span className={`font-mono ${className}`}>{children}</span>
}

/**
 * A small chip. Monospace by default because most of them carry an identifier;
 * `prose` for the ones that carry words, where mono reads like a debug dump.
 */
export function Tag({
  children,
  className = 'bg-[#eef0f2] text-ink-2',
  title,
  prose,
}: {
  children: ReactNode
  className?: string
  title?: string
  prose?: boolean
}) {
  return (
    <span
      title={title}
      className={`rounded-sm px-1.5 py-0.5 text-[10px] font-medium ${
        prose ? '' : 'font-mono'
      } ${className}`}
    >
      {children}
    </span>
  )
}

/**
 * A two-layer bar: `ceiling` is the engine's figure, drawn as a ghost segment;
 * `value` is what the selection reaches, drawn solid on top. The ghost keeps the
 * reading honest — a solid bar at 40 % would look like a shortfall when the rest
 * is simply not chosen yet. The client computes only `value` (provisional, via
 * `pickedCoverage`); every figure that reaches a baseline is the engine's.
 */
export function Meter({
  value,
  ceiling,
  className,
}: {
  value: number
  ceiling?: number
  className: string
}) {
  const clamp = (n: number) => Math.round(Math.max(0, Math.min(1, n)) * 100)
  return (
    <span className="relative inline-block h-1.75 w-22.5 overflow-hidden rounded-sm bg-track">
      {ceiling === undefined ? null : (
        <span
          className={`absolute inset-y-0 left-0 opacity-25 ${className}`}
          style={{ width: `${clamp(ceiling)}%` }}
        />
      )}
      <span
        className={`absolute inset-y-0 left-0 ${className}`}
        style={{ width: `${clamp(value)}%` }}
      />
    </span>
  )
}

export function Checkbox({
  checked,
  onClick,
  disabled,
  tone = 'accent',
  label,
  testId,
}: {
  checked: boolean
  onClick: () => void
  disabled?: boolean
  tone?: 'accent' | 'alert'
  label: string
  testId?: string
}) {
  const border = tone === 'alert' ? 'border-alert' : 'border-accent'
  const fill = tone === 'alert' ? 'bg-alert' : 'bg-accent'
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      aria-label={label}
      data-testid={testId}
      disabled={disabled}
      onClick={onClick}
      className={`h-4 w-4 flex-none rounded-sm border-[1.5px] p-0 text-[10px] leading-3.25 font-semibold text-white ${border} ${
        checked ? fill : 'bg-surface'
      } ${disabled ? 'cursor-default opacity-60' : 'cursor-pointer'}`}
    >
      {checked ? '✓' : ''}
    </button>
  )
}

export function PrimaryButton({
  children,
  onClick,
  disabled,
  className = '',
  title,
  tone = 'accent',
  testId,
}: {
  children: ReactNode
  onClick: () => void
  disabled?: boolean
  className?: string
  /** When disabled, why — the operator should never meet a dead button in silence. */
  title?: string
  tone?: 'accent' | 'ink'
  testId?: string
}) {
  const enabled = tone === 'ink' ? 'bg-ink hover:bg-accent-ink' : 'bg-accent hover:bg-accent-ink'
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      data-testid={testId}
      className={`rounded-md border-none px-4 py-2.5 text-[13px] font-semibold text-white ${
        disabled ? 'cursor-default bg-ink-5' : `cursor-pointer ${enabled}`
      } ${className}`}
    >
      {children}
    </button>
  )
}

export function GhostButton({
  children,
  onClick,
  disabled,
  className = '',
}: {
  children: ReactNode
  onClick: () => void
  disabled?: boolean
  className?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`cursor-pointer rounded-md border border-line-strong bg-transparent px-4 py-2 text-[12.5px] font-semibold text-ink-2 hover:border-ink hover:text-ink disabled:cursor-default disabled:opacity-50 ${className}`}
    >
      {children}
    </button>
  )
}

/** A banner the operator cannot dismiss — a declared state, never a toast. */
export function Notice({
  tone,
  label,
  children,
}: {
  tone: 'warn' | 'alert' | 'ok' | 'muted'
  label?: string
  children: ReactNode
}) {
  const tones = {
    warn: 'bg-warn-tint border-warn-line text-warn-ink',
    alert: 'bg-alert-tint border-alert-line text-alert-ink',
    ok: 'bg-ok-tint border-ok-line text-ok-ink',
    muted: 'bg-surface-2 border-line-dashed border-dashed text-ink-3',
  }[tone]
  const badge = {
    warn: 'bg-warn',
    alert: 'bg-alert',
    ok: 'bg-ok',
    muted: 'bg-ink-4',
  }[tone]
  return (
    <div className={`flex items-baseline gap-2.5 rounded-md border px-4 py-3 text-[13px] ${tones}`}>
      {label ? (
        <span
          className={`flex-none rounded-sm px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-[0.08em] text-white ${badge}`}
        >
          {label}
        </span>
      ) : null}
      <span>{children}</span>
    </div>
  )
}

/**
 * Reference material or a take-away choice the operator opens on demand. Never for
 * a decision, warning or anything the engine declared — those stay on the page
 * where they cannot be closed. A dialog nobody opens must not change what they know.
 */
export function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, open])

  if (!open) return null

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-100 flex items-center justify-center bg-[rgba(24,34,48,.45)] p-6 max-narrow:items-start max-narrow:p-3"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
        className="max-h-[80vh] w-full max-w-165 overflow-y-auto rounded-[10px] bg-surface px-7 py-6 shadow-[0_20px_60px_rgba(24,34,48,.3)] max-narrow:max-h-[92vh] max-narrow:px-4 max-narrow:py-4.5"
      >
        <div className="mb-3 flex items-baseline justify-between gap-4">
          <h3 className="m-0 text-base font-semibold">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="flex-none cursor-pointer border-none bg-transparent p-0 text-[11.5px] font-semibold text-ink-3 hover:text-ink"
          >
            cerrar ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

/** The quiet button that opens a `Modal`: an offer to read, not a state. */
export function InfoButton({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="cursor-pointer rounded-[5px] border border-line-strong bg-transparent px-3 py-1.5 text-[11.5px] font-semibold text-ink-2 hover:border-accent hover:text-accent"
    >
      ⓘ {children}
    </button>
  )
}

/**
 * A block the operator opens by hand. The summary count is always of the whole
 * list: folding shortens the screen, never makes anything look smaller than it is.
 * The click is stopped because these live inside clickable cards.
 */
export function Fold({
  summary,
  defaultOpen = false,
  className = '',
  children,
}: {
  summary: ReactNode
  defaultOpen?: boolean
  className?: string
  children: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className={className}>
      <button
        type="button"
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation()
          setOpen(!open)
        }}
        // The option cards are themselves a checkbox: without this, opening a
        // fold with the keyboard would also tick the option it lives in.
        onKeyDown={(event) => event.stopPropagation()}
        className="cursor-pointer border-none bg-transparent p-0 text-left text-xs font-semibold text-ink-3 hover:text-ink"
      >
        {open ? '▾' : '▸'} {summary}
      </button>
      {open ? children : null}
    </div>
  )
}

/** The controls for a `usePage` slice (`lib/paging.ts`). */
export function Pager({
  page,
  pages,
  from,
  to,
  total,
  noun,
  onPage,
}: {
  page: number
  pages: number
  from: number
  to: number
  total: number
  /** What is being paged, in the plural: «controles», «anotaciones». */
  noun: string
  onPage: (page: number) => void
}) {
  if (pages <= 1) return null
  const step =
    'cursor-pointer rounded-[5px] border border-line-strong bg-transparent px-2.5 py-1 text-[11px] font-semibold text-ink-2 hover:border-accent hover:text-accent disabled:cursor-default disabled:opacity-40 disabled:hover:border-line-strong disabled:hover:text-ink-2'
  return (
    <div className="mt-2.5 flex flex-wrap items-center gap-2.5 text-[11.5px] text-ink-3">
      <button type="button" className={step} disabled={page === 0} onClick={() => onPage(page - 1)}>
        ‹ anteriores
      </button>
      <span>
        {from + 1}–{to} de {total} {noun} · página {page + 1} de {pages}
      </span>
      <button
        type="button"
        className={step}
        disabled={page >= pages - 1}
        onClick={() => onPage(page + 1)}
      >
        siguientes ›
      </button>
    </div>
  )
}
