/**
 * Etapa 4 — the signature. What blocks it is not a UI rule but the engine's own
 * unclosed mandates, the contradictions it refused to settle, and the ledger's
 * refusal of a blank justification. Each blocker links to its capability. The
 * server re-verifies before signing; this screen just tells the operator early.
 */

import { useNavigate } from '@tanstack/react-router'

import { useComposition } from '../composition'
import { GhostButton, PrimaryButton, Section } from '../../../components/ui'

export function StageSign({ onOpenSign }: { onOpenSign: () => void }) {
  const { progress, signed, baseline, candidates, focusOn, choices } = useComposition()
  const navigate = useNavigate()
  const blocked = signed || !candidates || progress.blockers.length > 0

  return (
    <Section
      id="s5"
      step={4}
      title="Revisa y firma la línea base"
      hint="Último repaso antes de dejarlo por escrito. Al firmar, todas tus decisiones y sus razones quedan registradas de forma permanente y la composición pasa a ser de solo lectura."
      scope="todas las zonas del activo"
    >
      {signed && baseline ? (
        <div className="text-[13px] leading-[1.6] text-ok-ink">
          Firmada por <b>{baseline.signed_by}</b> el{' '}
          {new Date(baseline.signed_at).toLocaleString('es-ES')}. Se han añadido{' '}
          {baseline.audit_events} anotaciones al registro de decisiones.
          <div className="mt-1.5 text-[11px] text-ink-4">
            Referencia de la línea base: <span className="font-mono">{baseline.baseline_id}</span>
            <span
              title={Object.entries(baseline.versions)
                .map(([name, value]) => `${name} ${value}`)
                .join(' · ')}
              className="ml-2 cursor-help underline decoration-dotted"
            >
              ver versiones de catálogo y reglas usadas
            </span>
          </div>
        </div>
      ) : progress.blockers.length > 0 ? (
        <>
          <p className="m-0 mb-2.5 text-[12.5px] leading-[1.55] text-ink-3">
            Todavía no se puede firmar. Falta esto por resolver — pulsa cualquier línea para ir
            directamente a ella:
          </p>
          <div className="flex flex-col gap-1.25">
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
        <p className="m-0 mb-3 text-[13px] leading-[1.55] font-medium text-ok-ink">
          ✓ Todo listo: no queda ningún requisito obligatorio sin decidir, ningún conflicto sin
          resolver y ninguna decisión sin justificar. Al firmar se registrarán {choices.length}{' '}
          decisión(es).
        </p>
      ) : (
        <p className="m-0 text-[13px] text-ink-4">
          Antes hay que pasar por el paso 2 y elegir los controles de cada requisito.
        </p>
      )}

      {signed ? (
        <GhostButton className="mt-4" onClick={() => void navigate({ to: '/' })}>
          Volver a líneas base
        </GhostButton>
      ) : (
        <PrimaryButton tone="ink" className="mt-4" disabled={blocked} onClick={onOpenSign}>
          Firmar la línea base
        </PrimaryButton>
      )}
    </Section>
  )
}
