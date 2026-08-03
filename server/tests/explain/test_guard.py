"""UCM-14 - The guard: what counts as a verdict, and what is only a description.

Two failure directions matter here and they pull against each other. A guard that
lets "debería elegir el control CIS" through puts a decision the LLM is not
allowed to make on the operator's screen. A guard that withholds "la similitud no
descarta la equivalencia" teaches the reader that the flag means nothing. So the
lexicon is asserted in both directions, negations included.
"""

from __future__ import annotations

import pytest

from app.explain.guard import normalise, screen, verdict_terms
from app.explain.schemas import EvidenceKey

DESCRIPTIVE = (
    "El catálogo mapea este control a la capacidad con un mapeo total de peso 1, "
    "procedente de un crosswalk oficial estadounidense."
)


# --- verdict language ---------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Recomiendo este control para la zona.",
        "Es la mejor opción de las disponibles.",
        "El operador debería adoptar este control.",
        "Descarte los candidatos de CIS en esta zona.",
        "Resulta más adecuado que el resto del catálogo.",
        "Es el candidato idóneo para la capacidad.",
        "Conviene priorizar este control.",
        "Es la primera opción del ranking.",
    ],
)
def test_a_verdict_is_never_shown_as_written(text: str) -> None:
    verdict = screen(text)

    assert verdict.passed is False
    assert verdict.matches
    assert verdict.categories
    assert verdict.reason and "presentacional" in verdict.reason


def test_the_lexicon_ignores_accents_and_case() -> None:
    assert screen("ESTE CONTROL ES MÁS ADECUADO").passed is False
    assert screen("El operador debería revisarlo").passed is False
    assert normalise("Debería") == "deberia"


def test_a_negated_verdict_is_a_description() -> None:
    """"No descarta" states a limit; withholding it would be a false positive."""
    assert screen("La similitud no descarta ni confirma la equivalencia.").passed is True
    assert screen("El catálogo nunca recomienda un control por su similitud.").passed is True
    assert verdict_terms("no es la mejor") == [("juicio comparativo", "mejor")]


def test_plain_description_passes() -> None:
    verdict = screen(DESCRIPTIVE, [EvidenceKey.CATALOG_MAPPING], [EvidenceKey.CATALOG_MAPPING])

    assert verdict.passed is True
    assert verdict.reason is None
    assert verdict.matches == ()


def test_words_that_merely_contain_a_verdict_are_left_alone() -> None:
    """`mejora` is not `mejor`: the patterns are anchored on word boundaries."""
    assert screen("Mejora la cobertura declarada de la capacidad.").passed is True


# --- groundedness -------------------------------------------------------------


def test_citing_evidence_the_candidate_does_not_have_is_withheld() -> None:
    verdict = screen(
        DESCRIPTIVE,
        basis=[EvidenceKey.CATALOG_MAPPING, EvidenceKey.SIMILARITY],
        allowed=[EvidenceKey.CATALOG_MAPPING, EvidenceKey.MAPPING_TYPE],
    )

    assert verdict.passed is False
    assert verdict.ungrounded == (EvidenceKey.SIMILARITY,)
    # The key is named in the operator's words; the enum stays in `ungrounded`.
    assert verdict.reason and "la similitud de texto" in verdict.reason


def test_a_subset_of_the_allowed_evidence_is_grounded() -> None:
    verdict = screen(
        DESCRIPTIVE,
        basis=[EvidenceKey.CATALOG_MAPPING],
        allowed=[EvidenceKey.CATALOG_MAPPING, EvidenceKey.MAPPING_TYPE, EvidenceKey.FRAMEWORK],
    )

    assert verdict.passed is True


def test_both_failures_are_reported_together() -> None:
    verdict = screen(
        "Es la mejor opción disponible.",
        basis=[EvidenceKey.SIMILARITY],
        allowed=[EvidenceKey.CATALOG_MAPPING],
    )

    assert verdict.passed is False
    assert verdict.matches and verdict.ungrounded
    assert verdict.reason and "lenguaje de decisión" in verdict.reason
    assert verdict.reason and "evidencia que este candidato no tiene" in verdict.reason
