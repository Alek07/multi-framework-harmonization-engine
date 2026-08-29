"""UCM-13 - A catalog index without Qdrant and without the embedding model.

The suite has to run on any machine, offline, with no containers up — the same
rule the parse tests follow (UCM-12). So the fake below replaces exactly one
thing: the vectors. Everything else is the shipped code path — the real payload
projection from the catalog, the real filter language, the real service and the
real trail — because those are what the invariant of this ticket lives in.

The stand-in ranker is token overlap between the capability's text and the
control's, which is deterministic, ordering-stable and good enough to produce the
mix of confirmations and widenings the tests need. It is *not* a claim about
retrieval quality: that is measured against the real model in
`test_live_qdrant.py` and, honestly and with every miss analysed, in UCM-18.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from qdrant_client import models as qdrant

from app.catalog.schemas import Catalog
from app.retrieval.embeddings import control_text
from app.retrieval.index import CatalogIndex, ControlPayload, IndexHit

WORD = re.compile(r"\w+", re.UNICODE)


def tokens(text: str) -> set[str]:
    return {word.lower() for word in WORD.findall(text) if len(word) > 3}


def overlap(query: str, passage: str) -> float:
    """A stable stand-in for cosine similarity, in [0, 1]."""
    left, right = tokens(query), tokens(passage)
    if not left:
        return 0.0
    return len(left & right) / len(left)


def _field_matches(condition: qdrant.FieldCondition, payload: ControlPayload) -> bool:
    """One `FieldCondition` (a `MatchAny`) against the payload."""
    wanted = set(condition.match.any)
    value = getattr(payload, condition.key)
    held = set(value) if isinstance(value, list) else {value}
    return bool(held & wanted)


def _branch(condition: Any, payload: ControlPayload) -> bool:
    """One branch of a nested `should`: a `MatchAny`, or an emptiness check."""
    if isinstance(condition, qdrant.IsEmptyCondition):
        return not getattr(payload, condition.is_empty.key)
    return _field_matches(condition, payload)


def matches(query_filter: Any, payload: ControlPayload) -> bool:
    """Apply a Qdrant filter in Python, by reading the conditions it declares.

    Interpreting the real `qdrant.Filter` — rather than the `PayloadFilter` it was
    built from — means these tests also check that `to_qdrant` emits the structure
    it claims to. The sector axis (UCM-52) is a nested `should` (transversal *or*
    in scope), so a `must` entry is either a `FieldCondition` or a sub-filter.
    """
    if query_filter is None:
        return True
    for condition in query_filter.must or []:
        if isinstance(condition, qdrant.Filter):
            if not any(_branch(branch, payload) for branch in condition.should or []):
                return False
        elif not _field_matches(condition, payload):
            return False
    return True


class FakeIndex(CatalogIndex):
    """The real catalog projection, a scripted ranker, no network of any kind."""

    def __init__(self, catalog: Catalog, returns_nothing: bool = False):
        super().__init__(catalog=catalog, client=None, encoder=None)
        self.returns_nothing = returns_nothing
        self.queries: list[tuple[str, int, Any]] = []

    @property
    def client(self) -> Any:  # pragma: no cover - reaching for it is the failure
        raise AssertionError("the fake index must never open a Qdrant connection")

    @property
    def encoder(self) -> Any:  # pragma: no cover - reaching for it is the failure
        raise AssertionError("the fake index must never load the embedding model")

    def ensure(self, force: bool = False) -> bool:
        return False

    def search(self, text: str, limit: int, query_filter: Any = None) -> list[IndexHit]:
        self.queries.append((text, limit, query_filter))
        if self.returns_nothing:
            return []

        scored = [
            (overlap(text, control_text(control)), control.id)
            for control in self.catalog.controls
        ]
        # Score first, control ID as tie-break: the order must not depend on how
        # the catalog was ingested (the same rule the core's mapping follows).
        scored.sort(key=lambda pair: (-pair[0], pair[1]))

        hits: list[IndexHit] = []
        for score, control_id in scored:
            payload = self._payloads[control_id]
            if not matches(query_filter, payload):
                continue
            hits.append(IndexHit(control_id=control_id, score=score, payload=payload))
            if len(hits) == limit:
                break
        return hits


@pytest.fixture
def fake_index(catalog: Catalog) -> FakeIndex:
    return FakeIndex(catalog)


@pytest.fixture
def empty_index(catalog: Catalog) -> FakeIndex:
    """An index that finds nothing: the path where a gap has to be declared."""
    return FakeIndex(catalog, returns_nothing=True)
