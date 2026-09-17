"""The suggestion tail is ordered by a rule, and ordering never removes.

A suggestion the zone's gating has already ruled out reads last and reads marked;
burying or hiding it would be a quiet drop. So the property under test is arithmetic
before presentation: the set of offered ids is the same before and after the sort.
"""

from __future__ import annotations

from app.catalog.schemas import ControlStrength, Framework, FrameworkControl, Jurisdiction
from app.engine.schemas import GatingOutcome
from app.retrieval.schemas import (
    ORDERING_VERSION,
    GatingAnnotation,
    RetrievalRelation,
    RetrievedControl,
    sink_gated,
)


def control(control_id: str) -> FrameworkControl:
    return FrameworkControl.model_validate(
        {
            "id": control_id,
            "framework": Framework.CIS,
            "official_id": control_id[-4:],
            "title": f"Control {control_id}",
            "paraphrased_description": "Descripción parafraseada del control.",
            "jurisdiction": Jurisdiction.US,
            "strength": ControlStrength(kind="ig", level=1),
            "type": "technical",
        }
    )


def suggestion(control_id: str, score: float, gated: bool) -> RetrievedControl:
    annotation = (
        GatingAnnotation(
            zone_id="Z-OT-CORRIDOR",
            outcome=GatingOutcome.NOT_APPLICABLE,
            rule_id="GATE-PREMISE-UNMET",
            rationale="Presupone una premisa que la zona no cumple.",
        )
        if gated
        else None
    )
    return RetrievedControl(
        control=control(control_id),
        score=score,
        relation=RetrievalRelation.WIDENS,
        rationale="Sugerencia del recuperador.",
        gated_out=annotation,
    )


def test_gated_suggestions_read_last() -> None:
    retrieved = [
        suggestion("CTL-CIS-0001", 0.91, gated=True),
        suggestion("CTL-CIS-0002", 0.88, gated=False),
        suggestion("CTL-CIS-0003", 0.85, gated=True),
        suggestion("CTL-CIS-0004", 0.82, gated=False),
    ]

    assert [r.control_id for r in sink_gated(retrieved)] == [
        "CTL-CIS-0002",
        "CTL-CIS-0004",
        "CTL-CIS-0001",
        "CTL-CIS-0003",
    ]


def test_ordering_never_removes_a_suggestion() -> None:
    """The invariant, stated as arithmetic: same multiset in, same multiset out."""
    retrieved = [
        suggestion(f"CTL-CIS-{n:04}", 1.0 - n / 100, gated=n % 3 == 0) for n in range(1, 16)
    ]

    sorted_ids = [r.control_id for r in sink_gated(retrieved)]

    assert sorted(sorted_ids) == sorted(r.control_id for r in retrieved)
    assert len(sorted_ids) == len(retrieved)


def test_within_each_group_the_retrievers_rank_is_kept() -> None:
    """The sort decides gated vs not, and nothing else — score order survives it."""
    retrieved = [suggestion(f"CTL-CIS-{n:04}", 1.0 - n / 100, gated=False) for n in range(1, 6)]

    assert sink_gated(retrieved) == retrieved


def test_nothing_gated_is_left_exactly_as_it_came() -> None:
    retrieved = [suggestion("CTL-CIS-0001", 0.9, gated=True)]

    assert sink_gated(retrieved) == retrieved
    assert sink_gated([]) == []


def test_the_ordering_rule_is_versioned() -> None:
    """Declared like the cut policy: the order is part of what the engine says."""
    assert ORDERING_VERSION == "v1"
