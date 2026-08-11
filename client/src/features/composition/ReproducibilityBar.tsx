/**
 * What governed this run, on screen at all times.
 *
 * Every value here is read from a response — catalog and rule versions from the
 * candidates run, model and decoding parameters from the parse's provenance, the
 * catalog digest from the retrieval's. Nothing is a constant typed into the
 * client: a bar that said "temp 0 · seed 42" from a literal would keep saying it
 * after somebody changed the setting, which is the opposite of what it is for.
 *
 * What changed for the operator is only the wording. The bar used to read like a
 * debug console (`temp 0 · top_p 1 · sha256:…`); those values are still on
 * screen, but as tooltips behind sentences that say what they *mean* — that two
 * runs on the same asset give the same result, and which edition of the
 * regulatory catalog was used.
 */

import { Link } from '@tanstack/react-router'

import { useComposition } from './composition'

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

  return (
    <div
      className="fixed inset-x-0 top-0 z-50 flex h-9 items-center overflow-x-auto whitespace-nowrap bg-bar px-4 text-[11.5px] leading-none font-medium text-bar-ink"
      data-screen-label="ReproducibilityBar"
    >
      <Link
        to="/"
        title="Volver a la lista. Lo que llevas compuesto se guarda en este navegador."
        className="mr-3.5 flex-none rounded border border-[#3c4b62] px-2.5 py-1 text-[10.5px] font-semibold text-bar-ink no-underline hover:border-bar-muted hover:text-bar-ink hover:no-underline"
      >
        ← Líneas base
      </Link>
      <span className="label-caps mr-4 flex-none text-bar-muted">Trazabilidad de esta sesión</span>

      {candidates ? (
        <span
          className="flex-none"
          title={[
            `Catálogo de normativa v${candidates.catalog_version}`,
            `Reglas de resolución v${candidates.rules_version}`,
            `Reglas de exclusión v${candidates.gating_version}`,
            `Reglas de priorización v${candidates.prioritization_version}`,
          ].join(' · ')}
        >
          Catálogo de normativa v{candidates.catalog_version}
        </span>
      ) : (
        <span className="flex-none text-bar-muted">
          Catálogo de normativa — aún no se ha calculado nada
        </span>
      )}

      <Sep />
      <span
        className="flex-none"
        title={
          model
            ? `Modelo de lenguaje local, ejecutado en este equipo: ${model}`
            : 'El asistente todavía no ha intervenido en esta sesión'
        }
      >
        {model ? 'Asistente local (sin conexión a internet)' : 'Asistente sin usar todavía'}
      </span>
      {isFallback ? (
        <span
          className="ml-2 flex-none rounded-sm bg-warn px-1.5 py-0.5 text-[10px] text-white"
          title="Se está usando el modelo reducido, previsto para equipos con poca memoria. El resultado del cálculo no cambia; solo la calidad de la lectura del texto."
        >
          modelo reducido
        </span>
      ) : null}

      {provenance ? (
        <>
          <Sep />
          <span
            className="flex-none"
            title={`Parámetros fijados: temperature ${provenance.temperature}, seed ${provenance.seed}, top_p ${provenance.top_p}. Huella del modelo ${provenance.model_digest}.`}
          >
            Resultado repetible: mismo texto ⇒ misma ficha
          </span>
        </>
      ) : null}

      <Sep />
      <span
        className="flex-none"
        title={
          source === 'manual'
            ? 'Has rellenado la ficha del activo a mano: el asistente no ha intervenido.'
            : 'El asistente ha leído tu descripción y tú has revisado la ficha resultante.'
        }
      >
        {source === 'manual' ? 'Ficha rellenada a mano' : 'Ficha revisada por ti'}
      </span>

      {digest ? (
        <span
          className="ml-2.5 flex-none text-bar-muted"
          title={`Huella del catálogo usado en la búsqueda (${retrieval?.collection}): ${digest}`}
        >
          huella {digest.slice(0, 4)}…{digest.slice(-4)}
        </span>
      ) : null}

      {baseline ? (
        <span
          className="ml-auto flex-none rounded-sm bg-ok px-2 py-0.5 text-[10px] text-white"
          title={`Línea base ${baseline.baseline_id}`}
        >
          Firmada · solo lectura
        </span>
      ) : null}
    </div>
  )
}
