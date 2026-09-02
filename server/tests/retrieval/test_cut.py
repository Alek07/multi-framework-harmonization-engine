from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.retrieval.cut import CUT_POLICY_VERSION, apply_cut, band_width, current_policy
from app.retrieval.index import ControlPayload, IndexHit
from app.retrieval.schemas import CutPolicy, CutReason, RetrievalCut

JURISDICTIONS = {"CSF": "US", "NIS2": "EU", "IEC62443": "INTL", "CIS": "US", "IMO": "INTL-MARITIME"}


def policy(
    *,
    depth: int = 50,
    floor: int = 10,
    tie_epsilon: float = 0.01,
    ceiling: int = 16,
    framework_cap: int = 4,
) -> CutPolicy:
    return CutPolicy(
        version=CUT_POLICY_VERSION,
        depth=depth,
        floor=floor,
        tie_epsilon=tie_epsilon,
        ceiling=ceiling,
        framework_cap=framework_cap,
    )


def hit(control_id: str, score: float, framework: str = "CSF") -> IndexHit:
    """One ranked candidate. Only the framework and the score matter to the rule."""
    return IndexHit(
        control_id=control_id,
        score=score,
        payload=ControlPayload(
            control_id=control_id,
            framework=framework,
            official_id=f"{framework} {control_id}",
            title=f"control {control_id}",
            jurisdiction=JURISDICTIONS[framework],
            control_type="technical",
            strength="exigible desde SL1",
            capability_ids=["CAP-X"],
            mapping_types=["partial"],
            provenance_sources=["author_judgment"],
            catalog_version="0.4.0",
            text=f"passage: {control_id}",
        ),
    )


def band(scores: list[float], framework: str = "CSF") -> list[IndexHit]:
    return [hit(f"CTL-{i:03d}", score, framework) for i, score in enumerate(scores)]


def crowded() -> list[IndexHit]:
    """Eight CSF siblings ahead of four other readings, stepping by twice the tie epsilon."""
    scores = [round(0.90 - 0.02 * i, 4) for i in range(14)]
    frameworks = ["CSF"] * 8 + ["NIS2"] * 2 + ["IEC62443"] * 2 + ["CIS"] * 2
    return [
        hit(f"CTL-{framework}-{i:02d}", score, framework)
        for i, (score, framework) in enumerate(zip(scores, frameworks, strict=True))
    ]


def cut(hits: list[IndexHit], **kwargs: object) -> tuple[list[IndexHit], RetrievalCut]:
    return apply_cut(
        hits,
        capability_name="Gestión de riesgos",
        indexed_controls=226,
        policy=policy(**kwargs),  # type: ignore[arg-type]
    )



def test_a_separated_band_is_cut_at_the_floor() -> None:
    """Nothing to be unsure about: the eleventh is far below, so ten it is."""
    scores = [0.90 - 0.02 * i for i in range(20)]

    kept, report = cut(band(scores), framework_cap=99)

    assert len(kept) == 10
    assert report.retained == 10
    assert report.band_extension == 0
    assert report.ceiling_reached is False


def test_fewer_candidates_than_the_floor_are_all_retained() -> None:
    kept, report = cut(band([0.9, 0.8, 0.7]))

    assert len(kept) == 3
    assert report.dropped == 0
    assert report.first_dropped is None
    assert "No quedó nada bajo el corte" in report.rationale


def test_no_candidates_at_all_is_a_report_and_not_a_crash() -> None:
    kept, report = cut([])

    assert kept == []
    assert (report.evaluated, report.retained, report.dropped) == (0, 0, 0)
    assert report.not_returned == 226



def test_the_cut_does_not_separate_what_the_retriever_cannot_tell_apart() -> None:
    """The premise of the band, in one assertion: ties travel with the tenth."""
    scores = [0.90 - 0.002 * i for i in range(14)] + [0.60, 0.59]

    kept, report = cut(band(scores), framework_cap=99)

    assert len(kept) == 14
    assert report.band_extension == 4
    # The fifteenth is 0.26 below the fourteenth: distinguishable, and dropped.
    assert report.first_dropped is not None
    assert report.first_dropped.score == pytest.approx(0.60)
    assert report.first_dropped.dropped_by is CutReason.RANK


def test_the_band_stops_where_the_scores_separate() -> None:
    """Extension is not a slide: one gap wider than epsilon ends it."""
    scores = [0.90 - 0.002 * i for i in range(11)] + [0.80 - 0.002 * i for i in range(9)]

    _, report = cut(band(scores), framework_cap=99)

    assert report.retained == 11
    assert report.band_extension == 1


def test_a_band_the_cap_cannot_fill_reports_both_numbers() -> None:
    """Band opened ten, the cap filled four, the yield restored the floor."""
    _, report = cut(band([0.9 - 0.05 * i for i in range(20)]), framework_cap=4)

    assert report.band_width == 10
    assert report.retained == 10
    assert report.cap_yielded == 6


def test_the_band_width_is_reported_apart_from_what_the_cap_filled() -> None:
    """Two frameworks, a wide band: the slots the cap could not fill are not hidden."""
    hits = [hit(f"CTL-CSF-{i}", 0.9 - 0.001 * i, "CSF") for i in range(20)]
    hits += [hit(f"CTL-NIS2-{i}", 0.88 - 0.001 * i, "NIS2") for i in range(20)]

    kept, report = cut(hits, framework_cap=4)

    assert report.band_width == 16
    assert report.retained == len(kept) == 10
    assert report.cap_yielded == 2
    assert "La banda abrió" not in report.rationale


def test_the_ceiling_bounds_a_flat_band_and_says_that_it_did() -> None:
    """A bound that hides the fact it bound is the failure this ticket is about."""
    scores = [0.88 - 0.0005 * i for i in range(40)]

    kept, report = cut(band(scores), framework_cap=99)

    assert len(kept) == 16
    assert report.ceiling_reached is True
    assert report.near_ties_dropped > 0
    assert "El techo (16) detuvo la extensión" in report.rationale


def test_the_ceiling_is_not_claimed_when_the_band_ended_on_its_own() -> None:
    scores = [0.88 - 0.0005 * i for i in range(16)] + [0.50]

    _, report = cut(band(scores), framework_cap=99)

    assert report.retained == 16
    assert report.ceiling_reached is False


def test_the_band_reads_the_scores_alone() -> None:
    """`band_width` is independent of the cap: how many, not which."""
    assert band_width([], policy()) == 0
    assert band_width([0.9] * 3, policy()) == 3
    assert band_width([0.9 - 0.02 * i for i in range(30)], policy()) == 10
    assert band_width([0.9] * 30, policy()) == 16



def test_a_dense_framework_cannot_own_the_cut() -> None:
    """The measured failure of UCM-51, prevented: nine siblings do not take nine slots."""
    hits = [hit(f"CTL-CSF-{i}", 0.88 - 0.001 * i, "CSF") for i in range(9)]
    hits += [hit("CTL-NIS2-A21", 0.845, "NIS2"), hit("CTL-IEC-1", 0.844, "IEC62443")]
    hits += [hit(f"CTL-CIS-{i}", 0.80 - 0.001 * i, "CIS") for i in range(6)]

    kept, report = cut(hits)

    frameworks = [k.payload.framework for k in kept]
    assert frameworks.count("CSF") == 4
    # The slots the cap freed went to the readings that were being evicted.
    assert "CTL-NIS2-A21" in {k.control_id for k in kept}
    assert "CTL-IEC-1" in {k.control_id for k in kept}
    assert {f"CTL-CSF-{i}" for i in range(4, 9)} <= {d.control_id for d in report.displaced}
    assert all(d.dropped_by is CutReason.FRAMEWORK_CAP for d in report.displaced)
    assert report.cap_yielded == 0


def test_a_displaced_candidate_is_named_with_its_score_and_its_reason() -> None:
    """Desplazar no es descartar — the same doctrine `set_aside` follows."""
    _, report = cut(crowded())

    displaced = report.displaced
    assert [d.control_id for d in displaced] == [f"CTL-CSF-{i:02d}" for i in (4, 5, 6, 7)]
    for candidate in displaced:
        assert candidate.dropped_by is CutReason.FRAMEWORK_CAP
        assert candidate.score > 0
        assert "tope de marco" in candidate.rationale
        assert "desplazar no es descartar" in candidate.rationale.lower()


def test_a_displacement_that_cost_a_better_score_says_so_in_its_margin() -> None:
    """A negative margin: the cap displaced something that outscored the last one shown."""
    _, report = cut(crowded())

    first = report.displaced[0]
    assert first.score == pytest.approx(0.82)
    # The last of the ten shown scores 0.64, so this one was 0.18 *above* the line.
    assert first.margin == pytest.approx(-0.18, abs=1e-6)


def test_the_cap_reallocates_a_slot_it_does_not_spend_it() -> None:
    """The list stays exactly as long, and four readings share it instead of one."""
    kept, report = cut(crowded())

    assert len(kept) == 10
    assert report.cap_yielded == 0
    assert [k.payload.framework for k in kept] == (
        ["CSF"] * 4 + ["NIS2"] * 2 + ["IEC62443"] * 2 + ["CIS"] * 2
    )


def test_the_cap_yields_rather_than_showing_the_operator_less() -> None:
    """One framework in the neighbourhood: the floor is a guarantee, the cap is not."""
    kept, report = cut(band([0.9 - 0.01 * i for i in range(20)]), framework_cap=4)

    assert len(kept) == 10
    assert report.cap_yielded == 6
    # The ten it kept are the ten best, exactly as before the rule existed.
    assert [k.control_id for k in kept] == [f"CTL-{i:03d}" for i in range(10)]
    assert "El tope cedió 6 hueco(s)" in report.rationale


def test_the_cap_yields_only_up_to_the_floor_never_past_it() -> None:
    """The floor is what it gives back. The band extension is not a guarantee."""
    kept, report = cut(band([0.9] * 20), framework_cap=4)

    assert len(kept) == 10
    assert report.cap_yielded == 6
    assert report.retained == 10



def test_the_counts_close_against_each_other() -> None:
    hits = [hit(f"CTL-CSF-{i}", 0.9 - 0.004 * i, "CSF") for i in range(12)]
    hits += [hit(f"CTL-NIS2-{i}", 0.85 - 0.004 * i, "NIS2") for i in range(12)]

    kept, report = cut(hits)

    assert report.evaluated == 24
    assert report.retained == len(kept)
    assert report.retained + report.dropped == report.evaluated
    assert report.not_returned == 226 - 24


def test_the_first_dropped_is_the_best_scoring_one_that_did_not_make_it() -> None:
    """Whichever rule dropped it: the report names the best one that is not shown."""
    _, report = cut(crowded())

    assert report.first_dropped is not None
    assert report.first_dropped.control_id == "CTL-CSF-04"
    assert report.first_dropped.dropped_by is CutReason.FRAMEWORK_CAP
    assert report.first_dropped.score == pytest.approx(0.82)


def test_a_gap_of_exactly_epsilon_is_a_tie_and_travels_with_the_band() -> None:
    """`tie_epsilon` is inclusive: at exactly epsilon the two are not told apart."""
    _, report = cut(band([0.90 - 0.01 * i for i in range(12)]), framework_cap=99)

    assert report.retained == 12
    assert report.dropped == 0


def test_the_margin_is_measured_against_the_last_candidate_shown() -> None:
    scores = [0.90 - 0.002 * i for i in range(10)] + [0.60, 0.50]

    _, report = cut(band(scores), framework_cap=99)

    assert report.retained == 10
    assert report.first_dropped is not None
    # 0.882 is the tenth; the eleventh is 0.60.
    assert report.first_dropped.margin == pytest.approx(0.282, abs=1e-6)


def test_a_report_that_names_nothing_it_dropped_cannot_be_built() -> None:
    """The invariant enforced by the type, not by a test that has to be remembered."""
    with pytest.raises(ValidationError, match="names none of them"):
        RetrievalCut(
            policy=policy(),
            evaluated=40,
            retained=10,
            band_extension=0,
            ceiling_reached=False,
            dropped=30,
            near_ties_dropped=0,
            not_returned=186,
            first_dropped=None,
            rationale="30 cayeron y no digo cuál",
            band_width=10,
        )


def test_a_report_whose_arithmetic_does_not_close_cannot_be_built() -> None:
    with pytest.raises(ValidationError, match="not the 40 candidates"):
        RetrievalCut(
            policy=policy(),
            evaluated=40,
            retained=10,
            band_extension=0,
            ceiling_reached=False,
            dropped=5,
            near_ties_dropped=0,
            not_returned=186,
            rationale="las cuentas no cuadran",
            band_width=10,
        )



def test_the_same_band_is_cut_the_same_way_every_time() -> None:
    hits = [hit(f"CTL-{i}", 0.9 - 0.001 * i, ["CSF", "NIS2", "CIS"][i % 3]) for i in range(30)]

    first = cut(list(hits))[1]
    second = cut(list(hits))[1]

    assert first.model_dump_json() == second.model_dump_json()


def test_the_shipped_policy_is_the_one_the_settings_declare() -> None:
    """A cut is replayable from its parameters alone."""
    from app.core.config import settings

    shipped = current_policy()

    assert shipped.version == CUT_POLICY_VERSION
    assert shipped.depth == settings.RAG_RETRIEVAL_DEPTH
    assert shipped.floor == settings.RAG_TOP_K
    assert shipped.tie_epsilon == settings.RAG_CUT_TIE_EPSILON
    assert shipped.ceiling == settings.RAG_MAX_K
    assert shipped.framework_cap == settings.RAG_FRAMEWORK_CAP
    assert "por marco" in shipped.describe()
