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

import {
  FR_FIELDS,
  type AssetProfileDraft,
  type CaseType,
  type ConsequenceScale,
  type NatureField,
  type ParseNote,
} from '../../api/types'
import { CONSEQUENCE_SCALE, NATURE } from '../../lib/labels'
import { useComposition } from '../../state/composition'
import { Caps, Notice, PrimaryButton, Section, Tag } from '../ui'

const INPUT =
  'rounded-[5px] border border-line bg-surface-2 px-2.5 py-1.5 text-xs text-ink outline-accent'

function EvidenceList({ notes }: { notes: ParseNote[] }) {
  if (notes.length === 0) return null
  return (
    <div className="flex flex-col gap-1.5">
      <Caps>Evidencia — de qué frase sale cada campo</Caps>
      {notes.map((note, index) => (
        <div
          key={`${note.field}-${index}`}
          className="rounded-md border border-line-2 bg-surface-2 px-3 py-2 text-[11.5px] leading-[1.5]"
        >
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="font-mono text-[10.5px] font-semibold text-accent">{note.field}</span>
            <Tag
              className={
                note.kind === 'stated' ? 'bg-ok-tint text-ok-ink' : 'bg-warn-tint text-warn-ink'
              }
            >
              {note.kind === 'stated' ? 'dicho' : 'inferido'}
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
        <Caps className="mb-2">Caso</Caps>
        <div className="flex gap-1.5">
          {(['PURE_OT', 'HYBRID_IT_OT'] as CaseType[]).map((value) => (
            <button
              key={value}
              type="button"
              disabled={signed}
              onClick={() =>
                patchDraft(
                  (next) => {
                    next.case = value
                  },
                  { path: 'case', from: model?.case ?? '—', to: value },
                )
              }
              className={`cursor-pointer rounded-[5px] border px-3 py-1.5 font-mono text-[11px] font-semibold ${
                draft.case === value
                  ? 'border-accent bg-accent-tint text-accent'
                  : 'border-line bg-surface-2 text-ink-3'
              }`}
            >
              {value}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function SLGrid({ draft }: { draft: AssetProfileDraft }) {
  const { correctSL, correctTargetSL, patchDraft, corrections, signed } = useComposition()
  const corrected = (path: string) => corrections.some((c) => c.path === path)

  return (
    <>
      <div className="mb-2 flex items-baseline justify-between">
        <Caps>Zonas y vector SL-T (clic en una celda para corregir)</Caps>
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

      <div className="mb-4 grid items-center gap-1 text-xs [grid-template-columns:190px_54px_repeat(7,44px)_auto_28px]">
        <span />
        <span className="text-center font-mono text-[10.5px] font-semibold text-ink-4">SL-T</span>
        {FR_FIELDS.map((fr) => (
          <span key={fr} className="text-center font-mono text-[10.5px] font-semibold text-ink-4">
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
                title="SL objetivo de la zona (1–4)"
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
                title="quitar zona"
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
      <Caps className="mt-4 mb-2">Criticidad — consecuencia física</Caps>
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
            <span className="text-[11px] font-semibold text-accent">◆ corregido</span>
          ) : null}
        </div>
        {text('physical_consequence', 'consecuencia física, p. ej. overpressure_rupture_leak')}
        {text('threat_model', 'modelo de amenaza citado, p. ej. ATTACK_for_ICS')}
      </div>
    </>
  )
}

function Conduits({ draft }: { draft: AssetProfileDraft }) {
  const { patchDraft, signed } = useComposition()

  return (
    <>
      <div className="mb-2 flex items-baseline justify-between">
        <Caps>Conductos</Caps>
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
          + añadir conducto
        </button>
      </div>

      <div className="flex flex-col gap-1.5">
        {draft.conduits.length === 0 ? (
          <span className="text-xs text-ink-4">
            El texto no describe ningún conducto. Un activo aislado es legítimo.
          </span>
        ) : null}
        {draft.conduits.map((conduit, index) => (
          <div key={index} className="flex items-center gap-1.5">
            <input
              value={conduit.id}
              disabled={signed}
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
              placeholder="extremos, separados por comas"
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
              placeholder="control, p. ej. jump_host"
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
              title="quitar conducto"
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
      <p className="m-0 mb-4 text-[12.5px] text-ink-3">
        {source === 'manual'
          ? 'Perfil a mano: nada viene del modelo, todo lo declara el operador. La UI no valida semántica; comprueba que no falte nada.'
          : 'Todo campo es editable. Un campo corregido queda marcado ◆ y viaja al motor dentro del AssetProfile de esta ejecución; el borrador del modelo no es nunca la entrada. La UI no valida semántica: comprueba que no falte nada.'}
      </p>

      <Identity draft={draft} />
      <SLGrid draft={draft} />

      <div className="grid grid-cols-2 gap-5">
        <div>
          <Caps className="mb-2">Naturaleza del activo</Caps>
          <div className="flex flex-wrap gap-1.5">
            {(Object.keys(NATURE) as NatureField[]).map((field) => {
              const value = draft.nature[field]
              const mark = corrections.some((c) => c.path === `nature.${field}`)
              return (
                <button
                  key={field}
                  type="button"
                  disabled={signed}
                  onClick={() => correctNature(field)}
                  title="sí → no → sin declarar"
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
                  {value === true ? '■' : value === false ? '□' : '·'} {NATURE[field]}{' '}
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
              <Caps className="mt-4 mb-2">Sin sitio en el esquema — reportado, no descartado</Caps>
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
          <Notice tone="warn" label="FALTA">
            El perfil no está completo. Rellena estos campos antes de pedir candidatos:{' '}
            <span className="font-mono text-[11.5px]">{missing.join(', ')}</span>
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

  return (
    <>
      <Section
        id="s1"
        step={1}
        title="El activo — descripción y perfil"
        scope="activo completo — no depende de la zona"
      >
        <p className="m-0 mb-4 text-[12.5px] text-ink-3">
          Un único input: la descripción en texto libre. De aquí nace el{' '}
          <span className="font-mono">AssetProfile</span> de esta baseline (
          <span className="font-mono">POST /asset/parse</span>). El modelo extrae; no decide.
        </p>

        <div className="grid grid-cols-2 items-start gap-5">
          <div className="flex flex-col gap-2.5">
            <Caps>Descripción — texto libre</Caps>
            {!descriptionLocked ? (
              <>
                <textarea
                  value={description}
                  disabled={signed || parsing}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="Describe el activo: qué es, qué controla, cómo se conecta, quién lo toca…"
                  className="min-h-[220px] w-full resize-y rounded-md border border-line-strong bg-surface-2 px-3.5 py-3 text-[13.5px] leading-[1.6] text-ink outline-accent"
                />
                <div className="flex flex-wrap items-center gap-3.5">
                  <PrimaryButton
                    testId="parse"
                    disabled={signed || parsing || description.trim() === ''}
                    onClick={() => void runParse()}
                  >
                    Extraer perfil · POST /asset/parse
                  </PrimaryButton>
                  <button
                    type="button"
                    disabled={signed || parsing}
                    onClick={startManualDraft}
                    className="cursor-pointer border-none bg-transparent p-0 text-[12.5px] text-accent underline disabled:opacity-50"
                  >
                    introducir perfil a mano
                  </button>
                </div>
                {parsing ? (
                  <span className="animate-blink font-mono text-xs font-medium text-warn">
                    el modelo está decodificando en CPU — esto tarda minutos
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
                    editar descripción
                  </button>
                  <span className="text-[11px] text-ink-4">
                    editarla invalida el perfil extraído hasta volver a parsear
                  </span>
                </div>
              </>
            )}

            {parseError ? (
              <Notice tone="alert" label="PARSE">
                {parseError}
              </Notice>
            ) : null}
          </div>

          <div className="flex flex-col gap-2">
            <Caps>
              AssetProfile — borrador extraído por{' '}
              {parseResult?.provenance.model ?? 'el modelo local'}
            </Caps>
            {!draft ? (
              <div className="rounded-md border border-dashed border-line-strong px-4 py-7 text-center text-[12.5px] text-ink-4">
                El borrador aparecerá aquí campo a campo, con la frase de la que sale cada valor.
              </div>
            ) : null}
            {draft && source === 'manual' ? (
              <div className="rounded-md border border-line-2 bg-surface-2 px-3.5 py-3 text-[12.5px] text-ink-3">
                Perfil a mano: el modelo no ha intervenido, así que no hay evidencia que mostrar.
                Rellena los campos abajo; lo que falte se lista en rojo.
              </div>
            ) : null}
            {parseResult ? (
              <>
                <div className="flex flex-wrap gap-1">
                  <Tag>{parseResult.profile_id}</Tag>
                  <Tag>{parseResult.provenance.attempts} intento(s)</Tag>
                  <Tag title="SHA-256 del texto de origen">
                    src:{parseResult.provenance.source_sha256.slice(0, 8)}
                  </Tag>
                  <Tag className="bg-warn-tint text-warn-ink">revisión humana obligatoria</Tag>
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
        title="Revisión y corrección — el humano decide"
        scope="activo completo — no depende de la zona"
      >
        {draft ? (
          <Review draft={draft} />
        ) : (
          <p className="m-0 text-[13px] text-ink-4">
            Pendiente: describe el activo y extrae el perfil, o introdúcelo a mano.
          </p>
        )}
        {profile ? (
          <div className="mt-4 text-[11.5px] text-ink-4">
            Perfil listo: <span className="font-mono">{profile.id}</span> · {profile.zones.length}{' '}
            zona(s) · caso <span className="font-mono">{profile.case}</span>
          </div>
        ) : null}
      </Section>
    </>
  )
}
