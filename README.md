# Motor de armonización multi-marco (TFM POC)

POC del TFM (Máster en Ciberseguridad UCM) que asiste a un operador de infraestructura crítica en
la **composición soberana** de la línea base de ciberseguridad de un activo OT/IT/híbrido.

- La IA (local, acotada) parsea la descripción del activo y recupera controles candidatos (RAG).
- Un **núcleo determinista** mapea, resuelve conflictos, aplica gating y prioriza.
- El **humano compone y firma** la baseline final, con bitácora trazable de punta a punta.

**Invariantes:** IA sugiere/recupera · reglas deciden · humano compone y firma. Nada se restringe
ni se borra en silencio. Reproducibilidad total (temp 0, seed fija, modelo fijado, mapeos
versionados).

## Arrancar

```bash
./scripts/start.sh        # Linux y macOS
.\scripts\start.ps1       # Windows
```

| | URL |
| -- | -- |
| Aplicación | <http://localhost:8080> |
| Swagger — plan B declarado de la demo | <http://localhost:8000/docs> |

**El primer arranque descarga ~5,8 GB** (el modelo de ~4,7 GB y los *embeddings* de ~1,1 GB) y tarda
entre 15 y 30 minutos; los siguientes tardan menos de un minuto. Nada de eso se hornea en las
imágenes: vive en volúmenes y se reutiliza.

El lanzador elige la ruta según el hardware, espera a los cuatro contenedores y comprueba dónde ha
quedado el modelo. Opciones: `--cpu` fuerza la ruta portable, `--gpu` la fuerza al revés, `--down`
para el sistema, `--logs` sigue los registros.

## Usar la aplicación

Una sola vista, cinco pasos. Se puede recorrer entera sin IA salvo el primero.

| Paso | Qué se hace |
| -- | -- |
| **1 · Describir** | Se pega la descripción del activo en texto libre. El modelo extrae y **cita** cada campo; lo que no ha podido situar se lista, no se descarta. |
| **1b · Revisar** | Todo campo es editable y `◆` marca tus correcciones. No deja continuar con un valor obligatorio sin decidir. |
| **2 · Elegir** | Opciones equivalentes lado a lado por capacidad — marco, jurisdicción, fuerza, tier — y qué ha quitado el gating y por qué. Se elige por zona. Es la contribución central. |
| **3 · Comparar** | Una zona leída bajo US y bajo +EU. Lecturas acumulativas, nunca un catálogo paralelo. |
| **4 · Firmar** | Se verifica que el bloque obligatorio está completo y se firma. Nada obligatorio llega a la baseline sin un nombre detrás: elegido, compensado, hueco aceptado por escrito o ratificado. |
| **5 · Registro** | Bitácora *append-only*, cadena verificada contra su SHA-256 y el evento anterior. |

Componer, firmar, leer la bitácora y el delta regional **no necesitan IA**: funcionan con Ollama y
Qdrant apagados. Lo único que espera al modelo es leer una descripción, y eso también puede hacerse
a mano.

Cinco descripciones de ejemplo, de cinco sectores distintos, y lo que produjo cada una cuando se
ejecutó de verdad: **[docs/demo-playbook.md](docs/demo-playbook.md)**.

## API

Superficie **cerrada**: cinco endpoints. La lista se declara como dato en
`server/app/api/router.py` para que una prueba lo compruebe (`tests/api/test_surface.py`).

| Endpoint | Función |
| -- | -- |
| `POST /asset/parse` | Texto libre → borrador de `AssetProfile`, revisable |
| `POST /candidates` | Perfil → opciones equivalentes por capacidad y zona |
| `POST /baseline/compose` | Elecciones del humano → línea base firmada |
| `GET /baseline/{id}/audit-log` | Trazabilidad completa, con verificación de la cadena |
| `POST /delta` | Delta regional para una zona del perfil |

`GET /api/v1/health` no forma parte de la superficie: es la sonda del `healthcheck` de compose.

## Estructura

| Ruta | Contenido |
| -- | -- |
| `server/` | FastAPI + Python 3.12 (uv): núcleo determinista, API, bitácora |
| `server/data/` | Catálogo, reglas del motor y perfiles, versionados y congelados en Git |
| `server/app/parse/`, `retrieval/` | Las dos pasadas de IA: borrador de perfil y recuperación de candidatos |
| `server/app/candidates/`, `baseline/`, `delta/` | Opciones por capacidad, composición y firma, delta regional |
| `client/` | React + Vite + TypeScript: UI de una vista |

## Configuración

Todo tiene valor por defecto: **no hace falta ningún `.env`**. Para cambiar algo, copia
`.env.example` a `.env` en la raíz (modelo, puertos, capa de explicaciones). El backend nativo lee
`server/.env` (ver `server/.env.example`).

Las versiones fijadas — imágenes con su digest, modelo con su digest, catálogo y reglas — están en
`docker-compose.yml` y en `.env.example`.

En máquinas de 8 GB, el lanzador recomienda por consola el modelo de respaldo
(`qwen2.5:3b-instruct-q4_K_M`, con su digest). Se cambia a mano en `.env` y **no se aplica solo**:
unos pesos distintos producen un borrador distinto, y elegirlos por tamaño de máquina haría que el
resultado dependiera de la máquina.

Por la misma razón hay que decir esto tal cual: **la reproducibilidad se sostiene dentro de cada
ruta de hardware, no entre ellas.** CPU y GPU resuelven de otra forma un empate ajustado en los
*logits*, así que la memoria tiene que nombrar en cuál se produjeron los números de la evaluación.
El lanzador dice siempre qué ruta ha usado.

## Desarrollo

```bash
docker compose up -d ollama qdrant     # solo la capa IA

cd server && uv sync
uv run uvicorn app.main:app --reload   # http://localhost:8000/api/v1
uv run pytest

cd client && bun install
bun run dev                            # http://localhost:5173
```

La suite corre en cualquier máquina, sin contenedores y sin red: las pruebas que necesitan los
servicios reales quedan deseleccionadas salvo que se pidan (`pytest -m llm`, `pytest -m rag`).

Las reglas, invariantes y convenciones de trabajo del proyecto están en [CLAUDE.md](CLAUDE.md).
