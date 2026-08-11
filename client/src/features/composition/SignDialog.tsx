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

import { CHOICE_KIND } from '../../lib/labels'
import { useComposition } from './composition'
import { Checkbox, PrimaryButton } from '../../components/ui'

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
    <div className="fixed inset-0 z-100 flex items-center justify-center bg-[rgba(24,34,48,.45)] p-6 max-narrow:items-start max-narrow:p-3">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Firmar baseline"
        className="w-full max-w-140 overflow-y-auto rounded-[10px] bg-surface px-7 py-6 shadow-[0_20px_60px_rgba(24,34,48,.3)] max-narrow:max-h-[92vh] max-narrow:px-4 max-narrow:py-4.5"
      >
        <h3 className="m-0 mb-1 text-base font-semibold">Firmar la línea base</h3>
        <p className="m-0 mb-3.5 text-[12.5px] leading-normal text-ink-3">
          Esto es lo que va a quedar registrado con tu nombre. No se puede editar desde aquí: si
          algo no cuadra, cierra este cuadro y corrígelo en el paso 2.
        </p>

        <div className="mb-4 grid grid-cols-2 gap-2 rounded-md border border-line-2 bg-surface-2 px-3.5 py-3 text-[12.5px] max-mid:grid-cols-1">
          <Row label={CHOICE_KIND.option_selected} value={count('option_selected')} />
          <Row label={CHOICE_KIND.compensatory_declared} value={count('compensatory_declared')} />
          <Row label={CHOICE_KIND.option_rejected} value={count('option_rejected')} />
          <Row label={CHOICE_KIND.gap_accepted} value={count('gap_accepted')} />
          <Row label="Correcciones a la ficha del activo" value={corrections.length} />
          <Row
            label="Requisitos obligatorios decididos"
            value={`${progress.tier0Done}/${progress.tier0Total}`}
          />
        </div>

        <div className="mb-3 grid grid-cols-2 gap-2.5 max-mid:grid-cols-1">
          <input
            value={operator}
            onChange={(event) => setOperator(event.target.value)}
            placeholder="Tu nombre y apellidos"
            className="rounded-[5px] border border-line-strong px-2.5 py-2 text-[13px] outline-accent"
          />
          <input
            value={role}
            onChange={(event) => setRole(event.target.value)}
            placeholder="Tu cargo o responsabilidad"
            className="rounded-[5px] border border-line-strong px-2.5 py-2 text-[13px] outline-accent"
          />
        </div>

        <textarea
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
          placeholder="Explica por qué esta línea base es la adecuada para este activo y sus zonas. Es la justificación global de la firma…"
          className="mb-3 min-h-16 w-full resize-y rounded-[5px] border border-line-strong px-2.5 py-2 text-[13px] outline-accent"
        />

        <label className="mb-4 flex cursor-pointer items-start gap-2.5 text-[12.5px] leading-normal text-ink-2">
          <Checkbox
            checked={accepted}
            onClick={() => setAccepted(!accepted)}
            label="acepto que las decisiones queden registradas de forma permanente"
          />
          He revisado los controles que he elegido, los requisitos que quedan sin cubrir y los
          conflictos que he resuelto. Entiendo que, una vez firmado, el registro no se puede
          modificar ni borrar.
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
            Volver sin firmar
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
            {signing ? 'Firmando…' : 'Firmar y dejar constancia'}
          </PrimaryButton>
        </div>
      </div>
    </div>
  )
}
