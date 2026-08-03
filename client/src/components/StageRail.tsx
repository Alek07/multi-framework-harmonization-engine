/**
 * The rail: what asset is being composed, which zones it has, and where in the
 * flow the operator is.
 *
 * The zone cards are the engine's argument made clickable — same catalog, same
 * profile, different zone, different baseline — so they carry the zone's own
 * target level and its own count of mandatory requirements, and switching zone
 * switches what the candidates stage shows.
 */

import { useState } from 'react'

import { FR_FIELDS, type SLVector } from '../api/types'
import { CONSEQUENCE_SCALE, FR_MEANING, ZONE_DOMAIN } from '../lib/labels'
import { useComposition, type Step } from '../state/composition'
import { Caps } from './ui'

const STEP_NAMES: Record<Step, string> = {
  1: 'Describir el activo',
  2: 'Elegir los controles',
  3: 'Comparar por región',
  4: 'Revisar y firmar',
  5: 'Registro de decisiones',
}

const STEP_TIPS: Record<Step, string> = {
  1: 'Cuenta con tus palabras qué es el activo, qué controla, cómo se conecta y quién lo usa. El asistente rellena una ficha con lo que ha entendido y te enseña la frase de la que sale cada dato. Tú lo revisas y lo corriges: lo que se usa después es tu versión, no la suya.',
  2: 'Aquí compones. Para cada requisito de la zona verás, unas al lado de otras, todas las opciones equivalentes de los distintos marcos. Ninguna viene marcada como «la mejor» y ninguna se oculta: eliges tú y escribes por qué.',
  3: 'Mira qué cambia en una zona si además de la normativa de EE. UU. tienes que responder ante la europea. La segunda columna es acumulativa: «+UE» significa lo de EE. UU. más lo que añade la UE.',
  4: 'Repaso final. No se puede firmar mientras quede una obligación sin decidir, un conflicto sin resolver o una decisión sin justificar. Al firmar, todo queda registrado de forma permanente.',
  5: 'El historial completo: qué hizo el sistema, qué decidiste tú, cuándo y por qué. No se puede editar ni borrar, y el propio sistema comprueba que nadie lo haya alterado.',
}

const SL_FILL = ['bg-line-3', 'bg-[#ded8ca]', 'bg-[#b9c8e4]', 'bg-[#5b7cc0]', 'bg-ink']

function SLCells({ vector, target }: { vector: SLVector | null; target: number }) {
  const values = vector ? FR_FIELDS.map((fr) => vector[fr]) : FR_FIELDS.map(() => target)
  return (
    <span
      className="my-1.5 flex gap-0.5"
      title="Nivel exigido en cada una de las siete familias de requisitos"
    >
      {values.map((value, index) => (
        <span
          key={index}
          title={`${FR_MEANING[FR_FIELDS[index]]} — nivel ${value} de 4`}
          className={`inline-block h-1.5 w-[13px] rounded-[2px] ${SL_FILL[value] ?? SL_FILL[0]}`}
        />
      ))}
    </span>
  )
}

function AssetCard() {
  const { candidates, profile, source, corrections, draft } = useComposition()
  const name = candidates?.profile_name ?? profile?.name ?? draft?.name
  if (!name) return null

  const scale = profile?.criticality.scale ?? draft?.criticality.scale ?? null
  const via = source === 'manual' ? 'ficha rellenada a mano' : 'descripción revisada por ti'

  return (
    <div className="mb-3 rounded-lg border border-line bg-surface px-[13px] py-3">
      <Caps className="mb-1.5">Activo que estás componiendo</Caps>
      <div className="text-[12.5px] leading-[1.4] font-semibold">{name}</div>
      <div className="mt-2 flex flex-wrap gap-1">
        {scale ? (
          <span
            title="Gravedad de la consecuencia física si el activo falla o es atacado"
            className="rounded-sm bg-ink px-1.5 py-0.5 text-[9.5px] font-semibold text-white"
          >
            consecuencia {CONSEQUENCE_SCALE[scale]}
          </span>
        ) : null}
        <span className="rounded-sm bg-[#eef0f2] px-1.5 py-0.5 text-[9.5px] font-medium text-ink-2">
          {via}
        </span>
        {corrections.length > 0 ? (
          <span
            title="Datos que has corregido respecto a lo que el asistente propuso"
            className="rounded-sm bg-accent-tint px-1.5 py-0.5 text-[9.5px] font-semibold text-accent"
          >
            ◆ {corrections.length} corregido(s)
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
      <div className="mb-1.5 px-0.5 text-[10.5px] leading-[1.45] text-ink-4">
        Cada zona se compone por separado: mismas normas, distinto resultado.
      </div>
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
        const parts = [`obligatorios ${stats.tier0Done}/${stats.tier0Total}`]
        if (stats.gaps) parts.push(`${stats.gaps} sin cobertura`)
        if (stats.conflictsOpen)
          parts.push(`${stats.conflictsOpen} conflicto${stats.conflictsOpen > 1 ? 's' : ''}`)
        const complete = stats.tier0Done >= stats.tier0Total

        return (
          <button
            key={id}
            type="button"
            data-testid="zone-card"
            data-zone-id={id}
            title={`Por qué el sistema ha identificado esta zona: ${zone.zone.derivation}`}
            onClick={() => {
              setZoneId(id)
              if (step !== 2 && step !== 3) goToStep(2)
            }}
            className={`mb-1.5 flex w-full cursor-pointer flex-col items-start rounded-lg px-3 py-2.5 text-left ${
              active ? 'border-2 border-accent bg-accent-tint-2' : 'border border-line bg-surface'
            }`}
          >
            <span className="text-[11.5px] leading-tight font-semibold">
              {ZONE_DOMAIN[zone.zone.domain]}
            </span>
            <span className="text-[10px] font-medium text-ink-3">
              {id} · nivel objetivo {zone.zone.target_sl} de 4
              {zone.zone.safety_relevant ? ' · con seguridad de personas' : ''}
            </span>
            <SLCells vector={zone.zone.sl_vector} target={zone.zone.target_sl} />
            <span
              className={`text-[10px] font-semibold ${complete ? 'text-ok' : 'text-alert-ink'}`}
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
  const { step, goToStep, stepLocks, candidates, profile, progress, signed } = useComposition()
  const [openTip, setOpenTip] = useState<Step | null>(null)

  const hasProfile = Boolean(profile)
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
      <Caps className="px-2.5 pt-1.5 pb-2">Pasos</Caps>
      {([1, 2, 3, 4, 5] as Step[]).map((n) => {
        const current = step === n
        const locked = stepLocks[n]
        const blocked = n === 4 && !signed && progress.blockers.length > 0
        const mark = locked ? '·' : done[n] ? '✓' : blocked ? '!' : '○'
        const state = locked
          ? `todavía no disponible — ${locked}`
          : done[n]
            ? 'completado'
            : blocked
              ? 'pendiente: quedan cosas por resolver'
              : 'sin completar'
        return (
          <div key={n} className="flex flex-col">
            <div className="flex items-center gap-0.5">
              <button
                type="button"
                aria-current={current}
                aria-disabled={Boolean(locked)}
                disabled={Boolean(locked)}
                data-locked={locked ? 'true' : undefined}
                title={`Paso ${n} — ${STEP_NAMES[n]} · ${state}`}
                onClick={() => goToStep(n)}
                className={`flex flex-1 items-center gap-2 rounded-md border-none px-2.5 py-[7px] text-[12.5px] ${
                  locked
                    ? 'cursor-default bg-transparent font-medium text-ink-5'
                    : `cursor-pointer hover:bg-[#eceae4] ${
                        current
                          ? 'bg-line-2 font-semibold text-ink'
                          : 'bg-transparent font-medium text-ink-2'
                      }`
                }`}
              >
                <span
                  className={`w-4 flex-none text-center font-mono text-[11px] font-semibold ${
                    locked
                      ? 'text-[#c7cbd1]'
                      : done[n]
                        ? 'text-ok'
                        : blocked
                          ? 'text-alert'
                          : 'text-[#b0b7c1]'
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
                title={`Qué se hace en el paso ${n}`}
                aria-label={`qué se hace en el paso ${n}`}
                onClick={() => setOpenTip(openTip === n ? null : n)}
                className="flex-none cursor-pointer border-none bg-transparent px-1.5 py-1 text-[11px] font-semibold text-ink-5 hover:text-accent"
              >
                ⓘ
              </button>
            </div>
            {openTip === n ? (
              <div className="mx-2.5 my-0.5 mb-1.5 rounded-md border border-line bg-surface px-2.5 py-2 text-[11px] leading-[1.5] text-ink-3">
                {STEP_TIPS[n]}
                {locked ? (
                  <div className="mt-1.5 border-t border-line-2 pt-1.5 font-medium text-ink-4">
                    Aún no puedes entrar aquí: {locked}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        )
      })}
    </nav>
  )
}
