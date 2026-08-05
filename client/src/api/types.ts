/**
 * The engine's contracts, in TypeScript.
 *
 * Every type here mirrors a Pydantic model of the backend, field for field, and
 * the module each one comes from is named above it. Nothing is summarised or
 * flattened on the way across: the API deliberately carries the core's own
 * shapes — `CapabilityResolution`, `CapabilityGating`, `CapabilityPriority` —
 * because a summary is a place where a candidate can quietly stop being
 * mentioned (invariant 2, `server/app/candidates/schemas.py`). The UI renders
 * those shapes; it does not recompute them.
 *
 * The five endpoints are the whole surface (invariant 4). There is no sixth call
 * anywhere in this client.
 */

// --- catalog (server/app/catalog/schemas.py) ---------------------------------

export type Framework = 'CSF' | 'IEC62443' | 'CIS' | 'NIS2' | 'IMO'
export type Jurisdiction = 'US' | 'EU' | 'INTL' | 'INTL-MARITIME'
export type MappingType = 'total' | 'partial' | 'compensatory' | 'contextual'
export type ProvenanceSource = 'official_crosswalk' | 'author_judgment'
export type ControlType = 'technical' | 'legal'

export interface Capability {
  id: string
  name: string
  description: string
  csf_seed_category: string
  ot_refinements: string[]
}

export interface FrameworkControl {
  id: string
  framework: Framework
  official_id: string
  title: string
  paraphrased_description: string
  jurisdiction: Jurisdiction
  strength: string
  type: ControlType
}

export interface Provenance {
  source: ProvenanceSource
  jurisdiction: Jurisdiction
  note: string
}

export interface Mapping {
  capability_id: string
  control_id: string
  type: MappingType
  coverage_weight: number
  provenance: Provenance
}

// --- asset profile (server/app/assets/schemas.py) ----------------------------

export type CaseType = 'PURE_OT' | 'HYBRID_IT_OT'
export type ConsequenceScale = 'catastrophic' | 'high' | 'moderate' | 'low'

export const FR_FIELDS = ['FR1', 'FR2', 'FR3', 'FR4', 'FR5', 'FR6', 'FR7'] as const
export type FoundationalRequirement = (typeof FR_FIELDS)[number]

export type SLVector = Record<FoundationalRequirement, number>

export interface Zone {
  id: string
  target_sl: number
  /**
   * Per zone, never per asset (UCM-9). A hybrid asset holds zones of different
   * natures at once — an embedded controller and a Windows workstation — and a
   * single asset-wide reading has to be wrong about one of them.
   */
  nature: TechNature
  purdue?: string | null
  role?: string | null
  position?: string | null
  sl_vector?: SLVector | null
  safety_out_of_scope: boolean
  reference?: string | null
}

export interface TechNature {
  general_purpose_os: boolean
  networked: boolean
  hybrid_it_ot: boolean
  interactive_users: boolean
  office_it_surface: boolean
}

export const NATURE_FIELDS = [
  'general_purpose_os',
  'networked',
  'hybrid_it_ot',
  'interactive_users',
  'office_it_surface',
] as const
export type NatureField = (typeof NATURE_FIELDS)[number]

export interface Conduit {
  id: string
  endpoints: string[]
  control: string
}

export interface Criticality {
  physical_consequence: string
  scale: ConsequenceScale
  threat_model: string
  consequence_path?: string | null
  attack_reference?: string | null
}

export interface AssetProfile {
  id: string
  name: string
  case: CaseType
  zones: Zone[]
  conduits: Conduit[]
  criticality: Criticality
}

// --- POST /asset/parse (server/app/parse/schemas.py) -------------------------

/** How a value got into the draft. There is no third kind: unsupported = absent. */
export type EvidenceKind = 'stated' | 'inferred'

export interface ParseNote {
  field: string
  kind: EvidenceKind
  evidence: string
  note: string
}

export type SLVectorDraft = Partial<Record<FoundationalRequirement, number | null>>

export interface ZoneDraft {
  id: string
  target_sl: number | null
  nature: TechNatureDraft
  purdue: string | null
  role: string | null
  position: string | null
  sl_vector: SLVectorDraft | null
  safety_out_of_scope: boolean | null
  reference: string | null
}

export type TechNatureDraft = Record<NatureField, boolean | null>

export interface ConduitDraft {
  id: string
  endpoints: string[]
  control: string | null
}

export interface CriticalityDraft {
  physical_consequence: string | null
  scale: ConsequenceScale | null
  threat_model: string | null
  consequence_path: string | null
  attack_reference: string | null
}

export interface AssetProfileDraft {
  name: string | null
  case: CaseType | null
  zones: ZoneDraft[]
  conduits: ConduitDraft[]
  criticality: CriticalityDraft
  notes: ParseNote[]
  /** Statements the schema had no place for. Reported, never dropped. */
  unmapped: string[]
}

export interface AssetParseRequest {
  description: string
  profile_id?: string | null
}

export interface ParseProvenance {
  model: string
  model_digest: string
  prompt_version: string
  temperature: number
  seed: number
  top_p: number
  num_predict: number
  attempts: number
  source_sha256: string
}

export interface ParseResult {
  profile_id: string
  draft: AssetProfileDraft
  missing_required: string[]
  provenance: ParseProvenance
  /** A constant `true`: the model proposes, the operator decides. */
  review_required: boolean
}

// --- deterministic core (server/app/engine/schemas.py) -----------------------

export type ZoneDomain = 'OT' | 'IT' | 'HYBRID'
export type CandidateStatus = 'eligible' | 'superseded' | 'contested'
export type ConflictType = 'overlap' | 'granularity' | 'contradiction'
export type ResolutionMethod =
  | 'collapsed'
  | 'coverage_weights'
  | 'framework_precedence'
  | 'safety_override'
export type GapKind =
  | 'no_candidate'
  | 'no_effective_mechanism'
  | 'partial_only'
  | 'residual_coverage'
export type GatingOutcome =
  | 'not_applicable'
  | 'objective_without_mechanism'
  | 'wrong_scope'
export type CapabilityStatus =
  | 'covered_by_mechanism'
  | 'compensatory_required'
  | 'deferred_to_organizational_layer'
export type PriorityTier = 'tier_0' | 'tier_1'
export type MandateSource = 'sl_target' | 'legal_obligation'
export type OrdinalLevel = 'low' | 'medium' | 'high'
export type ImplementationLayer = 'asset' | 'organizational'

export interface ZoneContext {
  zone_id: string
  domain: ZoneDomain
  target_sl: number
  safety_relevant: boolean
  derivation: string
  sl_vector: SLVector | null
}

export interface CandidateOption {
  control: FrameworkControl
  mapping: Mapping
  status: CandidateStatus
  status_reason: string | null
  rule_id: string | null
}

export interface Conflict {
  id: string
  conflict_type: ConflictType
  capability_id: string
  zone_id: string
  control_ids: string[]
  method: ResolutionMethod
  prevailing_control_ids: string[]
  superseded_control_ids: string[]
  requires_human_decision: boolean
  rationale: string
  rule_id: string | null
}

export interface CapabilityGap {
  capability_id: string
  zone_id: string
  kind: GapKind
  coverage: number
  residual: number
  rationale: string
}

export interface CapabilityResolution {
  capability: Capability
  zone_id: string
  options: CandidateOption[]
  coverage: number
  has_full_mechanism: boolean
  conflicts: Conflict[]
  gap: CapabilityGap | null
}

export interface GatingDecision {
  zone_id: string
  capability_id: string
  control_id: string
  outcome: GatingOutcome
  rule_id: string
  rationale: string
  evidence: string[]
  compensation: string | null
  deferred_to: string | null
  also_matched_rule_ids: string[]
}

export interface CapabilityGating {
  capability_id: string
  zone_id: string
  /** Never false: gating removes mechanisms, never required capabilities. */
  required: true
  status: CapabilityStatus
  retained_control_ids: string[]
  compensatory_control_ids: string[]
  excluded: GatingDecision[]
  coverage: number
  coverage_before_gating: number
  deferred_to: string | null
  gap: CapabilityGap | null
  rationale: string
}

export interface Mandate {
  source: MandateSource
  control_id: string
  official_id: string
  framework: Framework
  jurisdiction: Jurisdiction
  foundational_requirement: FoundationalRequirement | null
  required_at_sl: number | null
  zone_sl_target: number | null
  rationale: string
}

export interface CapabilityPriority {
  capability_id: string
  zone_id: string
  tier: PriorityTier
  layer: ImplementationLayer
  status: CapabilityStatus
  mandates: Mandate[]
  coverage: number
  coverage_level: OrdinalLevel
  leverage: number
  unlocks: string[]
  depends_on: string[]
  benefit: OrdinalLevel
  cost: OrdinalLevel
  /** Null on Tier 0 — what is mandatory is not ranked, it is completed. */
  priority: OrdinalLevel | null
  implementation_group: string | null
  phase: number
  /** A mandate the engine could not close on its own: the human must. */
  outstanding: boolean
  gap: CapabilityGap | null
  rationale: string
}

export interface RoadmapPhase {
  index: number
  name: string
  tier: PriorityTier
  capability_ids: string[]
  rationale: string
}

// --- RAG pass (server/app/retrieval/schemas.py) ------------------------------

export type RetrievalRelation = 'widens' | 'confirms_mapping'
export type FilterAxis = 'jurisdiction' | 'zone' | 'mapping_type'

export interface PayloadFilter {
  // Null, not empty: "no lens on this axis" and "a lens that admits nothing" are
  // different states, and the engine never applies one on its own initiative.
  jurisdictions: Jurisdiction[] | null
  frameworks: Framework[] | null
  mapping_types: MappingType[] | null
  zone_domain: ZoneDomain | null
  rationale: string
}

export interface SetAsideCandidate {
  control_id: string
  official_id: string
  framework: Framework
  jurisdiction: Jurisdiction
  score: number
  relation: RetrievalRelation
  excluded_by: FilterAxis[]
  rationale: string
}

export interface RetrievedControl {
  control: FrameworkControl
  /** Cosine similarity. A reading order — never a coverage weight. */
  score: number
  relation: RetrievalRelation
  mapped_capability_ids: string[]
  mapping_types: MappingType[]
  rationale: string
}

export interface CapabilityRetrieval {
  capability_id: string
  capability_name: string
  zone_id: string
  catalog_control_ids: string[]
  retrieved: RetrievedControl[]
  set_aside: SetAsideCandidate[]
  gap: CapabilityGap | null
  rationale: string
}

export interface RetrievalProvenance {
  embedding_model: string
  embedding_dim: number
  collection: string
  catalog_version: string
  catalog_digest: string
  indexed_controls: number
  text_template_version: string
  top_k: number
  payload_filter: PayloadFilter
}

// --- LLM explanations, P1 (server/app/explain/schemas.py) --------------------

export type CandidateOrigin = 'catalog' | 'retrieval'
export type ExplanationStatus = 'generated' | 'withheld' | 'unavailable' | 'disabled'
export type EvidenceKey =
  | 'catalog_mapping'
  | 'mapping_type'
  | 'coverage_weight'
  | 'mapping_provenance'
  | 'neighbouring_mapping'
  | 'similarity'
  | 'framework'
  | 'jurisdiction'
  | 'strength'
  | 'control_text'
  | 'candidate_status'
  | 'zone_context'

export interface CandidateExplanation {
  control_id: string
  official_id: string
  framework: Framework
  jurisdiction: Jurisdiction
  origin: CandidateOrigin
  text: string
  status: ExplanationStatus
  basis: EvidenceKey[]
  notice: string | null
}

export interface ExplanationProvenance {
  model: string
  model_digest: string | null
  prompt_version: string
  sheet_template_version: string
  temperature: number
  seed: number
  top_p: number
  num_predict: number
  attempts: number
  catalog_version: string
  ignored_control_ids: string[]
  notice: string | null
}

export interface CapabilityExplanations {
  capability_id: string
  capability_name: string
  zone_id: string
  offered_control_ids: string[]
  explanations: CandidateExplanation[]
  provenance: ExplanationProvenance
  /** `Literal[True]` on the server: this layer may not decide anything. */
  presentational: true
}

// --- POST /candidates (server/app/candidates/schemas.py) ---------------------

export type RetrievalStatus = 'ok' | 'disabled' | 'unavailable'

export interface ExplainScope {
  zone_id: string
  capability_ids: string[]
}

export interface CandidatesRequest {
  profile?: AssetProfile | null
  profile_id?: string | null
  retrieval?: boolean
  lens?: PayloadFilter | null
  explain?: ExplainScope | null
}

export interface RetrievalReport {
  status: RetrievalStatus
  suggestions: number
  set_aside: number
  provenance: RetrievalProvenance | null
  notice: string | null
}

export interface CapabilityCandidates {
  capability_id: string
  capability_name: string
  zone_id: string
  resolution: CapabilityResolution
  gating: CapabilityGating
  priority: CapabilityPriority
  retrieval: CapabilityRetrieval | null
  explanations: CapabilityExplanations | null
  /** Catalog options first, in the core's order, then retrieved suggestions. */
  offered_control_ids: string[]
  rationale: string
}

export interface ZoneCandidates {
  zone: ZoneContext
  capabilities: CapabilityCandidates[]
  phases: RoadmapPhase[]
  /** Real contradictions the engine must not settle. They go to the human. */
  open_decisions: Conflict[]
  tier_0_complete: boolean
  outstanding_capability_ids: string[]
  rationale: string
}

export interface CandidatesResponse {
  run_id: string
  profile_id: string
  profile_name: string
  catalog_version: string
  rules_version: string
  gating_version: string
  prioritization_version: string
  retrieval: RetrievalReport
  explanations_notice: string | null
  zones: ZoneCandidates[]
  tier_0_complete: boolean
  audit_events: number
}

// --- POST /baseline/compose (server/app/baseline/schemas.py) -----------------

export type ChoiceKind =
  | 'option_selected'
  | 'option_rejected'
  | 'compensatory_declared'
  | 'gap_accepted'

export interface CompositionChoice {
  kind: ChoiceKind
  zone_id: string
  capability_id: string
  /** Omitted — and only omitted — when accepting a gap. */
  control_id?: string | null
  rationale: string
  explanations_digest?: string | null
}

export interface Signature {
  operator: string
  rationale: string
}

export interface ComposeRequest {
  run_id: string
  profile?: AssetProfile | null
  profile_id?: string | null
  choices: CompositionChoice[]
  signature: Signature
}

export type SelectionOrigin = 'catalog_mapping' | 'adopted_suggestion'

export interface ComposedCapability {
  zone_id: string
  capability_id: string
  capability_name: string
  tier: PriorityTier
  status: CapabilityStatus
  outstanding: boolean
  required: boolean
  selected_control_ids: string[]
  rejected_control_ids: string[]
  compensatory_control_ids: string[]
  adopted_control_ids: string[]
  /** Retained by the core and accepted by the signature — not chosen. */
  ratified_control_ids: string[]
  gap_accepted: boolean
  rationale: string
}

export interface ComposedZone {
  zone_id: string
  capabilities: ComposedCapability[]
  tier_0_complete: boolean
  outstanding_capability_ids: string[]
  rationale: string
}

export interface ComposedBaseline {
  baseline_id: string
  run_id: string
  profile_id: string
  profile_name: string
  signed_by: string
  signed_at: string
  versions: Record<string, string>
  tier_0_complete: boolean
  zones: ComposedZone[]
  audit_events: number
  audit_log_path: string
}

// --- GET /baseline/{id}/audit-log (server/app/audit/schemas.py) --------------

export type AuditActor = 'engine' | 'human'
export type AuditStage =
  | 'run'
  | 'mapping'
  | 'conflict_resolution'
  | 'gating'
  | 'prioritization'
  | 'retrieval'
  | 'composition'
  | 'signature'

export type AuditEventType =
  | 'run_started'
  | 'zone_derived'
  | 'capability_mapped'
  | 'conflict_resolved'
  | 'conflict_escalated'
  | 'gap_declared'
  | 'mechanism_excluded'
  | 'capability_status_set'
  | 'mandate_recorded'
  | 'mandate_outstanding'
  | 'priority_assigned'
  | 'roadmap_phased'
  | 'stage_completed'
  | 'run_completed'
  | 'candidates_retrieved'
  | 'candidate_set_aside'
  | 'option_selected'
  | 'option_rejected'
  | 'compensatory_declared'
  | 'gap_accepted'
  | 'mechanism_ratified'
  | 'baseline_signed'

export interface AuditEventRead {
  id: string
  sequence: number
  recorded_at: string
  actor: AuditActor
  actor_ref: string | null
  stage: AuditStage
  event_type: AuditEventType
  run_id: string
  baseline_id: string | null
  profile_id: string
  zone_id: string | null
  capability_id: string | null
  control_id: string | null
  rule_id: string | null
  decision: string
  rationale: string
  versions: Record<string, string>
  payload: Record<string, unknown>
  prev_hash: string
  event_hash: string
}

export interface ChainVerification {
  valid: boolean
  events: number
  first_broken_sequence: number | null
  detail: string
}

export interface BaselineAuditLog {
  baseline_id: string
  events: AuditEventRead[]
  chain: ChainVerification
  engine_events: number
  human_events: number
  rationale: string
}

// --- GET /delta (server/app/delta/schemas.py) --------------------------------

export interface RegionalRequirement {
  control_id: string
  official_id: string
  framework: Framework
  jurisdiction: Jurisdiction
  mapping_type: MappingType
  coverage_weight: number
  strength: string
  added_by: Jurisdiction
  /** Whether it moves coverage, or only what is owed. Both travel together. */
  changes_coverage: boolean
  rationale: string
}

export interface CapabilityRegionView {
  region: Jurisdiction
  /** "US", "+EU": the `+` says the reading is cumulative. */
  label: string
  jurisdictions: Jurisdiction[]
  offered_control_ids: string[]
  only_here_control_ids: string[]
  /** Apartar no es descartar: what this reading's lens left out. */
  set_aside_control_ids: string[]
  frameworks: Framework[]
  coverage: number
  has_full_mechanism: boolean
  gap: CapabilityGap | null
  rationale: string
}

export interface CapabilityDelta {
  capability_id: string
  capability_name: string
  zone_id: string
  common_control_ids: string[]
  regions: CapabilityRegionView[]
  added: RegionalRequirement[]
  changed: boolean
  changes_coverage: boolean
  rationale: string
}

export interface RegionalDelta {
  profile_id: string
  profile_name: string
  zone: ZoneContext
  catalog_version: string
  rules_version: string
  regions: Jurisdiction[]
  common_jurisdictions: Jurisdiction[]
  lenses: PayloadFilter[]
  capabilities: CapabilityDelta[]
  changed_capability_ids: string[]
  unchanged_capability_ids: string[]
  regional_gap_capability_ids: string[]
  rationale: string
}

// --- errors (server/app/core/schemas.py) -------------------------------------

export interface Message {
  detail: string
}
