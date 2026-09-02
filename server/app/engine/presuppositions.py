"""UCM-53 - A control whose declared premise the zone does not meet is not applicable here.

The gap this closes is one of arithmetic. The profile has always known that a
zone hosts no general-purpose OS — `parse` reads the negation out of the
operator's description and the operator confirms it, per zone. The catalog never
knew that a control *needs* one. With only one side of the comparison declared
there was nothing to compare, so the discrimination rested entirely on the
hand-written rule set: 108 of 226 controls named by a rule, and the other 118
retained identically for every asset (UCM-55).

`FrameworkControl.presupposes` supplies the missing side, and this module is the
comparison. It is deliberately *the same operation as gating*, and it reuses the
gating machinery rather than inventing one — like sectoral applicability
(UCM-47), an unmet premise becomes a `GatingDecision` with the `NOT_APPLICABLE`
outcome, carrying a rule id, the premise observed on the profile and a written
justification. Nothing is dropped in silence.

Three asymmetries keep the direction of the check safe:

* **No declared premise excludes nothing.** A control with an empty
  `presupposes` is retained in every zone, exactly as it was before the field
  existed. Absence of a premise is not a premise.
* **An authored rule always wins.** When a hand-written gating rule already
  fires on the control, that rule decides and this determination is recorded in
  `also_matched_rule_ids`. A human who wrote a rule for this control by name
  knew more than a premise derived from its description does, and the engine
  must not overrule them — but neither may it forget what it saw.
* **It removes mechanisms, never capabilities.** As with every other gating
  outcome, the requirement behind the control stays required; what leaves is
  this way of meeting it, with its reason attached.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.catalog.schemas import FrameworkControl, Presupposition
from app.core.wording import say
from app.engine.schemas import GatingDecision, GatingOutcome, ZoneContext

# The declared "rule" of a premise exclusion. Like `APPLIC-SECTOR`, it lives on
# the control (`presupposes`) rather than in the gating JSON, so one constant
# names the determination and the evidence names the premises that made it fire.
PREMISE_RULE_ID = "GATE-PREMISE-UNMET"


def unmet_premises(control: FrameworkControl, zone: ZoneContext) -> list[Presupposition]:
    """The premises this control needs that the zone declares otherwise.

    Empty for a control that declares none, which is most of the catalog, and
    empty for a zone that meets all of them.
    """
    return [
        premise
        for premise in control.presupposes
        if getattr(zone.nature, premise.premise.value) is not premise.expected
    ]


def presupposition_decision(
    control: FrameworkControl,
    capability_id: str,
    zone: ZoneContext,
    also_matched_rule_ids: Iterable[str] = (),
) -> GatingDecision | None:
    """A justified `NOT_APPLICABLE` exclusion when a declared premise is unmet.

    Returns `None` when every premise holds — including the vacuous case of a
    control that declares none — so the caller keeps the mechanism.
    """
    unmet = unmet_premises(control, zone)
    if not unmet:
        return None

    return GatingDecision(
        zone_id=zone.zone_id,
        capability_id=capability_id,
        control_id=control.id,
        outcome=GatingOutcome.NOT_APPLICABLE,
        rule_id=PREMISE_RULE_ID,
        rationale=_rationale(control, zone, unmet),
        evidence=_evidence(zone, unmet),
        also_matched_rule_ids=list(also_matched_rule_ids),
    )


def _rationale(
    control: FrameworkControl, zone: ZoneContext, unmet: list[Presupposition]
) -> str:
    # The catalog author's own sentence, which is the whole reason `note` is a
    # required field: it says what the mechanism needs, in the words of whoever
    # reviewed it, rather than in a phrase this function made up.
    notes = " ".join(premise.note.rstrip(".") + "." for premise in unmet)
    missing = ", ".join(say(premise.premise.value) for premise in unmet)
    return (
        f"{control.official_id} no es aplicable en la zona {zone.zone_id}: presupone "
        f"{missing}, y el perfil declara lo contrario para esta zona. {notes} "
        f"Exclusión justificada por premisa declarada del control (regla {PREMISE_RULE_ID}). "
        "Es un entregable de la baseline —lo que se dejó fuera y por qué—, no un hueco: se "
        "retira este mecanismo, nunca la capacidad, que si otra norma la exige sigue exigida."
    )


def _evidence(zone: ZoneContext, unmet: list[Presupposition]) -> list[str]:
    """The premises that made it fire, read off the profile as sentences."""
    return [
        f"el control presupone que la zona {'tiene' if premise.expected else 'no tiene'} "
        f"{say(premise.premise.value)}, y la zona declara lo contrario"
        for premise in unmet
    ]
