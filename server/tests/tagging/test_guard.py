"""UCM-53 - The guard keeps only the premises the control's own text supports."""

from __future__ import annotations

from app.tagging.guard import MIN_QUOTE_CHARS, normalise, screen
from app.tagging.schemas import PremiseDraft
from tests.tagging.conftest import premise

TITLE = "Deploy and Maintain Anti-Malware Software"
DESCRIPTION = "Desplegar y mantener software antimalware en los equipos de la organización."


def drafts(*payloads: dict[str, object]) -> list[PremiseDraft]:
    return [PremiseDraft.model_validate(p) for p in payloads]


def test_a_quote_from_the_control_survives() -> None:
    kept, rejected = screen(drafts(premise()), TITLE, DESCRIPTION)

    assert rejected == []
    assert [p.premise.value for p in kept] == ["general_purpose_os"]
    assert kept[0].expected is True


def test_the_quote_may_drift_in_accents_case_and_punctuation() -> None:
    """The model re-types the prose; that must not decide whether a premise stands."""
    kept, rejected = screen(
        drafts(premise(quote="Software Antimalware, en los equipos de la ORGANIZACION")),
        TITLE,
        DESCRIPTION,
    )

    assert rejected == []
    assert len(kept) == 1


def test_a_premise_with_no_anchor_in_the_text_is_refused() -> None:
    """The failure this guard exists for: recalled from training, not read here."""
    kept, rejected = screen(
        drafts(premise(premise="office_it_surface", quote="filtrado de correo electrónico")),
        TITLE,
        DESCRIPTION,
    )

    assert kept == []
    assert len(rejected) == 1
    assert "no aparece" in rejected[0].reason
    # Refused, not discarded: the reviewer can still overrule the guard.
    assert rejected[0].premise == "office_it_surface"
    assert rejected[0].quote == "filtrado de correo electrónico"


def test_a_quote_too_short_to_anchor_anything_is_refused() -> None:
    kept, rejected = screen(drafts(premise(quote="de la")), TITLE, DESCRIPTION)

    assert kept == []
    assert str(MIN_QUOTE_CHARS) in rejected[0].reason


def test_the_same_premise_twice_keeps_the_first_reading() -> None:
    kept, rejected = screen(
        drafts(premise(), premise(note="Otra lectura de lo mismo.")),
        TITLE,
        DESCRIPTION,
    )

    assert len(kept) == 1
    assert kept[0].note.startswith("Requiere un sistema operativo")
    assert "ya estaba declarada" in rejected[0].reason


def test_a_premise_nobody_can_explain_is_a_filter() -> None:
    kept, rejected = screen(drafts(premise(note="   ")), TITLE, DESCRIPTION)

    assert kept == []
    assert "explicar" in rejected[0].reason


def test_normalise_strips_accents_punctuation_and_extra_space() -> None:
    assert normalise("  Está,  aquí:  la  Organización ") == "esta aqui la organizacion"
