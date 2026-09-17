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
  const cut = retrieval?.cut_policy

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

      {cut ? (
        <span
          className="ml-2.5 flex-none text-bar-muted"
          title={[
            `Regla del corte de la búsqueda ${cut.version}`,
            `se evalúan ${cut.depth} candidatos por requisito`,
            `se muestran ${cut.floor} y hasta ${cut.ceiling} mientras empaten a ${cut.tie_epsilon}`,
            `como máximo ${cut.framework_cap} por marco`,
            'lo que queda fuera se cuenta en cada requisito',
          ].join(' · ')}
        >
          corte {cut.version}
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
