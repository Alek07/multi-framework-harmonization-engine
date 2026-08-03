/**
 * Etapa 2 — candidates: the central contribution, on screen.
 *
 * A crosswalk translates (A ≈ B). What this stage shows is every equivalent
 * option for a capability *in this zone* — framework, jurisdiction, strength,
 * mapping type, coverage weight, tier — next to each other, with the engine's
 * reason for each one and no recommendation attached. Underneath, the gating
 * panel: what was left out of this zone and why, which is a deliverable of the
 * baseline rather than noise.
 */

import { useEffect } from 'react'

import { GATING_OUTCOME, RETRIEVAL_STATUS, ZONE_DOMAIN } from '../../lib/labels'
import { useActiveZone, useComposition } from '../../state/composition'
import { CapabilityCard } from '../candidates/CapabilityCard'
import { Caps, Notice, PrimaryButton, Section, Tag } from '../ui'

function GatingPanel() {
  const zone = useActiveZone()
  if (!zone) return null

  const decisions = zone.capabilities.flatMap((capability) => capability.gating.excluded)

  return (
    <div className="mt-6 border-t border-line-2 pt-4">
      <Caps className="mb-2.5">
        Gating de la zona {zone.zone.zone_id} — exclusiones justificadas (entregable, no ruido)
      </Caps>
      {decisions.length === 0 ? (
        <p className="m-0 text-[12.5px] text-ink-4">
          Ninguna regla de gating excluyó un mecanismo en esta zona.
        </p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {decisions.map((decision, index) => {
            const outcome = GATING_OUTCOME[decision.outcome]
            return (
              <div
                key={`${decision.control_id}-${decision.capability_id}-${index}`}
                data-testid="gating-decision"
                data-outcome={decision.outcome}
                className="flex flex-wrap items-baseline gap-2.5 rounded-[5px] border border-line-2 bg-surface-2 px-3 py-2 text-[12.5px]"
              >
                <span className="min-w-[150px] flex-none font-mono text-[11px] font-semibold">
                  {decision.control_id}
                </span>
                <span
                  className={`flex-none rounded-sm px-[7px] py-0.5 font-mono text-[10px] font-semibold ${outcome.className}`}
                >
                  {outcome.label}
                </span>
                <span className="text-ink-3">
                  {decision.capability_id} · {decision.rationale}
                </span>
                {decision.evidence.length > 0 ? (
                  <span className="font-mono text-[10px] text-ink-4">
                    {decision.evidence.join(' · ')}
                  </span>
                ) : null}
                <Tag title="regla de gating declarada">{decision.rule_id}</Tag>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function Roadmap() {
  const zone = useActiveZone()
  if (!zone || zone.phases.length === 0) return null

  return (
    <div className="mt-6 border-t border-line-2 pt-4">
      <Caps className="mb-2.5">
        Hoja de ruta por fases — la fase 0 es el bloque obligatorio y no es un ranking
      </Caps>
      <div className="flex flex-col gap-1.5">
        {zone.phases.map((phase) => (
          <div
            key={phase.index}
            className="rounded-[5px] border border-line-2 bg-surface-2 px-3 py-2 text-[12.5px]"
          >
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="font-mono text-[11px] font-semibold">fase {phase.index}</span>
              <span className="font-semibold">{phase.name}</span>
              <Tag className={phase.tier === 'tier_0' ? 'bg-ink text-white' : 'bg-[#eef0f2] text-ink-2'}>
                {phase.tier === 'tier_0' ? 'T0' : 'T1'}
              </Tag>
            </div>
            <div className="mt-1 font-mono text-[11px] text-ink-3">
              {phase.capability_ids.join(' · ') || '—'}
            </div>
            <div className="mt-1 text-[11.5px] text-ink-3">{phase.rationale}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function StageCandidates() {
  const {
    candidates,
    candidatesLoading,
    candidatesError,
    loadCandidates,
    profile,
    missing,
    focusRequest,
    clearFocus,
  } = useComposition()
  const zone = useActiveZone()

  const ready = Boolean(profile)

  useEffect(() => {
    if (ready && !candidates && !candidatesLoading && !candidatesError) void loadCandidates()
  }, [candidates, candidatesError, candidatesLoading, loadCandidates, ready])

  useEffect(() => {
    if (!focusRequest) return
    const element = document.getElementById(focusRequest)
    if (element) {
      const top = element.getBoundingClientRect().top + window.scrollY - 130
      window.scrollTo({ top, behavior: 'smooth' })
    }
    clearFocus()
  }, [clearFocus, focusRequest])

  if (!ready) {
    return (
      <Section id="s3" step={2} title="Candidatos por capacidad">
        <p className="m-0 text-[13px] text-ink-4">
          Pendiente: la etapa 1 tiene que dejar un perfil.{' '}
          {missing.length > 0 ? `Faltan ${missing.length} campo(s) del borrador.` : ''}
        </p>
      </Section>
    )
  }

  return (
    <Section
      id="s3"
      step={2}
      title="Candidatos por capacidad"
      scope={zone ? `${ZONE_DOMAIN[zone.zone.domain]} · ${zone.zone.zone_id}` : undefined}
    >
      {zone ? (
        <div className="m-0 mb-2.5 text-xs text-ink-3 italic">{zone.zone.derivation}</div>
      ) : null}

      <p className="m-0 mb-3.5 text-[12.5px] text-ink-3">
        Orden determinista: <span className="font-mono">mapping_type</span> (total → partial →
        compensatory → contextual) y, dentro, marco en el orden fijo del catálogo. Nada se ordena
        por «mejor». Borde <b>sólido</b> = crosswalk oficial · borde <b>punteado</b> = juicio del
        autor.
      </p>

      {candidatesLoading ? (
        <p className="m-0 font-mono text-xs text-ink-4">
          ejecutando el núcleo determinista y la pasada de recuperación… la primera consulta de
          cada arranque carga el modelo de embeddings (~1,1 GB) y tarda más que las siguientes.
        </p>
      ) : null}

      {candidatesError ? (
        <div className="mb-3.5">
          <Notice tone="alert" label="MOTOR">
            {candidatesError}{' '}
            <button
              type="button"
              onClick={() => void loadCandidates()}
              className="cursor-pointer border-none bg-transparent p-0 underline"
            >
              reintentar
            </button>
          </Notice>
        </div>
      ) : null}

      {candidates && candidates.retrieval.status !== 'ok' ? (
        <div className="mb-3.5">
          <Notice tone="muted">
            {RETRIEVAL_STATUS[candidates.retrieval.status]} —{' '}
            {candidates.retrieval.notice ?? ''} Se muestran los candidatos deterministas del
            catálogo. El flujo continúa: la recuperación solo amplía, nunca restringe.
          </Notice>
        </div>
      ) : null}

      {candidates?.explanations_notice ? (
        <div className="mb-3.5">
          <Notice tone="muted">{candidates.explanations_notice}</Notice>
        </div>
      ) : null}

      {zone ? (
        <>
          {zone.outstanding_capability_ids.length > 0 ? (
            <div className="mb-3.5">
              <Notice tone="warn" label="TIER 0">
                El motor no pudo cerrar por sí solo{' '}
                {zone.outstanding_capability_ids.length} mandato(s) de esta zona:{' '}
                <span className="font-mono">
                  {zone.outstanding_capability_ids.join(', ')}
                </span>
                . Se cierran eligiendo un mecanismo, declarando uno compensatorio o aceptando el
                hueco por escrito.
              </Notice>
            </div>
          ) : null}

          <div className="flex flex-col gap-4">
            {zone.capabilities.map((capability) => (
              <CapabilityCard
                key={capability.capability_id}
                capability={capability}
                conflicts={zone.open_decisions.filter(
                  (conflict) => conflict.capability_id === capability.capability_id,
                )}
              />
            ))}
          </div>

          <GatingPanel />
          <Roadmap />

          <div className="mt-6 flex items-center gap-3 border-t border-line-2 pt-4">
            <PrimaryButton onClick={() => void loadCandidates()}>
              Recalcular candidatos · POST /candidates
            </PrimaryButton>
            <span className="text-[11.5px] text-ink-4">
              Cada ejecución escribe sus decisiones en la bitácora ({candidates?.audit_events ?? 0}{' '}
              eventos en la última) y devuelve un{' '}
              <span className="font-mono">run_id</span> nuevo:{' '}
              <span className="font-mono">{candidates?.run_id.slice(0, 8)}</span>.
            </span>
          </div>
        </>
      ) : null}
    </Section>
  )
}
