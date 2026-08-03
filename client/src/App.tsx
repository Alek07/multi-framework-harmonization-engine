/**
 * One screen, five stages: describe the asset, review what the model made of
 * it, compose from the options the engine laid side by side, compare regions,
 * sign, read the trail.
 *
 * Every fact on screen comes from an engine response, and when the backend is
 * not there this component says so plainly rather than pretending to work
 * offline. What it never says is *how* it asked: routes, schema names and rule
 * identifiers are the engineer's vocabulary, not the operator's.
 */

import { useState } from 'react'

import { ComposerDock } from './components/ComposerDock'
import { ReproducibilityBar } from './components/ReproducibilityBar'
import { SignDialog } from './components/SignDialog'
import { StageRail } from './components/StageRail'
import { StageAsset } from './components/stages/StageAsset'
import { StageAudit } from './components/stages/StageAudit'
import { StageCandidates } from './components/stages/StageCandidates'
import { StageDelta } from './components/stages/StageDelta'
import { StageSign } from './components/stages/StageSign'
import { GhostButton, PrimaryButton } from './components/ui'
import { CompositionProvider } from './state/CompositionProvider'
import { useComposition, type Step, type StepLocks } from './state/composition'

const STEP_LABELS: Record<Step, string> = {
  1: 'Describir el activo',
  2: 'Elegir los controles',
  3: 'Comparar por región',
  4: 'Revisar y firmar',
  5: 'Registro de decisiones',
}

function BackendDown() {
  return (
    <div className="fixed inset-0 z-200 flex items-center justify-center bg-page p-6">
      <div className="max-w-[460px] text-center">
        <div className="mb-3 text-[11px] font-semibold tracking-[0.1em] text-ink-4 uppercase">
          Servicio no disponible
        </div>
        <h2 className="m-0 mb-2.5 text-xl font-semibold">No se puede conectar con el sistema</h2>
        <p className="m-0 mb-5 text-sm leading-[1.6] text-ink-3">
          La aplicación no ha podido contactar con el servicio que compone las líneas base. No se ha
          perdido nada: nada se guarda hasta que firmas. Comprueba que el sistema esté arrancado y
          vuelve a intentarlo.
        </p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="cursor-pointer rounded-md border-none bg-accent px-4 py-2.5 text-[13px] font-semibold text-white hover:bg-accent-ink"
        >
          Reintentar
        </button>
      </div>
    </div>
  )
}

/**
 * Forward and back, in the order the argument is made.
 *
 * A step whose input does not exist yet is offered disabled with the missing
 * piece written underneath, not hidden: the operator has to be able to see where
 * the flow goes and what unlocks it, and a button that vanishes teaches neither.
 */
function StepNav({
  step,
  goToStep,
  stepLocks,
}: {
  step: Step
  goToStep: (step: Step) => void
  stepLocks: StepLocks
}) {
  const next = step < 5 ? ((step + 1) as Step) : null
  const lock = next ? stepLocks[next] : null

  return (
    <div className="mt-1 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        {step > 1 ? (
          <GhostButton onClick={() => goToStep((step - 1) as Step)}>
            ← {step - 1}. {STEP_LABELS[(step - 1) as Step]}
          </GhostButton>
        ) : (
          <span />
        )}
        {next ? (
          <PrimaryButton
            onClick={() => goToStep(next)}
            disabled={Boolean(lock)}
            title={lock ?? undefined}
          >
            {next}. {STEP_LABELS[next]} →
          </PrimaryButton>
        ) : (
          <span />
        )}
      </div>
      {lock ? <div className="self-end text-right text-[11.5px] text-ink-4">{lock}</div> : null}
    </div>
  )
}

function Composition() {
  const { backendUp, step, goToStep, stepLocks, signed, baseline } = useComposition()
  const [signOpen, setSignOpen] = useState(false)

  if (backendUp === false) return <BackendDown />

  return (
    <div className="min-h-screen">
      <ReproducibilityBar />

      <div className="mx-auto flex max-w-[1240px] gap-7 px-6 pt-16 pb-32">
        <StageRail />

        <main className="flex min-w-0 flex-1 flex-col gap-9">
          {signed && baseline ? (
            <div className="rounded-md border border-ok-line bg-ok-tint px-4 py-3 text-[13px] leading-[1.55] text-ok-ink">
              <b>Línea base firmada.</b> A partir de aquí la composición es de solo lectura: el
              registro no se puede modificar ni borrar. Si algo tiene que cambiar, se compone y se
              firma una línea base nueva, y ambas quedan en el histórico.
              <div className="mt-1 text-[11.5px] text-ink-4">
                Referencia: <span className="font-mono">{baseline.baseline_id}</span>
              </div>
            </div>
          ) : null}

          {step === 1 ? <StageAsset /> : null}
          {step === 2 ? <StageCandidates /> : null}
          {step === 3 ? <StageDelta /> : null}
          {step === 4 ? <StageSign onOpenSign={() => setSignOpen(true)} /> : null}
          {step === 5 ? <StageAudit /> : null}

          <StepNav step={step} goToStep={goToStep} stepLocks={stepLocks} />
        </main>
      </div>

      <ComposerDock onOpenSign={() => setSignOpen(true)} />
      <SignDialog open={signOpen} onClose={() => setSignOpen(false)} />
    </div>
  )
}

export default function App() {
  return (
    <CompositionProvider>
      <Composition />
    </CompositionProvider>
  )
}
