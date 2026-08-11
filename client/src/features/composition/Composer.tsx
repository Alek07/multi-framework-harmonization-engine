/**
 * One screen, five stages: describe the asset, review what the model made of
 * it, compose from the options the engine laid side by side, compare regions,
 * sign, read the trail.
 *
 * Every fact on screen comes from an engine response, and routes, schema names
 * and rule identifiers stay the engineer's vocabulary, not the operator's.
 */

import { useState } from 'react'

import { useComposition, type Step, type StepLocks } from './composition'
import { ComposerDock } from './ComposerDock'
import { ReproducibilityBar } from './ReproducibilityBar'
import { SignDialog } from './SignDialog'
import { StageRail } from './StageRail'
import { StageAsset } from './stages/StageAsset'
import { StageAudit } from './stages/StageAudit'
import { StageCandidates } from './stages/StageCandidates'
import { StageDelta } from './stages/StageDelta'
import { StageSign } from './stages/StageSign'
import { GhostButton, PrimaryButton } from '../../components/ui'

const STEP_LABELS: Record<Step, string> = {
  1: 'Describir el activo',
  2: 'Elegir los controles',
  3: 'Comparar por región',
  4: 'Revisar y firmar',
  5: 'Registro de decisiones',
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

export function Composer() {
  const { step, goToStep, stepLocks, signed, baseline } = useComposition()
  const [signOpen, setSignOpen] = useState(false)

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
