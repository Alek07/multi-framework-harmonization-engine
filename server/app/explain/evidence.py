"""UCM-14 - What the model is allowed to know, and what is said when it says nothing.

Everything the explanation layer can be right about is assembled here, before any
token is generated, from data that already exists: the versioned catalog, the
core's resolution (UCM-8) and the retrieval pass (UCM-13). Three jobs, all
deterministic:

1. **Order the candidates** exactly as the operator will see them —
   `offered_control_ids`, catalog first, then the retrieved suggestions. The
   model receives them in that order and returns them in that order; it is never
   in a position to rank.
2. **Declare, per candidate, which facts may be cited** (`EvidenceKey`). A
   catalog candidate has an authored mapping, a type, a weight and a provenance;
   a retrieved one has a similarity and the capabilities it is mapped to
   elsewhere. Handing the model that list is how "cite only what is written down"
   becomes checkable: a citation outside it is caught by the service.
3. **Write the fallback**. Every candidate has readable text *before* the model
   runs — the mapping in the operator's language, or the retrieval's own
   rationale. That text is what stays on screen when the layer is off, unreachable
   or withheld, which is what makes a P1 feature unable to damage P0.

The fact sheet is Spanish because the model writes Spanish for the operator, and
its shape is fixed: same inputs, same sheet, so the same prompt reaches the model
on every machine (invariant 3).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.catalog.schemas import (
    Capability,
    Framework,
    FrameworkControl,
    Jurisdiction,
    Mapping,
    MappingType,
)
from app.engine.schemas import CandidateOption, CandidateStatus, CapabilityResolution, ZoneContext
from app.explain.schemas import CandidateOrigin, EvidenceKey
from app.retrieval.schemas import CapabilityRetrieval, RetrievedControl

# Evidence every candidate carries, whatever its origin: the control is in the
# catalog, so its framework, jurisdiction, strength and paraphrase are all facts.
COMMON_EVIDENCE: tuple[EvidenceKey, ...] = (
    EvidenceKey.FRAMEWORK,
    EvidenceKey.JURISDICTION,
    EvidenceKey.STRENGTH,
    EvidenceKey.CONTROL_TEXT,
)


@dataclass(frozen=True)
class CandidateFacts:
    """One candidate as the explanation layer sees it: identity, facts, fallback."""

    control: FrameworkControl
    origin: CandidateOrigin
    # The authored mapping, for a catalog candidate. `None` for a retrieved one —
    # and that absence is the point: a suggestion is not a mapping.
    mapping: Mapping | None = None
    status: CandidateStatus | None = None
    status_reason: str | None = None
    # Cosine similarity, when retrieval saw this control for this capability. A
    # catalog candidate that retrieval also returned (a confirmation) has one too.
    score: float | None = None
    # Where a retrieved control does its declared work in the catalog.
    mapped_capability_ids: tuple[str, ...] = ()
    mapping_types: tuple[MappingType, ...] = ()
    allowed: tuple[EvidenceKey, ...] = ()
    # Deterministic text, written by the engine, shown whenever the model's is not.
    fallback: str = ""

    @property
    def control_id(self) -> str:
        return self.control.id

    @property
    def official_id(self) -> str:
        return self.control.official_id

    @property
    def framework(self) -> Framework:
        return self.control.framework

    @property
    def jurisdiction(self) -> Jurisdiction:
        return self.control.jurisdiction


@dataclass(frozen=True)
class CapabilityFacts:
    """The whole prompt input for one capability in one zone, already ordered."""

    capability: Capability
    zone_id: str
    zone: ZoneContext | None = None
    candidates: tuple[CandidateFacts, ...] = field(default_factory=tuple)

    @property
    def offered_control_ids(self) -> list[str]:
        return [candidate.control_id for candidate in self.candidates]

    def candidate(self, control_id: str) -> CandidateFacts | None:
        for candidate in self.candidates:
            if candidate.control_id == control_id:
                return candidate
        return None


def facts_for(
    resolution: CapabilityResolution,
    retrieval: CapabilityRetrieval,
    zone: ZoneContext | None = None,
) -> CapabilityFacts:
    """Assemble the citable facts of every candidate, in the order they are offered.

    The two inputs have to describe the same capability in the same zone: an
    explanation written from one capability's retrieval over another's resolution
    would be fluent and wrong, which is the failure mode this whole POC is built
    to make impossible.
    """
    if resolution.capability.id != retrieval.capability_id:
        raise ValueError(
            f"the resolution is for {resolution.capability.id} and the retrieval for "
            f"{retrieval.capability_id}"
        )
    if resolution.zone_id != retrieval.zone_id:
        raise ValueError(
            f"the resolution is for zone {resolution.zone_id} and the retrieval for "
            f"{retrieval.zone_id}"
        )

    options = {option.control_id: option for option in resolution.options}
    confirmations = {hit.control_id: hit for hit in retrieval.confirmations}

    candidates: list[CandidateFacts] = []
    for control_id in retrieval.catalog_control_ids:
        option = options.get(control_id)
        if option is None:
            raise ValueError(
                f"{control_id} is offered by the retrieval of {retrieval.capability_id} but the "
                "resolution holds no option for it"
            )
        candidates.append(_from_catalog(option, resolution, confirmations.get(control_id), zone))

    for hit in retrieval.widening:
        candidates.append(_from_retrieval(hit, zone))

    return CapabilityFacts(
        capability=resolution.capability,
        zone_id=resolution.zone_id,
        zone=zone,
        candidates=tuple(candidates),
    )


# --- per-candidate assembly ---------------------------------------------------


def _from_catalog(
    option: CandidateOption,
    resolution: CapabilityResolution,
    confirmation: RetrievedControl | None,
    zone: ZoneContext | None,
) -> CandidateFacts:
    allowed = [
        EvidenceKey.CATALOG_MAPPING,
        EvidenceKey.MAPPING_TYPE,
        EvidenceKey.COVERAGE_WEIGHT,
        EvidenceKey.MAPPING_PROVENANCE,
        *COMMON_EVIDENCE,
    ]
    if option.status is not CandidateStatus.ELIGIBLE:
        allowed.append(EvidenceKey.CANDIDATE_STATUS)
    if confirmation is not None:
        allowed.append(EvidenceKey.SIMILARITY)
    if zone is not None:
        allowed.append(EvidenceKey.ZONE_CONTEXT)

    return CandidateFacts(
        control=option.control,
        origin=CandidateOrigin.CATALOG,
        mapping=option.mapping,
        status=option.status,
        status_reason=option.status_reason,
        score=confirmation.score if confirmation is not None else None,
        allowed=tuple(allowed),
        fallback=_catalog_fallback(option, resolution),
    )


def _from_retrieval(hit: RetrievedControl, zone: ZoneContext | None) -> CandidateFacts:
    allowed = [EvidenceKey.SIMILARITY, *COMMON_EVIDENCE]
    if hit.mapped_capability_ids:
        allowed.append(EvidenceKey.NEIGHBOURING_MAPPING)
    if zone is not None:
        allowed.append(EvidenceKey.ZONE_CONTEXT)

    return CandidateFacts(
        control=hit.control,
        origin=CandidateOrigin.RETRIEVAL,
        score=hit.score,
        mapped_capability_ids=tuple(hit.mapped_capability_ids),
        mapping_types=tuple(hit.mapping_types),
        allowed=tuple(allowed),
        # The retrieval already wrote why this control is on screen, with its
        # similarity and its declared limits. Rewriting it here would be a second
        # source of truth for the same sentence.
        fallback=hit.rationale,
    )


def _catalog_fallback(option: CandidateOption, resolution: CapabilityResolution) -> str:
    """The mapping, said plainly. No model involved, so it is always available."""
    mapping = option.mapping
    control = option.control
    provenance = mapping.provenance
    text = (
        f"Candidato del catálogo: {control.official_id} ({control.framework.value}, "
        f"{control.jurisdiction.value}) está mapeado a «{resolution.capability.name}» con un "
        f"mapeo {mapping.mapping_type.value} de peso {mapping.coverage_weight:g}, procedencia "
        f"{provenance.source.value} ({provenance.jurisdiction.value})."
    )
    if option.status is not CandidateStatus.ELIGIBLE:
        text += f" El núcleo lo marcó como {option.status.value}"
        text += f": {option.status_reason}" if option.status_reason else "."
    return text


# --- the fact sheet the model reads -------------------------------------------


def fact_sheet(facts: CapabilityFacts) -> str:
    """Render the candidates for the prompt. Deterministic, ordered, Spanish."""
    lines = [
        f"CAPACIDAD: {facts.capability.id} — {facts.capability.name}",
        f"  descripción: {facts.capability.description}",
    ]
    if facts.capability.ot_refinements:
        lines.append(f"  matices OT: {'; '.join(facts.capability.ot_refinements)}")
    lines.append(_zone_line(facts))
    lines.append("")

    for position, candidate in enumerate(facts.candidates, start=1):
        lines.extend(_candidate_lines(position, candidate))
        lines.append("")
    return "\n".join(lines).rstrip()


def _zone_line(facts: CapabilityFacts) -> str:
    if facts.zone is None:
        return f"ZONA: {facts.zone_id}"
    zone = facts.zone
    safety = "sí" if zone.safety_relevant else "no"
    return (
        f"ZONA: {zone.zone_id} (dominio {zone.domain.value}, SL objetivo {zone.target_sl}, "
        f"relevante para seguridad física: {safety})"
    )


def _candidate_lines(position: int, candidate: CandidateFacts) -> list[str]:
    control = candidate.control
    lines = [
        f"CANDIDATO {position} [origen={candidate.origin.value}] control_id={control.id}",
        f"  identificador oficial: {control.official_id} — {control.title}",
        f"  marco: {control.framework.value} · jurisdicción: {control.jurisdiction.value} · "
        f"fuerza: {control.strength} · tipo: {control.control_type.value}",
        f"  paráfrasis: {control.paraphrased_description}",
    ]

    if candidate.mapping is not None:
        mapping = candidate.mapping
        provenance = mapping.provenance
        lines.append(
            f"  mapeo del catálogo: tipo={mapping.mapping_type.value} "
            f"peso={mapping.coverage_weight:g} procedencia={provenance.source.value} "
            f"({provenance.jurisdiction.value})"
        )
        if provenance.note:
            lines.append(f"  nota de procedencia: {provenance.note}")
    else:
        lines.append("  mapeo del catálogo: ninguno para esta capacidad (es una sugerencia)")

    if candidate.mapped_capability_ids:
        types = ", ".join(sorted({t.value for t in candidate.mapping_types}))
        lines.append(
            f"  mapeado en el catálogo a: {', '.join(candidate.mapped_capability_ids)}"
            + (f" (tipos: {types})" if types else "")
        )

    if candidate.score is not None:
        lines.append(f"  similitud con el texto de la capacidad: {candidate.score:.3f}")

    if candidate.status is not None and candidate.status is not CandidateStatus.ELIGIBLE:
        reason = f" — {candidate.status_reason}" if candidate.status_reason else ""
        lines.append(f"  estado según el núcleo determinista: {candidate.status.value}{reason}")

    lines.append(f"  evidencia citable: {', '.join(key.value for key in candidate.allowed)}")
    return lines
