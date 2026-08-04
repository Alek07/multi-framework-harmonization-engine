/**
 * Etapa 1 — the asset: one free-text input, and the human's review of what the
 * model made of it.
 *
 * There is one way in and it is the operator's own paragraph. The asset is
 * described here from scratch — no picker of canned profiles, because composing
 * the baseline of *this* asset is what the engine is for, and an interface that
 * opened with a menu of prepared assets would be demonstrating the menu. The
 * only alternative offered is the fallback the PRD declares: the same draft,
 * filled in by hand, for a machine where the model is not available.
 *
 * The two halves of the stage are the two halves of invariant 1. The model
 * extracts; every extracted value is shown with the fragment of text it came
 * from, whether it was *stated* or *inferred*, and what the model could not
 * place at all (`unmapped`). Then every field is editable, and the profile the
 * core runs on is the corrected one — the draft never becomes an input on its
 * own.
 *
 * `missing_required` is what stands between a draft and a profile, and it is
 * listed in full, path by path. While it is non-empty the flow does not advance:
 * a profile with an invented SL would produce a baseline nobody decided.
 */

import { useEffect, useState } from 'react'

import {
  FR_FIELDS,
  type AssetProfileDraft,
  type CaseType,
  type ConsequenceScale,
  type NatureField,
  type ParseNote,
} from '../../api/types'
import { CASE_TYPE, CONSEQUENCE_SCALE, FR_MEANING, NATURE, fieldLabel } from '../../lib/labels'
import { useComposition } from '../../state/composition'
import { Caps, Hint, Notice, PrimaryButton, Section, Tag } from '../ui'

const INPUT =
  'rounded-[5px] border border-line bg-surface-2 px-2.5 py-1.5 text-xs text-ink outline-accent'

/** What the model is being asked to find, in the operator's own words. */
const LOOKING_FOR = [
  'las zonas del activo y el nivel de seguridad que se les exige',
  'cómo es el activo por dentro: si lleva un sistema operativo corriente, si está en red, quién lo usa',
  'los enlaces entre zonas y qué protege ese paso',
  'qué pasaría en el mundo físico si falla',
  'la frase tuya que respalda cada uno de esos datos',
]

/**
 * The panel while the model is reading, in the place where its answer will land.
 *
 * The parse comes back in one piece — there is no half-profile to stream — so
 * this does not pretend to fill fields in as they arrive, and says as much. What
 * it does show is real: what is being looked for, how long it has been running,
 * and that the wait is the price of the model running on this machine instead of
 * somewhere else. The elapsed time is measured; nothing here is an estimate.
 */
function Working({ words }: { words: number }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const started = Date.now()
    const timer = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)),
      1000,
    )
    return () => window.clearInterval(timer)
  }, [])

  const clock = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`

  return (
    <div
      data-testid="parse-working"
      aria-live="polite"
      aria-busy="true"
      className="rounded-md border border-warn-line bg-warn-tint px-3.5 py-3"
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="flex items-baseline gap-2 text-[12.5px] font-semibold text-warn-ink">
          <span className="animate-blink">●</span>
          El asistente está leyendo tu descripción
        </span>
        <span title="Tiempo que lleva trabajando" className="font-mono text-xs text-warn-ink">
          {clock}
        </span>
      </div>

      <div className="mt-1 text-[11px] text-warn-ink">
        {words} palabra(s) · se ejecuta en este equipo, sin enviar tu texto fuera
      </div>

      <div className="mt-3 text-[11.5px] leading-[1.5] text-ink-3">
        Está buscando en tu texto:
        <ul className="m-0 mt-1 flex list-disc flex-col gap-0.5 pl-5">
          {LOOKING_FOR.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>

      <div className="mt-3 flex flex-col gap-1.5" aria-hidden="true">
        {[0, 1, 2].map((row) => (
          <div key={row} className="rounded-md border border-line-2 bg-surface px-3 py-2">
            <div
              className="animate-shimmer h-2 w-[42%] rounded-sm bg-line-3"
              style={{ animationDelay: `${row * 0.22}s` }}
            />
            <div
              className="animate-shimmer mt-2 h-2 w-[85%] rounded-sm bg-line-3"
              style={{ animationDelay: `${row * 0.22 + 0.11}s` }}
            />
          </div>
        ))}
      </div>

      <Hint className="mt-3">
        Los datos aparecerán todos a la vez cuando termine: el asistente no devuelve resultados a
        medias. Tarda minutos y no segundos porque el modelo corre aquí; puedes dejar la pestaña
        abierta mientras tanto.
      </Hint>
    </div>
  )
}

function EvidenceList({ notes }: { notes: ParseNote[] }) {
  if (notes.length === 0) return null
  return (
    <div className="flex flex-col gap-1.5">
      <Caps>De qué frase tuya sale cada dato</Caps>
      <Hint className="mb-0.5">
        «Lo dices tú» significa que la frase lo afirma literalmente. «Lo deduce» significa que el
        asistente lo ha supuesto a partir del contexto: revísalo con especial atención.
      </Hint>
      {notes.map((note, index) => (
        <div
          key={`${note.field}-${index}`}
          className="rounded-md border border-line-2 bg-surface-2 px-3 py-2 text-[11.5px] leading-[1.5]"
        >
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="text-[11px] font-semibold text-accent">{fieldLabel(note.field)}</span>
            <Tag
              className={
                note.kind === 'stated' ? 'bg-ok-tint text-ok-ink' : 'bg-warn-tint text-warn-ink'
              }
            >
              {note.kind === 'stated' ? 'lo dices tú' : 'lo deduce el asistente'}
            </Tag>
          </div>
          <div className="mt-1 text-ink-3 italic">«{note.evidence}»</div>
          <div className="mt-0.5 text-ink-2">{note.note}</div>
        </div>
      ))}
    </div>
  )
}

/** Name and case: the two fields the core needs and no grid covers. */
function Identity({ draft }: { draft: AssetProfileDraft }) {
  const { patchDraft, parseResult, signed } = useComposition()
  const model = parseResult?.draft

  return (
    <div className="mb-4 grid grid-cols-2 gap-5">
      <div>
        <Caps className="mb-2">Nombre del activo</Caps>
        <input
          value={draft.name ?? ''}
          disabled={signed}
          placeholder="p. ej. Corredor OT de la terminal de GNL"
          onChange={(event) =>
            patchDraft(
              (next) => {
                next.name = event.target.value || null
              },
              { path: 'name', from: model?.name ?? '—', to: event.target.value || '—' },
            )
          }
          className={`w-full ${INPUT}`}
        />
      </div>
      <div>
        <Caps className="mb-2">Tipo de activo</Caps>
        <div className="flex gap-1.5">
          {(['PURE_OT', 'HYBRID_IT_OT'] as CaseType[]).map((value) => (
            <button
              key={value}
              type="button"
              disabled={signed}
              title={CASE_TYPE[value].note}
              onClick={() =>
                patchDraft(
                  (next) => {
                    next.case = value
                  },
                  { path: 'case', from: model?.case ?? '—', to: value },
                )
              }
              className={`cursor-pointer rounded-[5px] border px-3 py-1.5 text-[11.5px] font-semibold ${
                draft.case === value
                  ? 'border-accent bg-accent-tint text-accent'
                  : 'border-line bg-surface-2 text-ink-3'
              }`}
            >
              {CASE_TYPE[value].label}
            </button>
          ))}
        </div>
        <Hint className="mt-1.5">Determina qué marcos se consideran aplicables al activo.</Hint>
      </div>
    </div>
  )
}

function SLGrid({ draft }: { draft: AssetProfileDraft }) {
  const { correctSL, correctTargetSL, patchDraft, corrections, signed } = useComposition()
  const corrected = (path: string) => corrections.some((c) => c.path === path)

  return (
    <>
      <div className="mb-1 flex items-baseline justify-between">
        <Caps>Zonas y nivel de seguridad exigido</Caps>
        <button
          type="button"
          disabled={signed}
          onClick={() =>
            patchDraft((next) => {
              next.zones.push({
                id: `Z-${next.zones.length + 1}`,
                target_sl: null,
                purdue: null,
                role: null,
                position: null,
                sl_vector: null,
                safety_out_of_scope: null,
                reference: null,
              })
            })
          }
          className="cursor-pointer rounded-[5px] border border-line-strong bg-transparent px-2.5 py-1 text-[11px] font-semibold text-ink-2 hover:border-accent hover:text-accent"
        >
          + añadir zona
        </button>
      </div>
      <Hint className="mb-2.5">
        Una zona es una parte del activo con un mismo nivel de exposición y de exigencia. El{' '}
        <b>nivel objetivo</b> va de 1 (protección frente a errores casuales) a 4 (frente a un
        atacante con muchos recursos y tiempo). Las siete columnas siguientes permiten afinar ese
        nivel por familia de requisitos; si no lo sabes, déjalas como están. Pulsa una celda para
        subir su valor; al pasar de 4 vuelve a «sin declarar».
      </Hint>

      <div className="mb-4 grid items-center gap-1 text-xs [grid-template-columns:190px_54px_repeat(7,44px)_auto_28px]">
        <span className="text-[10.5px] font-semibold text-ink-4">Zona</span>
        <span
          title="Nivel de seguridad objetivo de la zona, de 1 a 4"
          className="text-center text-[10.5px] font-semibold text-ink-4"
        >
          Nivel
        </span>
        {FR_FIELDS.map((fr) => (
          <span
            key={fr}
            title={FR_MEANING[fr]}
            className="cursor-help text-center text-[10.5px] font-semibold text-ink-4"
          >
            {fr}
          </span>
        ))}
        <span />
        <span />

        {draft.zones.map((zone, zoneIndex) => {
          const zoneCorrections = corrections.filter((c) =>
            c.path.startsWith(`zones[${zone.id}]`),
          ).length
          return (
            <div key={zoneIndex} className="contents">
              <input
                value={zone.id}
                disabled={signed}
                title="Nombre corto de la zona; aparecerá en el registro de decisiones"
                onChange={(event) =>
                  patchDraft((next) => {
                    next.zones[zoneIndex].id = event.target.value.toUpperCase()
                  })
                }
                className={`font-mono text-[11.5px] font-medium ${INPUT}`}
              />
              <button
                type="button"
                disabled={signed}
                onClick={() => correctTargetSL(zoneIndex, ((zone.target_sl ?? 0) % 4) + 1)}
                title="Nivel de seguridad objetivo de la zona, de 1 a 4. Pulsa para cambiarlo."
                className={`h-[30px] cursor-pointer rounded-[5px] border font-mono text-[13px] font-semibold ${
                  corrected(`zones[${zone.id}].target_sl`)
                    ? 'border-accent bg-accent-tint text-accent'
                    : 'border-line bg-surface-2 text-ink'
                }`}
              >
                {zone.target_sl ?? '·'}
              </button>
              {FR_FIELDS.map((fr) => {
                const value = zone.sl_vector?.[fr]
                const mark = corrected(`zones[${zone.id}].sl_vector.${fr}`)
                return (
                  <button
                    key={fr}
                    type="button"
                    disabled={signed}
                    title={`${FR_MEANING[fr]} — nivel exigido en esta zona. Pulsa para cambiarlo.`}
                    onClick={() => correctSL(zoneIndex, fr)}
                    className={`h-[30px] cursor-pointer rounded-[5px] border font-mono text-[13px] font-semibold ${
                      mark
                        ? 'border-accent bg-accent-tint text-accent'
                        : `border-line text-ink ${(value ?? 0) >= 3 ? 'bg-line-3' : 'bg-surface-2'}`
                    }`}
                  >
                    {value ?? '·'}
                  </button>
                )
              })}
              <span className="pl-1.5 text-[11px] font-semibold text-accent">
                {zoneCorrections ? `◆ ${zoneCorrections} corregido(s)` : ''}
              </span>
              <button
                type="button"
                disabled={signed || draft.zones.length <= 1}
                title="Quitar esta zona"
                onClick={() =>
                  patchDraft((next) => {
                    next.zones.splice(zoneIndex, 1)
                  })
                }
                className="cursor-pointer border-none bg-transparent text-[13px] text-ink-5 hover:text-alert disabled:opacity-30"
              >
                ✕
              </button>
            </div>
          )
        })}
      </div>
    </>
  )
}

function Criticality({ draft }: { draft: AssetProfileDraft }) {
  const { correctCriticality, patchDraft, corrections, signed, parseResult } = useComposition()
  const model = parseResult?.draft

  const text = (field: 'physical_consequence' | 'threat_model', placeholder: string) => (
    <input
      value={draft.criticality[field] ?? ''}
      disabled={signed}
      placeholder={placeholder}
      onChange={(event) =>
        patchDraft(
          (next) => {
            next.criticality[field] = event.target.value || null
          },
          {
            path: `criticality.${field}`,
            from: model?.criticality[field] ?? '—',
            to: event.target.value || '—',
          },
        )
      }
      className={`w-full ${INPUT}`}
    />
  )

  return (
    <>
      <Caps className="mt-4 mb-1">Qué pasa en el mundo físico si esto falla</Caps>
      <Hint className="mb-2">
        No es la importancia del equipo, sino el daño real que se produciría: fuga, sobrepresión,
        parada de servicio, riesgo para personas.
      </Hint>
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-1.5">
          {(Object.keys(CONSEQUENCE_SCALE) as ConsequenceScale[]).map((scale) => (
            <button
              key={scale}
              type="button"
              disabled={signed}
              onClick={() => correctCriticality(scale)}
              className={`cursor-pointer rounded-[5px] border px-3 py-1.5 text-xs font-semibold ${
                draft.criticality.scale === scale
                  ? 'border-accent bg-accent-tint text-accent'
                  : 'border-line bg-surface-2 text-ink-3'
              }`}
            >
              {CONSEQUENCE_SCALE[scale]}
            </button>
          ))}
          {corrections.some((c) => c.path === 'criticality.scale') ? (
            <span className="text-[11px] font-semibold text-accent">◆ corregido por ti</span>
          ) : null}
        </div>
        {text(
          'physical_consequence',
          'Consecuencia concreta, p. ej. «sobrepresión y rotura de línea con fuga de gas»',
        )}
        {text(
          'threat_model',
          'Modelo de amenaza de referencia, p. ej. «MITRE ATT&CK for ICS» (si no usas ninguno, indícalo)',
        )}
      </div>
    </>
  )
}

function Conduits({ draft }: { draft: AssetProfileDraft }) {
  const { patchDraft, signed } = useComposition()

  return (
    <>
      <div className="mb-1 flex items-baseline justify-between">
        <Caps>Enlaces entre zonas</Caps>
        <button
          type="button"
          disabled={signed}
          onClick={() =>
            patchDraft((next) => {
              next.conduits.push({
                id: `C-${next.conduits.length + 1}`,
                endpoints: [],
                control: null,
              })
            })
          }
          className="cursor-pointer rounded-[5px] border border-line-strong bg-transparent px-2.5 py-1 text-[11px] font-semibold text-ink-2 hover:border-accent hover:text-accent"
        >
          + añadir enlace
        </button>
      </div>
      <Hint className="mb-2">
        Por dónde se comunican unas zonas con otras, y qué protege ese paso (cortafuegos, equipo de
        salto, diodo de datos…).
      </Hint>

      <div className="flex flex-col gap-1.5">
        {draft.conduits.length === 0 ? (
          <span className="text-xs text-ink-4">
            Tu descripción no menciona ningún enlace entre zonas. Un activo aislado es una respuesta
            válida: no hace falta inventarse uno.
          </span>
        ) : null}
        {draft.conduits.map((conduit, index) => (
          <div key={index} className="flex items-center gap-1.5">
            <input
              value={conduit.id}
              disabled={signed}
              title="Nombre corto del enlace"
              onChange={(event) =>
                patchDraft((next) => {
                  next.conduits[index].id = event.target.value.toUpperCase()
                })
              }
              className={`w-24 font-mono ${INPUT}`}
            />
            <input
              value={conduit.endpoints.join(', ')}
              disabled={signed}
              placeholder="Zonas que conecta, separadas por comas"
              onChange={(event) =>
                patchDraft((next) => {
                  next.conduits[index].endpoints = event.target.value
                    .split(',')
                    .map((part) => part.trim())
                    .filter(Boolean)
                })
              }
              className={`flex-1 ${INPUT}`}
            />
            <input
              value={conduit.control ?? ''}
              disabled={signed}
              placeholder="Qué protege el paso, p. ej. «equipo de salto»"
              onChange={(event) =>
                patchDraft((next) => {
                  next.conduits[index].control = event.target.value || null
                })
              }
              className={`flex-1 ${INPUT}`}
            />
            <button
              type="button"
              disabled={signed}
              title="Quitar este enlace"
              onClick={() =>
                patchDraft((next) => {
                  next.conduits.splice(index, 1)
                })
              }
              className="cursor-pointer border-none bg-transparent text-[13px] text-ink-5 hover:text-alert"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </>
  )
}

function Review({ draft }: { draft: AssetProfileDraft }) {
  const { correctNature, corrections, missing, signed, source } = useComposition()

  return (
    <>
      <p className="m-0 mb-4 text-[12.5px] leading-[1.55] text-ink-3">
        {source === 'manual'
          ? 'Estás rellenando la ficha a mano: nada de lo que hay aquí lo ha propuesto el asistente. No se comprueba si los valores son acertados —eso lo decides tú—, solo que no falte ninguno.'
          : 'Todo se puede cambiar. Lo que corrijas queda marcado con ◆ y es tu versión, no la del asistente, la que se usa para calcular. No se comprueba si los valores son acertados —eso lo decides tú—, solo que no falte ninguno.'}
      </p>

      <Identity draft={draft} />
      <SLGrid draft={draft} />

      <div className="grid grid-cols-2 gap-5">
        <div>
          <Caps className="mb-1">Cómo es el activo por dentro</Caps>
          <Hint className="mb-2">
            Pulsa para alternar entre <b>sí</b>, <b>no</b> y <b>sin declarar</b>. Estas respuestas
            deciden qué controles tienen sentido en este activo, así que dejar una sin declarar es
            preferible a adivinarla.
          </Hint>
          <div className="flex flex-wrap gap-1.5">
            {(Object.keys(NATURE) as NatureField[]).map((field) => {
              const value = draft.nature[field]
              const mark = corrections.some((c) => c.path === `nature.${field}`)
              const state = value === true ? 'sí' : value === false ? 'no' : 'sin declarar'
              return (
                <button
                  key={field}
                  type="button"
                  disabled={signed}
                  onClick={() => correctNature(field)}
                  title={`${NATURE[field].note} — ahora: ${state}`}
                  className={`cursor-pointer rounded-[5px] border px-2.5 py-1.5 text-xs font-semibold ${
                    mark ? 'border-accent' : 'border-line'
                  } ${
                    value === true
                      ? 'bg-accent-tint text-accent'
                      : value === false
                        ? 'bg-surface-2 text-ink-3'
                        : 'bg-surface-2 text-ink-5'
                  }`}
                >
                  {value === true ? '■' : value === false ? '□' : '·'} {NATURE[field].label}{' '}
                  {mark ? '◆' : ''}
                </button>
              )
            })}
          </div>
          <Criticality draft={draft} />
        </div>

        <div>
          <Conduits draft={draft} />
          {draft.unmapped.length > 0 ? (
            <>
              <Caps className="mt-4 mb-1">Lo que dijiste y no encaja en ningún campo</Caps>
              <Hint className="mb-2">
                No se ha descartado: queda aquí a la vista para que decidas si hace falta algo más.
              </Hint>
              <ul className="m-0 flex list-none flex-col gap-1 p-0">
                {draft.unmapped.map((statement, index) => (
                  <li
                    key={index}
                    className="rounded-[5px] border border-dashed border-line-dashed bg-surface-2 px-2.5 py-[7px] text-xs text-ink-3"
                  >
                    {statement}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      </div>

      {missing.length > 0 ? (
        <div className="mt-4">
          <Notice tone="warn" label="FALTAN DATOS">
            <div className="mb-1.5">
              Faltan {missing.length} dato(s) por rellenar antes de poder continuar. No se ponen
              valores por defecto a propósito: un nivel de seguridad que nadie ha decidido produciría
              una línea base que nadie ha decidido.
            </div>
            <ul className="m-0 flex list-disc flex-col gap-0.5 pl-5 text-[12px]">
              {missing.map((path) => (
                <li key={path}>{fieldLabel(path)}</li>
              ))}
            </ul>
          </Notice>
        </div>
      ) : null}
    </>
  )
}

export function StageAsset() {
  const {
    description,
    setDescription,
    descriptionLocked,
    unlockDescription,
    parsing,
    parseError,
    parseResult,
    draft,
    runParse,
    startManualDraft,
    signed,
    profile,
    source,
  } = useComposition()

  const words = description.trim().split(/\s+/).filter(Boolean).length

  return (
    <>
      <Section
        id="s1"
        step={1}
        title="Describe el activo con tus palabras"
        hint="Cuenta qué es el activo, qué controla, cómo está conectado y quién lo usa. El asistente leerá tu texto y rellenará una ficha con lo que haya entendido, señalando de qué frase sale cada dato. No decide nada: solo lee."
        scope="afecta a todo el activo"
      >
        <div className="grid grid-cols-2 items-start gap-5">
          <div className="flex flex-col gap-2.5">
            <Caps>Tu descripción</Caps>
            {!descriptionLocked ? (
              <>
                <textarea
                  value={description}
                  disabled={signed || parsing}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="Por ejemplo: «Estación de regulación y medida de un gasoducto. Un PLC gobierna las válvulas de corte y un SCADA en Windows las supervisa desde la sala de control. El SCADA está en la red corporativa y el mantenimiento entra por VPN dos veces al mes. Una fuga afectaría a una zona habitada.»"
                  className="min-h-[220px] w-full resize-y rounded-md border border-line-strong bg-surface-2 px-3.5 py-3 text-[13.5px] leading-[1.6] text-ink outline-accent"
                />
                <div className="flex flex-wrap items-center gap-3.5">
                  <PrimaryButton
                    testId="parse"
                    disabled={signed || parsing || description.trim() === ''}
                    onClick={() => void runParse()}
                  >
                    {parsing ? 'Analizando tu descripción…' : 'Analizar la descripción'}
                  </PrimaryButton>
                  <button
                    type="button"
                    disabled={signed || parsing}
                    onClick={startManualDraft}
                    className="cursor-pointer border-none bg-transparent p-0 text-[12.5px] text-accent underline disabled:opacity-50"
                  >
                    prefiero rellenar la ficha yo mismo
                  </button>
                </div>
                {parsing ? (
                  <span className="text-xs font-medium text-warn-ink">
                    Trabajando. Lo que va a extraer de tu texto está al lado →
                  </span>
                ) : null}
              </>
            ) : (
              <>
                <div className="rounded-md border border-line-2 bg-surface-2 px-3.5 py-3 text-[13.5px] leading-[1.6] whitespace-pre-wrap">
                  {description}
                </div>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    disabled={signed}
                    onClick={unlockDescription}
                    className="cursor-pointer rounded-[5px] border border-line-strong bg-transparent px-3 py-1.5 text-xs font-semibold text-ink-2 hover:border-accent hover:text-accent"
                  >
                    Editar la descripción
                  </button>
                  <span className="text-[11px] text-ink-4">
                    Si la cambias, tendrás que volver a analizarla para actualizar la ficha.
                  </span>
                </div>
              </>
            )}

            {parseError ? (
              <Notice tone="alert" label="NO SE PUDO ANALIZAR">
                {parseError}
              </Notice>
            ) : null}
          </div>

          <div className="flex flex-col gap-2">
            <Caps>Lo que el asistente ha entendido</Caps>
            {/* While the model runs, this column is the working panel: the stale
                evidence of a previous run belongs to that run, not to this one. */}
            {parsing ? <Working words={words} /> : null}
            {!parsing && !draft ? (
              <div className="rounded-md border border-dashed border-line-strong px-4 py-7 text-center text-[12.5px] leading-[1.5] text-ink-4">
                Aquí aparecerá, dato a dato, lo que el asistente haya sacado de tu texto, junto con
                la frase concreta de la que sale cada uno.
              </div>
            ) : null}
            {!parsing && draft && source === 'manual' ? (
              <div className="rounded-md border border-line-2 bg-surface-2 px-3.5 py-3 text-[12.5px] leading-[1.5] text-ink-3">
                Estás rellenando la ficha a mano, así que no hay nada que el asistente haya
                interpretado. Complétala abajo: lo que falte se avisa al final.
              </div>
            ) : null}
            {!parsing && parseResult ? (
              <>
                <div className="flex flex-wrap gap-1">
                  <Tag className="bg-warn-tint text-warn-ink">
                    revísalo antes de seguir
                  </Tag>
                  <Tag title="Identificador con el que este activo aparecerá en el registro de decisiones">
                    {parseResult.profile_id}
                  </Tag>
                </div>
                {draft ? <EvidenceList notes={draft.notes} /> : null}
              </>
            ) : null}
          </div>
        </div>
      </Section>

      <Section
        id="s2"
        step={1}
        title="Revisa y corrige la ficha"
        hint="Manda lo que tú dejes escrito aquí. Corrige lo que el asistente haya entendido mal y completa lo que falte: a partir de esta ficha se calculan todos los controles del paso siguiente."
        scope="afecta a todo el activo"
      >
        {parsing ? (
          <p className="m-0 text-[13px] text-ink-4">
            <span className="animate-blink mr-1.5 font-semibold text-warn-ink">●</span>
            El asistente todavía está leyendo tu descripción. En cuanto termine, la ficha aparecerá
            aquí entera para que la revises y la corrijas.
          </p>
        ) : draft ? (
          <Review draft={draft} />
        ) : (
          <p className="m-0 text-[13px] text-ink-4">
            Primero describe el activo arriba y pulsa «Analizar la descripción», o elige rellenar la
            ficha tú mismo.
          </p>
        )}
        {profile ? (
          <div className="mt-4 rounded-md border border-ok-line bg-ok-tint px-3.5 py-2.5 text-[12.5px] text-ok-ink">
            ✓ La ficha está completa: {profile.zones.length} zona(s) · tipo{' '}
            {CASE_TYPE[profile.case].label}. Ya puedes pasar al paso 2 y ver los controles
            disponibles.
          </div>
        ) : null}
      </Section>
    </>
  )
}
