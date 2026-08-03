import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dev server proxies `/api` to the backend so the browser talks to a single
// origin and CORS never becomes a variable of the demo. `VITE_API_BASE_URL`
// overrides the base the client calls (docker compose, a backend on another
// host); left unset, the client calls `/api/v1` on its own origin and this
// proxy forwards it to the FastAPI process.
const proxy = {
  '/api': {
    target: process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000',
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy },
  // `bun run preview` serves the production bundle the same way, so the built
  // artefact can be checked against a running backend before it is packaged.
  preview: { port: 4173, proxy },
})
