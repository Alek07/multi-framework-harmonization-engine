"""Gating rules: which mechanisms this asset cannot host, and why.

Data, not AI: applicability is decided by premises the zone declares
(`Zone.nature`) and the zone reading, never by the LLM. Versioned and validated
against the catalog, so a rule can never gate a control that does not exist.
The schema enforces "never silently": a wrong-scope rule must name its layer, an
objective-without-mechanism rule must state the compensation it owes.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.assets.schemas import TechNature
from app.catalog.schemas import Catalog
from app.core.config import settings
from app.core.wording import say
from app.engine.rules import BACKEND_ROOT, RuleProvenance
from app.engine.schemas import GatingOutcome, ZoneContext, ZoneDomain

# Order in which outcomes are considered when several rules fire on one control:
# wrong layer first, then missing premise, then orphaned objective.
OUTCOME_PRECEDENCE: dict[GatingOutcome, int] = {
    GatingOutcome.WRONG_SCOPE: 0,
    GatingOutcome.NOT_APPLICABLE: 1,
    GatingOutcome.OBJECTIVE_WITHOUT_MECHANISM: 2,
}


class GatingCondition(BaseModel):
    """When a rule fires. An empty condition means "always, in every zone".

    Only premises the profile declares are expressible: `TechNature` flags and
    the zone reading. The engine infers nothing else.
    """

    model_config = ConfigDict(extra="forbid")

    domains: list[ZoneDomain] = Field(default_factory=list)
    nature: dict[str, bool] = Field(default_factory=dict)
    safety_relevant: bool | None = None
    # The role the zone declares ("crown_jewel"), matched on the raw value so a
    # third asset can bring an unseen role. Distinct from `safety_relevant`, which
    # the engine concludes for the whole OT corridor: without this the SIS and the
    # corridor gate identically.
    roles: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_nature_flags(self) -> GatingCondition:
        unknown = sorted(set(self.nature) - set(TechNature.model_fields))
        if unknown:
            raise ValueError(f"condition references non-existent profile premises: {unknown}")
        self.roles = [role.strip().lower() for role in self.roles]
        return self

    def matches(self, zone: ZoneContext) -> bool:
        if self.domains and zone.domain not in self.domains:
            return False
        if self.safety_relevant is not None and zone.safety_relevant is not self.safety_relevant:
            return False
        if self.roles and zone.role not in self.roles:
            return False
        return all(
            getattr(zone.nature, flag) is expected for flag, expected in self.nature.items()
        )

    def evidence(self, zone: ZoneContext) -> list[str]:
        """The premises that made the rule fire, as read from the profile.

        A rule with no premises still says so: an exclusion never reaches the
        human with an empty justification.
        """
        if not (
            self.domains or self.nature or self.safety_relevant is not None or self.roles
        ):
            return ["se aplica siempre, sin condición sobre el activo"]

        # Sentences, not schema paths: this is the justification the operator sees
        # next to an excluded mechanism.
        found = [f"la zona es {say(zone.domain)}"] if self.domains else []
        if self.roles:
            found.append(f"la zona declara el rol «{zone.role}»")
        if self.safety_relevant is not None:
            found.append(
                "la zona es relevante para la seguridad de las personas"
                if zone.safety_relevant
                else "la zona no es relevante para la seguridad de las personas"
            )
        # "la zona", not "el activo": the premises are this zone's own — a hybrid
        # asset's neighbouring zone answers the same flag differently.
        found.extend(
            f"la zona {'tiene' if getattr(zone.nature, flag) else 'no tiene'} {say(flag)}"
            for flag in sorted(self.nature)
        )
        return found


class GatingRule(BaseModel):
    """A declared exclusion of mechanisms, with one of the three outcomes."""

    model_config = ConfigDict(extra="forbid")

    id: str
    outcome: GatingOutcome
    control_ids: list[str] = Field(min_length=1)
    applies_when: GatingCondition = Field(default_factory=GatingCondition)
    rationale: str
    # Owed by an objective-without-mechanism rule: what has to cover the outcome instead.
    compensation: str | None = None
    # Owed by a wrong-scope rule: where the requirement goes on being answered.
    deferred_to: str | None = None
    provenance: RuleProvenance | None = None

    @model_validator(mode="after")
    def _check_outcome_obligations(self) -> GatingRule:
        if self.outcome is GatingOutcome.OBJECTIVE_WITHOUT_MECHANISM and not self.compensation:
            raise ValueError(
                f"gating rule {self.id}: an objective without mechanism must declare the "
                "compensation it owes"
            )
        if self.outcome is GatingOutcome.WRONG_SCOPE and not self.deferred_to:
            raise ValueError(
                f"gating rule {self.id}: a wrong-scope rule must name the layer it defers to"
            )
        if self.outcome is not GatingOutcome.OBJECTIVE_WITHOUT_MECHANISM and self.compensation:
            raise ValueError(
                f"gating rule {self.id}: only an objective without mechanism owes a compensation"
            )
        return self

    def applies_to(self, control_id: str, zone: ZoneContext) -> bool:
        return control_id in self.control_ids and self.applies_when.matches(zone)


class GatingRules(BaseModel):
    """Versioned gating rule set (`GatingRules` of the data model, §7.3)."""

    model_config = ConfigDict(extra="ignore")

    rules_version: str
    scope_note: str | None = None
    principles: list[str] = Field(default_factory=list)
    rules: list[GatingRule] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_unique_ids(self) -> GatingRules:
        ids = [r.id for r in self.rules]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate gating rule IDs")
        return self

    def rules_for(self, control_id: str, zone: ZoneContext) -> list[GatingRule]:
        """Every rule that fires on the control, ordered by outcome precedence then
        rule ID — never by file position, so the outcome is ingestion-independent.
        The first decides; the rest stay recorded.
        """
        matched = [r for r in self.rules if r.applies_to(control_id, zone)]
        return sorted(matched, key=lambda r: (OUTCOME_PRECEDENCE[r.outcome], r.id))

    def validate_against(self, catalog: Catalog) -> None:
        """A rule may only gate controls the catalog actually has."""
        for rule in self.rules:
            for control_id in rule.control_ids:
                if control_id not in catalog.control_ids:
                    raise ValueError(
                        f"gating rule {rule.id} references a non-existent control: {control_id}"
                    )


def load_gating_rules(path: str | Path | None = None) -> GatingRules:
    """Read and validate the gating rules. Raises if the JSON or its integrity fail."""
    raw = Path(path) if path is not None else Path(settings.GATING_PATH)
    if not raw.is_absolute():
        raw = BACKEND_ROOT / raw
    data = json.loads(raw.read_text(encoding="utf-8"))
    return GatingRules.model_validate(data)


@lru_cache
def get_gating_rules() -> GatingRules:
    """Cached gating rules (a single load per process)."""
    return load_gating_rules()
