/**
 * The dock: the state of the composition, always visible, never persuasive.
 *
 * It counts what the engine reported (Tier 0 of every zone, declared gaps, open
 * contradictions) and what the operator has done about it, and when the
 * signature is blocked it says by what and links to it. It never suggests a
 * choice — there is no "recommended", no score and no sorting here, for the same
 * reason there is none in the candidate cards.
 */

import { useComposition } from './composition'
import { PrimaryButton } from '../../components/ui'

export function ComposerDock({ onOpenSign }: { onOpenSign: () => void }) {
  const { progress, signed, candidates, focusOn } = useComposition()
  const { tier0Done, tier0Total, gaps, gapsAcknowledged, conflictsOpen, blockers } = progress
  const blocked = signed || !candidates || blockers.length > 0
  const first = blockers[0]

  return (
    <div
      aria-live="polite"
      className="fixed inset-x-0 bottom-0 z-50 border-t-2 border-ink bg-surface px-6 py-3 shadow-[0_-4px_18px_rgba(24,34,48,.08)] max-mid:px-3 max-mid:py-2.5"
      data-screen-label="ComposerDock"
    >
      <div className="mx-auto flex max-w-298 flex-wrap items-center justify-between gap-6 max-mid:gap-2.5">
        <div className="flex flex-wrap items-center gap-5 max-mid:gap-3.5">
          <div
            className="flex flex-col gap-1.25"
            title="Requisitos que el nivel de seguridad de la zona o la ley hacen obligatorios. Tienen que estar todos decididos para poder firmar."
          >
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-[11px] font-semibold tracking-[0.08em] text-ink-2 uppercase">
                Obligatorios decididos
              </span>
              <span className="font-mono text-xs font-semibold text-ink">
                {tier0Done}/{tier0Total}
              </span>
            </div>
            <span className="block h-2 w-46 overflow-hidden rounded-[5px] bg-track">
              <span
                className={`block h-full ${tier0Total && tier0Done >= tier0Total ? 'bg-ok' : 'bg-accent'}`}
                style={{
                  width: `${tier0Total ? Math.round((tier0Done / tier0Total) * 100) : 0}%`,
                }}
              />
            </span>
          </div>

          <span className="block h-8.5 w-px bg-[#e0dcd3] max-mid:hidden" />

          <div
            className="flex flex-none flex-col gap-0.75"
            title="Requisitos que no quedan cubiertos por ningún control. Aceptarlos por escrito es una salida válida; ignorarlos, no."
          >
            <span className="text-[10.5px] font-semibold tracking-[0.08em] whitespace-nowrap text-ink-4 uppercase">
              Sin cobertura
            </span>
            <span className="text-[12.5px] leading-none whitespace-nowrap text-ink-3">
              <b className="font-mono text-[13px] font-semibold text-alert">{gaps}</b> ·{' '}
              {gapsAcknowledged} aceptados por escrito
            </span>
          </div>

          <div
            className="flex flex-none flex-col gap-0.75"
            title="Casos en los que dos marcos piden cosas incompatibles y el sistema te deja elegir a ti."
          >
            <span className="text-[10.5px] font-semibold tracking-[0.08em] whitespace-nowrap text-ink-4 uppercase">
              Decisiones pendientes
            </span>
            <span className="text-[12.5px] leading-none whitespace-nowrap text-ink-3">
              <b className="font-mono text-[13px] font-semibold text-warn">{conflictsOpen}</b> ·
              conflictos sin resolver
            </span>
          </div>
        </div>

        <div className="ml-auto flex min-w-0 flex-1 flex-wrap items-center justify-end gap-3.5 max-mid:w-full max-mid:flex-[1_1_100%] max-mid:[&_button]:min-h-11 max-mid:[&_button]:flex-auto">
          {!signed && first ? (
            <span className="min-w-0 flex-initial text-right text-xs text-alert-ink">
              Aún no puedes firmar:{' '}
              <a
                href="#"
                onClick={(event) => {
                  event.preventDefault()
                  focusOn(`cap-${first.zoneId}-${first.capabilityId}`, first.zoneId, 2)
                }}
              >
                {first.text}
                {blockers.length > 1 ? ` (y ${blockers.length - 1} cosa(s) más)` : ''}
              </a>
            </span>
          ) : null}
          <PrimaryButton testId="dock-sign" tone="ink" disabled={blocked} onClick={onOpenSign}>
            Firmar la línea base
          </PrimaryButton>
        </div>
      </div>
    </div>
  )
}
