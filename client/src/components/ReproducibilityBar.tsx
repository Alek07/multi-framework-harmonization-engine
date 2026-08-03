/**
 * What governed this run, on screen at all times.
 *
 * Every value here is read from a response — catalog and rule versions from the
 * candidates run, model and decoding parameters from the parse's provenance, the
 * catalog digest from the retrieval's. Nothing is a constant typed into the
 * client: a bar that said "temp 0 · seed 42" from a literal would keep saying it
 * after somebody changed the setting, which is the opposite of what it is for
 * (invariant 3).
 */

import { useComposition } from '../state/composition'

function Sep() {
  return <span className="mx-2.5 flex-none text-bar-sep">·</span>
}

export function ReproducibilityBar() {
  const { candidates, parseResult, baseline, source } = useComposition()

  const provenance = parseResult?.provenance
  const model = provenance?.model
  const isFallback = model?.includes(':3b') ?? false
  const retrieval = candidates?.retrieval.provenance
  const digest = retrieval?.catalog_digest
  const mode = source === 'parse' && parseResult ? 'ai' : 'deterministic'

  return (
    <div
      className="fixed inset-x-0 top-0 z-50 flex h-9 items-center overflow-x-auto whitespace-nowrap bg-bar px-4 font-mono text-[11.5px] leading-none font-medium text-bar-ink"
      data-screen-label="ReproducibilityBar"
    >
      <span className="label-caps mr-4 flex-none text-bar-muted">Reproducibilidad</span>

      {candidates ? (
        <span
          className="flex-none"
          title={`catálogo ${candidates.catalog_version} · reglas ${candidates.rules_version} · gating ${candidates.gating_version} · priorización ${candidates.prioritization_version}`}
        >
          catálogo v{candidates.catalog_version}
        </span>
      ) : (
        <span className="flex-none text-bar-muted">catálogo — sin ejecución todavía</span>
      )}

      <Sep />
      <span className="flex-none">{model ?? 'modelo sin invocar'}</span>
      {isFallback ? (
        <span className="ml-2 flex-none rounded-sm bg-warn px-1.5 py-0.5 text-[10px] text-white">
          fallback 3B
        </span>
      ) : null}

      {provenance ? (
        <>
          <Sep />
          <span className="flex-none" title={`digest del modelo ${provenance.model_digest}`}>
            temp {provenance.temperature} · seed {provenance.seed} · top_p {provenance.top_p}
          </span>
        </>
      ) : null}

      <Sep />
      <span className="flex-none">modo {mode}</span>

      {digest ? (
        <span
          className="ml-2.5 flex-none text-bar-muted"
          title={`vectores construidos sobre la colección ${retrieval?.collection}`}
        >
          sha256:{digest.slice(0, 4)}…{digest.slice(-4)}
        </span>
      ) : null}

      {baseline ? (
        <span className="ml-auto flex-none rounded-sm bg-ok px-2 py-0.5 text-[10px] text-white">
          baseline {baseline.baseline_id.slice(0, 8)} · solo lectura
        </span>
      ) : null}
    </div>
  )
}
