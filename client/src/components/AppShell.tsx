/**
 * What wraps both routes: the composition session, and the screen shown when
 * the engine is not there.
 *
 * The provider sits above the outlet, so walking back to the list does not
 * unmount the composition the operator is in the middle of.
 */

import { Outlet } from '@tanstack/react-router'

import { CompositionProvider } from '../features/composition/CompositionProvider'
import { useComposition } from '../features/composition/composition'

function BackendDown() {
  return (
    <div className="fixed inset-0 z-200 flex items-center justify-center bg-page p-6">
      <div className="max-w-115 text-center">
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

function Gate() {
  const { backendUp } = useComposition()
  return backendUp === false ? <BackendDown /> : <Outlet />
}

export function AppShell() {
  return (
    <CompositionProvider>
      <Gate />
    </CompositionProvider>
  )
}
