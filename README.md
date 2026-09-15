# Motor de armonización multi-marco

Un operador de infraestructura crítica describe un activo OT/IT/híbrido en texto libre y el motor
le ayuda a **componer de forma soberana** su línea base de ciberseguridad: la IA local sugiere y
recupera, un núcleo determinista decide, y el humano compone y firma —con una bitácora trazable de
punta a punta.

> **IA sugiere y recupera · las reglas deciden · el humano compone y firma.**
> Nada se restringe ni se borra en silencio. Reproducibilidad total: temperatura 0, semilla fija,
> modelo fijado, catálogo y mapeos versionados.

## El flujo, de un vistazo

```mermaid
flowchart TD
    IN["📝 Descripción del activo<br/>(texto libre)"]

    subgraph AI["🔵 IA · sugiere y recupera"]
        direction TB
        PARSE["Parseo<br/>Ollama · temp 0 · semilla fija"]
        RAG["Recuperación RAG<br/>Qdrant · ensancha, nunca restringe"]
    end

    PROFILE["Borrador de perfil del activo<br/>cita cada campo · lo no ubicado se lista, no se descarta"]
    REVIEW["✏️ Revisión y corrección ◆<br/>ningún campo obligatorio queda sin decidir"]

    subgraph CORE["🟢 Reglas · deciden — núcleo determinista, sin IA"]
        direction TB
        MAP["1 · Mapeo<br/>capacidades ↔ controles de cada marco"]
        CONF["2 · Conflictos<br/>solape · granularidad · contradicción real"]
        GATE["3 · Gating<br/>quita mecanismos, nunca capacidades, nunca en silencio"]
        PRIO["4 · Priorización<br/>Tier 0 obligatorio · Tier 1 por fases"]
        MAP --> CONF --> GATE --> PRIO
    end

    CAND["Opciones equivalentes lado a lado<br/>marco · jurisdicción · fuerza · tier — por zona"]

    subgraph HUMAN["🟡 Humano · compone y firma"]
        direction TB
        COMPOSE["Composición soberana<br/>elige por zona"]
        T0{"¿Bloque Tier 0<br/>completo?"}
        SIGN["Firma"]
    end

    BASE[("Línea base firmada")]
    AUDIT[("Bitácora append-only<br/>cadena SHA-256")]
    EXPORT["Declaración de aplicabilidad<br/>SoA · OSCAL"]

    IN --> PARSE --> PROFILE --> REVIEW --> MAP
    RAG -. candidatos .-> CAND
    PRIO --> CAND --> COMPOSE --> T0
    T0 -- "no · faltan mandatos" --> COMPOSE
    T0 -- "sí" --> SIGN --> BASE --> EXPORT
    SIGN --> AUDIT
    REVIEW -. registra .-> AUDIT
    COMPOSE -. cada elección + motivo .-> AUDIT

    classDef ai fill:#e8f0fe,stroke:#4285f4,color:#1a1a1a
    classDef rule fill:#e6f4ea,stroke:#34a853,color:#1a1a1a
    classDef human fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a
    classDef store fill:#f1f3f4,stroke:#5f6368,color:#1a1a1a
    class PARSE,RAG ai
    class MAP,CONF,GATE,PRIO rule
    class REVIEW,COMPOSE,T0,SIGN human
    class BASE,AUDIT,EXPORT store
```

**Cómo leerlo.** Cada color es un actor y la frontera entre ellos es innegociable: la IA (azul)
solo lee la descripción y recupera candidatos —nunca decide, ordena ni filtra—; las reglas (verde)
son deterministas y no tocan la IA; el humano (amarillo) es el único que elige y firma. La firma
está bloqueada hasta que el bloque obligatorio (Tier 0) esté completo, y **todo** —tanto lo que
decide el motor como lo que decide la persona— queda escrito en una bitácora que solo crece,
encadenada por SHA-256. El resultado firmado se puede exportar como declaración de aplicabilidad
(SoA) o como plan parcial OSCAL.

La contribución central está en el paso amarillo **Composición soberana**: no traduce un marco a
otro (A≈B, como haría un *crosswalk*), sino que pone las opciones equivalentes lado a lado y
**aconseja la selección** por zona.

## Arrancar

La primera vez —y después de cualquier cambio de código— hay que construir las imágenes de backend
y frontend:

```bash
make build
```

A partir de ahí, para arrancar reutilizando esas imágenes:

```bash
make up
```

| | URL |
| -- | -- |
| Aplicación | <http://localhost:8080> |
| Swagger — plan B declarado de la demo | <http://localhost:8000/docs> |

`make build` y `make up` detectan el hardware (NVIDIA → AMD → CPU) y levantan los cuatro
contenedores; la diferencia es que `make build` reconstruye las imágenes de backend y frontend y
`make up` reutiliza las ya construidas (por eso, sin haberlas construido antes, `make up` intenta
descargarlas y falla). `make help` lista el resto. **El primer arranque descarga ~5,8 GB**
(modelo + embeddings) y tarda 15–30 min; los siguientes, menos de un minuto. Componer, firmar, leer la
bitácora y el delta regional funcionan **sin IA**: lo único que espera al modelo es leer una
descripción.

## Probar la aplicación

Una sola vista, cinco pasos: **describir → revisar → elegir → comparar → firmar (con registro)**. Hay
cinco descripciones de ejemplo, de cinco sectores distintos, listas para pegar, y una guía de cómo
recorrerlas: **[docs/demo-playbook.md](docs/demo-playbook.md)**.

## API

Superficie **cerrada**: siete endpoints declarados como dato en `server/app/api/router.py`, y una
prueba (`tests/api/test_surface.py`) falla si aparece uno de más.

| Endpoint | Función |
| -- | -- |
| `POST /asset/parse` | Texto libre → borrador de `AssetProfile`, revisable |
| `POST /candidates` | Perfil → opciones equivalentes por capacidad y zona |
| `POST /baseline/compose` | Elecciones del humano → línea base firmada |
| `GET /baseline/{id}/audit-log` | Trazabilidad completa, con verificación de la cadena |
| `GET /baseline/{id}/statement` | Declaración de aplicabilidad (`?format=soa\|oscal`) |
| `POST /delta` | Delta regional para una zona del perfil |
| `GET /baselines` | Líneas base firmadas, de la más reciente a la más antigua |

## Más

Reglas del proyecto, invariantes, arquitectura, reproducibilidad por ruta de hardware y
convenciones de trabajo: **[CLAUDE.md](CLAUDE.md)**.

Anexos del trabajo de fin de máster, con el mapa que lleva de cada referencia `[A-N]` de la
memoria a la ruta donde el material vive: **[docs/anexos/README.md](docs/anexos/README.md)**.
