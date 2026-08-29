"""UCM-13 - The Qdrant index: the catalog, vectorised, and nothing else.

The index is **derived data**. Everything in it comes from the versioned catalog
JSON and can be thrown away and rebuilt; no decision of the engine is stored here
and nothing is authored here. That is what allows `ensure` to be idempotent and
the startup population to be non-fatal (`app/main.py`): a missing index is a
missing *convenience*, never lost state.

Two design points carry the reproducibility invariant.

**The collection name is a fingerprint, not a label.** It is
`{prefix}_v{catalog_version}_{digest}` where the digest is a SHA-256 of the
catalog as the engine parses it, plus the text template and the model. Change the
catalog, the way controls are rendered into text, or the embedding model, and the
name changes — so a stale collection is never *silently* queried, it is simply a
different collection that this process will not look at. A bump of the catalog
version is the documented convention (never edit a shipped catalog in place); the
digest catches the case where the convention was broken anyway.

**One point per control, not one per mapping.** A mapping is a
(capability, control) pair, and indexing those would mean the retrieval could only
ever return pairs the author already wrote down — it would confirm the catalog
and never widen it, which is the opposite of the point. So the unit is the
control, the mechanism itself, and the mappings it takes part in travel in the
payload (`capability_ids`, `mapping_types`) where they can be filtered on and
shown to the operator without steering the similarity.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field
from qdrant_client import QdrantClient
from qdrant_client import models as qdrant

from app.catalog.loader import get_catalog
from app.catalog.schemas import Catalog, FrameworkControl
from app.core.config import settings
from app.core.exceptions import AppException
from app.retrieval.embeddings import (
    TEXT_TEMPLATE_VERSION,
    Encoder,
    control_text,
    get_encoder,
)

logger = logging.getLogger(__name__)

# The payload keys a filter may act on (UCM-13's three axes plus UCM-52's sector).
# Declared here rather than inline so the index itself says what it is filterable by.
FILTERABLE_KEYS = (
    "jurisdiction",
    "framework",
    "mapping_types",
    "control_type",
    "applies_to_sectors",
)

# Bumped whenever the payload *projection* changes shape (a new field, a different
# aggregation) without the catalog itself changing. The collection name is a
# fingerprint of the catalog, the text template and the model — but not of this
# projection, so a projection change would otherwise be served by a collection
# built before it, silently missing the new field. Folding this into the digest
# forces a clean rebuild. v2: `applies_to_sectors` added for UCM-52.
PAYLOAD_SCHEMA_VERSION = "v2"


class IndexUnavailableError(AppException):
    """Qdrant is unreachable, or the collection could not be built."""

    status_code = 503


class ControlPayload(BaseModel):
    """What travels with a vector: everything a filter or the operator may need.

    None of it is authored here — it is a projection of the catalog. The mapping
    facts are aggregated across every capability the control serves, because the
    point is the control, not one of its mappings.
    """

    model_config = ConfigDict(extra="ignore")

    control_id: str
    framework: str
    official_id: str
    title: str
    jurisdiction: str
    control_type: str
    strength: str
    # The sectors this control governs (UCM-47), projected so the sector lens
    # (UCM-52) can filter on it. Empty means transversal — applies to every sector
    # — and the filter treats it as such, never excluding it.
    applies_to_sectors: list[str] = Field(default_factory=list)
    capability_ids: list[str]
    mapping_types: list[str]
    provenance_sources: list[str]
    catalog_version: str
    # The exact string that was embedded. Kept so a demo or an evaluation run
    # (UCM-18) can show *what* was compared, instead of asking for trust.
    text: str


class IndexHit(BaseModel):
    """One result of a similarity query."""

    model_config = ConfigDict(extra="forbid")

    control_id: str
    score: float
    payload: ControlPayload


def catalog_digest(catalog: Catalog) -> str:
    """Fingerprint of the catalog *as the engine reads it*, plus how it is rendered.

    Hashing the parsed model rather than the file bytes means reformatting the
    JSON does not invalidate the index, while any change to a description, a
    mapping or the text template does.
    """
    material = "\n".join(
        (
            catalog.model_dump_json(),
            TEXT_TEMPLATE_VERSION,
            PAYLOAD_SCHEMA_VERSION,
            settings.EMBEDDING_MODEL,
            str(settings.EMBEDDING_DIM),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


def collection_name(catalog: Catalog) -> str:
    """`catalog_v0_1_0_ab12cd34ef90`. Dots are not valid in a collection name."""
    version = catalog.catalog_version.replace(".", "_")
    return f"{settings.QDRANT_COLLECTION_PREFIX}_v{version}_{catalog_digest(catalog)}"


def point_id(control_id: str) -> str:
    """A stable UUIDv5 per control, so a rebuild overwrites rather than duplicates."""
    return str(uuid5(NAMESPACE_URL, f"tfm-harmonization-engine/control/{control_id}"))


def build_payloads(catalog: Catalog) -> dict[str, ControlPayload]:
    """Project the catalog onto one payload per control, mappings aggregated."""
    capabilities: dict[str, list[str]] = defaultdict(list)
    mapping_types: dict[str, list[str]] = defaultdict(list)
    provenance: dict[str, list[str]] = defaultdict(list)

    for mapping in sorted(catalog.mappings, key=lambda m: (m.control_id, m.capability_id)):
        capabilities[mapping.control_id].append(mapping.capability_id)
        mapping_types[mapping.control_id].append(mapping.mapping_type.value)
        provenance[mapping.control_id].append(mapping.provenance.source.value)

    return {
        control.id: ControlPayload(
            control_id=control.id,
            framework=control.framework.value,
            official_id=control.official_id,
            title=control.title,
            jurisdiction=control.jurisdiction.value,
            control_type=control.control_type.value,
            strength=control.strength.label,
            applies_to_sectors=[s.value for s in control.applies_to_sectors],
            capability_ids=capabilities[control.id],
            # Deduplicated and sorted: a filter asks "does this control take part
            # in a total mapping anywhere", not "how many times".
            mapping_types=sorted(set(mapping_types[control.id])),
            provenance_sources=sorted(set(provenance[control.id])),
            catalog_version=catalog.catalog_version,
            text=control_text(control),
        )
        for control in sorted(catalog.controls, key=lambda c: c.id)
    }


class CatalogIndex:
    """The catalog's vectors in Qdrant, built on demand and queried by capability.

    Synchronous on purpose: encoding is CPU-bound and the deterministic core it
    sits next to is synchronous too. The API layer (M3) offloads a retrieval to a
    worker thread rather than pretending this is I/O-bound.
    """

    def __init__(
        self,
        catalog: Catalog | None = None,
        client: QdrantClient | None = None,
        encoder: Encoder | None = None,
    ):
        self.catalog = catalog if catalog is not None else get_catalog()
        self._client = client
        self._encoder = encoder
        self.collection = collection_name(self.catalog)
        self.digest = catalog_digest(self.catalog)
        self._payloads = build_payloads(self.catalog)
        self._ready = False

    # --- lazily built collaborators ------------------------------------------

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(
                url=settings.QDRANT_URL, timeout=settings.QDRANT_TIMEOUT_SECONDS
            )
        return self._client

    @property
    def encoder(self) -> Encoder:
        if self._encoder is None:
            self._encoder = get_encoder()
        return self._encoder

    # --- population -----------------------------------------------------------

    def ensure(self, force: bool = False) -> bool:
        """Make sure the collection exists and holds every control. Idempotent.

        Returns True when it had to (re)build. A collection whose name matches is
        a collection built from this exact catalog with this exact model, so the
        only thing left to check is that it is complete — an interrupted first
        population is the realistic failure, and it is repaired by rebuilding.
        """
        if self._ready and not force:
            return False

        expected = len(self._payloads)
        try:
            if not force and self.client.collection_exists(self.collection):
                stored = self.client.count(self.collection, exact=True).count
                if stored == expected:
                    self._ready = True
                    logger.info(
                        "Qdrant: colección %s ya poblada (%d controles)", self.collection, stored
                    )
                    return False
                logger.warning(
                    "Qdrant: colección %s incompleta (%d de %d controles); se repuebla",
                    self.collection,
                    stored,
                    expected,
                )
            self._populate()
        except IndexUnavailableError:
            raise
        except Exception as exc:
            raise IndexUnavailableError(
                f"No se pudo preparar la colección '{self.collection}' en "
                f"{settings.QDRANT_URL}: {exc}"
            ) from exc

        self._ready = True
        return True

    def warm(self) -> None:
        """Load the embedding model now, so no operator's request has to.

        `ensure` only loads it when it has to *build* the collection. On every
        start after the first the collection is already there, `ensure` returns
        early, and the ~1.1 GB of weights are then deserialised inside whichever
        `POST /candidates` happens to arrive first — a minute of waiting on the
        one call the operator is watching, once per process, for no reason.

        So this is called from the startup task, in the same background thread
        and with the same best-effort contract: retrieval widens candidate
        coverage and never gates it, so a failure here costs a slow first query,
        never a baseline. One trivial encode is enough — the cost is the load,
        not the arithmetic.
        """
        self.encoder.encode_query("warmup")

    def _populate(self) -> None:
        """Encode every control and write the collection from scratch."""
        controls = sorted(self.catalog.controls, key=lambda c: c.id)
        vectors = self.encoder.encode_passages([self._payloads[c.id].text for c in controls])

        self.client.delete_collection(self.collection)
        self.client.create_collection(
            self.collection,
            vectors_config=qdrant.VectorParams(
                size=settings.EMBEDDING_DIM, distance=qdrant.Distance.COSINE
            ),
        )
        for key in FILTERABLE_KEYS:
            self.client.create_payload_index(
                self.collection, field_name=key, field_schema=qdrant.PayloadSchemaType.KEYWORD
            )

        self.client.upsert(
            self.collection,
            points=[
                qdrant.PointStruct(
                    id=point_id(control.id),
                    vector=vector,
                    payload=self._payloads[control.id].model_dump(),
                )
                for control, vector in zip(controls, vectors, strict=True)
            ],
            wait=True,
        )
        logger.info(
            "Qdrant: colección %s poblada con %d controles del catálogo %s",
            self.collection,
            len(controls),
            self.catalog.catalog_version,
        )

    # --- querying -------------------------------------------------------------

    def search(
        self, text: str, limit: int, query_filter: qdrant.Filter | None = None
    ) -> list[IndexHit]:
        """Nearest controls to a query text, most similar first.

        No score threshold, by design: a threshold drops candidates without saying
        so, and the one thing this pass may not do is restrict in silence. What
        bounds the result is `limit`, and what it left out is a *ranking* decision
        the caller records, not a hidden filter.
        """
        self.ensure()
        vector = self.encoder.encode_query(text)
        try:
            response = self.client.query_points(
                self.collection,
                query=vector,
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
            )
        except Exception as exc:
            raise IndexUnavailableError(
                f"Falló la consulta a Qdrant sobre '{self.collection}': {exc}"
            ) from exc

        return [
            IndexHit(
                control_id=str(payload["control_id"]),
                score=float(point.score),
                payload=ControlPayload.model_validate(payload),
            )
            for point in response.points
            if (payload := _payload_of(point))
        ]

    # --- catalog facts the service needs -------------------------------------

    def control(self, control_id: str) -> FrameworkControl:
        for control in self.catalog.controls:
            if control.id == control_id:
                return control
        raise KeyError(f"control not in the catalog: {control_id}")

    @property
    def indexed_controls(self) -> int:
        return len(self._payloads)


def _payload_of(point: qdrant.ScoredPoint) -> dict[str, Any] | None:
    payload = point.payload
    return payload if payload and payload.get("control_id") else None
