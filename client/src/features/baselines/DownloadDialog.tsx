/**
 * The three ways to take a signed baseline away, with what each one is for.
 *
 * One document in three spellings, not three documents: the printable version and
 * the JSON are the same declaration of applicability, and the OSCAL plan is that
 * declaration in NIST's vocabulary. The rows say so, because the difference that
 * matters to the operator is *who reads the file* — a person, an archive, or a
 * compliance tool — and nothing on the screen would otherwise tell them.
 *
 * Failures stay in this dialog instead of closing it: a download that silently
 * did nothing is the one outcome the operator cannot act on.
 */

import { Modal } from '../../components/ui'

interface Option {
  name: string
  format: string
  note: string
  run: () => void
}

function Row({ option, disabled }: { option: Option; disabled: boolean }) {
  return (
    <button
      type="button"
      onClick={option.run}
      disabled={disabled}
      className="flex w-full cursor-pointer items-baseline gap-3 rounded-md border border-line-2 bg-surface-2 px-3.5 py-3 text-left hover:border-ink disabled:cursor-default disabled:opacity-50"
    >
      <span className="flex-1">
        <span className="block text-[13px] font-semibold">{option.name}</span>
        <span className="mt-0.5 block text-[11.5px] leading-normal text-ink-3">{option.note}</span>
      </span>
      <span className="flex-none font-mono text-[10.5px] font-semibold text-ink-4">
        {option.format}
      </span>
    </button>
  )
}

export function DownloadDialog({
  open,
  onClose,
  loading,
  error,
  onPrint,
  onSoa,
  onOscal,
}: {
  open: boolean
  onClose: () => void
  loading: boolean
  error: string | null
  onPrint: () => void
  onSoa: () => void
  onOscal: () => void
}) {
  const options: Option[] = [
    {
      name: 'Declaración de aplicabilidad, para leer',
      format: 'PDF',
      note: 'Se abre listo para imprimir o guardar como PDF. Una fila por requisito con su decisión, sus exclusiones justificadas y su hueco, y la bitácora completa detrás. Es el documento que sirve de anexo.',
      run: onPrint,
    },
    {
      name: 'Declaración de aplicabilidad, en datos',
      format: 'JSON',
      note: 'El mismo documento tal y como lo emite el motor, sin nada añadido por esta pantalla. Para archivarlo o procesarlo.',
      run: onSoa,
    },
    {
      name: 'Plan de seguridad OSCAL',
      format: 'JSON',
      note: 'La misma declaración en el formato del NIST, para herramientas de cumplimiento que sepan leerlo. Es un export parcial y lo declara en sus propios metadatos.',
      run: onOscal,
    },
  ]

  return (
    <Modal open={open} onClose={onClose} title="Descargar esta línea base">
      <p className="m-0 mb-3.5 text-[12.5px] leading-normal text-ink-3">
        Los tres dicen lo mismo: son la línea base que se firmó, leída de la bitácora. Cambia quién
        los lee.
      </p>

      <div className="flex flex-col gap-2">
        {options.map((option) => (
          <Row key={option.format + option.name} option={option} disabled={loading} />
        ))}
      </div>

      {loading ? (
        <p className="mt-3 mb-0 text-[12px] text-ink-4">Preparando el documento…</p>
      ) : null}

      {error ? (
        <div className="mt-3 rounded-md border border-alert-line bg-alert-tint px-3.5 py-2.5 text-[12.5px] text-alert-ink">
          {error}
        </div>
      ) : null}
    </Modal>
  )
}
