/**
 * Etapa 3 — the regional delta: the same zone under the legal regimes governing
 * this asset, compared both ways. Fixed to the symmetric, legal reading — the
 * difference each way, with the common technical ground held out — because that is
 * the one question the screen asks. It carries the reviewed profile inline, so the
 * comparison is asset-specific; regimes out of the asset's sector are disclosed in
 * the applicability panel rather than silently dropped. Bound: one zone at a time.
 */

import { useEffect } from 'react'

import type {
  CapabilityDelta,
  Jurisdiction,
  RegionalDelta,
  RegionalRequirement,
} from '../../../api/types'
import { FRAMEWORK, FRAMEWORK_NOTE, JURISDICTION_SHORT, strengthText } from '../../../lib/labels'
import { useComposition } from '../composition'
import { Caps, Hint, Notice, Section, Tag } from '../../../components/ui'

/**
 * Which regimes govern this asset, as the engine determined. The engine never
 * chooses the comparison but does determine applicability and say so; a regime
 * that does not govern the asset is left out of the comparison, and this panel is
 * where that exclusion is disclosed rather than left silent.
 */
function RegimePanel({ delta }: { delta: RegionalDelta }) {
  if (delta.regime_applicability.length === 0) return null
  return (
    <div className="mb-4 rounded-[7px] border border-line-2 bg-surface-4 px-4 py-3.5">
      <Caps className="mb-1.75">Regímenes aplicables a este activo</Caps>
      <Hint className="mb-2.5">
        El motor determina qué leyes gobiernan este activo por su sector; las que no aplican no
        entran en la comparación. Reglas deciden aplicabilidad; el humano elige qué componer.
      </Hint>
      <div className="flex flex-col gap-2">
        {delta.regime_applicability.map((regime) => (
          <div
            key={`${regime.framework}-${regime.jurisdiction}`}
            className="flex flex-wrap items-baseline gap-2"
          >
            <Tag
              prose
              className={
                regime.applicable
                  ? 'border border-accent-line bg-accent-tint text-accent'
                  : 'border border-line bg-[#f2f1ed] text-ink-3'
              }
            >
              {regime.applicable ? 'aplica' : 'no aplica'}
            </Tag>
            <span
              className={`rounded-sm px-1.25 py-0.25 text-[9.5px] font-semibold ${FRAMEWORK[regime.framework].className}`}
            >
              {FRAMEWORK[regime.framework].label}
            </span>
            <span className="font-mono text-[10.5px] text-ink-3">
              {JURISDICTION_SHORT[regime.jurisdiction]}
            </span>
            <span className="flex-1 text-[11.5px] leading-normal text-ink-4">{regime.rationale}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** One obligation one region imposes and the other does not. */
function RequirementRow({ requirement }: { requirement: RegionalRequirement }) {
  const moves = requirement.changes_coverage
  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-2">
        <span
          title={FRAMEWORK_NOTE[requirement.framework]}
          className={`cursor-help font-mono text-[11.5px] font-semibold ${moves ? 'text-accent' : 'text-warn'}`}
        >
          {FRAMEWORK[requirement.framework].label} {requirement.official_id}
        </span>
        <Tag
          prose
          className={
            moves
              ? 'border border-accent-line bg-accent-tint text-accent'
              : 'border border-warn-line bg-warn-tint text-warn'
          }
          title={
            moves
              ? 'Prescribe un mecanismo: mueve la cobertura.'
              : 'Añade exigencia sobre una capacidad ya cubierta: no mueve la cobertura.'
          }
        >
          {moves ? 'mecanismo' : 'exigencia'}
        </Tag>
      </div>
      <Hint className="mt-0.5">{strengthText(requirement.strength)}</Hint>
    </div>
  )
}

/** One side of a card: what this region demands the other does not. */
function DemandSide({
  region,
  requirements,
}: {
  region: Jurisdiction
  requirements: RegionalRequirement[]
}) {
  return (
    <div className="px-3.75 py-3.25">
      <Caps className="mb-1.75 text-warn">{JURISDICTION_SHORT[region]} exige y la otra no</Caps>
      {requirements.length === 0 ? (
        <p className="m-0 text-[12.5px] leading-normal text-ink-4">
          Nada exclusivo: cuanto exige aquí, lo exige también la otra región.
        </p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {requirements.map((requirement) => (
            <RequirementRow key={requirement.control_id} requirement={requirement} />
          ))}
        </div>
      )}
    </div>
  )
}

/** The comparison itself: each changed capability, the difference reported both ways. */
function Comparison({ delta }: { delta: RegionalDelta }) {
  const [first, second] = delta.regions
  const changed = delta.capabilities.filter((capability) => capability.changed)
  const same = delta.capabilities.filter((capability) => !capability.changed)
  const demandedBy = (region: Jurisdiction) =>
    changed.filter((capability) => capability.added.some((r) => r.added_by === region)).length
  const forRegion = (capability: CapabilityDelta, region: Jurisdiction) =>
    capability.added.filter((requirement) => requirement.added_by === region)

  return (
    <>
      <RegimePanel delta={delta} />

      <div className="mb-4 grid grid-cols-2 overflow-hidden rounded-[7px] border border-line-2 max-mid:grid-cols-1">
        {[first, second].map((region, index) => (
          <div
            key={region}
            className={`px-4.5 py-4 ${index === 1 ? 'border-l border-line-2 max-mid:border-t max-mid:border-l-0' : ''}`}
          >
            <Caps className="mb-2 text-warn">{JURISDICTION_SHORT[region]} exige y la otra no</Caps>
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-[30px] leading-none font-semibold text-warn">
                {demandedBy(region)}
              </span>
              <span className="text-xs leading-[1.4] text-ink-3">
                de {delta.capabilities.length} capacidades con obligación propia
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="mb-3 flex items-center gap-2">
        <Caps className="text-warn">Qué exige cada región que la otra no</Caps>
        <span className="h-px flex-1 bg-line-2" />
        <span className="font-mono text-[10px] font-medium text-ink-4">
          {changed.length} capacidades
        </span>
      </div>

      {changed.length === 0 ? (
        <Notice tone="muted">
          En esta zona ninguna región exige nada que la otra no exija: lo compuesto aquí sirve para
          las dos.
        </Notice>
      ) : null}

      {changed.map((capability) => (
        <div
          key={capability.capability_id}
          className="mb-3 overflow-hidden rounded-[7px] border border-line-2 bg-surface"
        >
          <div className="flex flex-wrap items-baseline gap-2 border-b border-line-3 bg-surface-2 px-3.75 py-2.75">
            <span className="font-mono text-[11.5px] font-semibold">
              {capability.capability_id}
            </span>
            <span className="text-[12.5px] text-ink-3">{capability.capability_name}</span>
          </div>
          <div className="grid grid-cols-[1fr_auto_1fr] max-mid:grid-cols-1">
            <DemandSide region={first} requirements={forRegion(capability, first)} />
            <div className="flex items-center justify-center border-x border-line-3 bg-surface-3 px-2.5 max-mid:border-x-0 max-mid:border-y max-mid:py-2">
              <span
                title="Comparación en ambos sentidos"
                className="inline-flex h-7.5 w-7.5 items-center justify-center rounded-full border border-line bg-surface text-[15px] text-ink-3"
              >
                ⚖
              </span>
            </div>
            <DemandSide region={second} requirements={forRegion(capability, second)} />
          </div>
        </div>
      ))}

      <div className="rounded-[7px] border border-line-2 bg-surface-4 px-4 py-3.5">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="inline-flex h-6.5 w-6.5 items-center justify-center rounded-sm border border-line bg-[#f2f1ed] font-mono text-[13px] font-semibold text-ink-2">
            =
          </span>
          <Caps>Idéntico bajo ambas leyes</Caps>
          <span className="font-mono text-xs font-semibold text-ink-4">{same.length}</span>
        </div>
        <Hint className="mt-1.75">
          Ni {JURISDICTION_SHORT[first]} ni {JURISDICTION_SHORT[second]} exige aquí nada que la otra
          no exija: mismo suelo legal bajo las dos.
        </Hint>
      </div>
    </>
  )
}

export function StageDelta() {
  const { profile, zoneId, candidates, setZoneId, delta, deltaLoading, deltaError, loadDelta } =
    useComposition()

  const enabled = Boolean(profile && zoneId)

  useEffect(() => {
    if (enabled) void loadDelta()
  }, [enabled, loadDelta])

  if (!enabled) {
    return (
      <Section
        id="s4"
        step={3}
        title="Compara las leyes aplicables"
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

  return (
    <Section
      id="s4"
      step={3}
      title="Delta regional — leyes aplicables, EE. UU. frente a UE"
      hint="Qué exige cada régimen legal aplicable a este activo que el otro no, sobre la misma zona y en ambos sentidos. El terreno técnico común no se compara; las leyes fuera del sector del activo no entran."
      scope={zoneId ?? undefined}
    >
      {candidates ? (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="font-mono text-[10px] font-medium tracking-[0.06em] text-ink-4">ZONA</span>
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
        </div>
      ) : null}

      {deltaLoading ? (
        <p className="m-0 text-xs text-ink-4">Comparando la zona bajo cada normativa…</p>
      ) : null}
      {deltaError ? (
        <Notice tone="alert" label="NO SE PUDO COMPARAR">
          {deltaError}
        </Notice>
      ) : null}

      {delta ? <Comparison delta={delta} /> : null}
    </Section>
  )
}
