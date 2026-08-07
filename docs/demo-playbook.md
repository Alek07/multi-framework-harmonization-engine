# Demo playbook

How to run the demo, five descriptions to run it with, and what each one produced when it was
actually run — so a live run can be *evaluated* rather than merely watched.

The five assets are deliberately from five different sectors — **gas**, **electricity**,
**ports/maritime**, **food & beverage**, **water**. Only the first is the ACP pipeline case the
catalog was written around; the other four are there to test the claim that the engine reads
declared premises, not the vocabulary of an industry.

Everything in the "what to expect" sections is **measured**, not predicted. It was produced on
2026-08-05 against `catalog 0.2.0` · `rules 0.1.0` · `gating 0.2.0` · `prioritization 0.2.0` ·
`prompt 0.3.0` · `qwen2.5:7b-instruct-q4_K_M` (digest `845dbda0…`) · `temp 0` · `seed 42`, on the
**GPU path** (model fully resident: `size_vram == size`). Deterministic numbers — capabilities,
exclusions, gaps, tiers, delta — are reproducible on any path. LLM timings are not: the CPU path
costs roughly 2–4× more per parse, and a cold model adds ~185 s to the first one.

---

## 1. Pre-flight

Start in this order. Each step has a check; do not move on until it answers.

**Packaged — the one the tutors run** (four containers, one command; see
[README](../README.md)):

| # | Command (from repo root) | Check | Expected |
| - | - | - | - |
| 1 | `.\scripts\start.ps1` (or `./scripts/start.sh`) | its own output | all four `listo`, then a `Verificado` line |
| 2 | — | that `Verificado` line | `residente en GPU: … (100 %)`, or `en CPU` — know which you are on |
| 3 | — | `curl localhost:6333/collections` | a `catalog_v0_3_0_*` collection exists |
| 4 | — | open `http://localhost:8080` | step 1 renders, no "Servicio no disponible" |

The launcher waits for all four services and preloads the weights, so when it prints `Listo` the
stack really is ready — including the model, which is the part that used to be paid by whoever
clicked first. On the CPU path expect a parse to take ~6 min; on GPU, ~30 s.

On a **first** start, this includes ~5.8 GB of model downloads and takes 15–30 min. Do that the day
before, not with the camera rolling.

**Native — for development**, the two halves outside the containers:

| # | Command (from repo root) | Check | Expected |
| - | - | - | - |
| 1 | `docker compose up -d ollama qdrant` | `docker compose ps` | `ollama` and `qdrant` healthy |
| 2 | `cd server && uv run uvicorn app.main:app` | `curl localhost:8000/api/v1/health` | `{"status":"ok"}` |
| 3 | `cd client && bun run dev` | open `http://localhost:5173` | as above |

Notes worth having in your head before you present:

- **Warm the model before the camera rolls.** Step 1 preloads it and the backend preloads it again
  (`LLM_WARM_ON_STARTUP`), but if the machine has been idle past `OLLAMA_KEEP_ALIVE` (30 min), the
  first parse pays the reload. Run any parse once as a warm-up.
- **A `.env` is optional on either path.** Every value has a default — in `app/core/config.py` for
  the backend, in `docker-compose.yml` for the packaged stack; the run below used none at all.
- **Turn the explanation layer off for the demo** — see [§6, known risks](#6-known-risks-before-you-present).
  `EXPLAIN_ENABLED=false` in the root `.env` and `docker compose up -d` (packaged), or in
  `server/.env` and restart the backend (native).
- **Plan B is Swagger** (`http://localhost:8000/docs`), and it is a declared plan B, not an excuse.
  The five endpoints are all reachable there; compose and delta work with Ollama and Qdrant off.

### Degraded modes worth showing on purpose

| Turn off | What happens | Measured |
| - | - | - |
| Qdrant | `retrieval.status = "unavailable"`, deterministic candidates unchanged | — |
| RAG (`retrieval: false` in the request) | `status = "disabled"` + notice; catalog candidates intact | 0.8 s vs ~5 s per zone |
| Ollama | parse unavailable → operator fills the form by hand ("prefiero rellenar la ficha yo mismo"); compose, sign, audit and delta all still work | — |

That last row is the strongest reproducibility claim in the demo: **composing and signing needs no
AI at all.**

---

## 2. The arc — five stages, and what each one is for

| Stage | On screen | The sentence to say |
| - | - | - |
| 1 · Describir | free text → draft + evidence per field | "The model extracts and cites; it decides nothing. What it could not place is listed, not dropped." |
| 1b · Revisar | every field editable, `◆` marks your corrections | "What is computed is *my* sheet, not the model's. And it will not let me continue while a value is missing — a target SL nobody chose would produce a baseline nobody chose." |
| 2 · Elegir | equivalent options side by side per capability + what gating removed and why | "This is the contribution. A crosswalk *translates* A≈B; this advises the selection — framework, jurisdiction, strength, tier — and I choose per zone." |
| 3 · Comparar | one zone read under US and +EU | "Cumulative readings, never a parallel catalogue. What changes here is legal obligation, not mechanism — and saying so is the result." |
| 4 · Firmar | Tier 0 verified, then signature | "Nothing mandatory reaches a signed baseline without a name on it: chosen, compensated, gap accepted in writing, or ratified." |
| 5 · Registro | append-only trail, chain verified | "Engine and human events in one chain, each verified against its SHA-256 and the previous one." |

---

## 3. What every run produces, whatever you describe

Learn these numbers; they are the baseline against which each example's *differences* are the
interesting part. Per **zone**, on catalog v0.2.0 — confirmed identical across all five assets:

- **37 capabilities**, always. Gating never removes a capability.
- **263 catalog options** offered, plus **451 RAG suggestions** (714 total), **0 set aside**.
- **91 `wrong_scope` exclusions**, always, from the 10 organizational rules
  (`GATE-SCOPE-GOVERNANCE` 21, `GATE-SCOPE-LEGAL-OBLIGATION` 21, `GATE-SCOPE-SUPPLY-CHAIN` 15,
  `GATE-SCOPE-INCIDENT-ORGANIZATION` 9, `GATE-SCOPE-RISK-PROGRAM` 8, `GATE-SCOPE-IMPROVEMENT` 6,
  `GATE-SCOPE-AWARENESS` 4, `GATE-SCOPE-PHYSICAL-SECURITY` 3, `GATE-SCOPE-DATA-GOVERNANCE` 3,
  `GATE-SCOPE-SECURE-DEVELOPMENT` 1). These are the asset/organization boundary and do not depend
  on the asset — say so before someone reads it as a bug.
- **6 declared gaps**, `residual_coverage` 0.9/0.1: `CAP-PR-CRYPTO`, `CAP-PR-MALWARE`,
  `CAP-PR-MEDIA`, `CAP-PR-MFA`, `CAP-PR-PAM`, `CAP-PR-REMOTE`.
- **5 outstanding Tier 0 mandates** the engine refuses to close alone: the six above minus
  `CAP-PR-PAM`. Signing before closing them is rejected.
- **Tier 0 = 30 capabilities at SL 3, 29 at SL 2**; the rest is Tier 1 in 3 phases.

What *does* move with the asset: `not_applicable` and `objective_without_mechanism` exclusions,
open contradictions, extra gaps, and the zone's domain/safety reading. Two shapes recur, and it is
worth naming them early because four of the five examples are one or the other:

| Zone shape | Exclusions | Reading |
| - | - | - |
| Embedded, unattended, no office surface | **119–120** (91 scope + ~16 n/a + ~13 owm) | 13 embedded rules fire |
| Windows, interactive users, office surface | **91–92** (scope, plus the OT patch rule if safety-relevant) | no embedded rule applies |

---

## 4. The five examples

Each one: paste the Spanish text into step 1, press **Analizar la descripción**, then read the
"expect" block. The `parse` time is the wall clock of `POST /asset/parse` on the GPU path.

### Example 1 — Gaseoducto · gas transport (the headline: two zones, pure OT, the SIS)

> Corredor OT de un gasoducto de transporte. En el nivel 1 hay controladores PLC que gobiernan las
> válvulas de corte y la regulación de presión a lo largo de la línea, y están conectados en red con
> el SCADA supervisorio del nivel 2. Exigimos nivel de seguridad objetivo 3 en esa zona. Nadie
> trabaja delante de esos controladores: no hay usuarios interactivos ni puestos de trabajo, el
> equipo es embebido y no tiene sistema operativo de propósito general, ni correo ni navegador.
>
> Aparte, en su propia zona, está el sistema instrumentado de seguridad (SIS) que ejecuta la parada
> de emergencia. Es la joya de la corona del activo y también le exigimos nivel 3. Su función de
> seguridad no se modifica dentro de este alcance. Tomamos TRITON/TRISIS como referencia de amenaza.
>
> El paso hacia la IDMZ no admite ruta directa entre OT e IT. Si alguien manipulase la presión de la
> línea, la consecuencia sería sobrepresión, rotura y fuga de gas. El mantenimiento del corredor lo
> hace el fabricante dos veces al año en ventana de parada.

**Expect — parse (20 s, 1 attempt).** `PURE_OT`, 2 zones: `Z-CONTROLADORES` (L1, SL 3) and `Z-SIS`
(L1, SL 3), both embedded / no interactive users, `reference: TRITON/TRISIS`, physical consequence
extracted, 11 evidence notes, 3 statements in `unmapped` (the IDMZ rule, the threat reference, the
maintenance window). **4 fields in `missing_required`** → step 2 stays locked until you fill them:
`office_it_surface` on both zones, the conduit's control, and `criticality.scale`.

**Expect — four misses, and they are the argument, not the defect:**
1. `office_it_surface` comes back **null in both zones** even though the text says "ni correo ni
   navegador" — and the model still writes a *note* about it. Correct it in two clicks; that is
   human-in-the-loop working, not failing.
2. `Z-SIS.networked = false`, justified with a fragment that talks about interactive users. Wrong.
   Correct it.
3. `safety_out_of_scope = true` on **both** zones; the sentence only concerns the SIS. Correctable
   through the API but **not through the UI** (see §6).
4. `role` comes back `"control"` / `"safety"` — **not `crown_jewel`**. This matters: see below.

**Expect — engine, per zone** (identical for both zones, because their premises are identical):
120 exclusions = 91 `wrong_scope` + 16 `not_applicable` + 13 `objective_without_mechanism`, 24
rules fired, 6 gaps, 30 Tier 0 / 7 Tier 1, **1 open contradiction** the engine refuses to settle:
`CAP-PR-MFA` between `CTL-CIS-0605`, `CTL-IEC-SR113`, `CTL-IEC-SR17`. Both zones read
`domain=OT, safety_relevant=true`.

**Expect — the crown-jewel contrast** (needs `role: "crown_jewel"` on `Z-SIS`, so run it through the
API): 127 exclusions instead of 120. Four SIS-specific rules fire —
`GATE-NA-SIS-REMOTE-PATH` (4), `GATE-OWM-SIS-PATCH-IN-OPERATION` (2),
`GATE-NA-SIS-CONTINUOUS-MONITORING-AGENT` (2), `GATE-NA-SIS-PORTABLE-MEDIA` (1) — one capability
turns `compensatory_required`, and a **7th gap** appears: `CAP-PR-PATCH`, `partial_only`,
coverage 0.5. This is the cleanest demonstration in the whole POC that one declared premise changes
the baseline, with a written reason for every removal.

**Expect — compose and sign** (measured end to end):
- Signing with the mandates open → **HTTP 409**, naming all 10 (5 per zone) and the three ways to
  close each: *«eligiendo un mecanismo, declarando un control compensatorio o aceptando el hueco por
  escrito»*.
- With the 10 decisions → **HTTP 201**. Per zone: 30 capabilities, 5 chosen, **17 ratified**, 0 gaps
  accepted.
- Audit log: **631 events, 570 engine + 61 human**, chain `valid: true`. Human event types:
  `option_selected` 10, `mechanism_ratified` 50, `baseline_signed` 1. Point at `mechanism_ratified`
  and say why it exists: ratifying is not choosing, and the ledger will not claim a choice nobody
  made.

---

### Example 2 — Subestación eléctrica · electricity transmission (hybrid, and the regional delta)

> Puesto de operación e ingeniería de una subestación eléctrica de transporte de 220 kV, en el nivel
> 3 de la red de la subestación. Es un equipo Windows desde el que se parametrizan y se cargan los
> ajustes de las protecciones IEC 61850 de las posiciones. Trabajan personas delante de él, tiene
> correo corporativo y navegador, está en el dominio de la empresa y se usan memorias USB para llevar
> informes. Le exigimos nivel de seguridad objetivo 3.
>
> La carga de ajustes hacia la red de posiciones pasa mediada por una zona desmilitarizada. El
> fabricante de las protecciones entra en remoto para mantenimiento a través de un equipo de salto
> con doble factor y la sesión queda grabada.
>
> Este puesto no maniobra directamente, pero si lo comprometen se puede llegar a las protecciones y
> provocar la apertura indebida de interruptores y un cero de tensión en la zona. Usamos MITRE ATT&CK
> for ICS como modelo de amenaza y el apagón de Ucrania de 2016 como referencia. Estamos sujetos a la
> directiva NIS2 en España.

**Expect — parse (15 s).** The cleanest of the five: `HYBRID_IT_OT`, 1 zone
`Z-OPERACION_INGENIERIA` (L3, `north_of_idmz`, SL 3), **all five premises answered** — four
`stated`, `hybrid_it_ot` correctly `inferred` — plus `consequence_path` (*manipulación de
protecciones IEC 61850*) and `attack_reference` (*apagón de Ucrania de 2016*). Only **2 missing**
(the conduit's control and `criticality.scale`), 2 statements in `unmapped`: the vendor's remote
jump host and the threat-model sentence, neither of which any field holds.

**Expect — two cosmetic misses worth naming as you go:** the conduit gets the invented id
`C-DESALERTIFICACION` (a non-word derived from "desmilitarizada"), and `reference` on the zone holds
*«directiva NIS2 en España»*, which is a regulatory subjection rather than an incident reference.
Neither reaches the engine as a premise; both are the kind of thing the review stage exists to catch.

**Expect — engine.** `domain = HYBRID` (Purdue L3 *with* hybrid nature), `safety_relevant = false`,
**91 exclusions — `wrong_scope` only**, no embedded rule fires, 6 gaps, 30 Tier 0 / 7 Tier 1,
**0 open decisions**. The derivation string on screen says exactly which rule read it that way.

**Expect — the premise-flip, live.** Toggle `hybrid_it_ot` to *no* in step 1b and recompute step 2:

| `hybrid_it_ot` | domain | safety_relevant | exclusions | open decisions |
| - | - | - | - | - |
| `true` (as parsed) | **HYBRID** | false | 91 | 0 |
| `false` | **OT** (L3 without hybrid nature) | true (catastrophic OT consequence) | 92 (+`GATE-OWM-PATCH-CADENCE-SAFETY-OT`) | **1** — the `CAP-PR-MFA` contradiction |

One premise, a different reading of the zone, the OT safety override switching on, and a
contradiction the engine escalates instead of settling. This is the "same catalogue, different
answer" claim in its smallest form.

**Expect — regional delta** (step 3, `US → +EU`): **16 of 37 capabilities change, 0 regional gaps.**
All 16 change by *adding obligation without moving coverage*: `CAP-GOV-OVERSIGHT`, `-POLICY`,
`-RISK`, `-ROLES`, `-SUPPLY`, `CAP-ID-ASSET`, `CAP-ID-THREAT`, `CAP-PR-ACCESS`, `-AWARENESS`,
`-BACKUP`, `-CRYPTO`, `-MFA`, `-PATCH`, `CAP-RC-RECOVER`, `CAP-RS-IR`, `CAP-RS-REPORT`. The one to
open on camera is `CAP-RS-REPORT`: US offers 4 controls and sets `CTL-NIS2-A23` aside *by name*;
+EU offers the same 4 plus that one — *«obligación legal (24h/72h/1 mes)»*. Common ground (`INTL`,
`INTL-MARITIME`) appears in both readings.

---

### Example 3 — Terminal de contenedores · ports & maritime (genericity: "admite ≠ sabe")

> Terminal de contenedores. La zona de patio controla las grúas pórtico de muelle y los sistemas de
> posicionamiento y anticolisión con PLC dedicados en nivel 1, sin sistema operativo corriente y sin
> nadie sentado delante; están en red con el sistema de gestión del terminal. Le exigimos nivel de
> seguridad objetivo 3.
>
> Durante la escala se conecta el enlace buque-tierra con el portacontenedores: se intercambian datos
> de estiba y de carga con el sistema de a bordo, que está fuera de nuestra administración y se rige
> por el sistema de gestión de la seguridad del buque bajo la resolución MSC.428(98) de la OMI.
>
> Un fallo de la anticolisión con la grúa en movimiento provocaría el vuelco de la carga y
> aplastamiento en el muelle. El terminal está en la UE y le aplica la NIS2. El código PBIP/ISPS ya
> cubre la seguridad física del recinto.

**Expect — parse (8 s).** 1 zone `Z-PATIO` (L1, SL 3, embedded, no interactive users),
`HYBRID_IT_OT`, the crushing consequence extracted. **4 missing.** The statements the schema cannot
hold — the ship-to-shore link with its IMO regime, and NIS2 + ISPS — land in `unmapped`, verbatim.
That is the invariant working: an asset the catalog was not written around does not lose statements
silently.

**Expect — one real miss to point at:** only **1 evidence note** for 5 filled fields. The prompt asks
for one note per non-null value and the 7B skipped four of them. Nothing was invented and nothing was
dropped, but the justification column is incomplete — worth saying out loud, because the honest
version of this demo names its gaps.

**Expect — engine.** Numerically **identical to the gas corridor**: 120 exclusions, the same 24
rules, 6 gaps, 30 Tier 0, and the same single `CAP-PR-MFA` contradiction. Do not apologise for that
— it *is* the genericity claim. The engine conditions on declared premises (embedded, unattended,
networked, SL 3, catastrophic consequence), not on the vocabulary of an industry, so a quay crane
PLC and a pipeline PLC get the same reading because they *are* the same reading.

**Expect — where the maritime layer actually shows up:** in the options, not in the gating. The
zone's 263 catalog options break down as **US 178 · INTL 58 · INTL-MARITIME 8 · EU 19**, and IMO
controls appear in 8 capabilities — `CAP-GOV-RISK`, `CAP-ID-ASSET`, `CAP-ID-RISK`, `CAP-PR-ACCESS`,
`CAP-DE-MONITOR`, `CAP-RS-IR`, `CAP-RC-RECOVER`, `CAP-RS-REPORT` — as `CTL-IMO-42898` (MSC.428(98))
and the five `MSC-FAL.1/Circ.3 §3.5.x` functional elements. Open `CAP-RS-REPORT` and show
MSC.428(98) sitting beside CSF and NIS2.

**Say the limit out loud:** there is no maritime *gating* rule, and the ship-to-shore link is not a
premise the engine can read — gating cannot condition on conduits, a declared limitation of
`gating.v0.2.0`. Extending coverage is JSON plus a Qdrant repopulate: configuration, not redesign.
"Admite" — yes. "Sabe" — not yet, and the run says which.

---

### Example 4 — Línea de embotellado · food & beverage (the engine refusing to invent)

> Tenemos una línea de embotellado con un autómata y un panel de operador. Queremos protegerla mejor.

**Expect — parse (8 s).** `PURE_OT`, and the model correctly splits **two zones**
(`Z-EMBOTELLADO_AUTOMATA`, `Z-EMBOTELLADO_PANEL_OPERADOR`) with the one premise each half of the
sentence supports: the automaton is not general-purpose, the operator panel is and has interactive
users. Everything else is **null**: no target SL, no criticality at all.

**Expect — the point of the example: 10 entries in `missing_required`,** listed by name on screen,
and step 2 **locked**. Two `target_sl`, five `nature` premises, and all three `criticality` fields.
Read the notice aloud — *«No se ponen valores por defecto a propósito: un nivel de seguridad que
nadie ha decidido produciría una línea base que nadie ha decidido»*. A helpful model would have
guessed SL 2 here; this one leaves it empty and asks.

**Expect — one bad note.** `general_purpose_os` on the automaton is `inferred` with the evidence
«Queremos protegerla mejor.» — a fragment that supports nothing. The evidence column is what lets
you catch that in one second, which is the whole reason it exists.

**Expect — after filling it in by hand** (SL 2 on both, consequence `moderate`): 29 Tier 0 / 8 Tier 1
per zone, **0 open decisions** (no catastrophic consequence ⇒ no OT safety override ⇒ the MFA
contradiction does not arise), and the two zones diverge — 119 exclusions on the embedded zone
against 92 on the operator panel. Note this is also the only example with **no conduits at all**;
the UI says so in words rather than inventing one.

---

### Example 5 — Planta potabilizadora · water (two zones, two baselines, one catalogue)

> Planta potabilizadora de agua. Tiene dos partes bien distintas.
>
> La zona de proceso, en nivel 1: PLC embebidos que gobiernan las bombas de captación y la
> dosificación de cloro. No llevan sistema operativo corriente, no hay nadie trabajando delante de
> ellos y no tienen correo ni navegador. Están en red con la sala de control. Nivel de seguridad
> objetivo 3.
>
> La sala de control, en nivel 2: un servidor Windows con el histórico y dos puestos de operador donde
> el personal de turno entra con su usuario del dominio de la empresa, consulta el correo y saca
> informes en memorias USB. Nivel de seguridad objetivo 2.
>
> Si la dosificación de cloro se altera se contamina el agua de abastecimiento de la ciudad. La sala
> de control tiene salida a la red corporativa a través de una zona desmilitarizada.

**Expect — parse (13 s), and this is the one that shows prompt 0.3.0 earning its version bump.** Two
zones, each with **its own** premises, **its own** target SL and even its own side of the IDMZ, never
copied across:

| zone | purdue | position | SL | `general_purpose_os` | `interactive_users` | `office_it_surface` | `hybrid_it_ot` |
| - | - | - | - | - | - | - | - |
| `Z-PROCESO` | L1 | north | 3 | false | false | *null* → you fill it | false |
| `Z-SALA_CONTROL` | L2 | south | 2 | true | true | true | true |

7 evidence notes, **4 missing**, 2 statements in `unmapped`. One note is worth pausing on:
`Z-SALA_CONTROL.networked` is justified with «Nivel de seguridad objetivo 2.», a fragment that says
nothing about connectivity. The value is right and the evidence is wrong — exactly what the
`stated`/`inferred` column plus the quoted fragment are there to expose.

**Expect — engine: same catalogue, two different baselines.**

| | `Z-PROCESO` | `Z-SALA_CONTROL` |
| - | - | - |
| domain / SL | OT / 3 | OT / 2 |
| Tier 0 · Tier 1 | 30 · 7 | 29 · 8 |
| exclusions | **120** (91 scope + 16 n/a + 13 owm) | **92** (91 scope + 1 owm) |
| embedded rules fired | 13 | 0 |
| roadmap phases | 30 / 3 / 3 / 1 | 29 / 3 / 4 / 1 |

Both zones keep all 37 capabilities and all 6 gaps, and both are `safety_relevant` (the chlorine
consequence is catastrophic and both zones are OT), so each carries the same single `CAP-PR-MFA`
contradiction. Say the golden rule while both columns are on screen: *gating removes mechanisms,
never capabilities, and never silently.*

---

## 5. Evaluation sheet

One row per zone per run. The first six checks should match §3 exactly on any asset; a deviation is
either a finding or a bug, and both are worth the pause.

| Check | Expected | Observed |
| - | - | - |
| Capabilities offered | 37 | |
| Silent omissions | **0** (every empty capability declares a gap) | |
| `wrong_scope` exclusions | 91 | |
| Declared gaps | 6 (+1 if `crown_jewel`) | |
| Outstanding Tier 0 | 5 per zone | |
| Tier 0 size | 30 at SL 3 · 29 at SL 2 | |
| Zone shape vs. §3 table | 119–120 embedded · 91–92 Windows | |
| Premises the parse got right | count of `stated`/`inferred` you did **not** correct | |
| Premises you corrected (`◆`) | the human-in-the-loop measure — 0–4 is normal | |
| Statements dropped entirely | **0** (each one is in a field or in `unmapped`) | |
| Filled fields with no evidence note | example 3 has 4; example 2 has 0 | |
| Notes with unsupportive evidence | examples 1, 4 and 5 have 1 each | |
| Gating outcomes vs. your own judgement | rule id by rule id | |
| Sign attempt with mandates open | 409 naming every one | |
| Chain verification | `valid: true` | |
| Parse wall clock | 8–20 s GPU · ~2–4× on CPU | |
| `/candidates` wall clock | ~5–7 s per zone with RAG · ~0.8 s without | |

The two rows that carry the TFM's claims are **silent omissions = 0** and **statements dropped = 0**.
Everything else is quality; those two are the invariant.

---

## 6. Known risks before you present

1. **The explanation layer can return HTTP 500 — turn it off for the demo.** Measured on two
   different profiles: requesting an explanation for `CAP-DE-LOG` failed with `Internal Server Error`
   after ~35 s on both the substation and a pipeline workstation profile, as did `CAP-PR-REMOTE` and
   `CAP-PR-SEGMENT`; `CAP-PR-BACKUP` succeeded both times (21 explanations, ~38 s). Cause: when the
   model returns an explanation with an empty `basis`, `screen()` lets it through and
   `CandidateExplanation`'s own validator rejects it — from inside `_assemble`, which is *outside*
   the broad `except` in `app/explain/service.py:115` that exists precisely to make this cost only
   the paragraph. The whole `/candidates` request dies with it. Set `EXPLAIN_ENABLED=false` until it
   is fixed; the candidates and their deterministic justifications are unaffected either way.
2. **`role` is not editable in the UI.** `StageAsset` exposes name, case, zones, SL vector, the five
   premises, criticality and conduits — but not `role`, and the parse does not emit `crown_jewel`.
   So the four SIS rules are unreachable from the browser. Demo that contrast through Swagger or a
   `curl` against `/candidates` with `role: "crown_jewel"`, or expect the question from a tutor.
   Same applies to `safety_out_of_scope`.
3. **`POST /delta`, not `GET`.** The README still documents `GET /delta?...`; the endpoint moved to
   `POST` with `{profile|profile_id, zone_id, regions}` (see the header of `app/delta/router.py`).
   Fix the README before submission — a tutor reading it will try the GET.
4. **The README's "5 of 24 capabilities change" is a v0.1.0 number.** Under catalog v0.2.0 both the
   frozen `PROFILE-B` / `Z-ENG-STATION` zone and the substation above measure **16 of 37**. The
   *conclusion* is unchanged and still stands — all 16 add obligation without moving coverage — but
   the figures need updating wherever they are quoted, memoir included.
5. **The 7B is not deterministic across hardware paths.** Do not record the video on one path and
   report evaluation numbers from the other. Name the path in the memoir.

---

## 7. Fast recovery, live

| Symptom | Move |
| - | - |
| "Servicio no disponible" full-screen | backend is down; restart uvicorn, the UI's Reintentar picks it up. Nothing is lost — nothing is saved until you sign. |
| Parse spins for minutes | model was evicted and is reloading (~185 s). Say so; the working panel already explains it runs locally. |
| Parse returns nonsense for a zone | intended path: correct it in step 1b and point at the `◆`. This is the human-in-the-loop argument, so use it rather than re-running. |
| 500 on step 2 | almost certainly the explanation layer (§6.1). Restart with `EXPLAIN_ENABLED=false`. |
| Step 2 button locked | `missing_required` is non-empty; the missing fields are listed by name at the bottom of step 1b. |
| Signing rejected (409) | read the message aloud — it names every open mandate. Close them and sign again. |
| Qdrant down | keep going; `retrieval` reports `unavailable` and the P0 candidates are all there. |
| Everything is on fire | Swagger at `/docs`, `POST /candidates` with `profile_id: "PROFILE-A"`. Declared plan B. |
