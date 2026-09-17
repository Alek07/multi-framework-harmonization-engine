"""How much of the catalog the gating looks at, and how much the profile changes.

Discrimination of controls per asset rests on the gating alone: retrieval applies
no lens of its own and the parse always delivers a complete `nature` per zone. So
if two very different assets come out with nearly the same baseline, the gating
rule set is the ceiling -- and this measures that with numbers instead of
impressions.

Three readings, meant to be run before and after a gating bump:

* Reach -- how many catalog controls no rule ever names (retained identically in
  every zone of every profile, whatever the asset is).
* Outcome per zone -- how each control ends up in each zone: retained, or excluded
  with one of the three declared outcomes.
* Discrimination -- for each pair of zones, how many controls end up with a
  different outcome; the engine's answer to "does the asset change the baseline?".

Run from `server/`:

    uv run python scripts/gating_report.py
"""

from __future__ import annotations

import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.assets.loader import available_profiles, get_profile  # noqa: E402
from app.catalog.loader import get_catalog  # noqa: E402
from app.engine.gating_rules import get_gating_rules  # noqa: E402
from app.engine.service import gate_profile  # noqa: E402

RETAINED = "retenido"


def outcomes_by_zone() -> dict[str, dict[str, str]]:
    """`{zone_id: {control_id: outcome}}` over every catalog control, per zone.

    A control can be mapped to several capabilities and be excluded in one of
    them and kept in another; what the operator sees on the zone's baseline is
    whether the mechanism survived *anywhere*, so that is what is reported here.
    """
    catalog = get_catalog()
    per_zone: dict[str, dict[str, str]] = {}

    for profile_id in available_profiles():
        gating = gate_profile(get_profile(profile_id))
        for zone in gating.zones:
            retained = {
                control_id
                for capability in zone.capabilities
                for control_id in (
                    *capability.retained_control_ids,
                    *capability.compensatory_control_ids,
                )
            }
            excluded: dict[str, str] = {}
            for decision in zone.decisions:
                excluded.setdefault(decision.control_id, decision.outcome.value)

            per_zone[f"{profile_id}/{zone.zone.zone_id}"] = {
                control.id: RETAINED
                if control.id in retained
                else excluded.get(control.id, RETAINED)
                for control in catalog.controls
            }
    return per_zone


def reach() -> None:
    catalog = get_catalog()
    rules = get_gating_rules()
    named = {control_id for rule in rules.rules for control_id in rule.control_ids}

    print(
        f"== Alcance del gating v{rules.rules_version} "
        f"sobre el catálogo v{catalog.catalog_version}"
    )
    print(f"   reglas={len(rules.rules)}")
    print(
        f"   controles nombrados por alguna regla: {len(named)}/{len(catalog.controls)} "
        f"({100 * len(named) / len(catalog.controls):.0f}%)"
    )
    print(f"   controles que ninguna regla mira:    {len(catalog.control_ids - named)}")

    by_outcome = Counter(rule.outcome.value for rule in rules.rules)
    print("   reglas por salida: " + ", ".join(f"{k}={v}" for k, v in sorted(by_outcome.items())))

    unconditional = [
        r.id for r in rules.rules if not r.applies_when.model_dump(exclude_defaults=True)
    ]
    print(f"   reglas sin condición sobre el activo: {len(unconditional)} {unconditional}")


def premises() -> None:
    """What the catalog itself declares, beside what the rules name.

    Two different things exclude a mechanism and the report keeps them apart: a
    rule naming the control, and a premise the control declares about the zone it
    needs. The number that matters is the last printed -- controls that neither
    looks at, still retained identically for every asset.
    """
    catalog = get_catalog()
    rules = get_gating_rules()
    named = {control_id for rule in rules.rules for control_id in rule.control_ids}
    declaring = {c.id for c in catalog.controls if c.presupposes}
    total = len(catalog.controls)

    print()
    print(f"== Premisas declaradas en el catálogo v{catalog.catalog_version}")
    print(
        f"   controles que declaran alguna premisa: {len(declaring)}/{total} "
        f"({100 * len(declaring) / total:.0f}%)"
    )

    by_premise = Counter(p.premise.value for c in catalog.controls for p in c.presupposes)
    if by_premise:
        print(
            "   premisas por tipo: "
            + ", ".join(f"{k}={v}" for k, v in by_premise.most_common())
        )
        by_framework = Counter(c.framework.value for c in catalog.controls if c.presupposes)
        print(
            "   controles con premisa por marco: "
            + ", ".join(f"{k}={v}" for k, v in by_framework.most_common())
        )
    else:
        print("   (ninguna: el catálogo todavía no ha sido etiquetado)")

    print(f"   controles que solo la premisa mira:      {len(declaring - named)}")
    print(
        "   controles que ni regla ni premisa miran: "
        f"{len(catalog.control_ids - named - declaring)}"
    )

def discrimination() -> None:
    per_zone = outcomes_by_zone()
    total = len(next(iter(per_zone.values())))

    print("\n== Salidas por zona")
    for zone_id, outcomes in per_zone.items():
        counts = Counter(outcomes.values())
        print(f"   {zone_id:30} " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    print("\n== Discriminación (controles que cambian de salida entre zonas)")
    for a, b in combinations(per_zone, 2):
        differing = [c for c in per_zone[a] if per_zone[a][c] != per_zone[b][c]]
        print(f"   {a:30} vs {b:30} {len(differing):3}/{total}")
        if differing:
            print(f"      {sorted(differing)}")


if __name__ == "__main__":
    reach()
    premises()
    discrimination()
