# Crosswalk: engine schema ↔ NIST OSCAL

What each model of this engine corresponds to in [OSCAL](https://pages.nist.gov/OSCAL/), field by
field, and — the part that matters more — **where the correspondence breaks and what was done about
it**. UCM-46.

The engine emits the SSP half of this crosswalk for real:
`GET /api/v1/baseline/{id}/statement?format=oscal` (`server/app/baseline/oscal.py`). It is a
**partial export** and says so in its own `metadata`. Nothing here is a conformance claim.

Target model version: **OSCAL 1.1.3** ([SSP model
reference](https://pages.nist.gov/OSCAL-Reference/models/v1.1.3/system-security-plan/)). Pinned in
`OSCAL_VERSION`, like every other versioned input of the engine.

---

## 1. Layer for layer

| OSCAL model | This engine | Emitted? |
| -- | -- | -- |
| `catalog` | `data/catalog/catalog.v<semver>.json` — capabilities, framework controls, typed mappings | no (documented below) |
| `profile` | `AssetProfile` + the zone's required capability set the core derives from it | no |
| *mapping* (model in development) | `Mapping` — typed `total\|partial\|compensatory\|contextual`, with `coverage_weight` and `provenance` | no |
| `system-security-plan` | the signed baseline, projected as `BaselineStatement` | **yes**, partial |
| `assessment-results` | UCM-18: engine vs. hand-made golden baseline | no |
| `plan-of-action-and-milestones` | the phased roadmap (Tier 1, `phase`) | no |

Only the SSP is emitted, because only the SSP is the artefact the ticket needed: the document a
reviewer asks for when they want to know what applies to this asset. The rest of the table is the
crosswalk itself — the claim that the internal schema is *conceptually* OSCAL, made checkable.

## 2. The four decisions that shape the SSP export

### 2.1 `control-id` is the capability, not the framework control

OSCAL resolves `implemented-requirement.control-id` against the imported profile. The profile of
this engine is the asset's **required capability set**, whose members are the framework-neutral
capabilities (`CAP-DE-LOG`, …) — not CIS 8.2 or SR 2.8, which are the *mechanisms* that answer
them.

*Rejected alternative*: mapping the framework control to `control-id`. It reads more naturally at
first glance and it loses the requirement: a capability answered by SR 2.8 in the OT corridor and
by CIS 8.2 in the IT zone would export as two unrelated controls, and the fact that both answer one
obligation — which is the whole point of a harmonisation engine — would be gone.

### 2.2 A zone is a component (`type: "network"`)

An IEC 62443 zone is a grouping of assets under one security level. OSCAL's core component types
are `software`, `hardware`, `service`, `policy`, `process-procedure`, `plan`, `guidance`,
`standard`, `validation`, `network`, `this-system`. `network` is the closest, and the export says
in `system-implementation.remarks` that it is an interpretation rather than a defined value.

The consequence is the useful part: one `implemented-requirement` per capability carries one
`by-component` per zone, which is exactly how the same requirement gets a different answer in the
corridor and in the SIS. That is the engine's central demonstration (`same catalog + per-zone
gating ⇒ different baselines`), and OSCAL happens to have the right shape for it.

### 2.3 `implementation-status` uses core values only

| Engine outcome (`CapabilityOutcome`) | OSCAL `state` | Fit |
| -- | -- | -- |
| `implemented` — a mechanism chosen or ratified | `implemented` | exact |
| `compensated` — a declared compensatory control | `alternative` | exact: OSCAL defines it as "there is an alternative implementation for this control as explained in the remarks" |
| `deferred` — wrong scope, moved to the organisational layer | `not-applicable` | partial: not applicable **at this layer**, and the remarks say so. The requirement is not repealed |
| `roadmap` — discretionary, not decided, in the phased roadmap | `planned` | good enough: it is in the roadmap with its phase |
| `accepted_gap` — **assumed in writing by the signer** | `partial` | **no fit — see below** |
| `open_gap` | `partial` | approximate |

**The finding.** OSCAL has no state for a requirement the operator accepted without a mechanism and
with a written justification. It is not `planned` (there is no plan), not `not-applicable` (the
capability is still required), and not `alternative` (there is no alternative). This is a real gap
between the model and the discipline the engine implements, and it is where the engine is stricter
than the format: `gap_accepted` is a first-class, human-authored, non-repealing outcome here, and
in OSCAL it can only be approximated.

What the export does about it: `state: "partial"`, plus the extension property
`capability-outcome=accepted_gap`, plus `implementation-status.remarks` that states the mismatch in
full and quotes the operator's own acceptance. Smoothing it into `planned` would have produced a
document that validates and lies.

### 2.4 Everything non-core is an extension property under `urn:tfm:mfhe:oscal`

OSCAL prescribes `props[].ns` for exactly this: "a namespace qualifying the property's name allows
different organizations to associate distinct semantics with the same name". Every property this
engine adds carries it — asserted in the test suite
(`tests/api/test_oscal.py::test_everything_the_model_does_not_define_is_namespaced_as_an_extension`),
so a core name can never be quietly invented.

A URN and not an `https://` URI because this POC owns no domain, and claiming one in a document
about traceability would be its one lie.

| Property | Carries |
| -- | -- |
| `capability-outcome` | `implemented \| compensated \| deferred \| accepted_gap \| open_gap \| roadmap` |
| `tier`, `phase`, `priority`, `layer` | prioritisation (UCM-10) — Tier 0 is not ranked, and `priority` is absent on it |
| `in-signed-baseline` | whether the row is part of what was signed or a roadmap recommendation |
| `gating-status` | `CapabilityStatus` after gating (UCM-9) |
| `selected-control`, `excluded-control` | mechanism by mechanism, with the rule and the premise in `remarks` |
| `jurisdiction` | per included mechanism — the axis a crosswalk usually flattens |
| `gap-kind`, `gap-residual`, `gap-accepted` | the explicit gap and its residual |
| `mandate` | why the capability is Tier 0 (`sl_target` / `legal_obligation`) |
| `audit-sequences` | the ledger entries that back the row |
| `version-*`, `ledger-chain-valid`, `ledger-events`, `export-kind` | reproducibility and integrity |

## 3. Field by field

### `metadata`

| OSCAL | Source | Note |
| -- | -- | -- |
| `title` | `"Línea base compuesta y firmada — {profile_name}"` | |
| `last-modified` | `signed_at` | the ledger's own stamp, not the exporter's clock |
| `version` | `versions.catalog` | the same signature over another catalog is another baseline |
| `oscal-version` | `1.1.3` | pinned |
| `roles` / `parties` / `responsible-parties` | the signer | the only human actor the engine models |
| `links[rel=reference]` | `audit_log_path` | the trail the document is projected from |
| `remarks` | the partiality statement | |

### `import-profile`

`href` points at a deterministic `uuid5` of the profile id. The profile document itself is **not**
emitted — this export is the SSP half — so the reference is a stable identifier rather than a
resolvable document, and `remarks` says so.

### `system-characteristics`

| OSCAL | Source | Note |
| -- | -- | -- |
| `system-ids` | `profile_id`, `identifier-type` = our ns | |
| `system-name` / `description` | profile name, zone list | |
| `security-sensitivity-level` | `SL{max target_sl}` | the highest zone target, as a label |
| `system-information.information-types` | one generic type, no impact levels | **the engine does not classify information**, and the export declares that rather than inventing a FIPS-199 triad |
| `status.state` | `other` | not `operational`: this is a composed baseline, not an authorised system |
| `authorization-boundary` | the declared zones | the profile's boundary, not a formal authorisation's |

### `system-implementation`

`users` is required by the model and the engine models no system users, so it carries exactly one:
the signer, with role `signatory`, and a remark that says the engine does not model users of the
asset. `components` is one per zone (§2.2).

### `control-implementation`

One `implemented-requirement` per capability; one `by-component` per (capability, zone). `remarks`
carries the operator's own justification when there is one and the engine's when there is not — the
two are never merged, because only one of them makes an inclusion admissible.

## 4. What does not cross over

* **Coverage weights and mapping types.** `total | partial | compensatory | contextual` with a
  numeric `coverage_weight` is how this engine resolves 1:N granularity (UCM-8). OSCAL's SSP has
  no field for "this control covers 0.6 of the requirement"; it travels as an extension property
  on the selected control and nothing in an OSCAL toolchain will compute with it.
* **The hash chain.** `prev_hash`/`event_hash` make the ledger's integrity checkable (UCM-11).
  OSCAL has no place for it; the export carries `ledger-chain-valid` and `ledger-events` as
  properties and a link to the endpoint where a reader can re-verify it themselves.
* **Retrieval provenance.** Whether a mechanism came from a catalog mapping or from an adopted RAG
  suggestion is a first-class distinction here (`adopted`). In the export it is a property; there
  is no core OSCAL concept for "the operator adopted a suggestion the catalog does not map".
* **`assessment-results`.** UCM-18 measures the engine against a hand-made golden baseline. That
  maps onto OSCAL's assessment layer conceptually and is not emitted — the golden baseline is an
  external measuring instrument the engine must never read (invariant 9), and generating an OSCAL
  document from it would put it inside the system.

## 5. Validating the export

The export is asserted structurally by `server/tests/api/test_oscal.py`: required blocks present,
no `null` where OSCAL expects an absent field, every `*-uuid` a real UUID, only core
`implementation-status` states, every extension property namespaced, and the same baseline
exporting to the same bytes twice.

It is **not** validated against NIST's published JSON Schema, and that is a declared limitation
rather than an oversight: the schema is not vendored into this repository and the suite must run
offline on any machine (a standing constraint of the whole POC). A reader who wants that check can
run the emitted document through `oscal-cli` or any OSCAL validator themselves — the document is a
plain file and the endpoint is in Swagger.

## 6. Sources

* [OSCAL SSP model v1.1.3 reference](https://pages.nist.gov/OSCAL-Reference/models/v1.1.3/system-security-plan/)
* [OSCAL SSP v1.1.3 JSON format reference](https://pages.nist.gov/OSCAL-Reference/models/v1.1.3/system-security-plan/json-reference/)
* [OSCAL implementation-common metaschema](https://github.com/usnistgov/OSCAL/blob/main/src/metaschema/oscal_implementation-common_metaschema.xml) — the `implementation-status` state values
* [OSCAL SSP concepts](https://pages.nist.gov/OSCAL/learn/concepts/layer/implementation/ssp/)
