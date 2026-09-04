"""Prioritisation rules: what the SL-target mandates, what enables what, what it costs.

The three inputs prioritisation is not allowed to invent: SL mandates (at which SL
of which FR an SR becomes required, making a capability Tier 0 in a zone),
dependencies (a partial order — what cannot go before what) and ordinal cost
(three-level, no euros: comparing levels is legitimate, adding them is not).

Data, not AI, validated against the catalog: a mandate can only name existing
controls, the dependency graph must be acyclic, and every capability must carry a
declared cost (an undeclared cost would be a silent default deciding a roadmap).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.catalog.schemas import Catalog, Framework
from app.core.config import settings
from app.engine.rules import BACKEND_ROOT, RuleProvenance
from app.engine.schemas import FoundationalRequirement, OrdinalLevel


class SLMandate(BaseModel):
    """The SL at which a control stops being optional, on the FR it belongs to."""

    model_config = ConfigDict(extra="forbid")

    control_id: str
    foundational_requirement: FoundationalRequirement
    required_at_sl: int = Field(ge=1, le=4)
    rationale: str
    provenance: RuleProvenance | None = None

    def mandates_at(self, zone_sl_target: int) -> bool:
        return zone_sl_target >= self.required_at_sl


class CapabilityDependency(BaseModel):
    """Declared technical enablement: this capability presupposes those."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str
    requires: list[str] = Field(min_length=1)
    rationale: str
    provenance: RuleProvenance | None = None

    @model_validator(mode="after")
    def _check_not_self_referential(self) -> CapabilityDependency:
        if self.capability_id in self.requires:
            raise ValueError(f"dependency {self.capability_id} requires itself")
        if len(set(self.requires)) != len(self.requires):
            raise ValueError(f"dependency {self.capability_id} repeats a prerequisite")
        return self


class CapabilityCost(BaseModel):
    """Ordinal implementation cost of a capability, with its written justification."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str
    cost: OrdinalLevel
    rationale: str
    provenance: RuleProvenance | None = None


class PrioritizationRules(BaseModel):
    """Versioned prioritisation rule set (mandates, dependencies and ordinal cost)."""

    model_config = ConfigDict(extra="ignore")

    rules_version: str
    scope_note: str | None = None
    principles: list[str] = Field(default_factory=list)
    sl_mandates: list[SLMandate] = Field(default_factory=list)
    dependencies: list[CapabilityDependency] = Field(default_factory=list)
    costs: list[CapabilityCost] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_internal_consistency(self) -> PrioritizationRules:
        for label, ids in (
            ("sl_mandates", [m.control_id for m in self.sl_mandates]),
            ("dependencies", [d.capability_id for d in self.dependencies]),
            ("costs", [c.capability_id for c in self.costs]),
        ):
            if len(set(ids)) != len(ids):
                raise ValueError(f"{label} declares the same entry twice")

        cycle = _find_cycle({d.capability_id: sorted(d.requires) for d in self.dependencies})
        if cycle:
            raise ValueError(f"dependency cycle: {' -> '.join(cycle)}")
        return self

    def mandate_for(self, control_id: str) -> SLMandate | None:
        for mandate in self.sl_mandates:
            if mandate.control_id == control_id:
                return mandate
        return None

    def requires(self, capability_id: str) -> list[str]:
        """Prerequisites of a capability, in deterministic order."""
        for dependency in self.dependencies:
            if dependency.capability_id == capability_id:
                return sorted(dependency.requires)
        return []

    def unlocks(self, capability_id: str) -> list[str]:
        """Capabilities that declare this one as a prerequisite — its leverage."""
        return sorted(d.capability_id for d in self.dependencies if capability_id in d.requires)

    def cost_for(self, capability_id: str) -> OrdinalLevel:
        for declared in self.costs:
            if declared.capability_id == capability_id:
                return declared.cost
        raise KeyError(f"capability without a declared ordinal cost: {capability_id}")

    def validate_against(self, catalog: Catalog) -> None:
        """A rule may only speak of what the catalog has — and must cost every capability."""
        for mandate in self.sl_mandates:
            control = next((c for c in catalog.controls if c.id == mandate.control_id), None)
            if control is None:
                raise ValueError(
                    f"sl mandate references a non-existent control: {mandate.control_id}"
                )
            if control.framework is not Framework.IEC62443:
                raise ValueError(
                    f"sl mandate {mandate.control_id}: the SL-target is an IEC 62443 scale, "
                    f"it cannot be declared over a {control.framework.value} control"
                )

        capability_ids = catalog.capability_ids
        for dependency in self.dependencies:
            for capability_id in [dependency.capability_id, *dependency.requires]:
                if capability_id not in capability_ids:
                    raise ValueError(
                        f"dependency {dependency.capability_id} references a non-existent "
                        f"capability: {capability_id}"
                    )

        for declared in self.costs:
            if declared.capability_id not in capability_ids:
                raise ValueError(
                    f"cost references a non-existent capability: {declared.capability_id}"
                )
        undeclared = sorted(capability_ids - {c.capability_id for c in self.costs})
        if undeclared:
            raise ValueError(f"capabilities without a declared ordinal cost: {undeclared}")


def _find_cycle(graph: dict[str, list[str]]) -> list[str]:
    """Return one cycle of the dependency graph, or an empty list if it is a DAG."""
    visiting: set[str] = set()
    done: set[str] = set()

    def walk(node: str, trail: list[str]) -> list[str]:
        if node in done:
            return []
        if node in visiting:
            return [*trail[trail.index(node) :], node]
        visiting.add(node)
        for prerequisite in graph.get(node, []):
            cycle = walk(prerequisite, [*trail, node])
            if cycle:
                return cycle
        visiting.discard(node)
        done.add(node)
        return []

    for node in sorted(graph):
        cycle = walk(node, [])
        if cycle:
            return cycle
    return []


def load_prioritization_rules(path: str | Path | None = None) -> PrioritizationRules:
    """Read and validate the prioritisation rules. Raises if the JSON or its integrity fail."""
    raw = Path(path) if path is not None else Path(settings.PRIORITIZATION_PATH)
    if not raw.is_absolute():
        raw = BACKEND_ROOT / raw
    data = json.loads(raw.read_text(encoding="utf-8"))
    return PrioritizationRules.model_validate(data)


@lru_cache
def get_prioritization_rules() -> PrioritizationRules:
    """Cached prioritisation rules (a single load per process)."""
    return load_prioritization_rules()
