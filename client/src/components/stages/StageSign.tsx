/**
 * Etapa 4 — the signature.
 *
 * What blocks it is not a UI rule: it is the engine's own list of mandates it
 * could not close, plus the contradictions it refused to settle, plus the
 * ledger's refusal to record a decision with a blank justification. Each blocker
 * links to the capability it is about. The server verifies all of it again
 * before signing — this screen exists so the operator is not told at the last
 * step what they could have been told at the first.
 */

import { useComposition } from '../../state/composition'
import { PrimaryButton, Section } from '../ui'

export function StageSign({ onOpenSign }: { onOpenSign: () => void }) {
  const { progress, signed, baseline, candidates, focusOn, choices } = useComposition()
  const blocked = signed || !candidates || progress.blockers.length > 0

  return (
    <Section
      id="s5"
      step={4}
      title="Firma de la baseline"
      scope="activo completo — todas las zonas"
    >
      {signed && baseline ? (
        <div className="text-[13px] text-ok-ink">
          Firmada por <b>{baseline.signed_by}</b> ·{' '}
          <span className="font-mono">{baseline.baseline_id}</span> ·{' '}
          {new Date(baseline.signed_at).toLocaleString('es-ES')} · {baseline.audit_events} entradas
          añadidas a la bitácora.
          <div className="mt-1.5 font-mono text-[11px] text-ink-4">
            versiones:{' '}
            {Object.entries(baseline.versions)
              .map(([name, value]) => `${name} ${value}`)
              .join(' · ')}
          </div>
        </div>
      ) : progress.blockers.length > 0 ? (
        <>
          <p className="m-0 mb-2.5 text-[12.5px] text-ink-3">
            La firma está bloqueada. Cada motivo enlaza con el elemento culpable:
          </p>
          <div className="flex flex-col gap-[5px]">
            {progress.blockers.map((blocker, index) => (
              <div key={index} className="flex items-baseline gap-2 text-[12.5px]">
                <span className="flex-none text-alert">✕</span>
                <a
                  href="#"
                  onClick={(event) => {
                    event.preventDefault()
                    focusOn(`cap-${blocker.zoneId}-${blocker.capabilityId}`, blocker.zoneId, 2)
                  }}
                >
                  {blocker.text}
                </a>
              </div>
            ))}
          </div>
        </>
      ) : candidates ? (
        <p className="m-0 mb-3 text-[13px] font-medium text-ok-ink">
          ✓ Todo mandato que el motor dejó abierto está cerrado, los conflictos elevados están
          resueltos y cada decisión tiene su razón escrita. {choices.length} decisión(es) se
          registrarán al firmar.
        </p>
      ) : (
        <p className="m-0 text-[13px] text-ink-4">
          Pendiente: la etapa 2 tiene que haber pedido candidatos.
        </p>
      )}

      {!signed ? (
        <PrimaryButton tone="ink" className="mt-4" disabled={blocked} onClick={onOpenSign}>
          Firmar baseline
        </PrimaryButton>
      ) : null}
    </Section>
  )
}
