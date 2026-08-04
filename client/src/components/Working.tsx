/**
 * The panel a stage shows while it is waiting, in the place the answer will land.
 *
 * Shared so the two long waits — reading the description, computing the options —
 * read as the same thing. The clock is measured; nothing here is an estimate, and
 * neither call streams, so no partial progress is implied.
 */

import { useEffect, useState } from 'react'

export function Working({
  testId,
  title,
  subtitle,
  lead,
  items,
  footnote,
  rows = 3,
}: {
  testId: string
  title: string
  subtitle: string
  /** One line introducing `items`. */
  lead: string
  items: string[]
  footnote: string
  rows?: number
}) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const started = Date.now()
    const timer = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)),
      1000,
    )
    return () => window.clearInterval(timer)
  }, [])

  const clock = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`

  return (
    <div
      data-testid={testId}
      aria-live="polite"
      aria-busy="true"
      className="rounded-md border border-warn-line bg-warn-tint px-3.5 py-3"
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="flex items-baseline gap-2 text-[12.5px] font-semibold text-warn-ink">
          <span className="animate-blink">●</span>
          {title}
        </span>
        <span title="Tiempo que lleva trabajando" className="font-mono text-xs text-warn-ink">
          {clock}
        </span>
      </div>

      <div className="mt-1 text-[11px] text-warn-ink">{subtitle}</div>

      <div className="mt-3 text-[11.5px] leading-[1.5] text-ink-3">
        {lead}
        <ul className="m-0 mt-1 flex list-disc flex-col gap-0.5 pl-5">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>

      <div className="mt-3 flex flex-col gap-1.5" aria-hidden="true">
        {Array.from({ length: rows }, (_, row) => (
          <div key={row} className="rounded-md border border-line-2 bg-surface px-3 py-2">
            <div
              className="animate-shimmer h-2 w-[42%] rounded-sm bg-line-3"
              style={{ animationDelay: `${row * 0.22}s` }}
            />
            <div
              className="animate-shimmer mt-2 h-2 w-[85%] rounded-sm bg-line-3"
              style={{ animationDelay: `${row * 0.22 + 0.11}s` }}
            />
          </div>
        ))}
      </div>

      <p className="m-0 mt-3 text-[11.5px] leading-[1.5] text-ink-4">{footnote}</p>
    </div>
  )
}
