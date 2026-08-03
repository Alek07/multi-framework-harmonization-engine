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
| `server/app/candidates/` | Opciones equivalentes por capacidad y zona: núcleo + RAG + explicaciones |
| `server/app/baseline/` | Composición soberana: elecciones del humano, verificación de Tier 0 y firma |
| `server/app/delta/` | Delta regional: una zona leída bajo cada región, de forma acumulativa |
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

La documentación interactiva vive en `http://localhost:8000/docs` y es el plan B declarado de la
demo si se recorta la UI.

### Composición soberana

`POST /baseline/compose` es la contribución central: el humano elige por zona y firma. Antes de
firmar se verifica que el **bloque obligatorio está completo** — cada mandato que el motor no podía
cerrar solo (sin mecanismo aplicable o con residual declarado) tiene que cerrarlo el humano
eligiendo un mecanismo, declarando un compensatorio o aceptando el hueco por escrito. Mientras
quede uno abierto, la firma se **rechaza** (`409`) nombrando cuáles.

El resto de Tier 0 se **ratifica** al firmar, con tipo de evento propio (`mechanism_ratified`):
ratificar no es elegir, y la bitácora nunca afirma una elección que nadie hizo. Así, toda capacidad
obligatoria de toda zona acaba con una entrada humana — elegida, compensada, aceptada como hueco o
ratificada — y ninguna llega a la línea base firmada sin el nombre de alguien.

La firma se ancla a la ejecución del motor de la que salieron las opciones: se rechaza una
ejecución que la bitácora no ha visto, una de otro perfil, una ya firmada, y una calculada con
versiones de catálogo o reglas distintas de las que rigen ahora. Componer y firmar es
**determinista y sin IA**: se puede hacer con Ollama y Qdrant apagados.

### Delta regional

`GET /delta?regions=US,EU&profile_id=PROFILE-B&zone_id=Z-ENG-STATION` lee **una zona** bajo cada
región y muestra qué cambia. Las lecturas son **acumulativas**: «+EU» es la lectura estadounidense
*más* la capa de obligación europea, nunca un catálogo paralelo en el que un operador europeo no
tuviera CIS ni CSF. Toda jurisdicción que no está en comparación es terreno común y aparece en
todas las lecturas (IEC 62443 como estándar OT común, IMO como marítimo), así que la unión de las
lecturas es siempre el catálogo entero. Lo que cada lente aparta se devuelve con nombre.

El resultado sobre la zona de la demo: de 24 capacidades, **5 cambian** — gobernanza, roles,
cadena de suministro, concienciación y notificación de incidentes — y las cinco lo hacen
**añadiendo obligación sin mover la cobertura**. Todos los mapeos de NIS2 del catálogo son
`contextual` con peso bajo, así que un operador estadounidense cubre la notificación de incidentes
con CSF RS.CO-02 como buena práctica y uno sujeto a NIS2 debe *además* el Art. 23 con plazos de
24 h / 72 h / 1 mes. La diferencia regional de este catálogo es sobre todo **legal, no técnica**, y
decirlo así es el resultado, no una carencia. El delta lee mapeos autorizados, no distancias entre
vectores: también funciona con Ollama y Qdrant apagados, y no escribe en la bitácora (es una
*vista*; lo que se registra es la composición que informa).

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
