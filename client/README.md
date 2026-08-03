# Cliente — composición soberana (UCM-21)

Interfaz de una sola vista sobre los cinco endpoints del motor: describir el activo →
revisar y corregir el `AssetProfile` → componer a partir de las opciones equivalentes que el
motor pone lado a lado → consultar el delta regional → firmar → leer la bitácora.

Es **envoltorio de demostración, no producto**. Si el backend no responde, la aplicación lo
dice y remite a Swagger — el plan B declarado en el PRD.

## Regla de reparto: el cliente no calcula

El motor es el dueño de todo hecho — qué opciones existen, qué cubren, qué mandatos quedan
abiertos, qué contradicciones no resuelve, qué mecanismos apartó el gating. Todo eso llega en
la respuesta de `POST /candidates` y se **renderiza**, nunca se recalcula. Lo que vive en el
cliente es lo que el operador *ha hecho*: qué controles eligió, por qué, qué huecos aceptó,
qué corrigió del perfil.

Hay exactamente dos excepciones, ambas deliberadas y anotadas en el código:

| Lógica del cliente | Por qué existe | Fuente de verdad |
| -- | -- | -- |
| `src/lib/draft.ts` | Promover un borrador a `AssetProfile` es una función pura y offline; un sexto endpoint para hacerlo abriría una superficie cerrada (invariante 4) sin comprar nada. Comprueba presencia, nunca semántica. | `server/app/parse/completion.py` |
| `progress` en `src/state/CompositionProvider.tsx` | Decide si el botón de firmar está habilitado y qué bloqueadores se enseñan. El servidor vuelve a verificar lo mismo antes de firmar, así que un error aquí solo puede pedir de más, nunca firmar de menos. | `_check_mandates` en `server/app/baseline/service.py` |

## Estructura

```
src/api/types.ts       contratos TS espejo de los modelos Pydantic del servidor
src/api/client.ts      los cinco endpoints (axios) + la sonda /health del plan B
src/state/             el contexto de la sesión: llamadas al motor y decisiones del humano
src/lib/               promoción del borrador y vocabulario presentacional
src/components/        barra de reproducibilidad, raíl de etapas, dock, diálogo de firma
src/components/stages/ las cinco etapas
```

## Comandos

```bash
bun install
bun run dev        # http://localhost:5173 (proxy de /api al backend)
bun run build      # tsc -b && vite build
bun run preview    # sirve dist con el mismo proxy, para comprobar el artefacto
bun run lint
```

El backend se levanta desde `server/` con `uv run uvicorn app.main:app`.

## Variables de entorno

| Variable | Por defecto | Para qué |
| -- | -- | -- |
| `VITE_API_BASE_URL` | `/api/v1` | Base de la API. Sin valor, el cliente llama a su propio origen y el proxy de Vite reenvía; en compose se apunta al servicio del backend. |
| `VITE_API_PROXY_TARGET` | `http://localhost:8000` | Destino del proxy de desarrollo (`vite.config.ts`). |

Las fuentes IBM Plex van empaquetadas (`@fontsource/*`) en lugar de pedirse a Google Fonts:
`docker compose up` tiene que producir la misma pantalla en una máquina ajena (invariante 3).
