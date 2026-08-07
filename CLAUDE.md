# Multi-Framework Harmonization Engine — TFM POC

POC for the TFM (Máster en Ciberseguridad UCM). Assists a critical-infrastructure operator
(gas pipeline / ACP context) in the **sovereign composition** of the cybersecurity baseline of an
OT/IT/hybrid asset. Local AI parses the asset description and retrieves candidate controls (RAG);
a **deterministic core** maps, resolves conflicts, applies gating and prioritizes; the **human
composes and signs** the final baseline with an end-to-end traceable audit log.

Linear project: [TFM](https://linear.app/checkpoint-std/project/tfm-5febd8144146) · team **Maestría UCM** (issues `UCM-*`).

## Invariants (non-negotiable — enforce in every change)

1. **AI suggests/retrieves · rules decide · human composes and signs.** The LLM never decides,
   ranks, or filters; it only parses (with human review) and explains (P1, presentational only).
2. **Nothing is restricted or silently dropped.** Silent omissions target = **0** (measured
   invariant). Required capabilities without candidates are surfaced as explicit gaps, never
   swallowed. RAG only *widens* coverage, never restricts it.
3. **Reproducibility is total**: LLM at **temp 0 + fixed seed**, pinned model
   (`qwen2.5:7b-instruct-q4_K_M`, real fallback `qwen2.5:3b` for 8 GB machines), versioned
   catalog/mappings, `docker compose up` must produce the same result on a foreign 8–16 GB machine.
4. **Closed API surface — exactly 5 endpoints** (see M3). Any additional endpoint is scope creep
   unless justified in writing.
5. **The audit log is append-only** (`AuditEvent`, SQLite) and is the *only* mutable state.
   Every decision — engine or human — records actor (`engine|human`), what, why, when.
6. **Cut rule**: if time runs short, cut UI, never engine logic. Declared plan B: demo via
   API/Swagger.
7. **Catalog IP rule**: `FrameworkControl` descriptions are **paraphrased, never verbatim** from
   the standards (CSF 2.0, IEC 62443-3-3, CIS v8, NIS2, IMO MSC.428(98)).
8. **Language rule**: everything authored for developers is **English** — identifiers, schema
   field names, code comments, docstrings, config/`.env` comments. Only text an end user reads is
   **Spanish**: catalog content and audit-log `decision`/`rationale` strings.
9. **The golden baseline (ground truth) is an external measuring instrument** — the engine must
   never read or use it (`UCM-5`, evaluated in `UCM-18`).

## Architecture & stack

```
client/   React + Vite + TypeScript (Bun) — single-view sovereign-composition UI (built LAST, M5)
server/   FastAPI + Python 3.12 (uv) — engine core, API, audit log
  app/<feature>/          feature modules: schemas.py, router.py, service.py, repository.py, models.py
  app/core/               config, database (SQLAlchemy async + SQLite), middleware, exceptions
  app/catalog/            versioned read-only catalog (loader + Pydantic schemas)
  data/catalog/           catalog.v<semver>.json (manifest) + v<semver>/<framework>.json sources
                          frozen in Git, never mutated in place (bump version)
  tests/                  pytest (asyncio_mode=auto), mirrors app/ layout
```

Planned services (M2/M5): **Ollama** (qwen2.5 7B Q4_K_M), **Qdrant** (populated from the catalog
at startup, payload-filtered by jurisdiction/zone/mapping type), embeddings **multilingual-e5-base
on CPU**. Final deployment: docker compose with 4 containers (frontend, backend, ollama, qdrant);
the ~4.7 GB model is pulled at first start (documented entrypoint), never baked into the image.

Pydantic models are simultaneously: catalog schema, API contract, and LLM output type (`UCM-7`).
Core schemas (§7.3): `Capability`, `FrameworkControl` (with `jurisdiction`, `strength`),
`Mapping` (typed `total|partial|compensatory|contextual` + `coverage_weight` + provenance
`official_crosswalk|author_judgment` with jurisdiction), `AssetProfile`, `GatingRules`,
`Baseline`, `AuditEvent`.

## Engine rules (M1 — deterministic core, no AI)

Pipeline: **mapping → conflict resolution → gating → prioritization**. Must run end-to-end with
the 2 hand-written profiles (no AI) and be validated before starting M2.

- **Conflict resolution** (`UCM-8`) — three situations, never "most restrictive wins":
  - Overlap → collapse per capability.
  - Granularity (1:N) → coverage weights, flag gaps.
  - Real contradiction → precedence by context/zone (ICS→OT, NIST→IT) + OT-safety override;
    real conflicts are surfaced to the human.
  - Resolution must be **ingestion-order independent** — prove it with tests.
- **Gating** (`UCM-9`) — three outcomes for controls without equivalent:
  *no-aplica* (justified exclusion — a deliverable, not a gap), *objective-without-mechanism*
  (compensatory control), *wrong-scope* (deferred to organizational layer). Golden rule: gating
  removes **mechanisms**, never required **capabilities**, and never silently. Same catalog +
  per-zone gating ⇒ different baselines.
- **Prioritization** (`UCM-10`) — never rank everything together:
  - **Tier 0**: mandatory by the zone's SL-target — not prioritized, must be complete.
  - **Tier 1**: discretionary — coverage/leverage + dependencies (partial order) + ordinal cost.
  - Gordon-Loeb in spirit with **ordinal scales, no fake numbers** (declaring this is rigor).
    CIS IGs (IG1/2/3) reused as ready-made IT prioritization. Output: phased roadmap.

## AI layer rules (M2)

- Parse (`UCM-12`): Pydantic AI + Ollama, temp 0 + fixed seed, structured output validated with
  Pydantic, retry on format failure. Operator reviews/corrects the profile (human-in-the-loop);
  last-resort fallback: hand-editable profile in the UI.
- RAG (`UCM-13`): Qdrant populated from the catalog JSON at startup; retrieval with payload
  filtering (jurisdiction, zone, mapping type). e5-base embeddings on CPU (~1.1 GB, no GPU).
- LLM candidate explanations (`UCM-14`) are P1 and strictly presentational — they never alter
  ranking or selection.

## API surface (M3 — closed, 5 endpoints)

| Endpoint | Function |
| -- | -- |
| `POST /asset/parse` | Free text → `AssetProfile` |
| `POST /candidates` | Profile → side-by-side options per capability |
| `POST /baseline/compose` | Human choices → signed baseline (verify **Tier 0 complete** before signing; log every choice + reason) |
| `GET /baseline/{id}/audit-log` | Full traceability |
| `POST /delta` | Regional delta for one zone of the asset (`regions: [US, EU]`, `profile` inline or `profile_id`; one zone only; N regions = declared future work) |

Sovereign composition (`UCM-16`) is the **central contribution**: equivalent options side by side
(framework, jurisdiction, strength/SL, tier); the human chooses per zone and signs. Differentiator
vs. a crosswalk: a crosswalk *translates* (A≈B); this engine *advises the selection*.

## Evaluation rules (M4)

Engine vs. hand-made golden baseline for both profiles (`UCM-18`): RAG recall (reported honestly,
analyze every miss), silent omissions (**must be 0**), gating precision vs. expert, suggestion
acceptance rate, regional delta demonstrated in 1 zone. Genericity demo (`UCM-19`): third asset
live — candidates where covered, explicit gaps where not ("admite ≠ sabe"; extending coverage =
adding JSON + repopulating Qdrant, configuration not redesign).

## Delivery constraints (M5–M6)

- `docker compose up` = full system; complete `requirements.txt`/lockfiles and documented
  versions/env vars (explicit TFM-guide requirement). Reproducibility verified on a foreign
  machine **before** submission (`UCM-22`), including the real 3B fallback on 8 GB.
- Memoir ≤ 20 pages (7-section plan), video ≤ 5 min MP4/MKV, annexes (code, mapping tables with
  jurisdiction, gating rules, data-model schema, profiles, UI captures). Repo must be accessible
  to tutors Prof. Domínguez Gómez and Prof. Ramírez Giménez. No topic changes < 15 days before
  submission. Delivery zip: `Nombre_Apellido1_Apellido2_Titulo.zip`.

## Workflow conventions

- **Branches**: `feature/UCM-<n>_<short-slug>` (e.g. `feature/UCM-7_data-model`), from `main`.
  One Linear issue per branch; move the issue through Linear states as work progresses.
- **Commits**: Conventional Commits with the issue as scope — `feat(UCM-7): …`, `test(UCM-8): …`,
  `chore: …` for issue-less housekeeping.
- **Order of work** follows the PRD steps: M1 core (no AI) → M2 AI layer → M3 composition + API →
  M4 evaluation → M5 UI/compose → M6 memoir & delivery. Do not start a milestone before the
  previous one's validation gate (e.g. core validated with both hand-made profiles before M2).
- **Catalog changes** = new `catalog.v<semver>.json` + `CATALOG_PATH` bump; never edit a shipped
  catalog version in place. From v0.2.0 the catalog is a **manifest + one source file per
  framework** (`sources`, resolved relative to the manifest): the manifest keeps what is
  framework-neutral (version, notes, capabilities), each source the controls of one framework and
  the mappings reaching them. The version of record is the manifest's — touching any source bumps
  it, and a bump copies the whole source directory. A source file is not independently valid: the
  loader merges first and `Catalog` validates the whole.

## Commands

```bash
# whole system (from the repo root) — detects the GPU, waits, verifies where the model landed
./scripts/start.sh      # .\scripts\start.ps1 on Windows
./scripts/start.sh --cpu    # force the portable path (the reproducible one)
./scripts/start.sh --down   # stop; volumes are kept

# server (from server/)
uv sync                 # install deps
uv run uvicorn app.main:app --reload
uv run pytest           # tests
uv run ruff check .     # lint (line-length 100, py312)
uv run mypy app         # types

# client (from client/)
bun install
bun run dev             # Vite dev server (http://localhost:5173)
bun run build
```
