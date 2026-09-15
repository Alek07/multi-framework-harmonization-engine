# Anexos del TFM

Este directorio es el **índice de anexos** de la memoria *Composición soberana de líneas base de
ciberseguridad en infraestructura crítica multi-dominio*. No duplica el repositorio: cada
referencia `[A-N]` del documento apunta aquí, y desde aquí a la ruta donde el material vive de
verdad.

> **Estado de la entrega.** Cite y navegue siempre sobre el tag `tfm-entrega`, no sobre `main`.
> El tag congela el estado del repositorio en el momento de la entrega, de modo que las cifras del
> apartado 6 de la memoria se corresponden exactamente con el código y los datos que se enlazan
> abajo. `git checkout tfm-entrega`

---

## [A-1] Código, despliegue y fijación de versiones

| Qué | Dónde |
|---|---|
| Composición de contenedores, imágenes fijadas por etiqueta **y por digest** | `docker-compose.yml` |
| Rutas alternativas de aceleración | `docker-compose.gpu.yml`, `docker-compose.rocm.yml` |
| Arranque con autodetección NVIDIA → AMD → CPU y *fallback* documentado al modelo de 3B | `scripts/start.sh`, `scripts/start.ps1` |
| Órdenes de construcción, pruebas y ejecución | `Makefile` |
| Fijación de dependencias | `server/uv.lock`, `client/bun.lock` |
| Servidor y cliente | `server/`, `client/` |

Arranque completo: `docker compose up`. El detalle de la ruta elegida y del *fallback* lo imprime
el propio script de arranque.

## [A-2] Catálogo v0.6.0

El catálogo está partido en dos niveles, que conviene distinguir para navegarlo:

| Qué | Dónde |
|---|---|
| Las **37 capacidades**, los ejes, las fuentes y las limitaciones declaradas | `server/data/catalog/catalog.v0.6.0.json` |
| Los **238 controles** y los **278 mapeos**, un archivo por marco | `server/data/catalog/v0.6.0/` |

El reparto por marco: CSF 106 controles, IEC 62443 51, CIS 49, NIS2 13, TSA 8, IMO 7 y CIRCIA 4.

Las versiones anteriores (`catalog.v0.1.0` a `catalog.v0.5.0`, con sus directorios) se conservan
porque el experimento de escalado del apartado 6.3 las usa como puntos de medida. Nunca se editan
en su sitio: cada cambio abre una versión nueva.

Cada mapeo lleva su tipo (`total`, `partial`, `compensatory`, `contextual`), su peso de cobertura y
su procedencia (`official_crosswalk` frente a `author_judgment`) con jurisdicción anotada.

## [A-3] Reglas versionadas

| Regla | Archivo |
|---|---|
| Gating | `server/data/rules/gating.v0.1.0.json` … `gating.v0.4.0.json` |
| Precedencia entre marcos y *override* de safety | `server/data/rules/precedence.v0.1.0.json`, `precedence.v0.2.0.json` |
| Priorización | `server/data/rules/prioritization.v0.1.0.json`, `prioritization.v0.2.0.json` |

La independencia del orden de ingesta, que la memoria afirma en el apartado 4.3, se comprueba en
`server/tests/engine/test_order_independence.py`.

## [A-4] Esquemas Pydantic

`server/app/*/schemas.py` — una sola definición gobierna las tres fronteras: esquema del catálogo,
contrato de la API y tipo de salida del LLM.

Los más relevantes para la memoria: `catalog/schemas.py` (capacidades, controles y mapeos),
`engine/schemas.py` (resolución, gating y priorización), `baseline/schemas.py` (composición y
firma), `audit/schemas.py` (eventos de bitácora) y `delta/schemas.py` (comparación regional).

## [A-5] Superficie de API cerrada

`server/tests/api/test_surface.py` — contrasta las rutas montadas con el documento OpenAPI que
el servidor publica. Comprueba que la superficie es exactamente la declarada —las cinco del diseño
original más las dos añadidas— y que su tamaño es 7, de modo que un octavo endpoint no puede colarse
en silencio. El *health check* se sirve pero queda fuera de la superficie,
y también eso está comprobado.

El resto de `server/tests/api/` cubre cada endpoint por separado.

## [A-6] Flujo de composición, los cinco pasos

`docs/anexos/capturas/` — una captura por paso de una única corrida por la interfaz sobre el
activo de referencia (el gasoducto de transporte del apartado 5.1):

| Paso | Captura |
|---|---|
| Describir el activo y revisar el borrador extraído campo a campo | `01-describir-activo.png` |
| Elegir entre las opciones equivalentes de cada requisito | `02-elegir-opciones.png` |
| Comparar por región (EE. UU. → +UE) sobre una zona | `03-comparar-region.png` |
| Firmar la línea base | `04-firmar.png` |
| Consultar el registro de decisiones | `05-registro.png` |

El anexo es autónomo a propósito: no remite al video de presentación, porque el material que
respalda la memoria debe poder consultarse por sí solo.

El código de la interfaz está en `client/`.

## [A-7] Línea base firmada, bitácora y declaración de aplicabilidad

La misma corrida del flujo completo que produce las capturas del [A-6] firma una línea base de
ejemplo (`baseline_id` `f5a58d60-1c3a-402a-aa1f-098fe1613b75`, dos zonas del gasoducto de
transporte, 62/62 requisitos obligatorios decididos). De ahí salen sus tres artefactos, leídos de
la misma bitácora encadenada:

| Qué | Dónde |
|---|---|
| Bitácora encadenada completa (1055 anotaciones: 988 del motor y 67 humanas; cadena SHA-256 verificada) | `linea-base-firmada.bitacora.json` |
| Declaración de aplicabilidad (SoA) | `linea-base-firmada.soa.json` |
| Plan de seguridad OSCAL 1.1.3 (export parcial declarado en sus metadatos) | `linea-base-firmada.oscal.json` |

Los tres se descargaron por la propia interfaz sobre la línea base ya firmada; SoA y OSCAL son el
mismo documento en dos vocabularios.

El código que los produce está en `server/app/baseline/` y `server/app/audit/`; las pruebas de la
cadena SHA-256 en `server/tests/audit/test_log.py` y `test_trail.py`.

## [A-8] Evidencia de la evaluación

Los informes viven en `docs/anexos/eval/`. Los generadores que los producen están en
`server/scripts/`, de modo que cada cifra del apartado 6 se puede volver a calcular.

| Medida del apartado 6 | Informe | Generador |
|---|---|---|
| Escalado del recuperador: recall en cuatro tamaños de catálogo | `experimento-escalado-recuperador.md` y su `.json` | `retrieval_scaling.py` |
| Corte auditable, tres brazos | `corte-del-recuperador.md` | `retrieval_cut.py` |
| Etiquetado de premisas, dos *prompts* | `premisas-del-control.md`, `premisas-propuestas.json` | `tag_presuppositions.py`, `merge_presuppositions.py` |
| Delta regional, las dos lecturas | `ucm48-delta-evidencia.md`, `ucm48-delta-US-EU.json`, `ucm48-delta-EU-US.json` | flujo del motor |
| Precisión de aplicabilidad | `precision-de-aplicabilidad.md` | `gating_report.py` |
| Correspondencia con OSCAL | `oscal-crosswalk.md` | — |
| Alineación con los marcos reconocidos | `nota-de-alineacion.md` | — |

Estos informes se habían retirado del repositorio en el commit `b5a9261`; se restituyen aquí
porque son la evidencia que respalda las cifras que la memoria publica.

La verdad de referencia de aplicabilidad, congelada y externa al motor, está en
`server/eval/applicability_ground_truth.json`. El motor nunca la lee.

---

## Nota sobre el alcance del material

Todo el catálogo procede de fuentes públicas y las descripciones de control son **paráfrasis, nunca
literales** de la norma. No se incluyen datos internos de la Autoridad del Canal de Panamá ni de
ninguna otra organización.
