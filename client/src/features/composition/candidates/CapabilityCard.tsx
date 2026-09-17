import { useState, type ReactNode } from 'react'

import type { CapabilityCandidates, Conflict, RetrievalCut } from '../../../api/types'
import {
  CAPABILITY_STATUS,
  CONFLICT_TYPE,
  FR_MEANING,
  GAP_KIND,
  RESOLUTION_METHOD,
  TIER,
  coverageText,
} from '../../../lib/labels'
import { declaredGap, pickedCoverage, useComposition } from '../composition'
import { Caps, Checkbox, Fold, Hint, Meter, Tag } from '../../../components/ui'
import { CatalogOption, RetrievedOption } from './OptionCard'

const CATALOG_SHOWN = 6
const SUGGESTIONS_SHOWN = 5
const DISPLACED_SHOWN = 6

function foldTail<T>(
  options: T[],
  limit: number,
  frameworkOf: (option: T) => string,
): { shown: T[]; folded: T[] } {
  if (options.length <= limit) return { shown: options, folded: [] }

  const keep = new Set(options.slice(0, limit))
  const represented = new Set(options.slice(0, limit).map(frameworkOf))
  for (const option of options.slice(limit)) {
    if (represented.has(frameworkOf(option))) continue
    represented.add(frameworkOf(option))
    keep.add(option)
  }
  // Both lists keep the core's order: folding rearranges nothing.
  return {
    shown: options.filter((option) => keep.has(option)),
    folded: options.filter((option) => !keep.has(option)),
  }
}

function FoldToggle({
  open,
  onToggle,
  children,
}: {
  open: boolean
  onToggle: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="cursor-pointer border-none bg-transparent pt-2 text-xs font-semibold text-ink-3 hover:text-ink"
    >
      {open ? '▾' : '▸'} {children}
    </button>
  )
}

function ConflictPanel({
  conflict,
  picked,
  onPick,
  disabled,
}: {
  conflict: Conflict
  picked: string[]
  onPick: (controlId: string) => void
  disabled: boolean
}) {
  const resolved = conflict.control_ids.some((id) => picked.includes(id))
  return (
    <div
      data-testid="conflict"
      data-resolved={resolved}
      className="my-2.5 rounded-md border border-warn-line bg-warn-tint px-3.5 py-3 text-[12.5px] text-warn-ink"
    >
      <div className="mb-1.5 flex items-baseline gap-2">
        <span className="flex-none rounded-sm bg-warn px-1.5 py-0.5 text-[9.5px] font-semibold tracking-[0.08em] text-white">
          DECIDE TÚ
        </span>
        <span>
          <b title={CONFLICT_TYPE[conflict.conflict_type].note} className="cursor-help">
            {CONFLICT_TYPE[conflict.conflict_type].label}
          </b>
          <span title={conflict.rule_id ? `Regla aplicada: ${conflict.rule_id}` : undefined}>
            {' '}
            · el sistema {RESOLUTION_METHOD[conflict.method]}, pero la elección final es tuya.
          </span>{' '}
          {conflict.rationale}
        </span>
      </div>
      <div className="my-2 flex flex-wrap gap-2">
        {conflict.control_ids.map((controlId) => {
          const chosen = picked.includes(controlId)
          return (
            <button
              key={controlId}
              type="button"
              disabled={disabled}
              onClick={() => onPick(controlId)}
              className={`cursor-pointer rounded-[5px] border px-3 py-1.5 text-xs font-semibold text-warn-ink ${
                chosen ? 'border-warn bg-[#f7ecc9]' : 'border-warn-line bg-warn-tint-2'
              }`}
            >
              {chosen ? '●' : '○'} me quedo con <span className="font-mono">{controlId}</span>
            </button>
          )
        })}
      </div>
      <div className="text-[11.5px] leading-normal">
        {resolved
          ? 'Decidido. Escribe abajo por qué: se registrará tanto el control que eliges como el que descartas.'
          : 'Cuando dos marcos piden cosas incompatibles, el sistema no elige por ti: te lo plantea. Marca cuál se aplica en esta zona.'}
      </div>
    </div>
  )
}

export function CapabilityCard({
  capability,
  conflicts,
  defaultOpen = false,
}: {
  capability: CapabilityCandidates
  conflicts: Conflict[]
  defaultOpen?: boolean
}) {
  const {
    selectionsFor,
    toggleSelection,
    reasonFor,
    setReason,
    gapAccepted,
    toggleGap,
    signed,
    explaining,
    explainCapability,
    expandRequest,
  } = useComposition()

  /** `honoured` is the expand request this card has already answered. */
  const [fold, setFold] = useState<{ open: boolean; honoured: string | null }>({
    open: defaultOpen,
    honoured: null,
  })
  const [showSuperseded, setShowSuperseded] = useState(false)
  const [showFoldedOptions, setShowFoldedOptions] = useState(false)
  const [showFoldedSuggestions, setShowFoldedSuggestions] = useState(false)
  const zoneId = capability.zone_id
  const capabilityId = capability.capability_id
  const picked = selectionsFor(zoneId, capabilityId)
  const reason = reasonFor(zoneId, capabilityId)
  const accepted = gapAccepted(zoneId, capabilityId)
  const gap = declaredGap(capability)
  const tier0 = capability.priority.tier === 'tier_0'

  const eligible = capability.resolution.options.filter((o) => o.status !== 'superseded')
  const superseded = capability.resolution.options.filter((o) => o.status === 'superseded')
  const suggestions = (capability.retrieval?.retrieved ?? []).filter(
    (hit) => hit.relation === 'widens',
  )
  const options = foldTail(eligible, CATALOG_SHOWN, (o) => o.control.framework)
  // No framework rule on suggestions: they are not equivalences, so there is no
  // side-by-side reading to protect — just a long similarity-ordered tail to fold.
  const suggested = foldTail(suggestions, SUGGESTIONS_SHOWN, () => '')
  const explanationOf = (controlId: string) =>
    capability.explanations?.explanations.find((e) => e.control_id === controlId)

  const decided = picked.length > 0 || accepted
  // What this zone can reach, and what the selection reaches of it. The first is
  // the engine's; the second is provisional until the baseline is composed.
  const available = capability.resolution.coverage
  const chosen = pickedCoverage(capability, picked)
  const meterTone =
    chosen.value >= 1 ? 'bg-ok' : accepted || (gap && picked.length === 0) ? 'bg-alert' : 'bg-accent'
  const busy = explaining === `${zoneId}|${capabilityId}`
  const domId = `cap-${zoneId}-${capabilityId}`
  const openConflicts = conflicts.filter(
    (conflict) => !conflict.control_ids.some((id) => picked.includes(id)),
  ).length

  // A card navigated to from a step-4 blocker opens itself once; answering the
  // request rather than obeying it forever lets the operator close it again.
  const targeted = expandRequest === domId && fold.honoured !== expandRequest
  const open = targeted || fold.open
  const setOpen = (next: boolean) => setFold({ open: next, honoured: expandRequest })

  return (
    <div
      id={domId}
      data-testid="capability"
      data-open={open}
      data-capability-id={capabilityId}
      data-tier={capability.priority.tier}
      data-outstanding={capability.priority.outstanding}
      data-gap={gap !== null}
      data-conflicts={conflicts.length}
      className={`rounded-[7px] border border-[#e2ded5] bg-surface-3 px-4.5 py-4 ${
        tier0 ? 'border-l-4 border-l-ink' : ''
      }`}
    >
      <div
        role="button"
        tabIndex={0}
        aria-expanded={open}
        data-testid="capability-header"
        onClick={() => setOpen(!open)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            setOpen(!open)
          }
        }}
        className="mb-1 flex cursor-pointer flex-wrap items-center gap-2.5"
      >
        <span className="text-xs font-semibold text-ink-4">{open ? '▾' : '▸'}</span>
        <span className="text-sm font-semibold">{capability.capability_name}</span>
        <span
          className="font-mono text-[10.5px] text-ink-4"
          title="Identificador del requisito en el registro de decisiones"
        >
          {capabilityId}
        </span>
        <span
          title={TIER[capability.priority.tier].note}
          className={`cursor-help rounded-sm px-1.75 py-0.5 text-[10px] font-bold ${
            tier0 ? 'bg-ink text-white' : 'border border-ink-5 text-ink-2'
          }`}
        >
          {TIER[capability.priority.tier].label}
        </span>
        {capability.priority.outstanding ? (
          <Tag
            prose
            className="bg-alert-tint text-alert-ink"
            title="El sistema no puede cerrar este requisito por su cuenta: hace falta una decisión tuya."
          >
            pendiente de tu decisión
          </Tag>
        ) : null}
        {capability.gating.status !== 'covered_by_mechanism' ? (
          <Tag prose className="bg-defer-tint text-defer">
            {CAPABILITY_STATUS[capability.gating.status]}
          </Tag>
        ) : null}
        {/* What the body would have said, for a header that stands alone. */}
        {!open && gap && !accepted ? (
          <Tag prose className="bg-alert-tint text-alert-ink">
            sin cobertura
          </Tag>
        ) : null}
        {!open && openConflicts > 0 ? (
          <Tag prose className="bg-warn-tint text-warn-ink">
            {openConflicts} conflicto(s) por resolver
          </Tag>
        ) : null}
        {!open && decided && reason.trim() === '' ? (
          <Tag prose className="bg-alert-tint text-alert-ink">
            falta escribir por qué
          </Tag>
        ) : null}
        {!open && decided && reason.trim() !== '' ? (
          <Tag prose className="bg-ok-tint text-ok-ink">
            ✓ decidido
          </Tag>
        ) : null}
        <span
          className="ml-auto flex items-center gap-2 max-narrow:ml-0 max-narrow:w-full"
          title={
            'Lo que cubre lo que has elegido, sobre lo que esta zona puede ofrecer. La barra tenue ' +
            'es el máximo disponible; la sólida, lo que alcanza tu selección. Se calcula igual que ' +
            'lo calcula el motor —la mejor opción elegida, nunca la suma de varias— y es ' +
            'provisional: la cifra que se firma la calcula el motor al componer la línea base.'
          }
        >
          <Meter value={chosen.value} ceiling={available} className={meterTone} />
          <span className="text-xs font-semibold">
            {accepted
              ? 'aceptado sin cubrir'
              : picked.length === 0
                ? `sin elegir · hasta el ${coverageText(available)}`
                : `${coverageText(chosen.value)} elegido · hasta el ${coverageText(available)}`}
          </span>
          {/* Named, not folded into the number: a decision that cannot be weighed
              is still a decision, and rounding it to zero would hide it. */}
          {chosen.unweighted.length > 0 ? (
            <span
              className="text-[10.5px] text-ink-4"
              title="Controles que has elegido y no llevan peso de cobertura: las sugerencias del buscador puntúan por parecido, no por cobertura, y una obligación contextual es una exigencia, no un mecanismo. Cuentan como decisión y quedan en el registro; no suman porcentaje."
            >
              + {chosen.unweighted.length} sin peso
            </span>
          ) : null}
        </span>
      </div>

      {!open ? (
        <div className="text-[11.5px] leading-normal text-ink-4">
          {eligible.length > 0
            ? `${eligible.length} opción(es) equivalente(s)${
                suggestions.length > 0 ? ` · ${suggestions.length} sugerencia(s)` : ''
              } — pulsa para abrir`
            : 'Sin controles aplicables en esta zona — pulsa para abrir'}
        </div>
      ) : null}

      {open ? (
        <>
          <div className="mb-2 text-[11.5px] leading-normal text-ink-3">{capability.rationale}</div>

          {tier0 && capability.priority.mandates.length > 0 ? (
            <div className="mb-2 flex flex-wrap items-baseline gap-1">
              <span className="mr-0.5 text-[10.5px] font-semibold text-ink-4">
                Es obligatorio porque:
              </span>
              {capability.priority.mandates.map((mandate, index) => (
                <Tag
                  key={`${mandate.control_id}-${index}`}
                  prose
                  className="bg-[#eef0f2] text-ink-2"
                  title={mandate.rationale}
                >
                  {mandate.source === 'sl_target'
                    ? `obligatorio desde el nivel ${mandate.required_at_sl ?? ''}${
                        mandate.foundational_requirement
                          ? ` en ${FR_MEANING[mandate.foundational_requirement]}`
                          : ''
                      }`
                    : 'obligación legal'}{' '}
                  · <span className="font-mono">{mandate.official_id}</span>
                </Tag>
              ))}
            </div>
          ) : null}

          {conflicts.map((conflict) => (
            <ConflictPanel
              key={conflict.id}
              conflict={conflict}
              picked={picked}
              disabled={signed}
              onPick={(controlId) => toggleSelection(zoneId, capabilityId, controlId)}
            />
          ))}

          {gap ? (
            <div className="my-2.5 rounded-md border border-alert-line bg-alert-tint px-3.5 py-3 text-[12.5px] text-alert-ink">
              <div className="flex items-baseline gap-2">
                <span className="flex-none rounded-sm bg-alert px-1.5 py-0.5 text-[9.5px] font-semibold tracking-[0.08em] text-white">
                  SIN COBERTURA
                </span>
                <span>
                  <b title={GAP_KIND[gap.kind].note} className="cursor-help">
                    {GAP_KIND[gap.kind].label}
                  </b>{' '}
                  — se cubre el {coverageText(gap.coverage)} y queda un{' '}
                  {coverageText(gap.residual)} sin cubrir. {gap.rationale}
                </span>
              </div>
              <div className="my-1.5 mb-2.5 text-xs leading-normal text-alert-soft">
                Este aviso no se puede cerrar ni ocultar, y la falta de cobertura aparecerá en la línea
                base firmada. Es deliberado: nada se descarta en silencio.
              </div>
              <label className="flex cursor-pointer items-center gap-2 text-[12.5px] font-semibold">
                <Checkbox
                  tone="alert"
                  testId="gap-ack"
                  checked={accepted}
                  disabled={signed || picked.length > 0}
                  onClick={() => toggleGap(zoneId, capabilityId)}
                  label="acepto que este requisito quede sin cubrir"
                />
                Acepto que este requisito quede sin cubrir, con la razón que escriba abajo
              </label>
            </div>
          ) : null}

          {eligible.length > 0 ? (
            <Caps className="mt-3.5 mb-1.5">Opciones equivalentes — elige una o varias</Caps>
          ) : null}

          {eligible.length > 0 ? (
            <>
              <div className="mt-2 grid gap-2.5 grid-cols-[repeat(auto-fill,minmax(255px,1fr))]">
                {(showFoldedOptions ? eligible : options.shown).map((option) => (
                  <CatalogOption
                    key={option.control.id}
                    option={option}
                    picked={picked.includes(option.control.id)}
                    disabled={signed}
                    onPick={() => toggleSelection(zoneId, capabilityId, option.control.id)}
                    explanation={explanationOf(option.control.id)}
                  />
                ))}
              </div>
              {options.folded.length > 0 ? (
                <FoldToggle
                  open={showFoldedOptions}
                  onToggle={() => setShowFoldedOptions(!showFoldedOptions)}
                >
                  {showFoldedOptions
                    ? `Plegar las ${options.folded.length} opción(es) del catálogo con menos cobertura`
                    : `Ver las otras ${options.folded.length} opción(es) del catálogo — se pliegan para poder leer la pantalla, no se descartan`}
                </FoldToggle>
              ) : null}
            </>
          ) : (
            <div className="mt-2 rounded-md border border-dashed border-line-dashed bg-surface-2 px-3.5 py-2.5 text-[12.5px] leading-normal text-ink-3">
              Ninguno de los controles del catálogo es aplicable a este activo tal y como está descrito.
              El requisito <b>sigue siendo obligatorio</b>: lo que se ha descartado son los controles,
              no la obligación. Tendrás que declarar una medida compensatoria o aceptar por escrito que
              queda sin cubrir.
            </div>
          )}

          {/* Closed until asked for: these are not equivalences, and the screen is
              about the ones that are. The count is of the whole set, always. */}
          {suggestions.length > 0 ? (
            <Fold
              className="mt-3.5"
              summary={
                <span className="label-caps">
                  Otros controles parecidos que quizá te sirvan ({suggestions.length})
                </span>
              }
            >
              <Hint className="mt-1.5 mb-1.5">
                No son equivalencias del catálogo: son controles que se parecen a este requisito y se te
                ofrecen por si encajan. Adoptar uno es una decisión tuya y queda registrada como tal.
              </Hint>
              <div className="grid gap-2.5 grid-cols-[repeat(auto-fill,minmax(255px,1fr))]">
                {(showFoldedSuggestions ? suggestions : suggested.shown).map((hit) => (
                  <RetrievedOption
                    key={hit.control.id}
                    hit={hit}
                    picked={picked.includes(hit.control.id)}
                    disabled={signed}
                    onPick={() => toggleSelection(zoneId, capabilityId, hit.control.id)}
                    explanation={explanationOf(hit.control.id)}
                  />
                ))}
              </div>
              {suggested.folded.length > 0 ? (
                <FoldToggle
                  open={showFoldedSuggestions}
                  onToggle={() => setShowFoldedSuggestions(!showFoldedSuggestions)}
                >
                  {showFoldedSuggestions
                    ? `Plegar las ${suggested.folded.length} sugerencia(s) con menos parecido`
                    : `Ver las otras ${suggested.folded.length} sugerencia(s), de parecido decreciente`}
                </FoldToggle>
              ) : null}
            </Fold>
          ) : null}

          {superseded.length > 0 ? (
            <>
              <button
                type="button"
                onClick={() => setShowSuperseded(!showSuperseded)}
                className="cursor-pointer border-none bg-transparent pt-2 text-xs font-semibold text-ink-3 hover:text-ink"
              >
                {showSuperseded ? '▾' : '▸'} Ver {superseded.length} opción(es) que otra cubre mejor —
                siguen disponibles si prefieres alguna
              </button>
              {showSuperseded ? (
                <div className="mt-2 grid gap-2.5 grid-cols-[repeat(auto-fill,minmax(255px,1fr))]">
                  {superseded.map((option) => (
                    <CatalogOption
                      key={option.control.id}
                      option={option}
                      picked={picked.includes(option.control.id)}
                      disabled={signed}
                      onPick={() => toggleSelection(zoneId, capabilityId, option.control.id)}
                      explanation={explanationOf(option.control.id)}
                    />
                  ))}
                </div>
              ) : null}
            </>
          ) : null}

          {capability.retrieval && capability.retrieval.set_aside.length > 0 ? (
            <Fold
              className="mt-1"
              summary={`Sugerencias fuera del filtro de esta zona (${capability.retrieval.set_aside.length})`}
            >
              <div
                className="mt-1.5 rounded-[5px] border border-line-2 bg-surface-2 px-2.5 py-2 text-[11px] leading-normal text-ink-3"
                title="Se apartan por el filtro de jurisdicción, zona o tipo de equivalencia que se ha declarado para esta búsqueda"
              >
                No se ofrecen aquí, pero se dejan a la vista porque apartar no es descartar:{' '}
                {capability.retrieval.set_aside
                  .map((candidate) => `${candidate.official_id} (${candidate.excluded_by.join('/')})`)
                  .join(' · ')}
              </div>
            </Fold>
          ) : null}

          {capability.retrieval?.cut && capability.retrieval.cut.dropped > 0 ? (
            <Fold
              className="mt-1"
              summary={`Bajo el corte del recuperador (${capability.retrieval.cut.dropped})`}
            >
              <div
                className="mt-1.5 rounded-[5px] border border-line-2 bg-surface-2 px-2.5 py-2 text-[11px] leading-normal text-ink-3"
                title="La búsqueda evalúa más candidatos de los que muestra. La regla que decide cuántos y cuáles está declarada, y lo que deja fuera se cuenta aquí en vez de desaparecer."
              >
                <CutReport cut={capability.retrieval.cut} />
              </div>
            </Fold>
          ) : null}

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={signed || explaining !== null}
              title={
                explaining && !busy
                  ? 'Se redacta una explicación cada vez. Espera a que termine la que está en curso.'
                  : 'Pide al asistente local un párrafo que explique, en lenguaje llano, qué aporta cada opción. Es solo una ayuda de lectura: no cambia el orden ni marca ninguna como preferida.'
              }
              onClick={() => void explainCapability(zoneId, capabilityId)}
              className="cursor-pointer rounded-[5px] border border-line-strong bg-transparent px-3 py-1.5 text-[11.5px] font-semibold text-ink-2 hover:border-accent hover:text-accent disabled:cursor-default disabled:opacity-50"
            >
              {busy ? 'Escribiendo las explicaciones…' : 'Explícame estas opciones'}
            </button>
            {busy ? (
              <span className="animate-blink text-[11px] text-warn">
                Se escribe una explicación por opción en este mismo equipo: puede tardar varios minutos.
              </span>
            ) : null}
            {capability.explanations?.provenance.notice ? (
              <span className="text-[10.5px] text-ink-4">
                {capability.explanations.provenance.notice}
              </span>
            ) : null}
          </div>

          {decided ? (
            <div className="mt-2.5">
              <div
                className={`mb-1.5 text-[11.5px] font-semibold ${
                  conflicts.length > 0 || accepted || picked.some((id) => supersededIds(capability).has(id))
                    ? 'text-alert-ink'
                    : 'text-ink-3'
                }`}
              >
                {reasonLabel(capability, conflicts.length > 0, accepted, picked)}
              </div>
              <textarea
                value={reason}
                disabled={signed}
                data-testid="reason"
                onChange={(event) => setReason(zoneId, capabilityId, event.target.value)}
                placeholder="Escribe aquí por qué. Se guardará tal cual, con tu nombre, en el registro de decisiones…"
                className={`min-h-11 w-full resize-y rounded-[5px] border bg-surface px-2.5 py-2 text-[12.5px] outline-accent ${
                  reason.trim() === '' ? 'border-alert' : 'border-line'
                }`}
              />
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  )
}

function supersededIds(capability: CapabilityCandidates): Set<string> {
  return new Set(
    capability.resolution.options
      .filter((option) => option.status === 'superseded')
      .map((option) => option.control.id),
  )
}

function reasonLabel(
  capability: CapabilityCandidates,
  hasConflict: boolean,
  accepted: boolean,
  picked: string[],
): string {
  if (accepted)
    return 'Explica por qué aceptas dejar este requisito sin cubrir (obligatorio):'
  if (hasConflict)
    return 'Explica por qué se aplica el control que has elegido y no el otro (obligatorio):'
  if (picked.some((id) => supersededIds(capability).has(id)))
    return 'Has elegido una opción que el sistema había apartado. Explica por qué la prefieres (obligatorio):'
  return 'Explica por qué eliges este control (obligatorio: no se registra una decisión sin su razón):'
}


/** What the retriever's cut left below the line, read off the server's report. */
function CutReport({ cut }: { cut: RetrievalCut }) {
  const first = cut.first_dropped
  return (
    <>
      Se evaluaron {cut.evaluated} y se muestran {cut.retained}
      {cut.band_extension > 0
        ? ` (${cut.policy.floor} por regla y ${cut.band_extension} más por empate)`
        : ''}
      . El resto no se descarta en silencio: queda contado aquí, con la regla que lo dejó fuera.
      {first ? (
        <>
          {' '}
          El primero que no entra es <b className="text-ink-2">{first.official_id}</b> ({first.framework}),
          con similitud {first.score.toFixed(3)}
          {first.margin < 0
            ? `, por encima del último mostrado y desplazado por el tope de marco`
            : ` y a ${first.margin.toFixed(3)} del último mostrado`}
          .
        </>
      ) : null}
      {cut.near_ties_dropped > 0 ? (
        <>
          {' '}
          {cut.near_ties_dropped} de los descartados están a menos de {cut.policy.tie_epsilon.toFixed(2)}{' '}
          del último mostrado: la búsqueda no los distingue de él.
        </>
      ) : null}
      {cut.displaced.length > 0 ? (
        <>
          {' '}
          El tope de {cut.policy.framework_cap} por marco desplazó {cut.displaced.length}, para que un
          solo marco no ocupe la lista entera:{' '}
          {cut.displaced
            .slice(0, DISPLACED_SHOWN)
            .map((candidate) => `${candidate.official_id} (${candidate.score.toFixed(3)})`)
            .join(' · ')}
          {cut.displaced.length > DISPLACED_SHOWN
            ? ` y ${cut.displaced.length - DISPLACED_SHOWN} más`
            : ''}
          .
        </>
      ) : null}
      {cut.cap_yielded > 0 ? (
        <>
          {' '}
          El tope cedió {cut.cap_yielded} hueco(s) para no mostrar menos de {cut.policy.floor}: no había
          candidatos de otros marcos con los que ocuparlos.
        </>
      ) : null}
      {cut.not_returned > 0 ? (
        <>
          {' '}
          Quedan {cut.not_returned} controles del catálogo que la búsqueda no llegó a traer a esta
          profundidad.
        </>
      ) : null}
    </>
  )
}
