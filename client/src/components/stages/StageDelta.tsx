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
 * Two bounds are declared rather than hidden. One zone per call is the scope of
 * UCM-17 — N zones at once is future work. And `GET /delta` takes a `profile_id`,
 * so this stage only answers over a profile frozen in the repository: with a
 * profile the operator parsed here the stage is *disabled and says so*, never
 * removed from the flow.
 */

import { useEffect } from 'react'

import { FRAMEWORK, MAPPING_TYPE } from '../../lib/labels'
import { DELTA_ORDERS, useComposition } from '../../state/composition'
import { Caps, Notice, Section, Tag } from '../ui'

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
    frozenProfileId,
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
  const enabled = Boolean(frozenProfileId && zoneId)

  useEffect(() => {
    if (enabled) void loadDelta()
  }, [enabled, loadDelta])

  if (!enabled) {
    return (
      <Section
        id="s4"
        step={3}
        title="Delta regional — lecturas acumulativas"
        scope="una zona por consulta"
        dimmed
      >
        {frozenProfileId ? (
          <p className="m-0 text-[13px] text-ink-4">
            El delta se calcula sobre una zona concreta. Pasa por la etapa 2 para que el motor
            derive las zonas de <span className="font-mono">{frozenProfileId}</span> y vuelve aquí.
          </p>
        ) : (
          <p className="m-0 text-[13px] text-ink-4">
            Deshabilitado, no oculto. <span className="font-mono">GET /delta</span> lee un perfil
            congelado por identificador (<span className="font-mono">profile_id</span>), así que el
            delta existe para <span className="font-mono">PROFILE-A</span> /{' '}
            <span className="font-mono">PROFILE-B</span> y no para un perfil parseado en esta
            sesión. Elige un perfil congelado en la etapa 1 para verlo.
          </p>
        )}
      </Section>
    )
  }

  const second = regions[1]

  return (
    <Section
      id="s4"
      step={3}
      title={`Delta regional — ${regions[0]} vs. +${second}`}
      scope={`${frozenProfileId} · ${zoneId}`}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {DELTA_ORDERS.map((option, index) => (
          <button
            key={option.label}
            type="button"
            onClick={() => setDeltaOrder(index)}
            className={`cursor-pointer rounded-[5px] border px-3 py-1.5 font-mono text-[11px] font-semibold ${
              deltaOrder === index
                ? 'border-accent bg-accent-tint text-accent'
                : 'border-line bg-surface-2 text-ink-3'
            }`}
          >
            {option.label}
          </button>
        ))}
        {candidates ? (
          <select
            value={zoneId ?? ''}
            onChange={(event) => setZoneId(event.target.value)}
            className="rounded-[5px] border border-line bg-surface-2 px-2 py-1.5 font-mono text-[11px] text-ink-2"
          >
            {candidates.zones.map((zone) => (
              <option key={zone.zone.zone_id} value={zone.zone.zone_id}>
                {zone.zone.zone_id}
              </option>
            ))}
          </select>
        ) : null}
        <span className="text-[11.5px] text-ink-4">
          El orden importa: las lecturas son acumulativas, no dos catálogos paralelos.
        </span>
      </div>

      {deltaLoading ? (
        <p className="m-0 font-mono text-xs text-ink-4">leyendo la zona bajo cada lente…</p>
      ) : null}
      {deltaError ? (
        <Notice tone="alert" label="DELTA">
          {deltaError}
        </Notice>
      ) : null}

      {delta ? (
        <>
          <p className="m-0 mb-3 text-[12.5px] text-ink-3">{delta.rationale}</p>

          <div className="grid grid-cols-3 gap-3.5">
            <Column title={`COMÚN · ${regions.join(' ∩ ')}`} tone="neutral">
              {delta.capabilities
                .filter((capability) => capability.common_control_ids.length > 0)
                .map((capability) => (
                  <Entry key={capability.capability_id} head={capability.capability_id}>
                    {capability.common_control_ids.join(' · ')}
                  </Entry>
                ))}
            </Column>

            <Column title={`AÑADE +${second}`} tone="accent">
              {delta.capabilities.flatMap((capability) =>
                capability.added.map((requirement) => (
                  <Entry
                    key={`${capability.capability_id}-${requirement.control_id}`}
                    head={capability.capability_id}
                  >
                    <span className="font-semibold">
                      {FRAMEWORK[requirement.framework].label} {requirement.official_id}
                    </span>{' '}
                    · {MAPPING_TYPE[requirement.mapping_type].label} · {requirement.strength}
                    <div className="mt-0.5">{requirement.rationale}</div>
                  </Entry>
                )),
              )}
              {delta.changed_capability_ids.length === 0 ? (
                <div className="text-[12.5px] text-ink-3">
                  Ninguna capacidad cambia entre lecturas en esta zona. Es un resultado, no una
                  ausencia de resultado.
                </div>
              ) : null}
            </Column>

            <Column title="HUECOS POR REGIÓN" tone="alert">
              {delta.regional_gap_capability_ids.length === 0 ? (
                <div className="text-[12.5px] text-ink-3">
                  La jurisdicción no abre ni cierra ningún hueco en esta zona.
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
            <Caps className="mb-2">
              Divergencia de exigencia — misma capacidad, distinto strength
            </Caps>
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
                        <b className="text-ink">{view.label}</b> · cobertura{' '}
                        {view.coverage.toFixed(2)} · {view.offered_control_ids.length} opción(es)
                        {view.set_aside_control_ids.length > 0 ? (
                          <span className="text-ink-4">
                            {' '}
                            · apartadas: {view.set_aside_control_ids.join(', ')}
                          </span>
                        ) : null}
                      </span>
                    ))}
                    {capability.changes_coverage ? (
                      <Tag className="bg-accent-tint text-accent">mueve la cobertura</Tag>
                    ) : (
                      <Tag className="bg-warn-tint text-warn-ink">
                        cambia la exigencia, no la cobertura
                      </Tag>
                    )}
                  </span>
                </div>
              ))}
            <div className="mt-2 text-[11.5px] text-ink-4">
              Las lentes declaradas de cada lectura:{' '}
              {delta.lenses.map((lens, index) => (
                <span key={index} className="mr-2 font-mono">
                  [{delta.regions[index]}] {lens.rationale}
                </span>
              ))}
            </div>
          </div>
        </>
      ) : null}
    </Section>
  )
}
