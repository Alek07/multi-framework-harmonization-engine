/**
 * The rail: what asset is being composed, which zones it has, and where in the
 * flow the operator is.
 *
 * The zone cards are the argument of UCM-9 made clickable — same catalog, same
 * profile, different zone, different baseline — so they carry the zone's own
 * SL-T reading and its own Tier 0 count, and switching zone switches what the
 * candidates stage shows.
 */

import { useState } from 'react'

import { FR_FIELDS, type SLVector } from '../api/types'
import { CONSEQUENCE_SCALE, ZONE_DOMAIN } from '../lib/labels'
import { useComposition, type Step } from '../state/composition'
import { Caps } from './ui'

const STEP_NAMES: Record<Step, string> = {
  1: 'Activo y perfil',
  2: 'Candidatos',
  3: 'Delta regional',
  4: 'Firma',
  5: 'Bitácora',
}

const STEP_TIPS: Record<Step, string> = {
  1: 'Un único input: describe el activo en texto libre. El modelo extrae un borrador del AssetProfile y dice de qué frase sale cada campo; tú lo revisas y lo corriges. La IA propone, nunca decide.',
  2: 'El corazón: para cada capacidad de la zona activa el motor presenta las opciones equivalentes lado a lado, en orden determinista. Tú eliges; nada desaparece ni se ordena por «mejor».',
  3: 'Compara qué exige EE. UU. frente a la UE sobre una zona. Las lecturas son acumulativas: «+EU» es la lectura US más la obligación europea.',
  4: 'La firma se bloquea hasta que todo mandato que el motor no pudo cerrar esté cerrado y toda decisión tenga su razón escrita. El servidor lo vuelve a verificar antes de firmar.',
  5: 'Registro append-only de quién hizo qué y por qué, con la verificación de la cadena de hashes que devuelve el servidor.',
}

const SL_FILL = ['bg-line-3', 'bg-[#ded8ca]', 'bg-[#b9c8e4]', 'bg-[#5b7cc0]', 'bg-ink']

function SLCells({ vector, target }: { vector: SLVector | null; target: number }) {
  const values = vector ? FR_FIELDS.map((fr) => vector[fr]) : FR_FIELDS.map(() => target)
  return (
    <span className="my-1.5 flex gap-0.5">
      {values.map((value, index) => (
        <span
          key={index}
          title={`${FR_FIELDS[index]} · SL-T ${value}`}
          className={`inline-block h-1.5 w-[13px] rounded-[2px] ${SL_FILL[value] ?? SL_FILL[0]}`}
        />
      ))}
    </span>
  )
}

function AssetCard() {
  const { candidates, profile, frozenProfileId, source, corrections, draft } = useComposition()
  const name = candidates?.profile_name ?? profile?.name ?? draft?.name ?? frozenProfileId
  if (!name) return null

  const scale = profile?.criticality.scale ?? draft?.criticality.scale ?? null
  const via = source === 'frozen' ? 'perfil congelado' : 'LLM + revisión humana'

  return (
    <div className="mb-3 rounded-lg border border-line bg-surface px-[13px] py-3">
      <Caps className="mb-1.5">Activo</Caps>
      <div className="text-[12.5px] leading-[1.4] font-semibold">{name}</div>
      <div className="mt-2 flex flex-wrap gap-1">
        {scale ? (
          <span className="rounded-sm bg-ink px-1.5 py-0.5 font-mono text-[9.5px] font-semibold text-white">
            criticidad {CONSEQUENCE_SCALE[scale]}
          </span>
        ) : null}
        <span className="rounded-sm bg-[#eef0f2] px-1.5 py-0.5 font-mono text-[9.5px] font-medium text-ink-2">
          vía {via}
        </span>
        {corrections.length > 0 ? (
          <span className="rounded-sm bg-accent-tint px-1.5 py-0.5 font-mono text-[9.5px] font-semibold text-accent">
            ◆ {corrections.length}
          </span>
        ) : null}
      </div>
    </div>
  )
}

function ZoneCards() {
  const { candidates, zoneId, setZoneId, goToStep, step, progress } = useComposition()
  if (!candidates) return null

  return (
    <>
      <Caps className="px-0.5 pb-1.5">Zonas del activo</Caps>
      {candidates.zones.map((zone) => {
        const id = zone.zone.zone_id
        const active = id === zoneId
        const stats = progress.byZone[id] ?? {
          tier0Done: 0,
          tier0Total: 0,
          gaps: 0,
          gapsAcknowledged: 0,
          conflictsOpen: 0,
        }
        const parts = [`T0 ${stats.tier0Done}/${stats.tier0Total}`]
        if (stats.gaps) parts.push(`${stats.gaps} hueco${stats.gaps > 1 ? 's' : ''}`)
        if (stats.conflictsOpen) parts.push(`${stats.conflictsOpen} conflicto`)
        const complete = stats.tier0Done >= stats.tier0Total

        return (
          <button
            key={id}
            type="button"
            data-testid="zone-card"
            data-zone-id={id}
            title={zone.zone.derivation}
            onClick={() => {
              setZoneId(id)
              if (step !== 2 && step !== 3) goToStep(2)
            }}
            className={`mb-1.5 flex w-full cursor-pointer flex-col items-start rounded-lg px-3 py-2.5 text-left ${
              active ? 'border-2 border-accent bg-accent-tint-2' : 'border border-line bg-surface'
            }`}
          >
            <span className="text-[11.5px] leading-tight font-semibold">
              {ZONE_DOMAIN[zone.zone.domain]} · SL-T {zone.zone.target_sl}
              {zone.zone.safety_relevant ? ' · safety' : ''}
            </span>
            <span className="font-mono text-[9px] font-medium text-ink-4">{id}</span>
            <SLCells vector={zone.zone.sl_vector} target={zone.zone.target_sl} />
            <span
              className={`font-mono text-[10px] font-semibold ${complete ? 'text-ok' : 'text-alert-ink'}`}
            >
              {parts.join(' · ')}
            </span>
          </button>
        )
      })}
      <div className="h-2.5" />
    </>
  )
}

export function StageRail() {
  const { step, goToStep, candidates, profile, frozenProfileId, progress, signed } =
    useComposition()
  const [openTip, setOpenTip] = useState<Step | null>(null)

  const hasProfile = Boolean(profile ?? frozenProfileId)
  const done: Record<Step, boolean> = {
    1: hasProfile,
    2: Boolean(candidates) && progress.blockers.length === 0,
    3: Boolean(candidates),
    4: signed,
    5: signed,
  }

  return (
    <nav
      aria-label="Etapas"
      className="sticky top-[60px] flex max-h-[calc(100vh-160px)] w-[214px] flex-none flex-col gap-0.5 self-start overflow-y-auto"
      data-screen-label="StageRail"
    >
      {hasProfile ? <AssetCard /> : null}
      <ZoneCards />
      <Caps className="px-2.5 pt-1.5 pb-2">Etapas</Caps>
      {([1, 2, 3, 4, 5] as Step[]).map((n) => {
        const current = step === n
        const blocked = n === 4 && !signed && progress.blockers.length > 0
        const mark = done[n] ? '✓' : blocked ? '!' : '○'
        return (
          <div key={n} className="flex flex-col">
            <div className="flex items-center gap-0.5">
              <button
                type="button"
                aria-current={current}
                onClick={() => goToStep(n)}
                className={`flex flex-1 cursor-pointer items-center gap-2 rounded-md border-none px-2.5 py-[7px] text-[12.5px] hover:bg-[#eceae4] ${
                  current ? 'bg-line-2 font-semibold text-ink' : 'bg-transparent font-medium text-ink-2'
                }`}
              >
                <span
                  className={`w-4 flex-none text-center font-mono text-[11px] font-semibold ${
                    done[n] ? 'text-ok' : blocked ? 'text-alert' : 'text-[#b0b7c1]'
                  }`}
                >
                  {mark}
                </span>
                <span className="flex-1 text-left">
                  {n}. {STEP_NAMES[n]}
                </span>
              </button>
              <button
                type="button"
                aria-label={`qué es la etapa ${n}`}
                onClick={() => setOpenTip(openTip === n ? null : n)}
                className="flex-none cursor-pointer border-none bg-transparent px-1.5 py-1 font-mono text-[11px] font-semibold text-ink-5 hover:text-accent"
              >
                ⓘ
              </button>
            </div>
            {openTip === n ? (
              <div className="mx-2.5 my-0.5 mb-1.5 rounded-md border border-line bg-surface px-2.5 py-2 text-[11px] leading-[1.5] text-ink-3">
                {STEP_TIPS[n]}
              </div>
            ) : null}
          </div>
        )
      })}
    </nav>
  )
}
