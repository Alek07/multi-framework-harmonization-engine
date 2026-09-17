"""`strength` is a declared scale, not prose the engine has to parse.

Prioritisation reads two of these scales: the CIS Implementation Group orders the
discretionary IT tier, and the SL of an IEC SR puts a control in Tier 0 for a
zone. While `strength` was free text a reworded catalog string could silently
change a baseline, so these tests pin the structure, the bounds and the fact that
already-shipped catalogs still load with their authored meaning.
"""

import pytest
from pydantic import ValidationError

from app.catalog.loader import load_catalog
from app.catalog.schemas import (
    _LEGACY_STRENGTHS,
    ControlStrength,
    Framework,
    StrengthKind,
)

# The scale each framework grades on. A control whose kind drifts off its
# framework would be read on a scale the framework never published.
KIND_OF = {
    Framework.CIS: {StrengthKind.IG},
    Framework.CSF: {StrengthKind.OUTCOME},
    Framework.IEC62443: {StrengthKind.SL_BASELINE},
    Framework.NIS2: {StrengthKind.LEGAL},
    Framework.IMO: {StrengthKind.LEGAL, StrengthKind.GUIDELINE},
}


# --- the structure itself ---------------------------------------------------


def test_a_levelled_scale_needs_a_level_in_range() -> None:
    assert ControlStrength(kind=StrengthKind.IG, level=3).level == 3
    with pytest.raises(ValidationError):
        ControlStrength(kind=StrengthKind.IG, level=4)
    with pytest.raises(ValidationError):
        ControlStrength(kind=StrengthKind.SL_BASELINE)
    with pytest.raises(ValidationError):
        ControlStrength(kind=StrengthKind.SL_BASELINE, level=5)


def test_an_unlevelled_scale_refuses_a_level() -> None:
    """An outcome or a statute is not graded: a level there would be invented."""
    assert ControlStrength(kind=StrengthKind.OUTCOME).level is None
    with pytest.raises(ValidationError):
        ControlStrength(kind=StrengthKind.LEGAL, level=1)


def test_the_label_composes_scale_level_and_note() -> None:
    assert ControlStrength(kind=StrengthKind.SL_BASELINE, level=2).label == "exigible desde SL2"
    enhanced = ControlStrength(
        kind=StrengthKind.SL_BASELINE, level=1, note="con refuerzos (RE) a SL3"
    )
    assert enhanced.label == "exigible desde SL1 (con refuerzos (RE) a SL3)"
    assert ControlStrength(kind=StrengthKind.OUTCOME).label == "resultado esperado, no mecanismo"


# --- what the shipped catalogs meant ----------------------------------------


@pytest.mark.parametrize("legacy", sorted(_LEGACY_STRENGTHS))
def test_every_legacy_string_still_reads(legacy: str) -> None:
    """v0.1.0 and v0.2.0 are frozen in Git and must keep loading (reproducibility)."""
    kind, level, note = _LEGACY_STRENGTHS[legacy]
    parsed = ControlStrength.model_validate(legacy)

    assert (parsed.kind, parsed.level, parsed.note) == (kind, level, note)


def test_an_unknown_legacy_string_is_refused_loudly() -> None:
    """Guessing at prose is what this field stopped doing: no silent default."""
    with pytest.raises(ValidationError):
        ControlStrength.model_validate("obligatorio a SL7")


@pytest.mark.parametrize("version", ["0.1.0", "0.2.0"])
def test_the_shipped_catalogs_still_load(version: str) -> None:
    previous = load_catalog(f"data/catalog/catalog.v{version}.json")

    assert previous.controls
    for control in previous.controls:
        assert control.strength.kind in KIND_OF[control.framework], control.id


# --- what the current catalog declares --------------------------------------


def test_every_control_grades_on_the_scale_of_its_own_framework() -> None:
    for control in load_catalog("data/catalog/catalog.v0.3.0.json").controls:
        assert control.strength.kind in KIND_OF[control.framework], control.id


def test_the_cis_implementation_group_survives_the_round_trip() -> None:
    """Prioritisation reuses the IG verbatim, so it has to come back out unchanged."""
    catalog = load_catalog("data/catalog/catalog.v0.3.0.json")
    cis = [c for c in catalog.controls if c.framework is Framework.CIS]

    assert len(cis) == 49
    assert {c.strength.level for c in cis} == {1, 2, 3}
    assert all(c.strength.label.startswith(f"IG{c.strength.level}") for c in cis)
