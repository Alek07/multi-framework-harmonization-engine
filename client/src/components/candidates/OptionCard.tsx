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
} from '../../api/types'
import { FRAMEWORK, MAPPING_TYPE } from '../../lib/labels'

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
}: Common & {
  dotted: boolean
  faded?: boolean
  origin: 'catalog' | 'retrieval'
  meta: React.ReactNode
  banner?: React.ReactNode
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
          className={`rounded-sm px-1.5 py-0.5 text-[10px] font-semibold ${framework.className}`}
        >
          {framework.label}
        </span>
        <span className="font-mono text-xs font-semibold">{control.official_id}</span>
        <span className="rounded-sm bg-[#eef0f2] px-1.5 py-0.5 font-mono text-[10px] font-medium text-ink-2">
          {control.jurisdiction}
        </span>
      </div>

      <div className="text-[12.5px] leading-[1.35] font-semibold">{control.title}</div>
      <div className="text-[11.5px] leading-[1.45] text-ink-3">
        {control.paraphrased_description}
      </div>
      <div className="flex flex-wrap items-center gap-2.5 text-[11.5px] text-ink-2">{meta}</div>
      <div className="font-mono text-[10px] text-ink-4">
        strength: {control.strength} · {control.id}
      </div>

      {banner}

      {explanation ? (
        <div className="rounded-[5px] border border-dashed border-line-dashed bg-surface-4 px-2.5 py-[7px]">
          <div className="text-[10.5px] font-semibold text-ink-4">
            {explanation.status === 'generated'
              ? 'Explicación de IA — presentacional; no altera el orden ni la selección'
              : 'Justificación determinista del motor'}
          </div>
          <div className="mt-1 text-xs leading-[1.5] text-ink-3">{explanation.text}</div>
          {explanation.notice ? (
            <div className="mt-1 font-mono text-[10px] text-warn">{explanation.notice}</div>
          ) : null}
          {explanation.basis.length > 0 ? (
            <div className="mt-1 font-mono text-[10px] text-ink-4">
              evidencia: {explanation.basis.join(', ')}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function MappingMeta({ mapping }: { mapping: Mapping }) {
  const type = MAPPING_TYPE[mapping.type]
  const authored = mapping.provenance.source === 'author_judgment'
  return (
    <>
      <span>
        <span className="text-accent">{type.glyph}</span> {type.label}
      </span>
      <span className="font-mono text-[11px] font-semibold">
        peso {mapping.coverage_weight.toFixed(1)}
      </span>
      <span
        title={mapping.provenance.note}
        className={`rounded-sm border px-1.5 py-px text-[10px] font-semibold ${
          authored ? 'border-dashed text-warn' : 'border-solid text-[#1d6f4c]'
        }`}
      >
        {mapping.provenance.source}
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
            <span className="font-mono text-[10px] font-semibold text-alert-ink">
              {option.status}
            </span>
          ) : null}
        </>
      }
      banner={
        option.status_reason ? (
          <div className="rounded-[5px] bg-surface-2 px-2.5 py-1.5 text-[11px] leading-[1.45] text-ink-3">
            {option.status_reason}
            {option.rule_id ? (
              <span className="ml-1 font-mono text-[10px] text-ink-4">· {option.rule_id}</span>
            ) : null}
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
          <span className="rounded-sm border border-dashed border-warn px-1.5 py-px text-[10px] font-semibold text-warn">
            sugerencia RAG
          </span>
          <span className="font-mono text-[11px]">score {hit.score.toFixed(3)}</span>
          {hit.mapped_capability_ids.length > 0 ? (
            <span className="text-[11px] text-ink-3">
              mapeado en: {hit.mapped_capability_ids.join(', ')}
            </span>
          ) : null}
        </>
      }
      banner={
        <div className="rounded-[5px] bg-surface-2 px-2.5 py-1.5 text-[11px] leading-[1.45] text-ink-3">
          {hit.rationale}
        </div>
      }
    />
  )
}
