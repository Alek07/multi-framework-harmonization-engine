/**
 * One screen, five stages: describe the asset, review what the model made of
 * it, compose from the options the engine laid side by side, compare regions,
 * sign, read the trail.
 *
 * The UI is a demonstration wrapper, not the product (UCM-21). Every fact on
 * screen comes from one of the five endpoints, and when the backend is not there
 * this component says so and points at Swagger — the declared plan B — instead
 * of pretending to work offline.
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
import { useComposition, type Step } from './state/composition'

const STEP_LABELS: Record<Step, string> = {
  1: 'Activo y perfil',
  2: 'Candidatos',
  3: 'Delta regional',
  4: 'Firma',
  5: 'Bitácora',
}

function BackendDown() {
  return (
    <div className="fixed inset-0 z-200 flex items-center justify-center bg-page p-6">
      <div className="max-w-[460px] text-center">
        <div className="mb-3 font-mono text-[11px] font-semibold tracking-[0.1em] text-ink-4">
          BACKEND NO DISPONIBLE — PLAN B
        </div>
        <h2 className="m-0 mb-2.5 text-xl font-semibold">El motor se demuestra por API</h2>
        <p className="m-0 mb-4 text-sm text-ink-3">
          La UI es envoltorio de demostración, no producto. Toda la funcionalidad está en los cinco
          endpoints.
        </p>
        <a
          href="http://localhost:8000/docs"
          className="font-mono text-sm font-semibold"
          target="_blank"
          rel="noreferrer"
        >
          http://localhost:8000/docs
        </a>
      </div>
    </div>
  )
}

function Composition() {
  const { backendUp, step, goToStep, signed, baseline } = useComposition()
  const [signOpen, setSignOpen] = useState(false)

  if (backendUp === false) return <BackendDown />

  return (
    <div className="min-h-screen">
      <ReproducibilityBar />

      <div className="mx-auto flex max-w-[1240px] gap-7 px-6 pt-16 pb-32">
        <StageRail />

        <main className="flex min-w-0 flex-1 flex-col gap-9">
          {signed && baseline ? (
            <div className="rounded-md border border-ok-line bg-ok-tint px-4 py-3 text-[13px] text-ok-ink">
              Baseline <b className="font-mono">{baseline.baseline_id}</b> firmada. La composición
              es de <b>solo lectura</b>; cambiar algo exige una baseline nueva sobre una ejecución
              nueva (invariante 5).
            </div>
          ) : null}

          {step === 1 ? <StageAsset /> : null}
          {step === 2 ? <StageCandidates /> : null}
          {step === 3 ? <StageDelta /> : null}
          {step === 4 ? <StageSign onOpenSign={() => setSignOpen(true)} /> : null}
          {step === 5 ? <StageAudit /> : null}

          <div className="mt-1 flex items-center justify-between">
            {step > 1 ? (
              <GhostButton onClick={() => goToStep((step - 1) as Step)}>
                ← {step - 1}. {STEP_LABELS[(step - 1) as Step]}
              </GhostButton>
            ) : (
              <span />
            )}
            {step < 5 ? (
              <PrimaryButton onClick={() => goToStep((step + 1) as Step)}>
                {step + 1}. {STEP_LABELS[(step + 1) as Step]} →
              </PrimaryButton>
            ) : (
              <span />
            )}
          </div>
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
