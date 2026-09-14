"""The claim under test: this layer explains, and it changes nothing.

Every test below scripts a way for the model to overstep or to fail, and asserts the
same two things: the candidates the operator sees are exactly the ones the core and
the RAG pass offered, in the same order, and whatever the model did or did not do is
visible on the record rather than silently absorbed. The failure paths get more
attention than the happy one on purpose — a P1 feature that breaks P0 would cost the
whole POC's credibility.
"""

from __future__ import annotations

import pytest
from pydantic_ai.models.function import FunctionModel

from app.core.config import settings
from app.engine.schemas import ProfileResolution
from app.explain.evidence import SHEET_TEMPLATE_VERSION
from app.explain.prompt import PROMPT_VERSION
from app.explain.schemas import CandidateExplanation, ExplanationStatus
from app.explain.service import CandidateExplanationService
from app.parse.ollama import ModelUnavailableError
from app.retrieval.schemas import ProfileRetrieval
from tests.explain.conftest import Case, batch_json, entry, scripted, well_behaved

# --- the invariant ------------------------------------------------------------


async def test_every_candidate_is_explained_once_and_in_the_offered_order(case: Case) -> None:
    with scripted(well_behaved(case)) as (service, _):
        result = await service.explain_capability(
            case.resolution, case.retrieval, case.catalog_version, case.zone
        )

    assert result.offered_control_ids == case.offered
    assert [e.control_id for e in result.explanations] == case.offered
    assert all(e.status is ExplanationStatus.GENERATED for e in result.explanations)
    assert result.presentational is True


async def test_explaining_does_not_touch_the_core_or_the_retrieval(case: Case) -> None:
    """The strongest form: the inputs come out byte-identical."""
    resolution_before = case.resolution.model_dump_json()
    retrieval_before = case.retrieval.model_dump_json()

    with scripted(well_behaved(case)) as (service, _):
        await service.explain_capability(
            case.resolution, case.retrieval, case.catalog_version, case.zone
        )

    assert case.resolution.model_dump_json() == resolution_before
    assert case.retrieval.model_dump_json() == retrieval_before


async def test_the_same_candidates_and_the_same_reply_give_the_same_view(case: Case) -> None:
    with scripted(well_behaved(case), well_behaved(case)) as (service, _):
        first = await service.explain_capability(
            case.resolution, case.retrieval, case.catalog_version, case.zone
        )
        second = await service.explain_capability(
            case.resolution, case.retrieval, case.catalog_version, case.zone
        )

    assert first.model_dump_json() == second.model_dump_json()
    assert first.digest == second.digest


# --- the model oversteps ------------------------------------------------------


async def test_a_recommendation_is_withheld_and_the_candidate_is_not(case: Case) -> None:
    """The sentence this layer exists to prevent, on the first candidate."""
    facts = case.facts
    reply = batch_json(
        [
            entry(
                candidate.control_id,
                (
                    "Es la mejor opción para esta zona y el operador debería adoptarla."
                    if index == 0
                    else "Aparece por su relación declarada con la capacidad."
                ),
                [candidate.allowed[0].value],
            )
            for index, candidate in enumerate(facts.candidates)
        ]
    )

    with scripted(reply) as (service, _):
        result = await service.explain_capability(
            case.resolution, case.retrieval, case.catalog_version, case.zone
        )

    withheld = result.explanations[0]
    assert withheld.status is ExplanationStatus.WITHHELD
    assert withheld.text == facts.candidates[0].fallback
    assert withheld.notice and "mejor" in withheld.notice
    assert withheld.basis == []
    # The candidate itself is untouched, and so is everything after it.
    assert result.offered_control_ids == case.offered
    assert result.explanations[1].status is ExplanationStatus.GENERATED


async def test_an_ungrounded_citation_is_withheld(case: Case) -> None:
    """A suggestion has no authored mapping here, so it cannot have leaned on one.

    This is the fabrication that would matter most: prose claiming the catalog
    maps a control to this capability, next to controls where that is true.
    """
    facts = case.facts
    suggestion = next(c for c in facts.candidates if c.mapping is None)
    reply = batch_json(
        [
            entry(
                candidate.control_id,
                "El catálogo lo relaciona con la capacidad.",
                ["catalog_mapping"] if candidate is suggestion else [candidate.allowed[0].value],
            )
            for candidate in facts.candidates
        ]
    )

    with scripted(reply) as (service, _):
        result = await service.explain_capability(
            case.resolution, case.retrieval, case.catalog_version, case.zone
        )

    explanation = result.explanation(suggestion.control_id)
    assert explanation.status is ExplanationStatus.WITHHELD
    assert explanation.notice and "mapeo del catálogo" in explanation.notice
    assert explanation.text == suggestion.fallback


async def test_generated_text_with_no_basis_is_withheld_not_raised(case: Case) -> None:
    """A well-formed, verdict-free paragraph that cites nothing must not 500.

    The guard passes it (empty basis is a subset of anything), but a generated
    explanation that leans on nothing checkable is what `CandidateExplanation`
    refuses to build. The layer reconciles that by withholding, so the candidate
    keeps the engine's own rationale instead of the whole request failing.
    """
    facts = case.facts
    reply = batch_json(
        [entry(c.control_id, "Aparece por su relación declarada.", []) for c in facts.candidates]
    )

    with scripted(reply) as (service, _):
        result = await service.explain_capability(
            case.resolution, case.retrieval, case.catalog_version, case.zone
        )

    assert result.offered_control_ids == case.offered
    assert [e.control_id for e in result.explanations] == case.offered
    assert all(e.status is ExplanationStatus.WITHHELD for e in result.explanations)
    assert all(
        e.text == c.fallback
        for e, c in zip(result.explanations, facts.candidates, strict=True)
    )
    assert all(e.basis == [] for e in result.explanations)
    assert all(e.notice and "verificable" in e.notice for e in result.explanations)


async def test_a_candidate_the_model_invents_never_reaches_the_screen(case: Case) -> None:
    reply = batch_json(
        [entry("CTL-DOES-NOT-EXIST", "Un control que nadie ofreció.", ["control_text"])]
        + [
            entry(c.control_id, "Aparece por su relación declarada.", [c.allowed[0].value])
            for c in case.facts.candidates
        ]
    )

    with scripted(reply) as (service, _):
        result = await service.explain_capability(
            case.resolution, case.retrieval, case.catalog_version, case.zone
        )

    assert result.offered_control_ids == case.offered
    assert "CTL-DOES-NOT-EXIST" not in [e.control_id for e in result.explanations]
    # Not shown, and not swallowed either.
    assert result.provenance.ignored_control_ids == ["CTL-DOES-NOT-EXIST"]


async def test_a_candidate_the_model_forgets_keeps_the_engines_own_text(case: Case) -> None:
    facts = case.facts
    forgotten = facts.candidates[0]
    reply = batch_json(
        [
            entry(c.control_id, "Aparece por su relación declarada.", [c.allowed[0].value])
            for c in facts.candidates[1:]
        ]
    )

    with scripted(reply) as (service, _):
        result = await service.explain_capability(
            case.resolution, case.retrieval, case.catalog_version, case.zone
        )

    assert [e.control_id for e in result.explanations] == case.offered
    first = result.explanation(forgotten.control_id)
    assert first.status is ExplanationStatus.UNAVAILABLE
    assert first.text == forgotten.fallback
    assert first.notice and "no devolvió explicación" in first.notice


# --- the model fails ----------------------------------------------------------


async def test_an_unreachable_model_costs_the_prose_and_nothing_else(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.explain import service as service_module

    async def _unavailable() -> str:
        raise ModelUnavailableError("Ollama no está disponible")

    monkeypatch.setattr(service_module, "verify_model", _unavailable)

    with scripted(well_behaved(case)) as (service, prompts):
        result = await service.explain_capability(
            case.resolution, case.retrieval, case.catalog_version, case.zone
        )

    assert prompts == [], "the model must not be asked once the digest check failed"
    assert result.offered_control_ids == case.offered
    assert all(e.status is ExplanationStatus.UNAVAILABLE for e in result.explanations)
    assert all(
        e.text == c.fallback
        for e, c in zip(result.explanations, case.facts.candidates, strict=True)
    )
    assert result.provenance.model_digest is None
    assert result.provenance.notice and "Ollama" in result.provenance.notice


async def test_an_invalid_answer_costs_the_prose_and_nothing_else(case: Case) -> None:
    """Two malformed replies exhaust the single retry; the candidates survive it."""
    with scripted("no es json", "sigue sin ser json") as (service, prompts):
        result = await service.explain_capability(
            case.resolution, case.retrieval, case.catalog_version, case.zone
        )

    assert len(prompts) >= 1
    assert result.offered_control_ids == case.offered
    assert all(e.status is ExplanationStatus.UNAVAILABLE for e in result.explanations)
    assert result.provenance.notice and "No se pudo generar" in result.provenance.notice


async def test_a_provider_that_raises_costs_the_prose_and_nothing_else(case: Case) -> None:
    def explode(messages: object, info: object) -> object:
        raise RuntimeError("el proveedor se cayó a mitad de la petición")

    from app.explain.agent import explain_agent

    agent = explain_agent()
    with agent.override(model=FunctionModel(explode)):  # type: ignore[arg-type]
        service = CandidateExplanationService(agent=agent)
        result = await service.explain_capability(
            case.resolution, case.retrieval, case.catalog_version, case.zone
        )

    assert result.offered_control_ids == case.offered
    assert all(e.status is ExplanationStatus.UNAVAILABLE for e in result.explanations)
    # The operator is told the paragraph is missing, not *how* the provider broke:
    # the exception's own text is written for whoever reads the logs.
    assert result.provenance.notice and "No se pudo generar" in result.provenance.notice
    assert "se cayó" not in result.provenance.notice
    assert "RuntimeError" not in result.provenance.notice


# --- switched off, and nothing to explain -------------------------------------


async def test_switched_off_the_candidates_still_carry_their_justification(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "EXPLAIN_ENABLED", False)

    with scripted(well_behaved(case)) as (service, prompts):
        result = await service.explain_capability(
            case.resolution, case.retrieval, case.catalog_version, case.zone
        )

    assert prompts == []
    assert result.offered_control_ids == case.offered
    assert all(e.status is ExplanationStatus.DISABLED for e in result.explanations)
    assert all(e.text.strip() for e in result.explanations)
    assert result.provenance.attempts == 0


async def test_a_capability_with_no_candidate_asks_the_model_nothing(gap_case: Case) -> None:
    with scripted(well_behaved(gap_case)) as (service, prompts):
        result = await service.explain_capability(
            gap_case.resolution, gap_case.retrieval, gap_case.catalog_version, gap_case.zone
        )

    assert prompts == []
    assert result.explanations == []
    assert result.offered_control_ids == []


# --- what the model is told ---------------------------------------------------


async def test_the_model_only_ever_sees_facts_that_are_written_down(case: Case) -> None:
    with scripted(well_behaved(case)) as (service, prompts):
        await service.explain_capability(
            case.resolution, case.retrieval, case.catalog_version, case.zone
        )

    prompt = prompts[0]
    assert "CANDIDATOS" in prompt
    for candidate in case.facts.candidates:
        assert f"control_id={candidate.control_id}" in prompt
        assert "evidencia citable" in prompt
    assert case.resolution.capability.description in prompt


async def test_the_provenance_pins_how_the_prose_was_produced(case: Case) -> None:
    with scripted(well_behaved(case)) as (service, _):
        result = await service.explain_capability(
            case.resolution, case.retrieval, case.catalog_version, case.zone
        )

    provenance = result.provenance
    assert provenance.model == settings.LLM_MODEL
    assert provenance.temperature == settings.LLM_TEMPERATURE == 0.0
    assert provenance.seed == settings.LLM_SEED
    # Both inputs of the prose are pinned: the instructions and the fact sheet.
    assert provenance.prompt_version == PROMPT_VERSION
    assert provenance.sheet_template_version == SHEET_TEMPLATE_VERSION
    assert provenance.catalog_version == case.catalog_version
    assert provenance.attempts == 1


# --- a zone, on demand --------------------------------------------------------


async def test_a_zone_explains_only_what_was_asked_for(
    case: Case, resolution_a: ProfileResolution, retrieval_a: ProfileRetrieval
) -> None:
    zone_resolution = next(
        z for z in resolution_a.zones if z.zone.zone_id == case.resolution.zone_id
    )
    zone_retrieval = retrieval_a.zone(case.resolution.zone_id)
    wanted = [case.resolution.capability.id]

    with scripted(well_behaved(case)) as (service, prompts):
        result = await service.explain_zone(
            zone_resolution, zone_retrieval, case.catalog_version, wanted
        )

    assert [c.capability_id for c in result.capabilities] == wanted
    assert len(prompts) == 1
    assert result.zone_id == case.resolution.zone_id


async def test_a_zone_refuses_a_capability_it_did_not_resolve(
    case: Case, resolution_a: ProfileResolution, retrieval_a: ProfileRetrieval
) -> None:
    zone_resolution = next(
        z for z in resolution_a.zones if z.zone.zone_id == case.resolution.zone_id
    )
    zone_retrieval = retrieval_a.zone(case.resolution.zone_id)

    with scripted(well_behaved(case)) as (service, _):
        with pytest.raises(KeyError, match="CAP-NO-EXISTE"):
            await service.explain_zone(
                zone_resolution, zone_retrieval, case.catalog_version, ["CAP-NO-EXISTE"]
            )


def test_an_explanation_is_a_string_and_a_status_and_nothing_else() -> None:
    """Read as a list: identity, prose, provenance of the prose. No lever."""
    assert set(CandidateExplanation.model_fields) == {
        "control_id",
        "official_id",
        "framework",
        "jurisdiction",
        "origin",
        "text",
        "status",
        "basis",
        "notice",
    }
