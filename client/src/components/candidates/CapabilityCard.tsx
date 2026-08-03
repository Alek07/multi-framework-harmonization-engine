/**
 * One capability of one zone: every option the human may choose from, plus
 * everything the engine wants them to know before choosing.
 *
 * Order is the core's own — `mapping_type` first (total → partial →
 * compensatory → contextual), then framework in the catalog's fixed order — and
 * this component preserves it exactly. Nothing is sorted by "best", nothing is
 * hidden: a candidate the core superseded is folded away behind a count with its
 * rule next to it, never dropped, and a capability with no candidate at all
 * shows the gap the engine declared instead of an empty box.
 */

import { useState } from 'react'

import type { CapabilityCandidates, Conflict } from '../../api/types'
import {
  CAPABILITY_STATUS,
  CONFLICT_TYPE,
  GAP_KIND,
  RESOLUTION_METHOD,
  TIER,
} from '../../lib/labels'
import { declaredGap, useComposition } from '../../state/composition'
import { Caps, Checkbox, Meter, Tag } from '../ui'
import { CatalogOption, RetrievedOption } from './OptionCard'

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
        <span className="flex-none rounded-sm bg-warn px-1.5 py-0.5 font-mono text-[9.5px] font-semibold tracking-[0.08em] text-white">
          CONFLICTO
        </span>
        <span>
          <b>{CONFLICT_TYPE[conflict.conflict_type]}</b> ·{' '}
          {RESOLUTION_METHOD[conflict.method]}
          {conflict.rule_id ? (
            <>
              {' '}
              · regla <span className="font-mono">{conflict.rule_id}</span>
            </>
          ) : null}{' '}
          · requiere decisión humana. {conflict.rationale}
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
              {chosen ? '●' : '○'} prevalece <span className="font-mono">{controlId}</span>
            </button>
          )
        })}
      </div>
      <div className="text-[11.5px]">
        {resolved
          ? 'Resuelto por el humano. Escribe abajo la razón: se registra con la elección y con el descarte del otro control.'
          : 'El motor no resuelve una contradicción real: la eleva. Elige cuál prevalece.'}
      </div>
    </div>
  )
}

export function CapabilityCard({
  capability,
  conflicts,
}: {
  capability: CapabilityCandidates
  conflicts: Conflict[]
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
  } = useComposition()

  const [showSuperseded, setShowSuperseded] = useState(false)
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
  const explanationOf = (controlId: string) =>
    capability.explanations?.explanations.find((e) => e.control_id === controlId)

  const decided = picked.length > 0 || accepted
  const busy = explaining === `${zoneId}|${capabilityId}`

  return (
    <div
      id={`cap-${zoneId}-${capabilityId}`}
      data-testid="capability"
      data-capability-id={capabilityId}
      data-tier={capability.priority.tier}
      data-outstanding={capability.priority.outstanding}
      data-gap={gap !== null}
      data-conflicts={conflicts.length}
      className={`rounded-[7px] border border-[#e2ded5] bg-surface-3 px-[18px] py-4 ${
        tier0 ? 'border-l-4 border-l-ink' : ''
      }`}
    >
      <div className="mb-1 flex flex-wrap items-center gap-2.5">
        <span className="font-mono text-[12.5px] font-semibold text-ink">{capabilityId}</span>
        <span className="text-sm font-semibold">{capability.capability_name}</span>
        <span
          className={`rounded-sm px-[7px] py-0.5 font-mono text-[10px] font-bold ${
            tier0 ? 'bg-ink text-white' : 'border border-ink-5 text-ink-2'
          }`}
        >
          {TIER[capability.priority.tier]}
        </span>
        {capability.priority.outstanding ? (
          <Tag className="bg-alert-tint text-alert-ink">mandato abierto</Tag>
        ) : null}
        {capability.gating.status !== 'covered_by_mechanism' ? (
          <Tag className="bg-defer-tint text-defer">
            {CAPABILITY_STATUS[capability.gating.status]}
          </Tag>
        ) : null}
        <span className="ml-auto flex items-center gap-2">
          <Meter
            value={capability.resolution.coverage}
            className={
              gap ? 'bg-alert' : capability.resolution.has_full_mechanism ? 'bg-ok' : 'bg-accent'
            }
          />
          <span className="font-mono text-xs font-semibold">
            {capability.resolution.coverage.toFixed(2)}
          </span>
          <span className="text-[10.5px] text-ink-4">servidor</span>
        </span>
      </div>

      <div className="mb-2 text-[11.5px] leading-[1.5] text-ink-3">{capability.rationale}</div>

      {tier0 && capability.priority.mandates.length > 0 ? (
        <div className="mb-2 flex flex-wrap gap-1">
          {capability.priority.mandates.map((mandate, index) => (
            <Tag
              key={`${mandate.control_id}-${index}`}
              className="bg-[#eef0f2] text-ink-2"
              title={mandate.rationale}
            >
              {mandate.source === 'sl_target'
                ? `SL-T ${mandate.required_at_sl ?? ''} ${mandate.foundational_requirement ?? ''}`
                : 'obligación legal'}{' '}
              · {mandate.official_id}
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
            <span className="flex-none rounded-sm bg-alert px-1.5 py-0.5 font-mono text-[9.5px] font-semibold tracking-[0.08em] text-white">
              HUECO
            </span>
            <span>
              <b>{GAP_KIND[gap.kind]}</b> · cobertura {gap.coverage.toFixed(2)} · residual{' '}
              {gap.residual.toFixed(2)} · {gap.rationale}
            </span>
          </div>
          <div className="my-1.5 mb-2.5 text-xs text-alert-soft">
            Este aviso no se puede cerrar ni ocultar; el hueco viaja a la baseline firmada.
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-[12.5px] font-semibold">
            <Checkbox
              tone="alert"
              testId="gap-ack"
              checked={accepted}
              disabled={signed || picked.length > 0}
              onClick={() => toggleGap(zoneId, capabilityId)}
              label="reconozco este hueco"
            />
            Acepto este hueco — se registra como <span className="font-mono">gap_accepted</span> con
            mi razón
          </label>
        </div>
      ) : null}

      {eligible.length > 0 ? (
        <div className="mt-2 grid gap-2.5 [grid-template-columns:repeat(auto-fill,minmax(255px,1fr))]">
          {eligible.map((option) => (
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
      ) : (
        <div className="mt-2 rounded-md border border-dashed border-line-dashed bg-surface-2 px-3.5 py-2.5 text-[12.5px] text-ink-3">
          El catálogo no ofrece ningún mecanismo aplicable aquí tras el gating. La capacidad sigue
          siendo obligatoria: el gating quita mecanismos, nunca requisitos.
        </div>
      )}

      {suggestions.length > 0 ? (
        <>
          <Caps className="mt-3.5 mb-1.5">
            Sugerencias de recuperación — amplían, no son mapeos del catálogo
          </Caps>
          <div className="grid gap-2.5 [grid-template-columns:repeat(auto-fill,minmax(255px,1fr))]">
            {suggestions.map((hit) => (
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
        </>
      ) : null}

      {superseded.length > 0 ? (
        <>
          <button
            type="button"
            onClick={() => setShowSuperseded(!showSuperseded)}
            className="cursor-pointer border-none bg-transparent pt-2 text-xs font-semibold text-ink-3 hover:text-ink"
          >
            {showSuperseded ? '▾' : '▸'} {superseded.length} opción(es) apartada(s) por regla — se
            pueden elegir igualmente
          </button>
          {showSuperseded ? (
            <div className="mt-2 grid gap-2.5 [grid-template-columns:repeat(auto-fill,minmax(255px,1fr))]">
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
        <div className="mt-2.5 rounded-[5px] border border-line-2 bg-surface-2 px-2.5 py-2 text-[11px] text-ink-3">
          <b>Apartados por la lente declarada</b> (apartar no es descartar):{' '}
          {capability.retrieval.set_aside
            .map((candidate) => `${candidate.official_id} (${candidate.excluded_by.join('/')})`)
            .join(' · ')}
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={signed || explaining !== null}
          onClick={() => void explainCapability(zoneId, capabilityId)}
          className="cursor-pointer rounded-[5px] border border-line-strong bg-transparent px-3 py-1.5 text-[11.5px] font-semibold text-ink-2 hover:border-accent hover:text-accent disabled:cursor-default disabled:opacity-50"
        >
          {busy ? 'el modelo está escribiendo…' : 'explicar candidatos con IA (P1)'}
        </button>
        {busy ? (
          <span className="animate-blink font-mono text-[11px] text-warn">
            una explicación por candidato, en CPU: puede tardar varios minutos
          </span>
        ) : null}
        {capability.explanations ? (
          <span className="font-mono text-[10px] text-ink-4">
            {capability.explanations.provenance.notice ??
              `${capability.explanations.provenance.model} · ${capability.explanations.provenance.attempts} intento(s)`}
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
            placeholder="Razón de la decisión — se registra tal cual en la bitácora…"
            className={`min-h-[44px] w-full resize-y rounded-[5px] border bg-surface px-2.5 py-2 text-[12.5px] outline-accent ${
              reason.trim() === '' ? 'border-alert' : 'border-line'
            }`}
          />
        </div>
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
  if (accepted) return 'Razón obligatoria — aceptas un hueco declarado por el motor:'
  if (hasConflict) return 'Razón obligatoria — resuelves una contradicción que el motor elevó:'
  if (picked.some((id) => supersededIds(capability).has(id)))
    return 'Razón obligatoria — eliges una opción que una regla había apartado; contradices al motor:'
  return 'Razón de la elección — obligatoria: la bitácora no admite una decisión sin justificación:'
}
