/**
 * The baselines: what has been signed, and what is still being composed. Signed
 * ones are the server's (`GET /baselines`, from the ledger); the draft is this
 * browser's, since nothing reaches the server until it is signed.
 */

import { useNavigate } from '@tanstack/react-router'
import { useEffect, useState } from 'react'

import { missingRequired } from '../../lib/draft'
import { useBaselines } from './store'
import { isResumable, useSession } from '../composition/session'
import { Caps, GhostButton, Modal, Notice, PrimaryButton, Tag } from '../../components/ui'
import { BaselineRow } from './BaselineRow'

type Filter = 'todas' | 'firmadas' | 'borradores'

const FILTERS: Filter[] = ['todas', 'firmadas', 'borradores']

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 border-r border-line-3 pr-6 last:border-r-0">
      <Caps className="whitespace-nowrap">{label}</Caps>
      <span className="text-xl leading-none font-semibold">{value}</span>
    </div>
  )
}

/** The composition open in this browser, offered back rather than left buried. */
function DraftRow({ onContinue }: { onContinue: () => void }) {
  const session = useSession()
  const missing = session.draft ? missingRequired(session.draft) : []
  const decided = Object.values(session.reasons).filter((reason) => reason.trim()).length
  const name = session.draft?.name ?? session.description.split(/[:.\n]/)[0]?.trim()

  return (
    <div className="overflow-hidden rounded-lg border border-line border-l-4 border-l-warn-line bg-surface">
      <div className="grid items-center gap-4 px-4.5 py-4 grid-cols-[1.9fr_1.1fr_.9fr_1.2fr_auto] max-mid:grid-cols-1 max-mid:items-start max-mid:gap-2">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[11.5px] leading-normal font-semibold text-ink-4">
              sin referencia
            </span>
            <Tag prose className="bg-warn-tint text-warn">
              en composición
            </Tag>
          </div>
          <span className="text-[13px] leading-[1.35] font-semibold">
            {name || 'Activo todavía sin nombre'}
          </span>
          <span className="font-mono text-[10.5px] text-ink-4">
            {session.draft ? `${session.draft.zones.length} zona(s) · sin firmar` : 'sin ficha aún'}
          </span>
        </div>

        <div className="min-w-0 text-[12.5px]">
          <div className="font-semibold text-ink-4">—</div>
          <div className="text-[11.5px] text-ink-4">sin firmar</div>
        </div>

        <div
          className="font-mono text-xs text-ink-3"
          title={session.updatedAt ? new Date(session.updatedAt).toLocaleString('es-ES') : undefined}
        >
          {session.updatedAt
            ? new Date(session.updatedAt).toLocaleDateString('es-ES', {
                day: '2-digit',
                month: 'short',
                year: 'numeric',
              })
            : '—'}
        </div>

        <div className="flex flex-wrap gap-1.25">
          {missing.length > 0 ? (
            <Tag prose className="bg-warn-tint text-warn">
              {missing.length} dato(s) por rellenar
            </Tag>
          ) : (
            <Tag prose className="bg-ok-tint text-ok-ink">
              ficha completa
            </Tag>
          )}
          {session.corrections.length > 0 ? (
            <Tag prose title="Campos que has corregido sobre lo que propuso el asistente.">
              {session.corrections.length} corrección(es)
            </Tag>
          ) : null}
          <Tag prose title="Capacidades con una razón escrita.">
            {decided} decisión(es)
          </Tag>
        </div>

        <div className="flex justify-end max-mid:justify-start">
          <PrimaryButton tone="ink" onClick={onContinue}>
            Continuar
          </PrimaryButton>
        </div>
      </div>
    </div>
  )
}

export function BaselinesPage() {
  const navigate = useNavigate()
  const { baselines, catalogVersion, loading, error, loaded, load } = useBaselines()
  const session = useSession()
  const [filter, setFilter] = useState<Filter>('todas')
  const [confirming, setConfirming] = useState(false)

  useEffect(() => {
    void load()
  }, [load])

  const draft = isResumable(session)
  const showSigned = filter !== 'borradores'
  const showDraft = draft && filter !== 'firmadas'
  // The running catalog (from /health) is authoritative and available before any
  // baseline exists; a signed baseline's own version is the fallback.
  const catalog = catalogVersion ?? baselines[0]?.versions.catalog

  function startNew() {
    useSession.getState().reset()
    void navigate({ to: '/composer' })
  }

  return (
    <div className="mx-auto max-w-270 px-6 pt-14 pb-20">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-6">
        <div>
          <Caps className="mb-2">Motor de armonización</Caps>
          <h1 className="m-0 text-[27px] font-semibold tracking-[-0.015em]">Líneas base</h1>
          <p className="m-0 mt-2 max-w-[62ch] text-[13px] text-ink-3">
            Cada línea base es una composición de controles sobre un activo. Una vez firmada queda
            en solo lectura y puede descargarse como documento con su registro de decisiones
            completo.
          </p>
        </div>
        <PrimaryButton
          tone="ink"
          onClick={() => (draft ? setConfirming(true) : startNew())}
          className="flex-none"
        >
          + Nueva línea base
        </PrimaryButton>
      </div>

      <div className="mb-5 flex flex-wrap gap-6 rounded-lg border border-line bg-surface px-4.5 py-3.5">
        <Stat label="Líneas base" value={String(baselines.length + (draft ? 1 : 0))} />
        <Stat label="Firmadas" value={String(baselines.length)} />
        <Stat label="En composición" value={draft ? '1' : '0'} />
        <Stat label="Catálogo" value={catalog ? `v${catalog}` : '—'} />
      </div>

      <div className="mb-3 flex flex-wrap gap-1.5">
        {FILTERS.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setFilter(option)}
            className={`cursor-pointer rounded-[5px] border px-3.5 py-1.5 text-[11.5px] font-semibold ${
              filter === option
                ? 'border-accent bg-accent-tint text-accent'
                : 'border-line bg-surface text-ink-3 hover:border-accent'
            }`}
          >
            {option}
          </button>
        ))}
      </div>

      {error ? (
        <div className="mb-3">
          <Notice tone="alert" label="SIN LISTA">
            {error} <button
              type="button"
              onClick={() => void load()}
              className="cursor-pointer border-none bg-transparent p-0 font-semibold underline"
            >
              Reintentar
            </button>
          </Notice>
        </div>
      ) : null}

      <div className="mb-2 grid gap-4 px-4.5 pb-2 grid-cols-[1.9fr_1.1fr_.9fr_1.2fr_auto] max-mid:hidden">
        <Caps>Línea base</Caps>
        <Caps>Firmante</Caps>
        <Caps>Fecha</Caps>
        <Caps>Composición</Caps>
        <span />
      </div>

      <div className="flex flex-col gap-2">
        {showDraft ? <DraftRow onContinue={() => void navigate({ to: '/composer' })} /> : null}
        {showSigned
          ? baselines.map((baseline) => (
              <BaselineRow key={baseline.baseline_id} baseline={baseline} />
            ))
          : null}
      </div>

      {loading && !loaded ? (
        <p className="mt-4 text-[12.5px] text-ink-4">Leyendo las líneas base firmadas…</p>
      ) : null}

      {loaded && !loading && !showDraft && (!showSigned || baselines.length === 0) ? (
        <div className="rounded-lg border border-dashed border-line-strong px-5 py-10 text-center text-[13px] text-ink-4">
          {filter === 'todas'
            ? 'Todavía no hay ninguna línea base. Empieza una nueva y descríbele el activo al sistema.'
            : 'No hay líneas base con este filtro.'}
        </div>
      ) : null}

      <Modal
        open={confirming}
        onClose={() => setConfirming(false)}
        title="Hay una composición sin firmar"
      >
        <p className="m-0 mb-4 text-[13px] leading-[1.6] text-ink-3">
          Empezar una línea base nueva descarta la que tienes a medias, con sus correcciones y sus
          razones escritas. No se ha registrado nada de ella: hasta que se firma, una composición no
          existe fuera de este navegador.
        </p>
        <div className="flex flex-wrap justify-end gap-2.5">
          <GhostButton onClick={() => setConfirming(false)}>Seguir con la que tengo</GhostButton>
          <PrimaryButton
            onClick={() => {
              setConfirming(false)
              startNew()
            }}
          >
            Descartar y empezar de nuevo
          </PrimaryButton>
        </div>
      </Modal>
    </div>
  )
}
