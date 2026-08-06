/**
 * Etapa 3 — the regional delta: one zone, read once per region.
 *
 * Not "what does the EU call this US control" — that is translation — but
 * "compose this zone for a US operator, then for one who also answers to EU
 * obligations, and show what changes". The readings are cumulative, which is why
 * the second column is labelled `+EU` and not `EU`, and why the order of the
 * regions is not sorted away: `EU,US` asks a different, equally legitimate
 * question.
 *
 * The question is asked about *this* asset — the one described upstairs in free
 * text and reviewed by the operator — because the request carries the reviewed
 * profile inline. A delta that could only be asked about the profiles frozen in
 * the repository would be a demo of the frozen profiles.
 *
 * One bound is declared rather than hidden: one zone at a time, and the screen
 * says so in the operator's words instead of naming the issue that scoped it.
 */

import { useEffect } from 'react'

import {
  FRAMEWORK,
  JURISDICTION_SHORT,
  MAPPING_TYPE,
  STRENGTH_KIND,
  coverageText,
  strengthText,
} from '../../lib/labels'
import { DELTA_ORDERS, useComposition } from '../../state/composition'
import { Caps, Hint, Notice, Section, Tag } from '../ui'

function Column({
  title,
  tone,
  children,
}: {
  title: string
  tone: 'neutral' | 'accent' | 'alert'
  children: React.ReactNode
}) {
  const shell = {
    neutral: 'border-line-2 bg-surface',
    accent: 'border-accent-line bg-accent-tint-3',
    alert: 'border-alert-line bg-alert-tint-2',
  }[tone]
  const ink = {
    neutral: 'text-ink-2',
    accent: 'text-accent',
    alert: 'text-alert',
  }[tone]
  return (
    <div className={`rounded-md border p-3.5 ${shell}`}>
      <div className={`mb-2.5 font-mono text-[11px] font-semibold ${ink}`}>{title}</div>
      {children}
    </div>
  )
}

function Entry({ head, children }: { head: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-line-3 py-1.5 text-[12.5px]">
      <span className="font-mono text-[11.5px] font-semibold">{head}</span>
      <div className="mt-0.5 text-ink-3">{children}</div>
    </div>
  )
}

export function StageDelta() {
  const {
    profile,
    zoneId,
    candidates,
    setZoneId,
    delta,
    deltaLoading,
    deltaError,
    deltaOrder,
    setDeltaOrder,
    loadDelta,
  } = useComposition()

  const regions = DELTA_ORDERS[deltaOrder].regions
  const enabled = Boolean(profile && zoneId)

  useEffect(() => {
    if (enabled) void loadDelta()
  }, [enabled, loadDelta])

  if (!enabled) {
    return (
      <Section
        id="s4"
        step={3}
        title="Compara qué exige cada región"
        scope="una zona cada vez"
        dimmed
      >
        <p className="m-0 text-[13px] text-ink-4">
          {profile
            ? 'La comparación se hace sobre una zona concreta. Pasa por el paso 2 para que el sistema identifique las zonas del activo y vuelve aquí.'
            : 'Antes hay que completar la ficha del activo en el paso 1.'}
        </p>
      </Section>
    )
  }

  const second = regions[1]

  return (
    <Section
      id="s4"
      step={3}
      title={`Qué añade ${JURISDICTION_SHORT[second]} sobre ${JURISDICTION_SHORT[regions[0]]}`}
      hint={`Esta pantalla responde a una sola pregunta: si además de responder ante ${JURISDICTION_SHORT[regions[0]]} tuvieras que responder ante ${JURISDICTION_SHORT[second]}, ¿qué tendrías que añadir en esta zona? La segunda lectura incluye la primera; no son dos listas independientes.`}
      scope={zoneId ?? undefined}
    >
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        {DELTA_ORDERS.map((option, index) => (
          <button
            key={option.label}
            type="button"
            title={`Leer primero ${JURISDICTION_SHORT[option.regions[0]]} y añadir después ${JURISDICTION_SHORT[option.regions[1]]}`}
            onClick={() => setDeltaOrder(index)}
            className={`cursor-pointer rounded-[5px] border px-3 py-1.5 text-[11.5px] font-semibold ${
              deltaOrder === index
                ? 'border-accent bg-accent-tint text-accent'
                : 'border-line bg-surface-2 text-ink-3'
            }`}
          >
            {JURISDICTION_SHORT[option.regions[0]]} y luego {JURISDICTION_SHORT[option.regions[1]]}
          </button>
        ))}
        {candidates ? (
          <select
            value={zoneId ?? ''}
            aria-label="Zona a comparar"
            onChange={(event) => setZoneId(event.target.value)}
            className="rounded-[5px] border border-line bg-surface-2 px-2 py-1.5 text-[11.5px] text-ink-2"
          >
            {candidates.zones.map((zone) => (
              <option key={zone.zone.zone_id} value={zone.zone.zone_id}>
                Zona {zone.zone.zone_id}
              </option>
            ))}
          </select>
        ) : null}
      </div>
      <Hint className="mb-3">
        El orden cambia la pregunta, no el catálogo: «EE. UU. y luego UE» te dice qué añade Europa a
        un operador estadounidense, y al revés.
      </Hint>

      {deltaLoading ? (
        <p className="m-0 text-xs text-ink-4">Comparando la zona bajo cada normativa…</p>
      ) : null}
      {deltaError ? (
        <Notice tone="alert" label="NO SE PUDO COMPARAR">
          {deltaError}
        </Notice>
      ) : null}

      {delta ? (
        <>
          <p className="m-0 mb-3 text-[12.5px] leading-[1.55] text-ink-3">{delta.rationale}</p>

          <div className="grid grid-cols-3 gap-3.5">
            <Column title="LO QUE EXIGEN LAS DOS" tone="neutral">
              {delta.capabilities
                .filter((capability) => capability.common_control_ids.length > 0)
                .map((capability) => (
                  <Entry key={capability.capability_id} head={capability.capability_id}>
                    {capability.common_control_ids.join(' · ')}
                  </Entry>
                ))}
            </Column>

            <Column title={`LO QUE AÑADE ${JURISDICTION_SHORT[second].toUpperCase()}`} tone="accent">
              {delta.capabilities.flatMap((capability) =>
                capability.added.map((requirement) => (
                  <Entry
                    key={`${capability.capability_id}-${requirement.control_id}`}
                    head={capability.capability_id}
                  >
                    <span className="font-semibold">
                      {FRAMEWORK[requirement.framework].label} {requirement.official_id}
                    </span>{' '}
                    <span title={MAPPING_TYPE[requirement.mapping_type].note}>
                      · {MAPPING_TYPE[requirement.mapping_type].label}
                    </span>{' '}
                    <span title={STRENGTH_KIND[requirement.strength.kind]?.note}>
                      · exigencia {strengthText(requirement.strength)}
                    </span>
                    <div className="mt-0.5">{requirement.rationale}</div>
                  </Entry>
                )),
              )}
              {delta.changed_capability_ids.length === 0 ? (
                <div className="text-[12.5px] leading-[1.5] text-ink-3">
                  En esta zona no cambia nada entre una normativa y otra. Es una conclusión válida y
                  útil: significa que lo compuesto sirve para ambas.
                </div>
              ) : null}
            </Column>

            <Column title="LO QUE QUEDA SIN CUBRIR" tone="alert">
              {delta.regional_gap_capability_ids.length === 0 ? (
                <div className="text-[12.5px] leading-[1.5] text-ink-3">
                  Cambiar de región no deja ningún requisito sin cubrir en esta zona.
                </div>
              ) : null}
              {delta.capabilities
                .filter((capability) =>
                  delta.regional_gap_capability_ids.includes(capability.capability_id),
                )
                .flatMap((capability) =>
                  capability.regions
                    .filter((view) => view.gap)
                    .map((view) => (
                      <Entry
                        key={`${capability.capability_id}-${view.region}`}
                        head={`${view.label} · ${capability.capability_id}`}
                      >
                        {view.gap?.rationale}
                      </Entry>
                    )),
                )}
            </Column>
          </div>

          <div className="mt-3.5 rounded-md border border-line-2 p-3.5">
            <Caps className="mb-1">Mismo requisito, distinto grado de exigencia</Caps>
            <Hint className="mb-2">
              Requisitos que ambas normativas piden, pero con distinta dureza o distintas opciones
              disponibles.
            </Hint>
            {delta.capabilities
              .filter((capability) => capability.changed)
              .map((capability) => (
                <div
                  key={capability.capability_id}
                  className="grid grid-cols-[170px_1fr] items-baseline gap-3 border-t border-line-3 py-1.5 text-[12.5px]"
                >
                  <span className="font-mono text-[11.5px] font-semibold">
                    {capability.capability_id}
                  </span>
                  <span className="text-ink-3">
                    {capability.regions.map((view) => (
                      <span key={view.region} className="mr-3 inline-block">
                        <b className="text-ink">{view.label}</b> · cubre{' '}
                        {coverageText(view.coverage)} con {view.offered_control_ids.length}{' '}
                        opción(es)
                        {view.set_aside_control_ids.length > 0 ? (
                          <span
                            className="text-ink-4"
                            title="Controles que esta normativa no considera aplicables aquí"
                          >
                            {' '}
                            · fuera de esta lectura: {view.set_aside_control_ids.join(', ')}
                          </span>
                        ) : null}
                      </span>
                    ))}
                    {capability.changes_coverage ? (
                      <Tag
                        className="bg-accent-tint text-accent"
                        title="Con la otra normativa cambia cuánto queda cubierto"
                      >
                        cambia la cobertura
                      </Tag>
                    ) : (
                      <Tag
                        className="bg-warn-tint text-warn-ink"
                        title="Se cubre lo mismo, pero una normativa lo exige con más dureza que la otra"
                      >
                        se cubre igual, se exige distinto
                      </Tag>
                    )}
                  </span>
                </div>
              ))}
            <div className="mt-2.5 text-[11.5px] leading-[1.5] text-ink-4">
              <b>Criterio de cada lectura:</b>{' '}
              {delta.lenses.map((lens, index) => (
                <span key={index} className="mr-2">
                  [{JURISDICTION_SHORT[delta.regions[index]]}] {lens.rationale}
                </span>
              ))}
            </div>
          </div>
        </>
      ) : null}
    </Section>
  )
}
