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
 * The screen is shaped by what the payload actually says, and it says something
 * narrower than "US vs EU": in this catalog every mapping the European reading
 * adds is `contextual` with a low weight, so `changes_coverage` is false in all
 * of them. The mechanism does not move — the same controls, the same coverage —
 * and what moves is the *exigencia*. Hence the two halves of the screen: one
 * reading **offers**, the other **demands**, and a comparison drawn as two
 * competing catalogs would misdescribe the data.
 *
 * The question is asked about *this* asset — the one described upstairs in free
 * text and reviewed by the operator — because the request carries the reviewed
 * profile inline. A delta that could only be asked about the profiles frozen in
 * the repository would be a demo of the frozen profiles.
 *
 * One bound is declared rather than hidden: one zone at a time, and the screen
 * says so in the operator's words instead of naming the issue that scoped it.
 */

import { useEffect, useMemo } from 'react'

import type {
  CapabilityDelta,
  CapabilityRegionView,
  FrameworkControl,
  RegionalDelta,
} from '../../../api/types'
import {
  FRAMEWORK,
  FRAMEWORK_NOTE,
  JURISDICTION_SHORT,
  MAPPING_TYPE,
  STRENGTH_KIND,
  coverageText,
  strengthText,
} from '../../../lib/labels'
import { DELTA_ORDERS, useComposition } from '../composition'
import { Caps, Fold, Hint, Notice, Section, Tag } from '../../../components/ui'

/**
 * The controls of the zone, by id, as `POST /candidates` described them.
 *
 * The delta names its controls by id and carries the full description only of
 * the ones a reading *adds*; the rest are the zone's own candidates, which the
 * operator has already seen in step 2. Reading them from there is what lets this
 * screen show «CIS 4.1» where the payload says `CTL-CIS-0401` — the rule the
 * whole client follows (`lib/labels.ts`): an operator never reads a raw id.
 * Anything the index cannot resolve is still shown, by id: a control the screen
 * could not name is not a control the screen may drop.
 */
function useControlIndex(zoneId: string | null): Map<string, FrameworkControl> {
  const { candidates } = useComposition()
  return useMemo(() => {
    const index = new Map<string, FrameworkControl>()
    const zone = candidates?.zones.find((z) => z.zone.zone_id === zoneId)
    for (const capability of zone?.capabilities ?? []) {
      for (const option of capability.resolution.options) index.set(option.control.id, option.control)
    }
    return index
  }, [candidates, zoneId])
}

/**
 * The reading's own name, in the operator's words.
 *
 * The server labels them `US` and `+EU` — jurisdiction codes, which nobody reads
 * on this client — and the `+` is the part that matters: the second reading is
 * the first one plus a region, never a catalog of its own.
 */
function reading(view: CapabilityRegionView, position: number): string {
  const name = JURISDICTION_SHORT[view.region]
  return position === 0 ? name : `+${name}`
}

/** A list of references that stays a sentence: the first few, then how many more. */
function refList(items: string[], visible = 3): string {
  if (items.length <= visible) return items.join(', ')
  return `${items.slice(0, visible).join(', ')} y ${items.length - visible} más`
}

/** One control, named the way the rest of the client names it. */
function Ref({ id, control }: { id: string; control?: FrameworkControl }) {
  if (!control) {
    return (
      <span title="Control del catálogo que esta pantalla no ha podido nombrar" className="font-mono text-[10.5px] text-ink-3">
        {id}
      </span>
    )
  }
  const framework = FRAMEWORK[control.framework]
  return (
    <span className="inline-flex items-baseline gap-1.25" title={`${control.title} · ${id}`}>
      <span className={`rounded-sm px-1.25 py-0.25 text-[9.5px] font-semibold ${framework.className}`}>
        {framework.label}
      </span>
      <span className="font-mono text-[10.5px] font-medium text-ink-2">{control.official_id}</span>
    </span>
  )
}

/**
 * Which of the two comparisons the payload supports, and it is not a style
 * switch: `US → +EU` adds NIS2 articles, every one of them a `contextual`
 * mapping with `changes_coverage` false, so the second reading demands and does
 * not build. Reverse the order and the same zone answers a different question —
 * `+US` adds CSF and CIS *mechanisms*, coverage moves in every capability, and
 * the European reading on its own leaves gaps. A screen that said «exige» in
 * both directions would be describing only one of them.
 */
function deltaMode(delta: RegionalDelta): 'exigencia' | 'mecanismo' {
  const added = delta.capabilities.flatMap((capability) => capability.added)
  const moves = delta.capabilities.some((capability) => capability.changes_coverage)
  return added.length > 0 && !moves && added.every((r) => r.strength.kind === 'legal')
    ? 'exigencia'
    : 'mecanismo'
}

/** What the whole screen counts, computed once over the payload. */
function summarize(delta: RegionalDelta, index: Map<string, FrameworkControl>) {
  const [first, second] = delta.regions
  const changed = delta.capabilities.filter((capability) => capability.changed)
  const same = delta.capabilities.filter((capability) => !capability.changed)

  const added = changed.flatMap((capability) => capability.added)
  const references = [...new Set(added.map((requirement) => requirement.official_id))]
  const frameworks = [...new Set(added.map((requirement) => requirement.framework))]
  const movesCoverage = delta.capabilities.filter((capability) => capability.changes_coverage)
  const mode = deltaMode(delta)

  // What the starting reading already demands by law. Not derivable from the
  // delta alone — it describes what each reading *adds* — so it is read off the
  // zone's own candidates. Reading `US` first the answer is not zero: IMO
  // MSC.428(98) obliges, and it is common ground rather than a US framework.
  const legalFirst = delta.capabilities.filter((capability) =>
    capability.regions[0]?.offered_control_ids.some((id) => index.get(id)?.strength.kind === 'legal'),
  )
  const legalControls = [
    ...new Map(
      legalFirst
        .flatMap((capability) => capability.regions[0].offered_control_ids)
        .map((id) => index.get(id))
        .filter((control) => control?.strength.kind === 'legal')
        .map((control) => [control!.id, control!] as const),
    ).values(),
  ]
  // Common ground obliges in *both* readings; a legal control of the region
  // under comparison is that region's own, and saying otherwise would credit
  // «EU» with an obligation the reading brought with it.
  const ownLegal = legalControls.filter((control) => delta.regions.includes(control.jurisdiction))
  const legalRefs = (controls: typeof legalControls) =>
    refList(controls.map((control) => `${FRAMEWORK[control.framework].label} ${control.official_id}`))

  return {
    first,
    second,
    changed,
    same,
    references,
    frameworks,
    mode,
    movesCoverage,
    legalFirst,
    legalControls,
    ownLegal,
    legalRefs,
    /** The index is empty on a session that reached step 3 without step 2's answer. */
    named: index.size > 0,
    total: delta.capabilities.length,
  }
}

type Summary = ReturnType<typeof summarize>

/** The two readings as a pair of tiles: one offers, the other demands. */
function Scoreboard({ summary }: { summary: Summary }) {
  const { first, second, total } = summary
  return (
    <div className="mb-5 grid grid-cols-2 overflow-hidden rounded-[7px] border border-line-2 max-mid:grid-cols-1">
      <div className="bg-surface-4 px-4.5 py-4">
        <Caps className="mb-2">{JURISDICTION_SHORT[first]} · lectura de partida</Caps>
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-[30px] leading-none font-semibold">
            {summary.named ? summary.legalFirst.length : '—'}
          </span>
          <span className="text-xs leading-[1.4] text-ink-3">
            de {total} exigidas por ley
            <br />
            el resto, marcos voluntarios o técnicos
          </span>
        </div>
        <Hint className="mt-2">
          {!summary.named
            ? 'El recuento de exigencia legal se lee de las opciones del paso 2; vuelve a calcularlas para verlo.'
            : summary.legalFirst.length === 0
              ? 'Ninguno de sus controles entra en esta zona con exigencia legal: ofrecen mecanismo, no obligación.'
              : summary.ownLegal.length === 0
                ? `Las ${summary.legalFirst.length} que ya lo son obligan por el terreno común (${summary.legalRefs(summary.legalControls)}), no por un marco propio de ${JURISDICTION_SHORT[first]}`
                : `Ya obligan por ley: ${summary.legalRefs(summary.legalControls)}`}
        </Hint>
      </div>
      <div
        className={`border-l px-4.5 py-4 max-mid:border-t max-mid:border-l-0 ${
          summary.mode === 'exigencia'
            ? 'border-warn-line bg-warn-tint-2'
            : 'border-accent-line bg-accent-tint-3'
        }`}
      >
        <Caps className={`mb-2 ${summary.mode === 'exigencia' ? 'text-warn' : 'text-accent'}`}>
          +{JURISDICTION_SHORT[second]} · capa acumulativa
        </Caps>
        <div className="flex items-baseline gap-2">
          <span
            className={`font-mono text-[30px] leading-none font-semibold ${
              summary.mode === 'exigencia' ? 'text-warn' : 'text-accent'
            }`}
          >
            {summary.changed.length}
          </span>
          <span className="text-xs leading-[1.4] text-ink-3">
            de {total} {summary.mode === 'exigencia' ? 'exigidas por ley' : 'con mecanismo añadido'}
            <br />
            vía {summary.references.length} referencia(s) de{' '}
            {summary.frameworks.map((framework) => FRAMEWORK[framework].label).join(' · ')}
          </span>
        </div>
        <Hint className="mt-2">
          {summary.mode === 'exigencia'
            ? 'Mismo mecanismo, misma cobertura: lo que añade es obligación, no capacidad.'
            : `La cobertura se mueve en ${summary.movesCoverage.length}: esta lectura no solo obliga, también aporta controles que la anterior no ofrecía.`}
        </Hint>
      </div>
    </div>
  )
}

/** One capability whose reading changes with the region. */
function ChangeCard({
  capability,
  summary,
  index,
  regional,
}: {
  capability: CapabilityDelta
  summary: Summary
  index: Map<string, FrameworkControl>
  regional: boolean
}) {
  const [first, second] = capability.regions
  const resolved = first.offered_control_ids.filter((id) => index.has(id))
  const legal = resolved.filter((id) => index.get(id)!.strength.kind === 'legal')
  // Read per capability, not per screen: one that adds obligation reads
  // differently from one that adds a mechanism, and both can occur in one delta.
  const demands =
    !capability.changes_coverage &&
    capability.added.length > 0 &&
    capability.added.every((requirement) => requirement.strength.kind === 'legal')
  // Declared by the core out of the common ground, so it comes out the same in
  // every reading: named here, and named as *not* regional (invariant 2).
  const residual =
    !regional && first.gap && second.gap && first.gap.coverage === second.gap.coverage
      ? first.gap
      : null

  return (
    <div
      className={`mb-3 overflow-hidden rounded-[7px] border bg-surface ${
        regional ? 'border-alert-line' : 'border-line-2'
      }`}
    >
      <div className="flex flex-wrap items-baseline gap-2 border-b border-line-3 bg-surface-2 px-3.75 py-2.75">
        <span className="font-mono text-[11.5px] font-semibold">{capability.capability_id}</span>
        <span className="text-[12.5px] text-ink-3">{capability.capability_name}</span>
        {residual ? (
          <Tag
            className="ml-auto bg-[#f2f1ed] text-ink-2"
            title="Cobertura que el catálogo no afirma cerrar. Viene del terreno común: sale igual en las dos lecturas, así que no es una diferencia regional."
          >
            residuo declarado {residual.residual.toFixed(2)} — igual en ambas
          </Tag>
        ) : null}
      </div>

      <div className="grid grid-cols-[1fr_128px_1fr] max-mid:grid-cols-1">
        <Side view={first} index={index}>
          <div className="mt-2 flex flex-wrap gap-2">
            {resolved.length > legal.length ? (
              <Tag
                prose
                className="border border-line bg-[#f2f1ed] text-ink-2"
                title="Estos marcos describen el mecanismo: qué hay que conseguir y con qué. No obligan por sí mismos."
              >
                práctica / técnica
              </Tag>
            ) : null}
            {legal.length > 0 ? (
              <Tag
                prose
                className="border border-warn-line bg-warn-tint text-warn"
                title={STRENGTH_KIND.legal.note}
              >
                ya obliga: {legal.map((id) => index.get(id)?.official_id ?? id).join(', ')}
              </Tag>
            ) : null}
          </div>
          {first.set_aside_control_ids.length > 0 ? (
            <Hint className="mt-2">
              Apartado por esta lente:{' '}
              {refList(first.set_aside_control_ids.map((id) => index.get(id)?.official_id ?? id))} —
              pertenece a {JURISDICTION_SHORT[summary.second]} y entra en la lectura siguiente.
              Apartar no es descartar.
            </Hint>
          ) : null}
        </Side>

        <div className="flex flex-col items-center justify-center gap-1.5 border-x border-line-3 bg-surface-3 px-1.5 py-2.5 max-mid:flex-row max-mid:border-x-0 max-mid:border-y">
          <span
            className={`inline-flex h-7.5 w-7.5 items-center justify-center rounded-full border font-mono text-[15px] font-semibold ${
              demands
                ? 'border-warn-line bg-warn-tint text-warn'
                : 'border-accent-line bg-accent-tint text-accent'
            }`}
          >
            {demands ? '⚖' : '+'}
          </span>
          <span
            className={`text-center font-mono text-[8.5px] leading-[1.35] font-semibold tracking-[0.06em] ${
              demands ? 'text-warn' : 'text-accent'
            }`}
          >
            {demands ? (
              <>
                {JURISDICTION_SHORT[summary.second].toUpperCase()} EXIGE
                <br />
                {JURISDICTION_SHORT[summary.first].toUpperCase()} NO
              </>
            ) : (
              <>
                {JURISDICTION_SHORT[summary.second].toUpperCase()}
                <br />
                APORTA
              </>
            )}
          </span>
        </div>

        <div className={`px-3.75 py-3.25 ${demands ? 'bg-warn-tint-2' : 'bg-accent-tint-3'}`}>
          <Caps className={`mb-1.75 ${demands ? 'text-warn' : 'text-accent'}`}>
            {reading(second, 1)} {demands ? 'exige por ley' : 'aporta'}
          </Caps>
          <div className="flex flex-col gap-1.5">
            {capability.added.map((requirement) => (
              <div key={requirement.control_id}>
                <div className="flex flex-wrap items-baseline gap-2">
                  <span
                    title={FRAMEWORK_NOTE[requirement.framework]}
                    className={`cursor-help font-mono text-[11.5px] font-semibold ${
                      demands ? 'text-warn' : 'text-accent'
                    }`}
                  >
                    {FRAMEWORK[requirement.framework].label} {requirement.official_id}
                  </span>
                  <span
                    title={MAPPING_TYPE[requirement.mapping_type].note}
                    className="text-[11px] text-ink-4"
                  >
                    {MAPPING_TYPE[requirement.mapping_type].label} · peso{' '}
                    {requirement.coverage_weight.toFixed(1)}
                  </span>
                </div>
                {requirement.strength.note || !demands ? (
                  <Hint className="mt-0.5">{strengthText(requirement.strength)}</Hint>
                ) : null}
              </div>
            ))}
          </div>
          <Hint className="mt-2">
            {capability.changes_coverage
              ? `Aquí sí cambia el mecanismo: la cobertura pasa de ${coverageText(first.coverage)} a ${coverageText(second.coverage)}.`
              : `Mismo mecanismo que ${JURISDICTION_SHORT[summary.first]} — cobertura ${coverageText(second.coverage)}, sin cambio. Solo sube la exigencia.`}
          </Hint>
        </div>
      </div>

      {regional ? (
        <div className="border-t border-alert-line bg-alert-tint-2 px-3.75 py-2.5">
          <Notice tone="alert" label="HUECO REGIONAL">
            {capability.regions
              .map((view, position) =>
                view.gap
                  ? `En «${reading(view, position)}» queda sin cubrir: ${view.gap.rationale}`
                  : `«${reading(view, position)}» sí lo cubre.`,
              )
              .join(' ')}
          </Notice>
        </div>
      ) : null}
    </div>
  )
}

/** What one reading offers for a capability: frameworks, how many, how much. */
function Side({
  view,
  index,
  children,
}: {
  view: CapabilityRegionView
  index: Map<string, FrameworkControl>
  children: React.ReactNode
}) {
  return (
    <div className="px-3.75 py-3.25">
      <Caps className="mb-1.75">{reading(view, 0)} ofrece</Caps>
      {view.offered_control_ids.length === 0 ? (
        // Not an empty cell: a reading with no candidate at all is the finding.
        <p className="m-0 text-[12.5px] leading-normal text-alert">
          Ningún control bajo esta lectura.
        </p>
      ) : (
        <>
          <div className="font-mono text-[11.5px] leading-normal font-medium text-ink-2">
            {view.frameworks.map((framework) => FRAMEWORK[framework].label).join(' · ')}
          </div>
          <Fold
            className="mt-2"
            summary={`${view.offered_control_ids.length} controles · cubre ${coverageText(view.coverage)}`}
          >
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 border-t border-dashed border-line pt-2">
              {view.offered_control_ids.map((id) => (
                <Ref key={id} id={id} control={index.get(id)} />
              ))}
            </div>
          </Fold>
        </>
      )}
      {children}
    </div>
  )
}

/** The capabilities the region does not touch — folded, never dropped. */
function Unchanged({ summary }: { summary: Summary }) {
  return (
    <div className="rounded-[7px] border border-line-2 bg-surface-4 px-4 py-3.5">
      <div className="flex flex-wrap items-center gap-2.5">
        <span className="inline-flex h-6.5 w-6.5 items-center justify-center rounded-sm border border-line bg-[#f2f1ed] font-mono text-[13px] font-semibold text-ink-2">
          =
        </span>
        <Caps>
          {summary.mode === 'exigencia'
            ? 'Ninguna de las dos añade obligación'
            : 'Igual en las dos lecturas'}
        </Caps>
        <span className="font-mono text-xs font-semibold text-ink-4">{summary.same.length}</span>
      </div>
      <Hint className="mt-1.75">
        Mismo mecanismo y misma exigencia bajo {JURISDICTION_SHORT[summary.first]} y bajo{' '}
        {JURISDICTION_SHORT[summary.second]}. Aquí la comparación no tiene tensión: es el mismo
        suelo, y componer para una región es componer para las dos.
      </Hint>
      {summary.same.length > 0 ? (
        <Fold className="mt-2.5" summary={`ver las ${summary.same.length} capacidades`}>
          <div className="mt-2 border-t border-line-2">
            {summary.same.map((capability) => (
              <div
                key={capability.capability_id}
                className="grid grid-cols-[200px_1fr_130px] items-baseline gap-3 border-b border-line-3 py-1.75 text-xs max-narrow:grid-cols-1 max-narrow:gap-0.5"
              >
                <span className="font-mono text-[11px] font-semibold">
                  {capability.capability_id}
                </span>
                <span className="text-ink-3">{capability.capability_name}</span>
                <span
                  className={`font-mono text-[10.5px] font-medium ${
                    capability.regions[0].gap ? 'text-warn' : 'text-ink-4'
                  }`}
                >
                  cubre {coverageText(capability.regions[0].coverage)}
                  {capability.regions[0].gap
                    ? ` · res. ${capability.regions[0].gap.residual.toFixed(2)}`
                    : ''}
                </span>
              </div>
            ))}
          </div>
        </Fold>
      ) : null}
    </div>
  )
}

function Comparison({ delta }: { delta: RegionalDelta }) {
  const index = useControlIndex(delta.zone.zone_id)
  const summary = useMemo(() => summarize(delta, index), [delta, index])

  return (
    <>
      <Scoreboard summary={summary} />

      {delta.regional_gap_capability_ids.length > 0 ? (
        <div className="mb-3">
          <Notice tone="alert" label="HUECO REGIONAL">
            En {delta.regional_gap_capability_ids.length} capacidades el hueco depende de la región:
            una lectura ofrece mecanismo y la otra no. Es la razón por la que las lecturas son
            acumulativas — «+{JURISDICTION_SHORT[summary.second]}» es la anterior más esa región,
            nunca un catálogo paralelo.
          </Notice>
        </div>
      ) : null}

      <div className="mb-3 flex items-center gap-2">
        <Caps className={summary.mode === 'exigencia' ? 'text-warn' : 'text-accent'}>
          {summary.mode === 'exigencia'
            ? `Donde ${JURISDICTION_SHORT[summary.second]} exige y ${JURISDICTION_SHORT[summary.first]} no`
            : `Lo que añade +${JURISDICTION_SHORT[summary.second]}`}
        </Caps>
        <span className="h-px flex-1 bg-line-2" />
        <span className="font-mono text-[10px] font-medium text-ink-4">
          {summary.changed.length} capacidades
        </span>
      </div>

      {summary.changed.length === 0 ? (
        <Notice tone="muted">
          En esta zona no cambia nada entre una lectura y otra. Es una conclusión válida y útil:
          significa que lo compuesto aquí sirve para las dos.
        </Notice>
      ) : null}

      {summary.changed.map((capability) => (
        <ChangeCard
          key={capability.capability_id}
          capability={capability}
          summary={summary}
          index={index}
          regional={delta.regional_gap_capability_ids.includes(capability.capability_id)}
        />
      ))}

      <Unchanged summary={summary} />

      <p className="m-0 mt-3.5 text-[11.5px] leading-[1.6] text-ink-4">{delta.rationale}</p>
      <div className="mt-1.5 text-[11.5px] leading-normal text-ink-4">
        <b>Criterio de cada lectura:</b>{' '}
        {delta.lenses.map((lens, position) => (
          <span key={position} className="mr-2">
            [{JURISDICTION_SHORT[delta.regions[position]]}] {lens.rationale}
          </span>
        ))}
      </div>
    </>
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

  const [first, second] = regions

  return (
    <Section
      id="s4"
      step={3}
      title={
        delta && deltaMode(delta) === 'exigencia' ? (
          <>
            Delta regional — {JURISDICTION_SHORT[first]}{' '}
            <span className="text-ink-4">ofrece</span> · {JURISDICTION_SHORT[second]}{' '}
            <span className="text-warn">exige</span>
          </>
        ) : (
          `Delta regional — qué añade ${JURISDICTION_SHORT[second]} sobre ${JURISDICTION_SHORT[first]}`
        )
      }
      hint={`Esta pantalla responde a una sola pregunta: si además de responder ante ${JURISDICTION_SHORT[first]} tuvieras que responder ante ${JURISDICTION_SHORT[second]}, ¿qué tendrías que añadir en esta zona? La segunda lectura incluye la primera; no son dos listas independientes.`}
      scope={zoneId ?? undefined}
    >
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        {DELTA_ORDERS.map((option, position) => (
          <button
            key={option.label}
            type="button"
            title={`Leer primero ${JURISDICTION_SHORT[option.regions[0]]} y añadir después ${JURISDICTION_SHORT[option.regions[1]]}`}
            onClick={() => setDeltaOrder(position)}
            className={`cursor-pointer rounded-[5px] border px-3 py-1.5 text-[11.5px] font-semibold ${
              deltaOrder === position
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
      <Hint className="mb-4">
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

      {delta ? <Comparison delta={delta} /> : null}
    </Section>
  )
}
