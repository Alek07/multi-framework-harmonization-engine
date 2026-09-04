/**
 * One option, side by side with its equivalents: framework, official id,
 * jurisdiction, mapping type and weight, provenance (solid border = official
 * crosswalk, dotted = author judgment) and the core's verdict (`superseded`,
 * `contested`, and why). No recommendation, score or "best" mark — the engine
 * offers, the human chooses.
 */

import type {
  CandidateExplanation,
  CandidateOption,
  FrameworkControl,
  Mapping,
  RetrievedControl,
} from '../../../api/types'
import {
  CANDIDATE_STATUS,
  FRAMEWORK,
  GATING_OUTCOME,
  FRAMEWORK_NOTE,
  JURISDICTION_SHORT,
  MAPPING_TYPE,
  PROVENANCE,
  STRENGTH_KIND,
  strengthText,
} from '../../../lib/labels'
import { Fold } from '../../../components/ui'

interface Common {
  control: FrameworkControl
  picked: boolean
  disabled: boolean
  onPick: () => void
  explanation?: CandidateExplanation
}

function Shell({
  control,
  picked,
  disabled,
  onPick,
  explanation,
  dotted,
  faded,
  origin,
  meta,
  banner,
  bannerLabel,
}: Common & {
  dotted: boolean
  faded?: boolean
  origin: 'catalog' | 'retrieval'
  meta: React.ReactNode
  banner?: React.ReactNode
  /**
   * The sentence standing in for a paragraph-length banner while it is folded.
   * These prose blocks start closed to keep the card short — folded, never
   * dropped: what the engine said stays one click away on the option itself.
   */
  bannerLabel?: string
}) {
  const framework = FRAMEWORK[control.framework]
  return (
    <div
      role="checkbox"
      tabIndex={0}
      aria-checked={picked}
      data-testid="option"
      data-control-id={control.id}
      data-origin={origin}
      onClick={() => !disabled && onPick()}
      onKeyDown={(event) => {
        if (disabled) return
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onPick()
        }
      }}
      className={`flex cursor-pointer flex-col gap-1.5 rounded-[7px] px-3.5 py-3 hover:shadow-[0_1px_6px_rgba(24,34,48,.10)] ${
        dotted ? 'border-dashed' : 'border-solid'
      } ${
        picked
          ? 'border-2 border-accent bg-accent-tint-2'
          : `border ${dotted ? 'border-[#b5ad9d]' : 'border-[#d7d3ca]'} bg-surface`
      } ${faded ? 'opacity-70' : ''} ${disabled ? 'cursor-default' : ''}`}
    >
      <div className="flex flex-wrap items-center gap-1.75">
        <span
          className={`inline-block h-3.75 w-3.75 flex-none rounded-sm border-[1.5px] text-center text-[10px] leading-3.25 font-semibold ${
            picked ? 'border-accent bg-accent text-white' : 'border-ink-5 bg-surface'
          }`}
        >
          {picked ? '✓' : ''}
        </span>
        <span
          title={FRAMEWORK_NOTE[control.framework]}
          className={`cursor-help rounded-sm px-1.5 py-0.5 text-[10px] font-semibold ${framework.className}`}
        >
          {framework.label}
        </span>
        <span
          title="Referencia del control dentro de su norma"
          className="font-mono text-xs font-semibold"
        >
          {control.official_id}
        </span>
        <span
          title="Ámbito normativo al que responde este control"
          className="rounded-sm bg-[#eef0f2] px-1.5 py-0.5 text-[10px] font-medium text-ink-2"
        >
          {JURISDICTION_SHORT[control.jurisdiction]}
        </span>
      </div>

      {/*
        Paraphrase leads (Spanish, ours), official title follows quieter (the
        standard's, verbatim and untranslated so it stays citable against the
        source). Leading with the English made a Spanish screen read half-translated.
      */}
      <div className="text-[12.5px] leading-[1.35] font-semibold">
        {control.paraphrased_description}
      </div>
      <div
        lang="en"
        title="Título oficial del control en su norma, sin traducir: es el texto que hay que citar para localizarlo en la fuente."
        className="cursor-help text-[10.5px] leading-[1.4] text-ink-4"
      >
        {control.title}
      </div>
      <div className="flex flex-wrap items-center gap-2.5 text-[11.5px] text-ink-2">{meta}</div>
      {/*
        Scale looked up defensively: a client one version behind the server may see
        a `kind` this table lacks, and a tooltip is never worth crashing the card tree.
      */}
      <div
        className="cursor-help text-[10px] text-ink-4"
        title={[
          STRENGTH_KIND[control.strength.kind]?.note,
          `Referencia interna en el catálogo: ${control.id}.`,
        ]
          .filter(Boolean)
          .join(' ')}
      >
        Exigencia del control: {strengthText(control.strength)}
      </div>

      {banner && bannerLabel ? <Fold summary={bannerLabel}>{banner}</Fold> : banner}

      {explanation ? (
        <Fold
          summary={
            explanation.status === 'generated'
              ? 'Explicación del asistente'
              : 'Explicación del sistema'
          }
        >
          <div className="mt-1.5 rounded-[5px] border border-dashed border-line-dashed bg-surface-4 px-2.5 py-1.75">
            {explanation.status === 'generated' ? (
              <div className="text-[10.5px] font-semibold text-ink-4">
                Solo para ayudarte a leer; no cambia el orden ni marca preferencias
              </div>
            ) : null}
            <div className="mt-1 text-xs leading-normal text-ink-3">{explanation.text}</div>
            {explanation.notice ? (
              <div className="mt-1 text-[10px] text-warn">{explanation.notice}</div>
            ) : null}
            {explanation.basis.length > 0 ? (
              <div className="mt-1 text-[10px] text-ink-4">
                Se basa en: {explanation.basis.join(', ')}
              </div>
            ) : null}
          </div>
        </Fold>
      ) : null}
    </div>
  )
}

function MappingMeta({ mapping }: { mapping: Mapping }) {
  const type = MAPPING_TYPE[mapping.type]
  const provenance = PROVENANCE[mapping.provenance.source]
  const authored = mapping.provenance.source === 'author_judgment'
  return (
    <>
      <span title={type.note} className="cursor-help">
        <span className="text-accent">{type.glyph}</span> {type.label}
      </span>
      <span
        title="Parte del requisito que este control cubre por sí solo"
        className="text-[11px] font-semibold"
      >
        cubre {Math.round(mapping.coverage_weight * 100)} %
      </span>
      <span
        title={`${provenance.note}${mapping.provenance.note ? ` — ${mapping.provenance.note}` : ''}`}
        className={`cursor-help rounded-sm border px-1.5 py-px text-[10px] font-semibold ${
          authored ? 'border-dashed text-warn' : 'border-solid text-[#1d6f4c]'
        }`}
      >
        {provenance.label}
      </span>
    </>
  )
}

/** A candidate the deterministic core mapped to this capability. */
export function CatalogOption({
  option,
  picked,
  disabled,
  onPick,
  explanation,
}: {
  option: CandidateOption
} & Omit<Common, 'control'>) {
  const superseded = option.status === 'superseded'
  return (
    <Shell
      control={option.control}
      picked={picked}
      disabled={disabled}
      onPick={onPick}
      explanation={explanation}
      dotted={option.mapping.provenance.source === 'author_judgment'}
      faded={superseded}
      origin="catalog"
      meta={
        <>
          <MappingMeta mapping={option.mapping} />
          {option.status !== 'eligible' ? (
            <span
              title={CANDIDATE_STATUS[option.status].note}
              className="cursor-help text-[10px] font-semibold text-alert-ink"
            >
              {CANDIDATE_STATUS[option.status].label}
            </span>
          ) : null}
        </>
      }
      banner={
        option.status_reason ? (
          <div
            className="rounded-[5px] bg-surface-2 px-2.5 py-1.5 text-[11px] leading-[1.45] text-ink-3"
            title={option.rule_id ? `Regla aplicada: ${option.rule_id}` : undefined}
          >
            {option.status_reason}
          </div>
        ) : undefined
      }
    />
  )
}

/**
 * A RAG suggestion: a neighbour in embedding space, not a mapping. Offered
 * (retrieval only widens) and labelled as such; adopting one is a human judgement
 * recorded as `adopted_suggestion`, never absorbed into the authored mappings.
 */
export function RetrievedOption({
  hit,
  picked,
  disabled,
  onPick,
  explanation,
}: {
  hit: RetrievedControl
} & Omit<Common, 'control'>) {
  return (
    <Shell
      control={hit.control}
      picked={picked}
      disabled={disabled}
      onPick={onPick}
      explanation={explanation}
      dotted
      origin="retrieval"
      meta={
        <>
          <span
            title="No es una equivalencia del catálogo: es un control parecido que se te ofrece por si encaja. Adoptarlo es decisión tuya."
            className="cursor-help rounded-sm border border-dashed border-warn px-1.5 py-px text-[10px] font-semibold text-warn"
          >
            sugerencia, no equivalencia
          </span>
          <span
            title={`Grado de parecido calculado: ${hit.score.toFixed(3)}`}
            className="cursor-help text-[11px]"
          >
            parecido {Math.round(hit.score * 100)} %
          </span>
          {hit.mapped_capability_ids.length > 0 ? (
            <span className="text-[11px] text-ink-3">
              ya asociado a: {hit.mapped_capability_ids.join(', ')}
            </span>
          ) : null}
          {/* Reads last because the zone's gating ruled it out here. Shown marked,
              not hidden — the operator may still adopt it, with the reason on the card. */}
          {hit.gated_out ? (
            <span
              title={hit.gated_out.rationale}
              className={`cursor-help rounded-sm px-1.5 py-px text-[10px] font-semibold ${GATING_OUTCOME[hit.gated_out.outcome].className}`}
            >
              {GATING_OUTCOME[hit.gated_out.outcome].label}
            </span>
          ) : null}
        </>
      }
      bannerLabel="Por qué se te ofrece esta sugerencia"
      banner={
        <div className="mt-1.5 rounded-[5px] bg-surface-2 px-2.5 py-1.5 text-[11px] leading-[1.45] text-ink-3">
          {hit.rationale}
        </div>
      }
    />
  )
}
