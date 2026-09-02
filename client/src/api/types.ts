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

export type Framework = 'CSF' | 'IEC62443' | 'CIS' | 'NIS2' | 'IMO' | 'CIRCIA' | 'TSA'
export type Jurisdiction = 'US' | 'EU' | 'INTL' | 'INTL-MARITIME'

/**
 * The sector an asset operates in and a norm governs (server `Sector`, UCM-47).
 *
 * A neutral taxonomy both sides draw from, so the engine can intersect them: a
 * control names the sectors it governs (empty = transversal), an asset the ones
 * it operates in, and a zone may narrow the asset's. The order is the server's.
 */
export const SECTOR_FIELDS = [
  'energy',
  'water',
  'maritime',
  'transport',
  'health',
  'digital_infrastructure',
  'banking_finance',
  'public_administration',
  'manufacturing',
  'chemical',
  'food',
] as const
export type Sector = (typeof SECTOR_FIELDS)[number]
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

/** The scale a framework grades its controls on (server StrengthKind). */
export type StrengthKind = 'ig' | 'sl_baseline' | 'outcome' | 'legal' | 'guideline'

/**
 * What a control demands, on the scale of the framework that publishes it.
 * Structured because the engine reads it: `level` is the CIS IG or the SL at
 * which an IEC SR becomes mandatory. `note` is presentational.
 */
export interface ControlStrength {
  kind: StrengthKind
  level: number | null
  note: string
}

/** The five premises a zone answers about itself (server `Premise`). */
export type Premise =
  | 'general_purpose_os'
  | 'networked'
  | 'hybrid_it_ot'
  | 'interactive_users'
  | 'office_it_surface'

/**
 * What a control needs to be true of a zone for it to mean anything (UCM-53).
 *
 * A fact about the control, not a decision about any asset: what to do when the
 * zone does not meet it is the gating rules' business. `note` is the sentence the
 * operator reads when the mechanism leaves their baseline.
 */
export interface Presupposition {
  premise: Premise
  expected: boolean
  note: string
}

export interface FrameworkControl {
  id: string
  framework: Framework
  official_id: string
  title: string
  paraphrased_description: string
  jurisdiction: Jurisdiction
  strength: ControlStrength
  type: ControlType
  /** Empty means no premise has been declared — never that the control is universal. */
  presupposes: Presupposition[]
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
  nature: TechNature
  purdue?: string | null
  role?: string | null
  position?: string | null
  sl_vector?: SLVector | null
  safety_out_of_scope: boolean
  reference?: string | null
  /** Sectors this zone narrows the asset's to. Empty = inherits the asset's. */
  sectors: Sector[]
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
  /** Critical-infrastructure sectors the asset operates in. Empty = transversal. */
  sectors: Sector[]
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
  /** Empty unless the text distinguishes this zone's sectors from the asset's. */
  sectors: Sector[]
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
  /** Empty unless the text names them; never guessed — the operator completes it. */
  sectors: Sector[]
  zones: ZoneDraft[]
  conduits: ConduitDraft[]
  criticality: CriticalityDraft
  notes: ParseNote[]
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
  priority: OrdinalLevel | null
  implementation_group: string | null
  phase: number
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

/** Why a retrieved candidate is not among the ones being shown. */
export type CutReason = 'rank' | 'framework_cap'

/** The rule that bounds the ranking (UCM-54). */
export interface CutPolicy {
  version: string
  depth: number
  floor: number
  tie_epsilon: number
  ceiling: number
  framework_cap: number
}

export interface DroppedCandidate {
  control_id: string
  official_id: string
  framework: Framework
  jurisdiction: Jurisdiction
  score: number
  relation: RetrievalRelation
  dropped_by: CutReason
  margin: number
  rationale: string
}

/** What the cut left below the line (UCM-54): `retained + dropped === evaluated`. */
export interface RetrievalCut {
  policy: CutPolicy
  evaluated: number
  retained: number
  band_width: number
  band_extension: number
  ceiling_reached: boolean
  cap_yielded: number
  dropped: number
  near_ties_dropped: number
  not_returned: number
  first_dropped: DroppedCandidate | null
  displaced: DroppedCandidate[]
  rationale: string
}

/**
 * Why the engine's gating rules out this suggestion *in this zone* (UCM-52).
 *
 * A suggestion carrying this is not hidden: it is offered marked, and the
 * declared ordering rule (UCM-53) puts it at the end of the tail.
 */
export interface GatingAnnotation {
  zone_id: string
  outcome: GatingOutcome
  rule_id: string
  rationale: string
  evidence: string[]
}

export interface RetrievedControl {
  control: FrameworkControl
  score: number
  relation: RetrievalRelation
  mapped_capability_ids: string[]
  mapping_types: MappingType[]
  gated_out: GatingAnnotation | null
  rationale: string
}

export interface CapabilityRetrieval {
  capability_id: string
  capability_name: string
  zone_id: string
  catalog_control_ids: string[]
  retrieved: RetrievedControl[]
  set_aside: SetAsideCandidate[]
  cut: RetrievalCut | null
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
  cut_policy: CutPolicy
  /** The rule that ordered the suggestion tail (UCM-53). */
  ordering_version: string
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
  /** Run-wide totals of the retriever's cut (UCM-54). */
  below_cut: number
  displaced: number
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

// --- GET /baselines (server/app/baseline/listing.py) -------------------------

/** One signed baseline as the list shows it: its signature entry, read back. */
export interface BaselineSummary {
  baseline_id: string
  run_id: string
  profile_id: string
  profile_name: string
  signed_by: string
  signed_at: string
  versions: Record<string, string>
  zone_ids: string[]
  tier_0_complete: boolean
  /** Per zone, the mandates the engine could not close and the human closed by hand. */
  closed_mandates: Record<string, string[]>
  human_choices: number
  ratified_mandates: number
  gaps_accepted: number
  conflicts_resolved: number
  audit_events: number
  audit_log_path: string
  /** The operator's own justification, as recorded — not a rendering of it. */
  signature_rationale: string
}

export interface BaselineList {
  baselines: BaselineSummary[]
  total: number
  rationale: string
}

// --- GET /baseline/{id}/statement (server/app/baseline/statement.py) ---------

/**
 * What became of one mechanism. The three gating outcomes keep their own
 * identifiers: an exclusion in the declaration *is* the gating decision.
 */
export type MechanismDisposition =
  | 'selected'
  | 'ratified'
  | 'compensatory'
  | 'offered'
  | 'rejected'
  | 'not_applicable'
  | 'objective_without_mechanism'
  | 'wrong_scope'

/** How a required capability is satisfied. There is no `excluded`: gating removes
 * mechanisms, never requirements. */
export type CapabilityOutcome =
  | 'implemented'
  | 'compensated'
  | 'deferred'
  | 'accepted_gap'
  | 'open_gap'
  | 'roadmap'

export interface StatementMandate {
  source: string
  control_id: string | null
  official_id: string | null
  framework: Framework | null
  jurisdiction: Jurisdiction | null
  foundational_requirement: FoundationalRequirement | null
  required_at_sl: number | null
  zone_sl_target: number | null
  rationale: string
}

export interface StatementGap {
  kind: GapKind
  coverage: number | null
  residual: number | null
  rationale: string
}

export interface StatementMechanism {
  control_id: string
  official_id: string | null
  framework: Framework | null
  jurisdiction: Jurisdiction | null
  /** Already the Spanish phrase: the server composed it from the stored scale. */
  strength: string | null
  mapping_type: MappingType | null
  coverage_weight: number | null
  provenance: ProvenanceSource | null
  disposition: MechanismDisposition
  included: boolean
  /** Chosen although the catalog does not map it here: an adopted suggestion. */
  adopted: boolean
  /** The gating outcome the operator decided over, if they did. */
  despite_gating: string | null
  rule_id: string | null
  evidence: string[]
  compensation: string | null
  deferred_to: string | null
  rationale: string
  audit_sequences: number[]
}

export interface StatementRow {
  zone_id: string
  capability_id: string
  capability_name: string
  required: true
  tier: PriorityTier
  phase: number | null
  priority: OrdinalLevel | null
  layer: ImplementationLayer | null
  status: CapabilityStatus | null
  outcome: CapabilityOutcome
  in_signed_baseline: boolean
  outstanding: boolean
  coverage: number | null
  mandates: StatementMandate[]
  jurisdictions: Jurisdiction[]
  frameworks: Framework[]
  mechanisms: StatementMechanism[]
  gap: StatementGap | null
  gap_accepted: boolean
  decided_by_human: boolean
  /** Kept apart from the engine's on purpose: only one of them is the operator's. */
  human_rationale: string | null
  engine_rationale: string
  audit_sequences: number[]
}

export interface StatementCounts {
  capabilities: number
  tier_0: number
  tier_1: number
  signed: number
  implemented: number
  compensated: number
  deferred: number
  accepted_gaps: number
  open_gaps: number
  roadmap: number
  included_mechanisms: number
  offered_not_taken: number
  rejected_mechanisms: number
  justified_exclusions: number
  compensatory_requirements: number
  organizational_deferrals: number
}

export interface StatementZone {
  zone_id: string
  domain: ZoneDomain | null
  target_sl: number | null
  safety_relevant: boolean | null
  role: string | null
  tier_0_complete: boolean
  rows: StatementRow[]
  counts: StatementCounts
  rationale: string
}

export interface BaselineStatement {
  baseline_id: string
  run_id: string
  profile_id: string
  profile_name: string
  signed_by: string
  signed_at: string
  signature_rationale: string
  versions: Record<string, string>
  tier_0_complete: boolean
  zones: StatementZone[]
  counts: StatementCounts
  chain: ChainVerification
  audit_log_path: string
  rationale: string
  /** What the document is not. Declared inside the artefact itself. */
  limitations: string[]
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
  | 'candidates_cut'
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

// --- POST /delta (server/app/delta/schemas.py) -------------------------------

/** How the regional readings relate (UCM-50). */
export type DeltaMode = 'cumulative' | 'symmetric'

/** What enters the axis of comparison (UCM-50). */
export type DeltaRegime = 'all' | 'legal'

export interface RegionalRequirement {
  control_id: string
  official_id: string
  framework: Framework
  jurisdiction: Jurisdiction
  mapping_type: MappingType
  coverage_weight: number
  strength: ControlStrength
  added_by: Jurisdiction
  /** Whether it moves coverage, or only what is owed. Both travel together. */
  changes_coverage: boolean
  rationale: string
}

export interface CapabilityRegionView {
  region: Jurisdiction
  /** "US", "+EU" (cumulative) or plain "US"/"EU" (symmetric). */
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

/** Whether a legal regime of the compared regions governs this asset (UCM-50). */
export interface RegimeApplicability {
  framework: Framework
  jurisdiction: Jurisdiction
  governs_sectors: string[]
  applicable: boolean
  rationale: string
}

export interface RegionalDelta {
  profile_id: string
  profile_name: string
  zone: ZoneContext
  catalog_version: string
  rules_version: string
  mode: DeltaMode
  regime: DeltaRegime
  regions: Jurisdiction[]
  common_jurisdictions: Jurisdiction[]
  lenses: PayloadFilter[]
  capabilities: CapabilityDelta[]
  changed_capability_ids: string[]
  unchanged_capability_ids: string[]
  regional_gap_capability_ids: string[]
  regime_applicability: RegimeApplicability[]
  rationale: string
}

// --- errors (server/app/core/schemas.py) -------------------------------------

export interface Message {
  detail: string
}
