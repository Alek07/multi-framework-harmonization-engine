"""UCM-43/UCM-44 - What the catalog holds, and how the zones read it.

Two reports, printed side by side, both meant to be run *before* and *after* a
catalog or rules bump and pasted into the issue that made the change:

* **Content** — how much catalog there is, per framework and per mapping type,
  plus the integrity numbers the loader already enforces (orphan capabilities,
  unused controls). This is the "contenido escaso" measurement of UCM-43.
* **Tier balance** — for every zone of every frozen profile: how many
  capabilities land in Tier 0, how many in Tier 1, and *why* each Tier 0 is
  mandatory (SL-target, legal obligation, or both). A catalog bump can make
  everything mandatory without anyone noticing — a legal mapping is an
  unconditional Tier 0 regardless of its coverage weight — and a Tier 0 that
  swallows Tier 1 leaves the prioritisation of UCM-10 with nothing to order.

Neither report decides anything: it reads the same deterministic core the API
runs and counts it. Run from `server/`:

    uv run python scripts/catalog_report.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.assets.loader import available_profiles, get_profile  # noqa: E402
from app.catalog.loader import get_catalog  # noqa: E402
from app.engine.schemas import MandateSource, PriorityTier  # noqa: E402
from app.engine.service import prioritize_profile  # noqa: E402


def tally(counted: Counter[str]) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(counted.items()))


def content() -> None:
    catalog = get_catalog()
    print(f"== Catálogo v{catalog.catalog_version}")
    print(
        f"   capacidades={len(catalog.capabilities)} "
        f"controles={len(catalog.controls)} mapeos={len(catalog.mappings)}"
    )

    by_framework = Counter(c.framework.value for c in catalog.controls)
    print("   controles por marco: " + tally(by_framework))

    print(
        "   mapeos por tipo:     "
        + tally(Counter(m.mapping_type.value for m in catalog.mappings))
    )
    print(
        "   procedencia:         "
        + tally(Counter(m.provenance.source.value for m in catalog.mappings))
    )

    options = Counter(len(catalog.mappings_for(c.id)) for c in catalog.capabilities)
    single = sum(n for offered, n in options.items() if offered < 2)
    print(f"   capacidades con una sola opción: {single}/{len(catalog.capabilities)}")
    print(
        f"   huérfanas={len(catalog.orphan_capabilities())} "
        f"sin usar={len(catalog.unused_controls())}"
    )


def tier_balance() -> None:
    catalog = get_catalog()
    total = len(catalog.capabilities)
    print("\n== Balance de tiers por zona")

    for profile_id in available_profiles():
        result = prioritize_profile(get_profile(profile_id))
        for zone in result.zones:
            tier_0 = [c for c in zone.capabilities if c.tier is PriorityTier.TIER_0]
            tier_1 = [c for c in zone.capabilities if c.tier is PriorityTier.TIER_1]
            sources = Counter(m.source for c in tier_0 for m in c.mandates)
            only_legal = [
                c.capability_id
                for c in tier_0
                if all(m.source is MandateSource.LEGAL_OBLIGATION for m in c.mandates)
            ]
            phases = sorted({c.phase for c in tier_1})

            share = 100 * len(tier_0) / total if total else 0
            print(f"\n   {profile_id} / {zone.zone.zone_id}")
            print(f"      tier 0 = {len(tier_0)}/{total} ({share:.0f}%) · tier 1 = {len(tier_1)}")
            print(
                "      mandatos: "
                + ", ".join(f"{k.value}={v}" for k, v in sorted(sources.items(), key=str))
            )
            print(f"      tier 0 sólo por obligación legal: {len(only_legal)} {sorted(only_legal)}")
            print(f"      fases tier 1 pobladas: {phases}")
            print(f"      mandatos abiertos (outstanding): {len(zone.outstanding_mandates)}")


if __name__ == "__main__":
    content()
    tier_balance()
