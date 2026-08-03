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
| `server/app/api/` | Superficie cerrada de la API: dependencias y ensamblado de los cinco endpoints |
| `client/` | React + Vite + TypeScript: UI de una vista (composición soberana) |

## API

Superficie **cerrada**: cinco endpoints. Cualquier endpoint adicional es *scope creep* salvo
justificación escrita, y la lista se declara como dato en `server/app/api/router.py` para que una
prueba pueda comprobarlo (`tests/api/test_surface.py`).

| Endpoint | Función |
| -- | -- |
| `POST /asset/parse` | Texto libre → borrador de `AssetProfile`, revisable (nada se inventa) |
| `POST /candidates` | Perfil → opciones equivalentes por capacidad y zona, lado a lado |
| `POST /baseline/compose` | Elecciones del humano → línea base firmada |
| `GET /baseline/{id}/audit-log` | Trazabilidad completa, con verificación de la cadena |
| `GET /delta?regions=US,EU` | Delta regional para una zona del perfil |

`GET /api/v1/health` no forma parte de la superficie: es la sonda de vida del `healthcheck` de
compose, no una función del motor.

La composición soberana (UCM-16) y el delta regional (UCM-17) tienen aquí su **contrato firme** —
esquema de petición y respuesta, validación y OpenAPI — y responden `501` mientras se implementa su
lógica: la petición se valida de verdad, así que una composición mal formada es `422` antes de
llegar al `501`. La documentación interactiva vive en `http://localhost:8000/docs` y es el plan B
declarado de la demo si se recorta la UI.

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
