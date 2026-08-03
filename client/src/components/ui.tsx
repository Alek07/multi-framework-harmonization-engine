/** Shared shapes of the UCM-21 design: the card, its header, the small chips. */

import type { ReactNode } from 'react'

export function Section({
  id,
  step,
  title,
  scope,
  dimmed,
  children,
}: {
  id: string
  step: number
  title: string
  scope?: string
  dimmed?: boolean
  children: ReactNode
}) {
  return (
    <section
      id={id}
      className={`rounded-lg border border-line bg-surface px-7 py-6 ${dimmed ? 'opacity-60' : ''}`}
    >
      <div className="mb-1.5 flex flex-wrap items-baseline gap-2.5">
        <span className="font-mono text-xs font-semibold text-ink-4">{step}</span>
        <h2 className="m-0 text-[17px] font-semibold">{title}</h2>
        {scope ? (
          <span className="rounded-sm bg-[#eef0f2] px-[7px] py-0.5 font-mono text-[10px] font-medium text-ink-2">
            {scope}
          </span>
        ) : null}
      </div>
      {children}
    </section>
  )
}

export function Caps({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`label-caps ${className}`}>{children}</div>
}

export function Mono({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <span className={`font-mono ${className}`}>{children}</span>
}

/** A neutral identifier chip — control ids, versions, zone ids. */
export function Tag({
  children,
  className = 'bg-[#eef0f2] text-ink-2',
  title,
}: {
  children: ReactNode
  className?: string
  title?: string
}) {
  return (
    <span
      title={title}
      className={`rounded-sm px-1.5 py-0.5 font-mono text-[10px] font-medium ${className}`}
    >
      {children}
    </span>
  )
}

/** A progress bar the *server* filled in: the client never computes coverage. */
export function Meter({ value, className }: { value: number; className: string }) {
  return (
    <span className="inline-block h-[7px] w-[90px] overflow-hidden rounded-sm bg-track">
      <span
        className={`block h-full ${className}`}
        style={{ width: `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%` }}
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
      className={`h-4 w-4 flex-none rounded-sm border-[1.5px] p-0 text-[10px] leading-[13px] font-semibold text-white ${border} ${
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
  tone = 'accent',
  testId,
}: {
  children: ReactNode
  onClick: () => void
  disabled?: boolean
  className?: string
  tone?: 'accent' | 'ink'
  testId?: string
}) {
  const enabled = tone === 'ink' ? 'bg-ink hover:bg-accent-ink' : 'bg-accent hover:bg-accent-ink'
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
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
