/**
 * One capability of one zone: every option the human may choose from, plus
 * everything the engine wants them to know before choosing.
 *
 * Order is the core's own — `mapping_type` first (total → partial →
 * compensatory → contextual), then framework in the catalog's fixed order — and
 * this component preserves it exactly. Nothing is sorted by "best" and nothing
 * is dropped: long lists are folded behind a count that says how many are
 * folded, a candidate the core superseded keeps its rule next to it, and a
 * capability with no candidate at all shows the gap the engine declared instead
 * of an empty box.
 *
 * Folding is a reading aid and stops there. It happens after the response, over
 * a list the engine already computed in full: `/candidates` returns every
 * option, the audit trail records every option, and the counts on screen are of
 * the whole list, not of the visible part. The engine may not discard a
 * candidate — there is not even a similarity threshold in the retriever, for
 * exactly that reason (`RAG_TOP_K` in `server/app/core/config.py`) — so neither
 * may this component pretend the folded ones are not there.
 *
 * The card itself folds for the same reason and under the same rule. A zone with
 * a dozen capabilities is a dozen screens of options, and the operator works
 * through them one at a time; the first is open and the rest are headers. What a
 * closed header may not do is look decided when it is not, so it carries the
 * whole state of the capability — conflicts, gap, whether the decision has its
 * written reason yet — and a card the signature blockers point at opens itself.
 */

import { useState, type ReactNode } from 'react'

import type { CapabilityCandidates, Conflict } from '../../../api/types'
import {
  CAPABILITY_STATUS,
  CONFLICT_TYPE,
  FR_MEANING,
  GAP_KIND,
  RESOLUTION_METHOD,
  TIER,
  coverageText,
} from '../../../lib/labels'
import { declaredGap, useComposition } from '../composition'
import { Caps, Checkbox, Fold, Hint, Meter, Tag } from '../../../components/ui'
import { CatalogOption, RetrievedOption } from './OptionCard'

/** How many options stay open before the tail folds. */
const CATALOG_SHOWN = 6
const SUGGESTIONS_SHOWN = 5

/**
 * The first `limit` options, plus the first option of any framework that those
 * would have left off screen.
 *
 * The exception is the whole point. The core orders candidates by mapping type,
 * so a plain "first six" front-loads the `total` mappings and pushes the
 * `contextual` ones — which is where NIS2 and IMO always are, by design, since a
 * legal obligation is an exigency and never a mechanism — off the end. On
 * `CAP-PR-CRYPTO` that cut would leave six IEC and CIS options on screen and
 * fold away both CSF readings *and* the European obligation, on the one screen
 * built to show the same requirement answered by different frameworks and
 * jurisdictions. The fold may shorten the list; it may not quietly turn a
 * multi-framework choice into a single-framework one.
 */
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
  // No framework rule on the suggestions: they are declared *not* to be
  // equivalences, so there is no side-by-side reading to protect here — only a
  // long tail of near-matches, in descending similarity, that makes the screen
  // unreadable before the operator reaches the options that are.
  const suggested = foldTail(suggestions, SUGGESTIONS_SHOWN, () => '')
  const explanationOf = (controlId: string) =>
    capability.explanations?.explanations.find((e) => e.control_id === controlId)

  const decided = picked.length > 0 || accepted
  const busy = explaining === `${zoneId}|${capabilityId}`
  const domId = `cap-${zoneId}-${capabilityId}`
  const openConflicts = conflicts.filter(
    (conflict) => !conflict.control_ids.some((id) => picked.includes(id)),
  ).length

  // Step 4 links every blocker to the capability it is about, so a card that is
  // navigated to opens itself — once. Answering the request rather than obeying
  // it forever is what lets the operator close the card again afterwards.
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
          title="Cuánto del requisito queda cubierto por los controles disponibles en esta zona. Lo calcula el sistema, no la pantalla."
        >
          <Meter
            value={capability.resolution.coverage}
            className={
              gap ? 'bg-alert' : capability.resolution.has_full_mechanism ? 'bg-ok' : 'bg-accent'
            }
          />
          <span className="text-xs font-semibold">
            {coverageText(capability.resolution.coverage)} cubierto
          </span>
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
