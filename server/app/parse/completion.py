"""UCM-12 - From draft to `AssetProfile`: the deterministic half of the parse.

Everything here runs without the model. It answers two questions the LLM is not
allowed to answer:

* **What is still missing?** `missing_required` walks the draft against
  `AssetProfile` (UCM-7) and names, path by path, every value the core needs and
  the text did not give. The list is what the operator is asked to fill in — and
  the reason the parse never has to guess a target SL to return something.
* **Is this reviewed profile admissible?** `to_profile` builds the real
  `AssetProfile` from a draft the operator has corrected, and refuses if anything
  is still absent. There is no partial promotion and no default value: a profile
  with an invented SL would run through the core and produce a baseline nobody
  decided.

The paths are written the way the operator reads them (`zones[Z-SIS].target_sl`)
because they are what the UI puts next to the empty field, and what the audit log
records as the gap the human closed.
"""

from __future__ import annotations

import re
import unicodedata

from app.assets.schemas import AssetProfile
from app.core.exceptions import AppException
from app.parse.schemas import AssetProfileDraft, SLVectorDraft, TechNatureDraft, ZoneDraft

FR_FIELDS = ("FR1", "FR2", "FR3", "FR4", "FR5", "FR6", "FR7")

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


class IncompleteDraftError(AppException):
    """A draft was promoted to a profile with required values still missing."""

    status_code = 422

    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__("El perfil no está completo: " + ", ".join(missing))


def profile_id_for(draft: AssetProfileDraft, explicit: str | None = None) -> str:
    """Identifier of the parsed asset: the caller's, or a slug of the model's name.

    Derived rather than asked of the model: an id is a key, not an observation
    about the asset, and the same draft must always land on the same one. Accents
    are folded rather than replaced — this identifier is read back in the audit
    log, and `ESTACI-N` would be nobody's asset.
    """
    if explicit:
        return explicit
    folded = unicodedata.normalize("NFKD", draft.name or "").encode("ascii", "ignore").decode()
    slug = _NON_ALNUM.sub("-", folded.upper()).strip("-")
    return f"ASSET-{slug}" if slug else "ASSET"


def _missing_sl_vector(vector: SLVectorDraft, prefix: str) -> list[str]:
    """An SL vector is all seven FRs or none: a half vector is a gap, not a value."""
    present = [fr for fr in FR_FIELDS if getattr(vector, fr) is not None]
    if not present:
        return []
    return [f"{prefix}.sl_vector.{fr}" for fr in FR_FIELDS if getattr(vector, fr) is None]


def _missing_in_zone(zone: ZoneDraft, index: int) -> list[str]:
    prefix = f"zones[{zone.id or index}]"
    missing = [] if zone.target_sl is not None else [f"{prefix}.target_sl"]
    # Asked once per zone: gating reads these premises from the zone, so a zone
    # left without them is a zone the core cannot gate (UCM-9).
    missing += [
        f"{prefix}.nature.{field}"
        for field in TechNatureDraft.model_fields
        if getattr(zone.nature, field) is None
    ]
    if zone.sl_vector is not None:
        missing += _missing_sl_vector(zone.sl_vector, prefix)
    return missing


def missing_required(draft: AssetProfileDraft) -> list[str]:
    """Paths of every value `AssetProfile` requires and the draft does not have.

    Deterministic and total: the same draft always yields the same list, in
    document order, so two runs of the parse are comparable field by field.
    """
    missing: list[str] = []

    if not draft.name:
        missing.append("name")
    if draft.case is None:
        missing.append("case")
    # Asked of the operator, never guessed (UCM-47): the core runs without it —
    # an empty list simply excludes nothing by sector — but a sectoral norm
    # offered to the wrong asset is a false obligation, so the reviewed profile
    # declares at least one. Per-zone sectors stay optional: they only override.
    if not draft.sectors:
        missing.append("sectors")

    if not draft.zones:
        missing.append("zones")
    for index, zone in enumerate(draft.zones):
        missing += _missing_in_zone(zone, index)

    for index, conduit in enumerate(draft.conduits):
        prefix = f"conduits[{conduit.id or index}]"
        if not conduit.endpoints:
            missing.append(f"{prefix}.endpoints")
        if not conduit.control:
            missing.append(f"{prefix}.control")

    missing += [
        f"criticality.{field}"
        for field in ("physical_consequence", "scale", "threat_model")
        if getattr(draft.criticality, field) is None
    ]

    return missing


def to_profile(draft: AssetProfileDraft, profile_id: str | None = None) -> AssetProfile:
    """Build the `AssetProfile` the core runs on from a reviewed draft.

    Called after the operator has completed the draft, never on the model's raw
    output — which is why it raises instead of filling anything in. `conduits` may
    legitimately be empty (an isolated asset); the zones, the nature and the
    criticality may not.
    """
    gaps = missing_required(draft)
    if gaps:
        raise IncompleteDraftError(gaps)

    return AssetProfile.model_validate(
        {
            "id": profile_id_for(draft, profile_id),
            "name": draft.name,
            "case": draft.case,
            "sectors": draft.sectors,
            "zones": [zone.model_dump(exclude_none=True) for zone in draft.zones],
            "conduits": [conduit.model_dump(exclude_none=True) for conduit in draft.conduits],
            "criticality": draft.criticality.model_dump(exclude_none=True),
        }
    )
