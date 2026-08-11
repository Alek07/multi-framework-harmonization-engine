/**
 * One option, side by side with its equivalents.
 *
 * This card is the sovereign composition in one shape: framework, official id,
 * jurisdiction, what the mapping type and weight are, where the mapping comes
 * from (a solid border for an official crosswalk, a dotted one for the author's
 * judgment) and what the core already said about it (`superseded`, `contested`,
 * and why). What it does not carry is a recommendation, a score to sort by or a
 * "best" mark — the engine offers, the human chooses.
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
   * When the banner is a paragraph rather than a line, the sentence that stands
   * in for it while it is folded. The prose blocks at the foot of the card are
   * the longest thing in it and the operator reads them once, if at all, so they
   * start closed — folded, never dropped: what the engine said about an option
   * stays one click away on the option itself.
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
      <div className="flex flex-wrap items-center gap-[7px]">
        <span
          className={`inline-block h-[15px] w-[15px] flex-none rounded-sm border-[1.5px] text-center text-[10px] leading-[13px] font-semibold ${
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
        The paraphrase leads and the official title follows, quieter. The two are
        in different languages on purpose: the paraphrase is the operator's
        (Spanish, ours, CLAUDE.md §8) and the title is the standard's, verbatim
        and untranslated so it stays citable and contrastable against the source.
        Leading with the English made a Spanish screen read as half-translated.
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
        The scale is looked up defensively on purpose. A client talking to a
        server one version behind sees a `kind` this table does not have, and a
        tooltip is never worth taking the card tree down for — same reason
        `say()` falls back to the raw value instead of raising (core/wording.py).
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
          <div className="mt-1.5 rounded-[5px] border border-dashed border-line-dashed bg-surface-4 px-2.5 py-[7px]">
            {explanation.status === 'generated' ? (
              <div className="text-[10.5px] font-semibold text-ink-4">
                Solo para ayudarte a leer; no cambia el orden ni marca preferencias
              </div>
            ) : null}
            <div className="mt-1 text-xs leading-[1.5] text-ink-3">{explanation.text}</div>
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
 * A suggestion from the RAG pass: a neighbour in embedding space, not a mapping.
 *
 * It is offered — retrieval only ever widens — and it is labelled as what it is.
 * Adopting one is a human judgement on top of the catalog, and the signed
 * baseline records it as `adopted_suggestion` rather than absorbing it into the
 * authored mappings.
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
