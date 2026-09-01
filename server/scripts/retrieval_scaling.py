"""UCM-51 - How the retriever behaves as the corpus grows, measured on this project's own data.

The question is whether semantic retrieval starts to *discriminate* as the
catalog grows, or whether the flat similarity band recorded at v0.1.0 (~0.90 for
the first hit, ~0.83 for the tenth, `app/retrieval/service.py`) was a property of
the model rather than of a small, homogeneous corpus. It is answered with real
measurement points rather than synthetic corpora, because the repo happens to
contain the curve already: four frozen catalog versions.

**Two size points, not four.** The versions are v0.1.0 (69 controls), v0.2.0
(225), v0.3.0 (226) and v0.4.0 (226). The growth all happens once, at
v0.1.0 -> v0.2.0; the last two add one control between them. So v0.3.0 and v0.4.0
are not points on a *size* curve — they measure what changing the text and the
payload does at constant size, which is a different and smaller question. Saying
this here rather than plotting four points as if they were four sizes is the
whole difference between a curve and a decoration.

**The comparison is controlled.** v0.1.0's 24 capabilities and 69 controls are a
strict subset of v0.4.0's, and the 24 capability texts are byte-identical across
every version — so the same 24 queries run against every corpus, which is what
makes the numbers comparable. One confounder is real and is reported instead of
hidden: 20 of the 69 shared controls had their title or description edited after
v0.1.0, so the passages are not perfectly frozen. The report counts how often
those 20 reach a top-k, which is the size of the doubt.

**What is measured, and what is deliberately not.** Measured: the opening of the
similarity band, how hard the `top_k` cut is (what fraction of the catalog it
keeps, and how many near-ties it slices through blind — the input UCM-54 needs),
recall of the author's own mappings at several k, whether the retrieved set
changes from zone to zone, cost and latency, and the silent-omission invariant at
every size. Not measured: precision. Retrieval exists to widen (invariant 2), so
a hit outside the author's mappings is the feature and counting it as an error
would be measuring the opposite of the thing. Not measured either: precision and
recall against the golden baseline. That instrument exists (UCM-5) but lives
outside the repo by design — built blind to the catalog, held and frozen by the
author — and invariant 9 forbids the engine from reading it. It is also frozen
against the v0.1.0 world, which the `recall_frozen_truth` metric here happens to
show the cost of: judging 226 controls with a 69-control yardstick reports a
regression the engine did not commit.

Three arms, all against the same corpora:

* `plain` — the shipped query, `capability_text`.
* `zone` — the same query with the zone's own context appended. Run to *measure
  the dilution*, not because it is expected to win: a bi-encoder compresses the
  whole string into one vector and much of a zone's context is negation, which is
  structurally invisible to it.
* `title` — the passage reduced to the control's title, with the paraphrased
  description dropped. A stand-in for the "expanded descriptions" arm of the
  ticket: expanding the catalog's prose is an authoring bump (a new catalog
  version), while removing it measures the same thing — how much of the ranking
  the description is carrying — at no catalog cost. The capability names a
  control is mapped to are deliberately *not* added to any passage: that would
  leak the author's mappings into the vector and inflate the recall metric
  circularly.

The script decides nothing and changes no shipped default. It reads the retriever
through its own code path (`CatalogIndex`, real Qdrant, real e5) and counts.

It needs Qdrant up, and it leaves it as it found it. Each point of the curve gets
its own collection — the collection name is a fingerprint of the catalog, so the
one the API serves is never confused with a measurement — and every collection
built here is dropped at the end except that one, which is kept precisely so the
next API start does not have to repopulate it. Vectors built to be measured are
not deployment state.

Run from `server/`:

    uv run python scripts/retrieval_scaling.py
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.assets.loader import available_profiles, get_profile  # noqa: E402
from app.catalog.loader import get_catalog, load_catalog  # noqa: E402
from app.catalog.schemas import (  # noqa: E402
    Capability,
    Catalog,
    FrameworkControl,
    Sector,
)
from app.core.config import settings  # noqa: E402
from app.engine.gating_rules import load_gating_rules  # noqa: E402
from app.engine.schemas import ZoneContext  # noqa: E402
from app.engine.service import gate_profile, resolve_profile  # noqa: E402
from app.engine.zones import zone_context  # noqa: E402
from app.retrieval.embeddings import capability_text  # noqa: E402
from app.retrieval.filters import to_qdrant  # noqa: E402
from app.retrieval.index import (  # noqa: E402
    CatalogIndex,
    build_payloads,
    collection_name,
)
from app.retrieval.schemas import PayloadFilter  # noqa: E402
from app.retrieval.service import RetrievalService  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS = REPO_ROOT / "docs" / "experimento-escalado-recuperador.json"

# Every frozen catalog with the gating rules of its own era. The pairing is not
# cosmetic: gating v0.2.0 names controls that do not exist in v0.1.0 and refuses
# to validate against it, which is the rules layer correctly declining to judge a
# catalog it was not written for.
POINTS = (
    ("0.1.0", "data/catalog/catalog.v0.1.0.json", "data/rules/gating.v0.1.0.json"),
    ("0.2.0", "data/catalog/catalog.v0.2.0.json", "data/rules/gating.v0.2.0.json"),
    ("0.3.0", "data/catalog/catalog.v0.3.0.json", "data/rules/gating.v0.2.0.json"),
    ("0.4.0", "data/catalog/catalog.v0.4.0.json", "data/rules/gating.v0.2.0.json"),
)

BASELINE_POINT = "0.1.0"
REFERENCE_POINT = "0.4.0"

# The k values the report reads the ranking at. 10 is the shipped RAG_TOP_K.
K_VALUES = (1, 5, 10, 20, 50)

# Two scores closer than this are a tie the operator could not have told apart.
# It is a reading aid for the cut, not a threshold the engine applies anywhere.
TIE_EPSILON = 0.01


# --- passage and query templates ------------------------------------------------


def title_only(control: FrameworkControl) -> str:
    return f"{control.title.strip().rstrip('.')}."


def zone_enriched(capability: Capability, zone: ZoneContext) -> str:
    """The shipped query with the zone's declared premises appended, in Spanish."""
    nature = zone.nature
    traits = [
        "con sistema operativo de propósito general"
        if nature.general_purpose_os
        else "sin sistema operativo de propósito general",
        "conectado en red" if nature.networked else "aislado de la red",
        "híbrido IT/OT" if nature.hybrid_it_ot else "puramente de proceso",
        "con usuarios interactivos" if nature.interactive_users else "sin usuarios interactivos",
        "con superficie ofimática" if nature.office_it_surface else "sin superficie ofimática",
    ]
    if zone.safety_relevant:
        traits.append("relevante para la seguridad física")
    context = (
        f"Zona {zone.zone_id}, entorno {zone.domain.value}, nivel de seguridad objetivo "
        f"SL{zone.target_sl}, {', '.join(traits)}."
    )
    return f"{capability_text(capability)} {context}"


# --- indexes --------------------------------------------------------------------


def build_index(
    catalog: Catalog, passage: Callable[[FrameworkControl], str] | None = None
) -> tuple[CatalogIndex, float]:
    """One collection for this catalog, optionally with a different passage template.

    A variant template is applied by rewriting the projected payload text before
    the collection is populated, and by tagging the collection name so it cannot
    collide with the shipped one. Everything else — the encoder, the filters, the
    search — is the code the API runs.

    The population is **forced**. `ensure` is idempotent and returns early when the
    collection is already complete, which is right for the API and useless here:
    the second run of this script would report a build cost of 0.0 s and call it a
    measurement. Forcing it is what makes the number on the report the real price
    of encoding this corpus on this machine.
    """
    index = CatalogIndex(catalog=catalog)
    if passage is not None:
        payloads = build_payloads(catalog)
        for control in catalog.controls:
            payloads[control.id].text = passage(control)
        index._payloads = payloads  # noqa: SLF001 - variant arm, contained in this script
        index.collection = f"{index.collection}_title"
    index.encoder.encode_query("warmup")  # the model load is not the build cost
    started = time.perf_counter()
    index.ensure(force=True)
    return index, time.perf_counter() - started


# --- one measured query ---------------------------------------------------------


def ranked(index: CatalogIndex, query: str) -> list[tuple[str, float]]:
    """The whole corpus, ranked. Everything else in the report is derived from this."""
    hits = index.search(query, limit=index.indexed_controls)
    return [(hit.control_id, hit.score) for hit in hits]


def band(scores: list[float]) -> dict[str, float]:
    """The shape of the similarity distribution for one query over one corpus."""
    return {
        "first": scores[0],
        "tenth": scores[9] if len(scores) > 9 else scores[-1],
        "last": scores[-1],
        "spread_1_10": scores[0] - (scores[9] if len(scores) > 9 else scores[-1]),
        "spread_1_last": scores[0] - scores[-1],
        "stdev": statistics.pstdev(scores) if len(scores) > 1 else 0.0,
    }


def near_ties(scores: list[float], k: int) -> int:
    """How many controls sit within `TIE_EPSILON` of the k-th score.

    This is the cut's real ambiguity: `top_k` keeps k of them and drops the rest
    without being able to tell them apart. It is the number UCM-54 needs, and it
    is not the same as the band being narrow — a wide band can still be dense
    exactly where the knife falls.
    """
    if len(scores) <= k:
        return 0
    floor = scores[k - 1] - TIE_EPSILON
    return sum(1 for score in scores if score >= floor) - k


def recall_at(ranking: list[str], truth: set[str], k: int) -> float | None:
    """Fraction of the author's mapped controls that survive the top-k cut."""
    if not truth:
        return None
    return len(set(ranking[:k]) & truth) / len(truth)


# --- the sector lens as part of the measurement (UCM-47/UCM-52) -------------------


def asset_sectors() -> list[Sector]:
    """The sectors the shipped profiles actually declare. Read, never assumed.

    Both frozen profiles are `energy`, but hardcoding that would make the metric
    below a claim about a constant instead of about the assets the POC ships.
    """
    declared: list[Sector] = []
    for profile_id in available_profiles():
        for sector in get_profile(profile_id).sectors:
            if sector not in declared:
                declared.append(sector)
    return declared


def sector_applicable(control: FrameworkControl, sectors: list[Sector]) -> bool:
    """Whether the zone's sectors leave this control in scope (UCM-47's own rule).

    An empty declared scope is transversal and always applies — the CIS/CSF/IEC
    case. Only an *enumerated* scope disjoint from the asset's excludes, which is
    exactly what `filters.excluded_axes` does; the rule is mirrored rather than
    reinvented so the metric cannot disagree with the engine it measures.
    """
    declared = set(control.applies_to_sectors)
    return not declared or bool(declared & set(sectors))


def sector_adjusted(
    truth: set[str], reference: dict[str, FrameworkControl], sectors: list[Sector]
) -> set[str]:
    """The frozen ground truth minus what does not govern this asset at all.

    This exists because the yardstick and the engine disagree about a real thing.
    The truth is frozen at v0.1.0, a catalog that declared **no** sectoral scope
    whatsoever, so it maps IMO's maritime governance control to a gas pipeline's
    risk-management capability. UCM-47 later declared that scope, and UCM-52 acts
    on it. Counting that control as a retrieval miss scores the engine as failing
    at the moment it is correct — so applicability is read from the *reference*
    catalog (where it is declared) and applied to the frozen mapping set.

    Applied identically at every point of the curve, including the ones whose own
    catalog declares nothing, because a yardstick that changes between points
    measures nothing.
    """
    return {
        control_id
        for control_id in truth
        if control_id not in reference or sector_applicable(reference[control_id], sectors)
    }


# --- the points -----------------------------------------------------------------


def shared_capabilities(catalogs: dict[str, Catalog]) -> list[str]:
    """Capabilities present in every point, with identical text. The controlled query set."""
    ids: set[str] | None = None
    for catalog in catalogs.values():
        here = {c.id for c in catalog.capabilities}
        ids = here if ids is None else ids & here
    shared = sorted(ids or set())

    texts = {
        version: {c.id: capability_text(c) for c in catalog.capabilities}
        for version, catalog in catalogs.items()
    }
    drifted = [
        cap
        for cap in shared
        if len({texts[version][cap] for version in catalogs}) > 1
    ]
    if drifted:
        raise SystemExit(
            f"the shared capabilities are not textually identical across points: {drifted}. "
            "The comparison would not be controlled; fix the query set before reporting."
        )
    return shared


def edited_controls(catalogs: dict[str, Catalog]) -> set[str]:
    """Controls shared by the baseline and the reference whose passage text changed."""
    base = {c.id: c for c in catalogs[BASELINE_POINT].controls}
    ref = {c.id: c for c in catalogs[REFERENCE_POINT].controls}
    return {
        cid
        for cid in base.keys() & ref.keys()
        if (base[cid].title, base[cid].paraphrased_description)
        != (ref[cid].title, ref[cid].paraphrased_description)
    }


def measure_point(
    version: str,
    catalog: Catalog,
    index: CatalogIndex,
    queries: dict[str, str],
    truth: dict[str, set[str]],
    frozen_truth: dict[str, set[str]],
    sector_lens: PayloadFilter,
    adjusted_truth: dict[str, set[str]],
) -> dict[str, Any]:
    """Band, cut and recall for one corpus under one arm.

    Two rankings are read, not one. The unfiltered ranking is the bi-encoder on
    its own — the subject of the curve. The second applies the engine's own
    sectoral lens (UCM-52) and is scored against the applicability-corrected
    ground truth, because those two belong together: filtering the ranking while
    still demanding a maritime control back would measure a contradiction.
    """
    lens_filter = to_qdrant(sector_lens)
    per_capability: dict[str, Any] = {}
    for capability_id, query in queries.items():
        started = time.perf_counter()
        results = ranked(index, query)
        elapsed_ms = (time.perf_counter() - started) * 1000
        ids = [control_id for control_id, _ in results]
        scores = [score for _, score in results]
        lensed = [hit.control_id for hit in index.search(query, max(K_VALUES), lens_filter)]
        per_capability[capability_id] = {
            "band": band(scores),
            "near_ties_at_10": near_ties(scores, settings.RAG_TOP_K),
            "recall": {
                str(k): recall_at(ids, truth.get(capability_id, set()), k) for k in K_VALUES
            },
            "recall_frozen_truth": {
                str(k): recall_at(ids, frozen_truth.get(capability_id, set()), k) for k in K_VALUES
            },
            # The engine's lens applied, but still judged by the uncorrected
            # yardstick: isolates what the filter alone does to the ranking.
            "recall_sector_lens": {
                str(k): recall_at(lensed, frozen_truth.get(capability_id, set()), k)
                for k in K_VALUES
            },
            # Lens applied *and* the yardstick corrected for applicability. This is
            # the honest figure for the current engine on these assets.
            "recall_sector_adjusted": {
                str(k): recall_at(lensed, adjusted_truth.get(capability_id, set()), k)
                for k in K_VALUES
            },
            "truth_dropped_as_inapplicable": sorted(
                frozen_truth.get(capability_id, set()) - adjusted_truth.get(capability_id, set())
            ),
            "top_k_ids": ids[: settings.RAG_TOP_K],
            "full_query_ms": elapsed_ms,
        }

    return {
        "catalog_version": version,
        "controls": len(catalog.controls),
        "capabilities": len(catalog.capabilities),
        "mappings": len(catalog.mappings),
        "collection": index.collection,
        "cut_fraction": settings.RAG_TOP_K / len(catalog.controls),
        "capabilities_measured": per_capability,
    }


def averages(point: dict[str, Any], key: Callable[[dict[str, Any]], float | None]) -> float | None:
    values = [
        value
        for measured in point["capabilities_measured"].values()
        if (value := key(measured)) is not None
    ]
    return statistics.fmean(values) if values else None


def summarize(point: dict[str, Any], against: dict[str, Any] | None = None) -> dict[str, Any]:
    """The aggregates the report prints for one point, computed once and kept.

    The secondary arms are summarised so their per-capability detail does not have
    to be *stored*. The results file is derived data — the script regenerates it
    from scratch, deterministically — and 245 KB of zone-arm rows backing twelve
    printed numbers is not evidence, it is weight. What the document reasons over
    capability by capability is the `plain` arm, and that one keeps its detail.

    `against` is the same point under the plain query, used for the top-10 overlap:
    it has to be computed here because both sides' `top_k_ids` are about to go.
    """
    summary = {
        "first": averages(point, lambda m: m["band"]["first"]),
        "tenth": averages(point, lambda m: m["band"]["tenth"]),
        "recall_frozen_truth_10": averages(point, lambda m: m["recall_frozen_truth"]["10"]),
        "recall_sector_adjusted_10": averages(point, lambda m: m["recall_sector_adjusted"]["10"]),
    }
    if against is not None:
        measured = point["capabilities_measured"]
        reference = against["capabilities_measured"]
        summary["top10_shared_with_plain"] = statistics.fmean(
            [
                len(set(measured[cid]["top_k_ids"]) & set(reference[cid]["top_k_ids"]))
                for cid in measured
                if cid in reference
            ]
        )
    return summary


# --- zone discrimination and the invariant ---------------------------------------


def zone_discrimination(version: str, catalog: Catalog, gating_path: str) -> dict[str, Any]:
    """Does the retrieved set change from zone to zone? Measured through the shipped service.

    Run per profile, with the deterministic core's own resolution and gating, so
    what is compared is what an operator would actually be shown — including the
    sector lens UCM-52 builds from the zone. Two zones of one profile that come
    back with identical sets mean the retrieval is not reading the asset yet, and
    that is a finding, not a bug in the measurement.
    """
    service = RetrievalService(index=CatalogIndex(catalog=catalog))
    gating_rules = load_gating_rules(gating_path)
    report: dict[str, Any] = {}

    for profile_id in available_profiles():
        profile = get_profile(profile_id)
        resolution = resolve_profile(profile, catalog)
        gating = gate_profile(profile, resolution, gating_rules, catalog=catalog)
        retrieval = service.retrieve_profile(resolution, gating=gating)

        offered: dict[str, dict[str, set[str]]] = {}
        pairs = 0
        gaps = 0
        dropped = 0
        for zone in retrieval.zones:
            per_capability: dict[str, set[str]] = {}
            for capability in zone.capabilities:
                pairs += 1
                gaps += 1 if capability.gap is not None else 0
                if not set(capability.catalog_control_ids) <= set(capability.offered_control_ids):
                    dropped += 1
                per_capability[capability.capability_id] = {
                    hit.control_id for hit in capability.retrieved
                }
            offered[zone.zone.zone_id] = per_capability

        overlaps = []
        zone_ids = list(offered)
        for left in range(len(zone_ids)):
            for right in range(left + 1, len(zone_ids)):
                a, b = offered[zone_ids[left]], offered[zone_ids[right]]
                for capability_id in a.keys() & b.keys():
                    union = a[capability_id] | b[capability_id]
                    overlaps.append(
                        len(a[capability_id] & b[capability_id]) / len(union) if union else 1.0
                    )

        report[profile_id] = {
            "catalog_version": version,
            "zones": zone_ids,
            "capability_zone_pairs": pairs,
            "declared_gaps": gaps,
            "catalog_candidates_dropped": dropped,
            "mean_jaccard_between_zones": statistics.fmean(overlaps) if overlaps else None,
            "compared_capabilities": len(overlaps),
        }
    return report


def drop_experiment_collections(built: list[CatalogIndex]) -> list[str]:
    """Leave Qdrant as the experiment found it, minus the collection the API serves.

    Every point of the curve gets its own collection, and the `title` arm gets one
    more per point — vectors that exist only to be measured and that nothing else
    can ever query. Leaving them behind would quietly turn a measurement into
    deployment state. The collection of the *active* catalog is deliberately kept:
    dropping it would cost the next API start a full repopulation, and this script
    has no business making the deployment slower.
    """
    active = collection_name(get_catalog())
    dropped: list[str] = []
    for index in built:
        if index.collection == active:
            continue
        try:
            index.client.delete_collection(index.collection)
            dropped.append(index.collection)
        except Exception as exc:  # noqa: BLE001 - derived data; a failure here is cosmetic
            print(f"   aviso: no se pudo borrar {index.collection}: {exc}")
    return dropped


def shipped_latency(index: CatalogIndex, queries: dict[str, str]) -> dict[str, float]:
    """Latency of a query as the API issues it: the shipped limit, not the whole corpus.

    Reported as two figures that add up, because they scale with completely
    different things. `index.search` encodes the query itself, so the whole call is
    timed and the encode — measured separately — is subtracted out: what is left is
    Qdrant's own share. The encode is a fixed cost of the model on this CPU and does
    not care how big the catalog is; only the remainder does.
    """
    encode_ms: list[float] = []
    total_ms: list[float] = []
    for query in queries.values():
        started = time.perf_counter()
        index.encoder.encode_query(query)
        encode_ms.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        index.search(query, limit=settings.RAG_TOP_K)
        total_ms.append((time.perf_counter() - started) * 1000)
    encode = statistics.fmean(encode_ms)
    total = statistics.fmean(total_ms)
    return {
        "encode_query_ms_mean": encode,
        "query_total_ms_mean": total,
        "qdrant_share_ms_mean": total - encode,
        "queries": len(encode_ms),
    }


# --- the report -----------------------------------------------------------------


def run() -> tuple[dict[str, Any], dict[str, Catalog], set[str]]:
    catalogs = {version: load_catalog(path) for version, path, _ in POINTS}
    shared = shared_capabilities(catalogs)
    edited = edited_controls(catalogs)

    print("== Puntos de medición (catálogos congelados en el repo)")
    for version, _, gating_path in POINTS:
        catalog = catalogs[version]
        print(
            f"   v{version:6} capacidades={len(catalog.capabilities):3} "
            f"controles={len(catalog.controls):4} mapeos={len(catalog.mappings):4} "
            f"gating={Path(gating_path).name}"
        )
    print(f"   consultas controladas: {len(shared)} capacidades compartidas por los cuatro puntos")
    print(
        f"   confusor declarado: {len(edited)} de los {len(catalogs[BASELINE_POINT].controls)} "
        f"controles compartidos cambiaron de texto entre v{BASELINE_POINT} y v{REFERENCE_POINT}"
    )

    frozen_truth = {
        capability_id: {m.control_id for m in catalogs[BASELINE_POINT].mappings_for(capability_id)}
        for capability_id in shared
    }

    sectors = asset_sectors()
    sector_lens = PayloadFilter(sectors=sectors)
    reference_controls = {c.id: c for c in catalogs[REFERENCE_POINT].controls}
    adjusted_truth = {
        capability_id: sector_adjusted(truth_set, reference_controls, sectors)
        for capability_id, truth_set in frozen_truth.items()
    }
    inapplicable = {
        control_id
        for capability_id, truth_set in frozen_truth.items()
        for control_id in truth_set - adjusted_truth[capability_id]
    }
    print(
        f"   lente sectorial de los perfiles: {[s.value for s in sectors]}; "
        f"{sum(1 for c in catalogs[REFERENCE_POINT].controls if c.applies_to_sectors)} de "
        f"{len(catalogs[REFERENCE_POINT].controls)} controles declaran ámbito en "
        f"v{REFERENCE_POINT}"
    )
    print(
        f"   verdad corregida por aplicabilidad: {len(inapplicable)} control(es) que no gobiernan "
        f"este activo salen del patrón {sorted(inapplicable)}"
    )

    results: dict[str, Any] = {
        "settings": {
            "embedding_model": settings.EMBEDDING_MODEL,
            "embedding_dim": settings.EMBEDDING_DIM,
            "embedding_num_threads": settings.EMBEDDING_NUM_THREADS,
            "rag_top_k": settings.RAG_TOP_K,
            "tie_epsilon": TIE_EPSILON,
        },
        "points": [
            {"catalog_version": v, "controls": len(catalogs[v].controls)} for v, _, _ in POINTS
        ],
        "controlled_query_set": shared,
        "edited_shared_controls": sorted(edited),
        "detail_note": (
            "El brazo 'plain' conserva el detalle por capacidad, que es sobre el que razona el "
            "documento. Los brazos 'title' y 'zone' se guardan solo como agregados ('summary'): "
            "todo lo que el informe imprime de ellos está ahí, y el fichero se regenera entero "
            "ejecutando scripts/retrieval_scaling.py."
        ),
        "arms": {},
        "zone_discrimination": {},
    }

    # --- arm 1 and 3: the corpus curve, per passage template ---------------------
    indexes: dict[str, CatalogIndex] = {}
    built: list[CatalogIndex] = []
    for arm, passage in (("plain", None), ("title", title_only)):
        arm_results: dict[str, Any] = {}
        for version, _, _ in POINTS:
            catalog = catalogs[version]
            index, build_seconds = build_index(catalog, passage)
            built.append(index)
            if arm == "plain":
                indexes[version] = index
            queries = {
                c.id: capability_text(c) for c in catalog.capabilities if c.id in shared
            }
            truth = {
                capability_id: {m.control_id for m in catalog.mappings_for(capability_id)}
                for capability_id in shared
            }
            point = measure_point(
                version, catalog, index, queries, truth, frozen_truth, sector_lens, adjusted_truth
            )
            point["index_build_seconds"] = build_seconds
            point["latency"] = shipped_latency(index, queries)
            arm_results[version] = point
        results["arms"][arm] = arm_results

    # --- arm 2: the same queries, enriched with the zone's premises ---------------
    zone_arm: dict[str, Any] = {}
    for version, _, _ in POINTS:
        catalog = catalogs[version]
        index = indexes[version]
        by_id = {c.id: c for c in catalog.capabilities}
        truth = {
            capability_id: {m.control_id for m in catalog.mappings_for(capability_id)}
            for capability_id in shared
        }
        zones: list[ZoneContext] = []
        for profile_id in available_profiles():
            profile = get_profile(profile_id)
            zones.extend(zone_context(zone, profile) for zone in profile.zones)

        per_zone: dict[str, Any] = {}
        for zone in zones:
            queries = {cid: zone_enriched(by_id[cid], zone) for cid in shared}
            per_zone[zone.zone_id] = measure_point(
                version, catalog, index, queries, truth, frozen_truth, sector_lens, adjusted_truth
            )
        zone_arm[version] = per_zone
    results["arms"]["zone"] = zone_arm

    # Summarise the secondary arms and drop their per-capability rows: everything
    # the report prints for them is in the summary, and the file is regenerable.
    for version, _, _ in POINTS:
        plain_point = results["arms"]["plain"][version]
        results["arms"]["title"][version]["summary"] = summarize(
            results["arms"]["title"][version]
        )
        results["arms"]["title"][version].pop("capabilities_measured")
        for point in results["arms"]["zone"][version].values():
            point["summary"] = summarize(point, against=plain_point)
            point.pop("capabilities_measured")
        results["arms"]["plain"][version]["summary"] = summarize(plain_point)

    # --- zone discrimination through the shipped service --------------------------
    for version, _, gating_path in POINTS:
        results["zone_discrimination"][version] = zone_discrimination(
            version, catalogs[version], gating_path
        )

    results["dropped_collections"] = drop_experiment_collections(built)

    return results, catalogs, edited


def report(
    results: dict[str, Any],
    catalogs: dict[str, Catalog],
    edited: set[str],
) -> None:
    plain = results["arms"]["plain"]
    title = results["arms"]["title"]

    print("\n== Apertura de la banda de similitud (consulta enviada, media de las 24 capacidades)")
    print("   versión  controles   1º      10º     1º-10º   último   desv.  empates <=0,01")
    for version, _, _ in POINTS:
        point = plain[version]
        print(
            f"   v{version:6} {point['controls']:9} "
            f"{averages(point, lambda m: m['band']['first']):6.3f}  "
            f"{averages(point, lambda m: m['band']['tenth']):6.3f}  "
            f"{averages(point, lambda m: m['band']['spread_1_10']):6.3f}   "
            f"{averages(point, lambda m: m['band']['last']):6.3f}  "
            f"{averages(point, lambda m: m['band']['stdev']):6.3f}  "
            f"{averages(point, lambda m: float(m['near_ties_at_10'])):6.1f}"
        )

    print("\n== Dureza del corte: qué fracción del catálogo sobrevive a top_k=10")
    for version, _, _ in POINTS:
        point = plain[version]
        ties = averages(point, lambda m: float(m["near_ties_at_10"])) or 0.0
        print(
            f"   v{version:6} {point['controls']:4} controles -> "
            f"{point['cut_fraction'] * 100:5.1f}% del catálogo sobrevive; "
            f"{ties:5.1f} controles ({ties / point['controls'] * 100:4.1f}% del catálogo) quedan "
            f"a menos de 0,01 del décimo y se descartan sin poder distinguirlos"
        )

    print("\n== Recall de los mapeos del autor (verdad congelada en v0.1.0, la comparable)")
    header = "   versión  " + "  ".join(f"@{k:<5}" for k in K_VALUES)
    print(header)
    for version, _, _ in POINTS:
        point = plain[version]
        cells = "  ".join(
            f"{(averages(point, lambda m, k=k: m['recall_frozen_truth'][str(k)]) or 0) * 100:5.1f}%"
            for k in K_VALUES
        )
        print(f"   v{version:6} {cells}")

    print("\n== Recall con la lente sectorial del motor aplicada (UCM-47/UCM-52)")
    print("   La lente filtra el ranking; la verdad corregida además descuenta del patrón los")
    print("   controles cuyo ámbito declarado no gobierna este activo.")
    print(f"   {'versión':8} {'sin lente':>20}  {'con lente':>10}  {'+ verdad corregida':>20}")
    for version, _, _ in POINTS:
        point = plain[version]
        raw = (averages(point, lambda m: m["recall_frozen_truth"]["10"]) or 0) * 100
        lensed = (averages(point, lambda m: m["recall_sector_lens"]["10"]) or 0) * 100
        fixed = (averages(point, lambda m: m["recall_sector_adjusted"]["10"]) or 0) * 100
        print(f"   v{version:6} {raw:19.1f}% {lensed:10.1f}% {fixed:20.1f}%")
    print("   (recall@10; en los puntos que no declaran ámbito la lente no puede apartar nada)")

    print("\n== Recall de los mapeos del autor (verdad de cada versión, no comparable)")
    print(header)
    for version, _, _ in POINTS:
        point = plain[version]
        cells = "  ".join(
            f"{(averages(point, lambda m, k=k: m['recall'][str(k)]) or 0) * 100:5.1f}%"
            for k in K_VALUES
        )
        print(f"   v{version:6} {cells}")

    print("\n== Desplazamiento del top-10 al crecer el corpus (mismas 24 consultas)")
    base = plain[BASELINE_POINT]["capabilities_measured"]
    ref = plain[REFERENCE_POINT]["capabilities_measured"]
    survivors: list[int] = []
    newcomers: list[int] = []
    edited_hits = 0
    old_ids = {c.id for c in catalogs[BASELINE_POINT].controls}
    for capability_id in base:
        before = set(base[capability_id]["top_k_ids"])
        after = set(ref[capability_id]["top_k_ids"])
        survivors.append(len(before & after))
        newcomers.append(len([cid for cid in after if cid not in old_ids]))
        edited_hits += len(after & edited)
    print(
        f"   de los 10 primeros de v{BASELINE_POINT}, sobreviven "
        f"{statistics.fmean(survivors):.1f} en v{REFERENCE_POINT}"
    )
    print(
        f"   de los 10 primeros de v{REFERENCE_POINT}, "
        f"{statistics.fmean(newcomers):.1f} son controles que no existían en v{BASELINE_POINT}"
    )
    print(
        f"   confusor: {edited_hits} apariciones en top-10 de los {len(edited)} controles cuyo "
        f"texto se editó tras v{BASELINE_POINT}"
    )

    print("\n== Brazo 'título solo' (la descripción parafraseada retirada del pasaje)")
    print("   versión   1º(texto) 1º(título)  10º(texto) 10º(título)  recall@10 texto/título")
    for version, _, _ in POINTS:
        full, short = plain[version]["summary"], title[version]["summary"]
        print(
            f"   v{version:6} {full['first']:9.3f} {short['first']:10.3f} "
            f"{full['tenth']:11.3f} {short['tenth']:11.3f}  "
            f"{(full['recall_frozen_truth_10'] or 0) * 100:8.1f}% / "
            f"{(short['recall_frozen_truth_10'] or 0) * 100:.1f}%"
        )

    print("\n== Brazo 'consulta enriquecida con la zona' (dilución medida, no mejora esperada)")
    print("   versión  zona            1º      10º    recall@10   top-10 igual al llano")
    for version, _, _ in POINTS:
        for zone_id, point in results["arms"]["zone"][version].items():
            zoned = point["summary"]
            print(
                f"   v{version:6} {zone_id:15} "
                f"{zoned['first']:6.3f}  {zoned['tenth']:6.3f}  "
                f"{(zoned['recall_frozen_truth_10'] or 0) * 100:8.1f}%  "
                f"{zoned['top10_shared_with_plain']:6.1f}/10"
            )

    print("\n== Discriminación entre zonas (servicio completo: núcleo + gating + lente sectorial)")
    for version, _, _ in POINTS:
        for profile_id, measured in results["zone_discrimination"][version].items():
            jaccard = measured["mean_jaccard_between_zones"]
            shown = f"{jaccard:.3f}" if jaccard is not None else "n/a (una sola zona)"
            print(
                f"   v{version:6} {profile_id:12} zonas={len(measured['zones'])} "
                f"solape medio del conjunto recuperado entre zonas = {shown}"
            )

    print("\n== Invariante de omisión silenciosa (medida en cada punto)")
    for version, _, _ in POINTS:
        for profile_id, measured in results["zone_discrimination"][version].items():
            print(
                f"   v{version:6} {profile_id:12} "
                f"pares capacidad-zona={measured['capability_zone_pairs']:3} "
                f"huecos declarados={measured['declared_gaps']:2} "
                f"candidatos del catálogo perdidos={measured['catalog_candidates_dropped']}"
            )

    print("\n== Coste y latencia (CPU, un hilo, modelo e5-base ya cargado)")
    print("   versión  controles  índice(s)  encode(ms)  Qdrant(ms)  consulta total(ms)")
    for version, _, _ in POINTS:
        point = plain[version]
        latency = point["latency"]
        print(
            f"   v{version:6} {point['controls']:9} {point['index_build_seconds']:9.1f}  "
            f"{latency['encode_query_ms_mean']:10.1f}  "
            f"{latency['qdrant_share_ms_mean']:10.1f}  "
            f"{latency['query_total_ms_mean']:18.1f}"
        )

    print("\n== Marcos presentes en el catálogo de referencia")
    frameworks = Counter(c.framework.value for c in catalogs[REFERENCE_POINT].controls)
    print("   " + ", ".join(f"{k}={v}" for k, v in sorted(frameworks.items())))

    dropped = results.get("dropped_collections", [])
    print(
        f"\n== Limpieza: {len(dropped)} colecciones del experimento borradas; "
        f"la del catálogo activo ({collection_name(get_catalog())}) se conserva"
    )


if __name__ == "__main__":
    # A Windows console defaults to cp1252 and would kill the run on the first
    # accented word — after every measurement had already been paid for.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    measured, loaded, changed = run()
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(measured, indent=2, ensure_ascii=False), encoding="utf-8")
    report(measured, loaded, changed)
    print(f"\nDatos crudos: {RESULTS.relative_to(REPO_ROOT)}")
