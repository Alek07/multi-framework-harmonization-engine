# Motor de armonización multi-marco (TFM POC)

POC del TFM (Máster en Ciberseguridad UCM) que asiste a un operador de infraestructura crítica en
la **composición soberana** de la línea base de ciberseguridad de un activo OT/IT/híbrido.

- La IA (local, acotada) parsea la descripción del activo y recupera controles candidatos (RAG).
- Un **núcleo determinista** mapea, resuelve conflictos, aplica gating y prioriza.
- El **humano compone y firma** la baseline final, con bitácora trazable de punta a punta.

**Invariantes:** IA sugiere/recupera · reglas deciden · humano compone y firma. Nada se restringe
ni se borra en silencio. Reproducibilidad total (temp 0, seed fija, modelo fijado, mapeos
versionados).

## Estructura

| Ruta | Contenido |
| -- | -- |
| `server/` | FastAPI + Python 3.12 (uv): núcleo determinista, API, bitácora |
| `server/data/catalog/` | Catálogo JSON versionado (capacidades, controles, mapeos) |
| `server/data/rules/` | Reglas versionadas del motor: precedencia por zona, gating por perfil y priorización (mandatos por SL, dependencias, coste ordinal) |
| `server/data/profiles/` | Perfiles de activo escritos a mano (entradas congeladas de validación) |
| `server/app/parse/` | Pasada IA 1: texto libre → borrador de `AssetProfile` (revisado por el operador) |
| `server/app/retrieval/` | Pasada IA 2: recuperación de candidatos sobre Qdrant, con filtrado por payload — solo amplía cobertura |
| `client/` | React + Vite + TypeScript: UI de una vista (composición soberana) |

## Desarrollo

```bash
# servicios de la capa IA (ollama + qdrant)
docker compose up -d

# backend
cd server
uv sync
uv run uvicorn app.main:app --reload   # http://localhost:8000/api/v1
uv run pytest

# frontend
cd client
bun install
bun run dev                            # http://localhost:5173
```

La suite corre en cualquier máquina, sin contenedores y sin red: las pruebas que
necesitan los servicios reales quedan deseleccionadas salvo que se pidan.

```bash
uv run pytest -m llm   # parseo contra el modelo fijado en Ollama (UCM-12)
uv run pytest -m rag   # recuperación contra Qdrant + e5-base real (UCM-13)
```

En el primer arranque, `qdrant` se puebla desde el catálogo JSON y se descarga el
modelo de embeddings (~1,1 GB, CPU). Ambas cosas son datos derivados: se
reconstruyen solas y no son estado del sistema.

El despliegue final se hace con `docker compose up` (4 contenedores: frontend, backend, ollama,
qdrant) — ver hoja de ruta en el proyecto de Linear (milestones M1–M6).

Las reglas, invariantes y convenciones de trabajo del proyecto están en [CLAUDE.md](CLAUDE.md).
