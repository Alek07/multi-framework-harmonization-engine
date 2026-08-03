/**
 * The signature dialog.
 *
 * The summary is not editable and it is not a preview the client invented: it
 * counts the entries that are about to be sent as `CompositionChoice`s, by kind.
 * The two fields under it are the `Signature` the contract asks for — who
 * composes, and why this baseline is the right one for the asset — because a
 * signature without a written justification is exactly what UCM-11 refuses to
 * record. The declaration checkbox is the operator's acceptance that all of it
 * becomes immutable.
 */

import { useState } from 'react'

import { useComposition } from '../state/composition'
import { Checkbox, PrimaryButton } from './ui'

function Row({ label, value }: { label: string; value: number | string }) {
  return (
    <>
      <span>{label}</span>
      <span className="text-right font-mono text-xs font-semibold">{value}</span>
    </>
  )
}

export function SignDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { choices, corrections, signing, signError, sign, progress } = useComposition()
  const [operator, setOperator] = useState('')
  const [role, setRole] = useState('')
  const [rationale, setRationale] = useState('')
  const [accepted, setAccepted] = useState(false)

  if (!open) return null

  const count = (kind: string) => choices.filter((choice) => choice.kind === kind).length
  const ready =
    operator.trim() !== '' && role.trim() !== '' && rationale.trim() !== '' && accepted && !signing

  return (
    <div className="fixed inset-0 z-100 flex items-center justify-center bg-[rgba(24,34,48,.45)] p-6">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Firmar baseline"
        className="w-full max-w-[560px] rounded-[10px] bg-surface px-7 py-6 shadow-[0_20px_60px_rgba(24,34,48,.3)]"
      >
        <h3 className="m-0 mb-1 text-base font-semibold">Firmar baseline</h3>
        <p className="m-0 mb-3.5 text-[12.5px] text-ink-3">
          Resumen no editable de lo que se va a registrar:
        </p>

        <div className="mb-4 grid grid-cols-2 gap-2 rounded-md border border-line-2 bg-surface-2 px-3.5 py-3 text-[12.5px]">
          <Row label="Mecanismos elegidos" value={count('option_selected')} />
          <Row label="Controles compensatorios declarados" value={count('compensatory_declared')} />
          <Row label="Opciones descartadas (conflictos)" value={count('option_rejected')} />
          <Row label="Huecos aceptados" value={count('gap_accepted')} />
          <Row label="Correcciones al perfil" value={corrections.length} />
          <Row
            label="Tier 0 (mandatos cerrados)"
            value={`${progress.tier0Done}/${progress.tier0Total}`}
          />
        </div>

        <div className="mb-3 grid grid-cols-2 gap-2.5">
          <input
            value={operator}
            onChange={(event) => setOperator(event.target.value)}
            placeholder="Nombre del firmante"
            className="rounded-[5px] border border-line-strong px-2.5 py-2 text-[13px] outline-accent"
          />
          <input
            value={role}
            onChange={(event) => setRole(event.target.value)}
            placeholder="Rol"
            className="rounded-[5px] border border-line-strong px-2.5 py-2 text-[13px] outline-accent"
          />
        </div>

        <textarea
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
          placeholder="Por qué esta línea base es la adecuada para el activo y sus zonas…"
          className="mb-3 min-h-[64px] w-full resize-y rounded-[5px] border border-line-strong px-2.5 py-2 text-[13px] outline-accent"
        />

        <label className="mb-4 flex cursor-pointer items-start gap-2.5 text-[12.5px] text-ink-2">
          <Checkbox
            checked={accepted}
            onClick={() => setAccepted(!accepted)}
            label="acepto que las decisiones queden registradas de forma inmutable"
          />
          Declaro que he revisado las elecciones, los huecos aceptados y los conflictos resueltos, y
          acepto que queden registrados de forma inmutable.
        </label>

        {signError ? (
          <div className="mb-3 rounded-md border border-alert-line bg-alert-tint px-3.5 py-2.5 text-[12.5px] text-alert-ink">
            {signError}
          </div>
        ) : null}

        <div className="flex justify-end gap-2.5">
          <button
            type="button"
            onClick={onClose}
            className="cursor-pointer rounded-md border border-line-strong bg-transparent px-4 py-2 text-[13px] text-ink-2 hover:border-ink hover:text-ink"
          >
            Cancelar
          </button>
          <PrimaryButton
            testId="confirm-sign"
            tone="ink"
            disabled={!ready}
            onClick={() => {
              void sign({
                operator: `${operator.trim()} (${role.trim()})`,
                rationale: rationale.trim(),
              }).then((ok) => {
                // A refused signature keeps the dialog open with the server's own
                // sentence in it: an open mandate, a version that moved, a run
                // already signed. Closing would hide the reason.
                if (ok) onClose()
              })
            }}
          >
            {signing ? 'Firmando…' : 'Firmar y registrar'}
          </PrimaryButton>
        </div>
      </div>
    </div>
  )
}
