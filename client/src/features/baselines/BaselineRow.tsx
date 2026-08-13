/**
 * One signed baseline in the list, what its trail says, and the documents it emits.
 *
 * The summary comes with the list; the per-capability detail is the baseline's
 * own trail, fetched when the operator asks for it. The three documents — the
 * declaration of applicability, the partial OSCAL plan and the printed version of
 * both — are the server's own responses, downloaded verbatim (UCM-46). Each is
 * fetched once and reused.
 */

import { useState } from 'react'

import {
  ApiError,
  OfflineError,
  fetchAuditLog,
  fetchOscalStatement,
  fetchStatement,
} from '../../api/client'
import type { BaselineAuditLog, BaselineStatement, BaselineSummary } from '../../api/types'
import { downloadJson, fileName } from './download'
import { DownloadDialog } from './DownloadDialog'
import { printBaseline } from './printable'
import { decisionsOf, type DecisionRow } from './trail'
import { Caps, GhostButton, Tag } from '../../components/ui'

function messageOf(error: unknown): string {
  if (error instanceof ApiError || error instanceof OfflineError) return error.message
  return 'No se ha podido leer el registro de decisiones.'
}

function Chips({ baseline }: { baseline: BaselineSummary }) {
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`
  return (
    <div className="flex flex-wrap gap-1.25">
      <Tag
        prose
        className={baseline.tier_0_complete ? 'bg-ok-tint text-ok-ink' : 'bg-warn-tint text-warn'}
        title="Todo lo obligatorio para el SL-objetivo de cada zona quedó decidido antes de firmar."
      >
        {baseline.tier_0_complete ? 'obligatorio completo' : 'obligatorio incompleto'}
      </Tag>
      <Tag prose title="Requisitos sin mecanismo aplicable, asumidos por escrito.">
        {plural(baseline.gaps_accepted, 'hueco aceptado', 'huecos aceptados')}
      </Tag>
      <Tag prose title="Contradicciones que el motor no resolvió y decidió el humano.">
        {plural(baseline.conflicts_resolved, 'conflicto resuelto', 'conflictos resueltos')}
      </Tag>
      <Tag prose title="Decisiones con nombre y razón escrita en el registro.">
        {plural(baseline.human_choices, 'decisión', 'decisiones')}
      </Tag>
    </div>
  )
}

function Table({
  title,
  head,
  rows,
  empty,
}: {
  title: string
  head: string[]
  rows: DecisionRow[]
  empty: string
}) {
  return (
    <div>
      <Caps className="mb-1.5">{title}</Caps>
      {rows.length === 0 ? (
        <p className="m-0 text-[11.5px] text-ink-4">{empty}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-140 border-collapse text-left">
            <thead>
              <tr>
                {head.map((cell) => (
                  <th
                    key={cell}
                    className="border-b border-line-2 pr-3 pb-1 font-mono text-[10px] font-semibold text-ink-4"
                  >
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index}>
                  <td className="border-t border-line-3 py-1.5 pr-3 font-mono text-[11px] font-semibold">
                    {row.zoneId}
                  </td>
                  <td className="border-t border-line-3 py-1.5 pr-3 font-mono text-[11px]">
                    {row.capabilityId}
                  </td>
                  <td className="border-t border-line-3 py-1.5 pr-3 font-mono text-[11px]">
                    {row.controlId}
                  </td>
                  <td className="border-t border-line-3 py-1.5 text-[11.5px] leading-normal text-ink-3">
                    {row.rationale}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Detail({ baseline, log }: { baseline: BaselineSummary; log: BaselineAuditLog }) {
  const decisions = decisionsOf(log)
  const mandates = Object.entries(baseline.closed_mandates)

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-x-6 gap-y-1 text-[11.5px] grid-cols-[repeat(auto-fit,minmax(230px,1fr))]">
        <div>
          <Caps>Referencia</Caps>
          <span className="font-mono text-[11px]">{baseline.baseline_id}</span>
        </div>
        <div>
          <Caps>Activo</Caps>
          <span className="font-mono text-[11px]">{baseline.profile_id}</span>
        </div>
        <div>
          <Caps>Versiones que la gobernaron</Caps>
          <span className="font-mono text-[11px]">
            {Object.entries(baseline.versions)
              .map(([name, value]) => `${name} ${value}`)
              .join(' · ') || '—'}
          </span>
        </div>
        <div>
          <Caps>Integridad del registro</Caps>
          <span className={log.chain.valid ? 'text-ok-ink' : 'text-alert-ink'}>
            {log.chain.valid ? '✓ comprobada' : '✕ no se puede verificar'} · {log.events.length}{' '}
            entradas
          </span>
        </div>
      </div>

      <div>
        <Caps className="mb-1">Por qué se firmó</Caps>
        <p className="m-0 text-xs leading-[1.55] text-ink-3">{baseline.signature_rationale}</p>
      </div>

      {mandates.length > 0 ? (
        <div>
          <Caps className="mb-1">Mandatos que el motor no pudo cerrar y cerró el humano</Caps>
          <div className="flex flex-col gap-0.5 text-[11.5px]">
            {mandates.map(([zone, ids]) => (
              <div key={zone}>
                <span className="font-mono font-semibold">{zone}</span>{' '}
                <span className="font-mono text-ink-3">{ids.join(', ')}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <Table
        title="Elecciones por capacidad"
        head={['zona', 'capacidad', 'control', 'razón escrita']}
        rows={decisions.selected}
        empty="No se seleccionó ningún mecanismo: el bloque obligatorio quedó ratificado al firmar o aceptado como hueco."
      />
      <Table
        title="Huecos que viajan a la línea base"
        head={['zona', 'capacidad', 'control', 'razón escrita']}
        rows={decisions.gaps}
        empty="Ninguno: no se aceptó ningún hueco."
      />
      <Table
        title="Conflictos resueltos por el humano"
        head={['zona', 'capacidad', 'control descartado', 'razón escrita']}
        rows={decisions.rejected}
        empty="Ninguno: no hubo contradicciones que resolver."
      />

      {decisions.ratified > 0 ? (
        <p className="m-0 text-[11.5px] text-ink-4">
          Además, {decisions.ratified} mandato(s) que el motor ya daba por cubiertos y la firma
          ratifica. Ratificar no es elegir, y el registro lo anota con un tipo propio para no
          afirmar una elección que nadie hizo.
        </p>
      ) : null}
    </div>
  )
}

export function BaselineRow({ baseline }: { baseline: BaselineSummary }) {
  const [open, setOpen] = useState(false)
  const [log, setLog] = useState<BaselineAuditLog | null>(null)
  const [statement, setStatement] = useState<BaselineStatement | null>(null)
  const [downloads, setDownloads] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /** One place where a fetch either yields its document or leaves the row saying why. */
  async function load<T>(fetch: () => Promise<T>, cached: T | null): Promise<T | null> {
    if (cached) return cached
    setLoading(true)
    setError(null)
    try {
      return await fetch()
    } catch (caught) {
      setError(messageOf(caught))
      return null
    } finally {
      setLoading(false)
    }
  }

  /** The trail is fetched once and then reused by both the detail and the print. */
  async function trail(): Promise<BaselineAuditLog | null> {
    const fetched = await load(() => fetchAuditLog(baseline.baseline_id), log)
    if (fetched) setLog(fetched)
    return fetched
  }

  /** The declaration of applicability, which is what the printed document is. */
  async function declaration(): Promise<BaselineStatement | null> {
    const fetched = await load(() => fetchStatement(baseline.baseline_id), statement)
    if (fetched) setStatement(fetched)
    return fetched
  }

  async function toggle() {
    if (open) return setOpen(false)
    setOpen(true)
    await trail()
  }

  /**
   * The three exits of the download dialog.
   *
   * Each closes it only when the document actually reached the operator: a
   * dialog that shuts on a failed fetch would look like a download that
   * happened. The reason stays on screen instead, inside the dialog.
   */
  async function print() {
    const document = await declaration()
    const recorded = await trail()
    if (!document || !recorded) return
    if (!printBaseline(document, recorded)) {
      setError(
        'El navegador ha bloqueado la ventana del documento. Permite las ventanas emergentes de esta página y vuelve a intentarlo.',
      )
      return
    }
    setDownloads(false)
  }

  async function downloadSoa() {
    const document = await declaration()
    if (!document) return
    downloadJson(fileName('soa', baseline.baseline_id), document)
    setDownloads(false)
  }

  async function downloadOscal() {
    const document = await load(() => fetchOscalStatement(baseline.baseline_id), null)
    if (!document) return
    downloadJson(fileName('oscal-ssp', baseline.baseline_id), document)
    setDownloads(false)
  }

  function openDownloads() {
    // A refusal from a previous attempt is not about this one.
    setError(null)
    setDownloads(true)
  }

  return (
    <div
      className={`overflow-hidden rounded-lg border border-line border-l-4 border-l-ok bg-surface ${
        open ? 'ring-1 ring-accent' : ''
      }`}
    >
      <div className="grid items-center gap-4 px-4.5 py-4 grid-cols-[1.9fr_1.1fr_.9fr_1.2fr_auto] max-mid:grid-cols-1 max-mid:items-start max-mid:gap-2">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="font-mono text-[11.5px] leading-normal font-semibold"
              title={baseline.baseline_id}
            >
              {baseline.baseline_id.slice(0, 8)}
            </span>
            <Tag prose className="bg-ok-tint text-ok-ink">
              firmada
            </Tag>
          </div>
          <span className="text-[13px] leading-[1.35] font-semibold">{baseline.profile_name}</span>
          <span className="font-mono text-[10.5px] text-ink-4">
            {baseline.zone_ids.length} zona(s)
            {baseline.versions.catalog ? ` · catálogo v${baseline.versions.catalog}` : ''}
          </span>
        </div>

        <div className="min-w-0 text-[12.5px]">
          <div className="font-semibold">{baseline.signed_by || '—'}</div>
          <div className="text-[11.5px] text-ink-4">{baseline.audit_events} anotaciones</div>
        </div>

        <div className="font-mono text-xs text-ink-3">
          {new Date(baseline.signed_at).toLocaleDateString('es-ES', {
            day: '2-digit',
            month: 'short',
            year: 'numeric',
          })}
        </div>

        <Chips baseline={baseline} />

        <div className="flex flex-wrap justify-end gap-2 max-mid:justify-start">
          <GhostButton onClick={() => void toggle()}>{open ? 'Ocultar' : 'Detalle'}</GhostButton>
          <button
            type="button"
            onClick={openDownloads}
            title="La declaración de aplicabilidad de esta línea base, para leer, para archivar o en formato OSCAL"
            className="cursor-pointer rounded-md border-none bg-accent px-3.5 py-2 text-xs font-semibold whitespace-nowrap text-white hover:bg-accent-ink"
          >
            Descargar
          </button>
        </div>
      </div>

      {/* While the dialog is open it shows the refusal itself; two copies of one
          sentence would read as two problems. */}
      {error && !downloads ? (
        <div className="border-t border-line-3 bg-alert-tint px-4.5 py-2.5 text-xs text-alert-ink">
          {error}
        </div>
      ) : null}

      <DownloadDialog
        open={downloads}
        onClose={() => setDownloads(false)}
        loading={loading}
        error={error}
        onPrint={() => void print()}
        onSoa={() => void downloadSoa()}
        onOscal={() => void downloadOscal()}
      />

      {open ? (
        <div className="border-t border-line-3 bg-surface-2 px-4.5 py-4">
          {loading ? (
            <p className="m-0 text-xs text-ink-4">Leyendo el registro de decisiones…</p>
          ) : log ? (
            <Detail baseline={baseline} log={log} />
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
