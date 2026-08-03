"""UCM-14 - The explanation use case: candidates in, prose next to them out.

The service is written around one question — *what happens when this feature does
not work?* — because the answer is what makes a P1 layer safe to ship next to a
P0 pipeline:

* **It fails open, always.** Ollama down, wrong digest, invalid output, a
  candidate the model forgot, a sentence that reads as advice: every one of those
  paths ends with the same candidates on screen, in the same order, carrying the
  deterministic rationale the engine already wrote, and a `status` that says what
  happened. There is no path through this module that removes, adds or reorders a
  candidate — `CapabilityExplanations` would refuse to be built.
* **It writes nothing.** No audit entry (the LLM is not an actor, UCM-11), no
  mutation of the resolution or the retrieval it was handed, no state. The prose
  enters the record only when the human decides on it (UCM-16), and
  `CapabilityExplanations.digest` is how that entry names what was on screen.
* **It is on demand, capability by capability.** There is deliberately no
  profile-wide pass: 69 capabilities per zone at one model request each would put
  minutes of P1 in front of a P0 result. `explain_zone` therefore takes the
  explicit list of capabilities to explain — the operator opens a capability, and
  that capability is explained.

The one thing worth stating plainly: nothing here is on the path of the baseline.
The service reads the core's resolution and the retrieval, and returns text. If
this whole module were deleted, every candidate, every coverage number, every
gating decision and every priority would be identical.
"""

from __future__ import annotations

from pydantic_ai.messages import ModelResponse

from app.core.config import settings
from app.core.exceptions import AppException
from app.engine.schemas import CapabilityResolution, ZoneContext, ZoneResolution
from app.explain.agent import ExplainAgent, explain_agent
from app.explain.evidence import CandidateFacts, CapabilityFacts, fact_sheet, facts_for
from app.explain.guard import screen
from app.explain.prompt import PROMPT_VERSION, user_prompt
from app.explain.schemas import (
    CandidateExplanation,
    CapabilityExplanations,
    ExplanationDraft,
    ExplanationProvenance,
    ExplanationStatus,
    ZoneExplanations,
)
from app.parse.ollama import verify_model
from app.retrieval.schemas import CapabilityRetrieval, ZoneRetrieval

DISABLED_NOTICE = (
    "La capa de explicaciones está desactivada por configuración (EXPLAIN_ENABLED). Se muestra "
    "la justificación determinista del motor, que es la que sostiene al candidato."
)

MISSING_NOTICE = (
    "El modelo no devolvió explicación para este candidato. Se muestra la justificación "
    "determinista del motor; el candidato sigue disponible sin ningún cambio."
)


class CandidateExplanationService:
    """Explained candidates for one capability. The agent is injectable for tests."""

    def __init__(self, agent: ExplainAgent | None = None):
        self.agent = agent if agent is not None else explain_agent()

    # --- entry points ---------------------------------------------------------

    async def explain_capability(
        self,
        resolution: CapabilityResolution,
        retrieval: CapabilityRetrieval,
        catalog_version: str,
        zone: ZoneContext | None = None,
    ) -> CapabilityExplanations:
        """Explain every candidate offered for one capability in one zone."""
        facts = facts_for(resolution, retrieval, zone)

        # A capability with no candidate is an explicit gap (UCM-13). There is
        # nothing to explain and nothing to say about it that the gap's own
        # rationale does not already say.
        if not facts.candidates:
            return self._flat(facts, catalog_version, ExplanationStatus.UNAVAILABLE, notice=None)

        if not settings.EXPLAIN_ENABLED:
            return self._flat(
                facts, catalog_version, ExplanationStatus.DISABLED, notice=DISABLED_NOTICE
            )

        try:
            digest = await verify_model()
        except AppException as exc:
            return self._flat(
                facts, catalog_version, ExplanationStatus.UNAVAILABLE, notice=str(exc)
            )

        try:
            run = await self.agent.run(user_prompt(fact_sheet(facts)))
        # Broad on purpose, and this is the load-bearing line of the module.
        # Anything that can go wrong while writing a paragraph — a timeout, a
        # provider error, `UnexpectedModelBehavior` when the retry is spent — must
        # cost the paragraph and nothing else. Cancellation is not caught:
        # `CancelledError` is a `BaseException`, so a shutdown still propagates.
        except Exception as exc:
            return self._flat(
                facts,
                catalog_version,
                ExplanationStatus.UNAVAILABLE,
                notice=f"No se pudo generar la explicación: {exc}",
                digest=digest,
            )

        attempts = sum(1 for message in run.all_messages() if isinstance(message, ModelResponse))
        return self._assemble(facts, run.output.explanations, catalog_version, digest, attempts)

    async def explain_zone(
        self,
        resolution: ZoneResolution,
        retrieval: ZoneRetrieval,
        catalog_version: str,
        capability_ids: list[str],
    ) -> ZoneExplanations:
        """Explain the named capabilities of one zone, in the zone's own order.

        `capability_ids` is required rather than defaulted to "all": the caller has
        to say what the operator is looking at. Explaining a whole zone eagerly
        would spend one model request per capability on text nobody asked for.
        """
        wanted = set(capability_ids)
        unknown = wanted - {c.capability.id for c in resolution.capabilities}
        if unknown:
            raise KeyError(
                f"capabilities not resolved in {resolution.zone.zone_id}: {sorted(unknown)}"
            )

        explained = [
            await self.explain_capability(
                capability,
                retrieval.capability(capability.capability.id),
                catalog_version,
                resolution.zone,
            )
            for capability in resolution.capabilities
            if capability.capability.id in wanted
        ]
        return ZoneExplanations(zone_id=resolution.zone.zone_id, capabilities=explained)

    # --- assembly -------------------------------------------------------------

    def _assemble(
        self,
        facts: CapabilityFacts,
        drafts: list[ExplanationDraft],
        catalog_version: str,
        digest: str,
        attempts: int,
    ) -> CapabilityExplanations:
        """Match the model's answer to the candidates — never the other way round.

        The candidate list leads: it is iterated in the engine's order and every
        entry produces exactly one explanation. What the model returned is looked
        up, screened and used, or not used. Anything it returned that was not
        offered is not a candidate and is reported in the provenance rather than
        shown.
        """
        by_control: dict[str, ExplanationDraft] = {}
        ignored: list[str] = []
        for draft in drafts:
            if facts.candidate(draft.control_id) is None or draft.control_id in by_control:
                ignored.append(draft.control_id)
                continue
            by_control[draft.control_id] = draft

        explanations = [
            self._explain(candidate, by_control.get(candidate.control_id))
            for candidate in facts.candidates
        ]

        return CapabilityExplanations(
            capability_id=facts.capability.id,
            capability_name=facts.capability.name,
            zone_id=facts.zone_id,
            offered_control_ids=facts.offered_control_ids,
            explanations=explanations,
            provenance=self._provenance(
                catalog_version, digest=digest, attempts=attempts, ignored=ignored
            ),
        )

    def _explain(
        self, candidate: CandidateFacts, draft: ExplanationDraft | None
    ) -> CandidateExplanation:
        if draft is None or not draft.explanation.strip():
            return self._candidate(candidate, ExplanationStatus.UNAVAILABLE, notice=MISSING_NOTICE)

        verdict = screen(draft.explanation, draft.basis, candidate.allowed)
        if not verdict.passed:
            return self._candidate(candidate, ExplanationStatus.WITHHELD, notice=verdict.reason)

        return CandidateExplanation(
            control_id=candidate.control_id,
            official_id=candidate.official_id,
            framework=candidate.framework,
            jurisdiction=candidate.jurisdiction,
            origin=candidate.origin,
            text=draft.explanation.strip(),
            status=ExplanationStatus.GENERATED,
            # Deduplicated, in the order the model gave them, and already known to
            # be a subset of what this candidate has: the guard checked it.
            basis=list(dict.fromkeys(draft.basis)),
        )

    def _flat(
        self,
        facts: CapabilityFacts,
        catalog_version: str,
        status: ExplanationStatus,
        notice: str | None,
        digest: str | None = None,
    ) -> CapabilityExplanations:
        """Every candidate with the engine's own rationale. No model prose at all."""
        return CapabilityExplanations(
            capability_id=facts.capability.id,
            capability_name=facts.capability.name,
            zone_id=facts.zone_id,
            offered_control_ids=facts.offered_control_ids,
            explanations=[
                self._candidate(candidate, status, notice=notice)
                for candidate in facts.candidates
            ],
            provenance=self._provenance(catalog_version, digest=digest, notice=notice),
        )

    def _candidate(
        self, candidate: CandidateFacts, status: ExplanationStatus, notice: str | None
    ) -> CandidateExplanation:
        """The fallback shape: the engine's text, the reason it is the one shown."""
        return CandidateExplanation(
            control_id=candidate.control_id,
            official_id=candidate.official_id,
            framework=candidate.framework,
            jurisdiction=candidate.jurisdiction,
            origin=candidate.origin,
            text=candidate.fallback,
            status=status,
            notice=notice,
        )

    def _provenance(
        self,
        catalog_version: str,
        *,
        digest: str | None = None,
        attempts: int = 0,
        ignored: list[str] | None = None,
        notice: str | None = None,
    ) -> ExplanationProvenance:
        return ExplanationProvenance(
            model=settings.LLM_MODEL,
            model_digest=digest,
            prompt_version=PROMPT_VERSION,
            temperature=settings.LLM_TEMPERATURE,
            seed=settings.LLM_SEED,
            top_p=settings.LLM_TOP_P,
            num_predict=settings.LLM_NUM_PREDICT,
            attempts=attempts,
            catalog_version=catalog_version,
            ignored_control_ids=ignored or [],
            notice=notice,
        )
