/**
 * Etapa 2 — candidates: the central contribution, on screen.
 *
 * A crosswalk translates (A ≈ B). What this stage shows is every equivalent
 * option for a requirement *in this zone* — framework, jurisdiction, strength,
 * how much it covers, where the equivalence comes from — next to each other,
 * with the engine's reason for each one and no recommendation attached.
 * Underneath, what was left out of this zone and why, which is a deliverable of
 * the baseline rather than noise.
 *
 * The copy names things the way the operator does: requisito, control, nivel.
 * The engine's own vocabulary (`mapping_type`, `tier_0`, rule ids) lives in the
 * label maps and in tooltips, never in a visible label.
 */

import { useEffect, useState } from 'react'

import {
  GATING_OUTCOME,
  MAPPING_TYPE,
  PROVENANCE,
  RETRIEVAL_STATUS,
  TIER,
  ZONE_DOMAIN,
} from '../../../lib/labels'
import { usePage } from '../../../lib/paging'
import { useActiveZone, useComposition } from '../composition'
import { CapabilityCard } from '../candidates/CapabilityCard'
import { Caps, Hint, InfoButton, Modal, Notice, Pager, PrimaryButton, Section, Tag } from '../../../components/ui'
import { Working } from '../Working'

/** How many discarded controls are readable at once. */
const GATING_PER_PAGE = 5

/** The deterministic pipeline, named the way the operator reads it. */
const COMPUTING = [
  'buscando en el catálogo qué controles equivalen a cada requisito, en todos los marcos',
  'resolviendo los solapes y los conflictos entre marcos',
  'apartando los mecanismos que este activo no puede tener, con su motivo',
  'ordenando en obligatorios y discrecionales, y repartiéndolos por fases',
  'consultando el buscador para añadir sugerencias, que solo amplían las opciones',
]

/**
 * Read once, and the rest of the screen becomes readable — so it is offered
 * rather than imposed. It teaches the notation; it declares nothing, which is
 * what makes it safe to keep behind a button while the engine's own statements
 * (gaps, conflicts, exclusions) stay on the page where they cannot be closed.
 */
function Legend() {
  return (
    <div>
      <div className="grid gap-x-6 gap-y-1.5 text-[11.5px] leading-[1.5] text-ink-3 [grid-template-columns:repeat(auto-fit,minmax(250px,1fr))]">
        {(['total', 'partial', 'compensatory', 'contextual'] as const).map((type) => (
          <div key={type}>
            <span className="mr-1.5 text-accent">{MAPPING_TYPE[type].glyph}</span>
            <b>{MAPPING_TYPE[type].label}</b> — {MAPPING_TYPE[type].note}
          </div>
        ))}
        <div>
          <span className="mr-1.5 inline-block h-2.5 w-4 rounded-[2px] border border-solid border-[#7d7466] align-middle" />
          <b>{PROVENANCE.official_crosswalk.label}</b> — {PROVENANCE.official_crosswalk.note}
        </div>
        <div>
          <span className="mr-1.5 inline-block h-2.5 w-4 rounded-[2px] border border-dashed border-[#b5ad9d] align-middle" />
          <b>{PROVENANCE.author_judgment.label}</b> — {PROVENANCE.author_judgment.note}
        </div>
        <div>
          <span className="mr-1.5 rounded-sm bg-ink px-1.5 py-0.5 text-[9.5px] font-bold text-white">
            {TIER.tier_0.label}
          </span>
          {TIER.tier_0.note}
        </div>
        <div>
          <span className="mr-1.5 rounded-sm border border-ink-5 px-1.5 py-0.5 text-[9.5px] font-bold text-ink-2">
            {TIER.tier_1.label}
          </span>
          {TIER.tier_1.note}
        </div>
      </div>
      <Hint className="mt-2.5">
        Las opciones no vienen ordenadas por «cuál es mejor», ni se oculta ninguna: se agrupan por
        cuánto cubren y, dentro de cada grupo, por marco. La elección es tuya.
      </Hint>
    </div>
  )
}

/**
 * Paged at five, and the count in the heading is the count of the whole list.
 *
 * This panel is a deliverable — it is what answers an auditor asking why a
 * catalog control is not in the baseline — so the pager may shorten the scroll
 * and nothing else: every exclusion is still here, page by page, in the core's
 * own order.
 */
function GatingPanel() {
  const zone = useActiveZone()
  const decisions = zone?.capabilities.flatMap((capability) => capability.gating.excluded) ?? []
  const page = usePage(decisions, GATING_PER_PAGE, zone?.zone.zone_id)
  if (!zone) return null

  return (
    <div className="mt-6 border-t border-line-2 pt-4">
      <Caps className="mb-1">
        Controles descartados en esta zona, y por qué
        {decisions.length > 0 ? ` (${decisions.length})` : ''}
      </Caps>
      <Hint className="mb-2.5">
        Esta lista forma parte del entregable: justifica ante un auditor por qué un control del
        catálogo no aparece en la línea base. Descartar un <b>control</b> nunca elimina el{' '}
        <b>requisito</b> que había detrás.
      </Hint>
      {decisions.length === 0 ? (
        <p className="m-0 text-[12.5px] text-ink-4">
          En esta zona no se ha descartado ningún control: todos los del catálogo son aplicables.
        </p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {page.slice.map((decision, index) => {
            const outcome = GATING_OUTCOME[decision.outcome]
            return (
              <div
                key={`${decision.control_id}-${decision.capability_id}-${page.from + index}`}
                data-testid="gating-decision"
                data-outcome={decision.outcome}
                className="flex flex-wrap items-baseline gap-2.5 rounded-[5px] border border-line-2 bg-surface-2 px-3 py-2 text-[12.5px]"
              >
                <span className="min-w-[150px] flex-none font-mono text-[11px] font-semibold">
                  {decision.control_id}
                </span>
                <span
                  title={outcome.note}
                  className={`flex-none cursor-help rounded-sm px-[7px] py-0.5 text-[10px] font-semibold ${outcome.className}`}
                >
                  {outcome.label}
                </span>
                <span className="text-ink-3">{decision.rationale}</span>
                {decision.evidence.length > 0 ? (
                  <span
                    title="En qué se basa la exclusión"
                    className="text-[11px] text-ink-4"
                  >
                    ({decision.evidence.join(' · ')})
                  </span>
                ) : null}
                <Tag title={`Regla aplicada: ${decision.rule_id}`}>regla documentada</Tag>
              </div>
            )
          })}
        </div>
      )}
      <Pager
        page={page.page}
        pages={page.pages}
        from={page.from}
        to={page.to}
        total={page.total}
        noun="controles descartados"
        onPage={page.setPage}
      />
    </div>
  )
}

function Roadmap() {
  const zone = useActiveZone()
  if (!zone || zone.phases.length === 0) return null

  return (
    <div className="mt-6 border-t border-line-2 pt-4">
      <Caps className="mb-1">Plan de implantación por fases</Caps>
      <Hint className="mb-2.5">
        En qué orden conviene abordar el trabajo. La primera fase es el bloque obligatorio: no es
        una clasificación de importancia, es lo que tiene que estar completo.
      </Hint>
      <div className="flex flex-col gap-1.5">
        {zone.phases.map((phase) => (
          <div
            key={phase.index}
            className="rounded-[5px] border border-line-2 bg-surface-2 px-3 py-2 text-[12.5px]"
          >
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="text-[11.5px] font-semibold">Fase {phase.index + 1}</span>
              <span className="font-semibold">{phase.name}</span>
              <Tag
                title={TIER[phase.tier].note}
                className={phase.tier === 'tier_0' ? 'bg-ink text-white' : 'bg-[#eef0f2] text-ink-2'}
              >
                {TIER[phase.tier].label}
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
    explaining,
  } = useComposition()
  const zone = useActiveZone()
  const [showDerivation, setShowDerivation] = useState(false)
  const [showLegend, setShowLegend] = useState(false)

  const ready = Boolean(profile)
  // `explaining` is a "zone|capability" key; the operator needs the name.
  const explainingName = explaining
    ? (zone?.capabilities.find((c) => explaining.endsWith(`|${c.capability_id}`))?.capability_name ??
      explaining.split('|')[1])
    : null

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
      <Section id="s3" step={2} title="Elige los controles de cada requisito">
        <p className="m-0 text-[13px] text-ink-4">
          Antes hay que completar la ficha del activo en el paso 1.
          {missing.length > 0 ? ` Todavía faltan ${missing.length} dato(s).` : ''}
        </p>
      </Section>
    )
  }

  return (
    <Section
      id="s3"
      step={2}
      title="Elige los controles de cada requisito"
      hint="Para cada requisito de esta zona verás, unas al lado de otras, todas las opciones equivalentes que ofrecen los distintos marcos. Marca la que vas a implantar y escribe por qué: esa razón es la que quedará registrada."
      scope={zone ? `${ZONE_DOMAIN[zone.zone.domain]} · ${zone.zone.zone_id}` : undefined}
    >
      {/* Two explanations of the screen, offered instead of imposed: the stage
          opens on the options themselves, and the operator asks for the reading
          they need. Nothing the engine *decided* is behind a button. */}
      <div className="mb-4 flex flex-wrap gap-2">
        {zone ? (
          <InfoButton onClick={() => setShowDerivation(true)}>Por qué esta zona es así</InfoButton>
        ) : null}
        <InfoButton onClick={() => setShowLegend(true)}>Cómo leer las opciones</InfoButton>
      </div>

      <Modal
        open={showDerivation && zone !== null}
        onClose={() => setShowDerivation(false)}
        title="Por qué esta zona es así"
      >
        <p className="m-0 text-[13px] leading-[1.6] text-ink-2">{zone?.zone.derivation}</p>
      </Modal>

      <Modal open={showLegend} onClose={() => setShowLegend(false)} title="Cómo leer las opciones">
        <Legend />
      </Modal>

      {candidatesLoading ? (
        <div className="mb-4">
          <Working
            testId="candidates-working"
            title="El motor está calculando las opciones de esta zona"
            subtitle="Reglas deterministas, no IA: el asistente no elige ni ordena nada aquí"
            lead="Está haciendo, requisito a requisito:"
            items={COMPUTING}
            footnote="La primera vez después de arrancar el sistema tarda más, porque además se cargan los datos de búsqueda; las siguientes son cuestión de segundos."
          />
        </div>
      ) : null}

      {explaining ? (
        <div className="mb-3.5">
          <Notice tone="warn" label="REDACTANDO">
            El asistente está escribiendo las explicaciones de «{explainingName}». Tarda varios
            minutos porque el modelo corre en este equipo. No cambia el orden de las opciones ni
            marca ninguna como preferida: tus decisiones siguen intactas.
          </Notice>
        </div>
      ) : null}

      {candidatesError ? (
        <div className="mb-3.5">
          <Notice tone="alert" label="NO SE PUDO CALCULAR">
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
            {RETRIEVAL_STATUS[candidates.retrieval.status]}
            {candidates.retrieval.notice ? ` — ${candidates.retrieval.notice}` : ''} Se muestran
            igualmente todas las opciones del catálogo: la búsqueda solo sirve para <i>añadir</i>{' '}
            sugerencias, nunca para quitar opciones. Puedes continuar con normalidad.
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
              <Notice tone="warn" label="TE TOCA DECIDIR">
                Hay {zone.outstanding_capability_ids.length} requisito(s) obligatorio(s) de esta
                zona que el sistema no puede cerrar por sí solo:{' '}
                <span className="font-mono">{zone.outstanding_capability_ids.join(', ')}</span>. Se
                cierran de una de estas tres formas: eligiendo un control, declarando una medida
                compensatoria, o aceptando por escrito que quedará sin cubrir.
              </Notice>
            </div>
          ) : null}

          {/* Keyed by zone as well as capability: the cards hold their own
              open/closed state, and switching zone starts a new reading. */}
          <div className="flex flex-col gap-4">
            {zone.capabilities.map((capability, index) => (
              <CapabilityCard
                key={`${zone.zone.zone_id}-${capability.capability_id}`}
                capability={capability}
                defaultOpen={index === 0}
                conflicts={zone.open_decisions.filter(
                  (conflict) => conflict.capability_id === capability.capability_id,
                )}
              />
            ))}
          </div>

          <GatingPanel />
          <Roadmap />

          <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-line-2 pt-4">
            <PrimaryButton
              onClick={() => void loadCandidates()}
              disabled={candidatesLoading || explaining !== null}
              title={
                explaining
                  ? 'Espera a que termine la explicación en curso: un cálculo nuevo la descartaría.'
                  : undefined
              }
            >
              Volver a calcular las opciones
            </PrimaryButton>
            <span className="max-w-[560px] text-[11.5px] leading-[1.5] text-ink-4">
              Tus decisiones no se pierden al recalcular. Cada cálculo queda anotado en el registro
              del paso 5 ({candidates?.audit_events ?? 0} anotaciones en el último).
            </span>
          </div>
        </>
      ) : null}
    </Section>
  )
}
