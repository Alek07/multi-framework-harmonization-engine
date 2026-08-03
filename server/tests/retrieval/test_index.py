"""UCM-13 - The index is a faithful, disposable projection of the catalog."""

from __future__ import annotations

from app.catalog.schemas import Catalog
from app.core.config import settings
from app.retrieval.embeddings import capability_text, control_text
from app.retrieval.index import (
    CatalogIndex,
    build_payloads,
    catalog_digest,
    collection_name,
    point_id,
)


def test_every_control_is_indexed(catalog: Catalog) -> None:
    payloads = build_payloads(catalog)

    assert set(payloads) == catalog.control_ids
    assert len(payloads) == len(catalog.controls)


def test_the_payload_aggregates_every_mapping_of_the_control(catalog: Catalog) -> None:
    """The point is the control, so its mapping facts are the union of its mappings."""
    payloads = build_payloads(catalog)

    for control_id, payload in payloads.items():
        mappings = [m for m in catalog.mappings if m.control_id == control_id]
        assert payload.capability_ids == sorted(m.capability_id for m in mappings)
        assert payload.mapping_types == sorted({m.mapping_type.value for m in mappings})


def test_the_indexed_text_is_what_the_control_says_not_where_it_comes_from(
    catalog: Catalog,
) -> None:
    """Framework and official ID are payload, never encoded text.

    Otherwise a query could match on the name of a standard instead of on what the
    control does, and the retrieval would rediscover the catalog's own labels.
    """
    control = next(c for c in catalog.controls if c.framework.value == "IEC62443")
    text = control_text(control)

    assert control.title in text
    assert control.paraphrased_description in text
    assert control.official_id not in text
    assert control.framework.value not in text


def test_the_capability_query_carries_its_ot_refinements(catalog: Catalog) -> None:
    capability = next(c for c in catalog.capabilities if c.ot_refinements)
    text = capability_text(capability)

    assert capability.name in text
    for refinement in capability.ot_refinements:
        assert refinement.rstrip(".") in text


def test_the_collection_name_fingerprints_the_catalog(catalog: Catalog) -> None:
    """A catalog bump — or an edit in place — is a different collection, not stale vectors."""
    name = collection_name(catalog)

    assert name.startswith(f"{settings.QDRANT_COLLECTION_PREFIX}_v0_1_0_")
    assert catalog_digest(catalog) in name
    assert "." not in name

    edited = catalog.model_copy(deep=True)
    edited.controls[0].paraphrased_description += " (retocado)"

    assert catalog_digest(edited) != catalog_digest(catalog)
    assert collection_name(edited) != name


def test_the_collection_name_follows_the_embedding_model(catalog: Catalog) -> None:
    """Same catalog, different model: different vectors, so a different collection."""
    before = collection_name(catalog)
    settings.EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
    try:
        assert collection_name(catalog) != before
    finally:
        settings.EMBEDDING_MODEL = "intfloat/multilingual-e5-base"


def test_point_ids_are_stable_across_rebuilds(catalog: Catalog) -> None:
    """A repopulation must overwrite the same points, never duplicate them."""
    first = {c.id: point_id(c.id) for c in catalog.controls}
    second = {c.id: point_id(c.id) for c in catalog.controls}

    assert first == second
    assert len(set(first.values())) == len(first)


class _RecordingEncoder:
    """Stands in for the model: records that it was asked to encode, nothing more."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def encode_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.0] * settings.EMBEDDING_DIM

    def encode_passages(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover
        return [[0.0] * settings.EMBEDDING_DIM for _ in texts]


def test_warming_loads_the_model_without_touching_qdrant(catalog: Catalog) -> None:
    """The startup task's warm-up: the weights, and only the weights.

    `ensure` loads the model only when it has to *build* the collection, so on
    every start after the first the ~1.1 GB would be deserialised inside the
    operator's first `POST /candidates`. `warm` is what moves that cost to
    startup, and it must do it without needing Qdrant — the two are separate
    failures and the index may legitimately be up before the vector store is.
    """
    encoder = _RecordingEncoder()
    index = CatalogIndex(catalog=catalog, client=None, encoder=encoder)

    index.warm()

    assert encoder.queries, "warm() did not reach the encoder, so it warms nothing"
    # No collection was created, counted or queried: `client` was never resolved.
    assert index._client is None
