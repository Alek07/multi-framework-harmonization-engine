"""Precedence rules and declared contradictions (engine policy).

How the engine settles a clash — zone precedence and author-declared
contradictions — kept apart from the catalog and validated against it. Data, not
AI: the LLM never resolves a conflict (invariant 1) and the outcome is
reproducible (invariant 3).
"""

from __future__ import annotations

import json
from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.catalog.schemas import Catalog, Framework, ProvenanceSource
from app.core.config import settings
from app.engine.schemas import ZoneDomain

# app/engine/rules.py -> parents[2] == backend root (server/)
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class ResolutionStrategy(str, Enum):
    """How a declared contradiction is settled."""

    # Zone context decides which mechanism prevails (never the most restrictive).
    FRAMEWORK_PRECEDENCE = "framework_precedence"
    # OT safety override: the engine does not settle it, the human does.
    SAFETY_OVERRIDE = "safety_override"


class RuleProvenance(BaseModel):
    """Where a rule comes from. Traces the author's judgment; it never decides."""

    model_config = ConfigDict(extra="forbid")

    source: ProvenanceSource
    note: str = ""


class Contradiction(BaseModel):
    """A real contradiction between mechanisms of the same capability."""

    model_config = ConfigDict(extra="forbid")

    id: str
    capability_id: str
    control_ids: list[str] = Field(min_length=2)
    applies_to_domains: list[ZoneDomain] = Field(min_length=1)
    requires_safety_relevant_zone: bool = False
    resolution: ResolutionStrategy
    rationale: str
    provenance: RuleProvenance | None = None

    def applies_to(self, domain: ZoneDomain, safety_relevant: bool) -> bool:
        if domain not in self.applies_to_domains:
            return False
        return safety_relevant if self.requires_safety_relevant_zone else True


class RuleSet(BaseModel):
    """Versioned rule set: precedence per zone domain + declared contradictions."""

    model_config = ConfigDict(extra="ignore")

    rules_version: str
    scope_note: str | None = None
    principles: list[str] = Field(default_factory=list)
    framework_precedence: dict[ZoneDomain, list[Framework]]
    framework_precedence_rationale: dict[ZoneDomain, str] = Field(default_factory=dict)
    contradictions: list[Contradiction] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_internal_consistency(self) -> RuleSet:
        missing = [d for d in ZoneDomain if d not in self.framework_precedence]
        if missing:
            raise ValueError(
                f"framework_precedence lacks zone domains: {sorted(m.value for m in missing)}"
            )
        for domain, order in self.framework_precedence.items():
            absent = [f for f in Framework if f not in order]
            if absent:
                raise ValueError(
                    f"framework_precedence[{domain.value}] must be a total order; "
                    f"missing: {sorted(f.value for f in absent)}"
                )
            if len(set(order)) != len(order):
                raise ValueError(f"framework_precedence[{domain.value}] repeats a framework")

        ids = [c.id for c in self.contradictions]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate contradiction IDs")
        return self

    def precedence_index(self, domain: ZoneDomain, framework: Framework) -> int:
        """Position of a framework in the zone's order (lower = prevails)."""
        return self.framework_precedence[domain].index(framework)

    def contradictions_for(
        self, capability_id: str, domain: ZoneDomain, safety_relevant: bool
    ) -> list[Contradiction]:
        return [
            c
            for c in self.contradictions
            if c.capability_id == capability_id and c.applies_to(domain, safety_relevant)
        ]

    def validate_against(self, catalog: Catalog) -> None:
        """A rule may only name capabilities/controls the catalog actually has."""
        for c in self.contradictions:
            if c.capability_id not in catalog.capability_ids:
                raise ValueError(
                    f"contradiction {c.id} references a non-existent capability: {c.capability_id}"
                )
            mapped = {m.control_id for m in catalog.mappings_for(c.capability_id)}
            for control_id in c.control_ids:
                if control_id not in catalog.control_ids:
                    raise ValueError(
                        f"contradiction {c.id} references a non-existent control: {control_id}"
                    )
                if control_id not in mapped:
                    raise ValueError(
                        f"contradiction {c.id}: control {control_id} is not mapped to "
                        f"capability {c.capability_id}"
                    )


def load_rules(path: str | Path | None = None) -> RuleSet:
    """Read and validate the rule set. Raises if the JSON or its integrity fail."""
    raw = Path(path) if path is not None else Path(settings.RULES_PATH)
    if not raw.is_absolute():
        raw = BACKEND_ROOT / raw
    data = json.loads(raw.read_text(encoding="utf-8"))
    return RuleSet.model_validate(data)


@lru_cache
def get_rules() -> RuleSet:
    """Cached rule set (a single load per process)."""
    return load_rules()
