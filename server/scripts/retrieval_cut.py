from __future__ import annotations

import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalog.loader import load_catalog  # noqa: E402
from app.catalog.schemas import Catalog  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.retrieval.cut import apply_cut, current_policy  # noqa: E402
from app.retrieval.embeddings import capability_text  # noqa: E402
from app.retrieval.index import CatalogIndex, IndexHit  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS = REPO_ROOT / "docs" / "corte-del-recuperador.json"


def author_mappings(catalog: Catalog) -> dict[str, set[str]]:
    """The controls the author mapped to each capability. The weaker yardstick."""
    truth: dict[str, set[str]] = {c.id: set() for c in catalog.capabilities}
    for mapping in catalog.mappings:
        truth[mapping.capability_id].add(mapping.control_id)
    return truth


def recall_at(ranking: list[str], truth: set[str]) -> float | None:
    if not truth:
        return None
    return len(set(ranking) & truth) / len(truth)


def frameworks(hits: list[IndexHit]) -> int:
    return len({hit.payload.framework for hit in hits})


def measure(index: CatalogIndex, catalog: Catalog) -> dict[str, Any]:
    """One row per capability: the three arms over the same ranking."""
    truth = author_mappings(catalog)
    policy = current_policy()
    rows: dict[str, Any] = {}

    for capability in sorted(catalog.capabilities, key=lambda c: c.id):
        query = capability_text(capability)
        hits = index.search(query, policy.depth)
        kept, cut = apply_cut(
            hits,
            capability_name=capability.name,
            indexed_controls=index.indexed_controls,
            policy=policy,
        )
        expected = truth[capability.id]
        cosine_10 = hits[: settings.RAG_TOP_K]
        cosine_k = hits[: len(kept)]

        rows[capability.id] = {
            "capability": capability.name,
            "expected": sorted(expected),
            "cosine_10": {
                "retained": len(cosine_10),
                "recall": recall_at([h.control_id for h in cosine_10], expected),
                "frameworks": frameworks(cosine_10),
                "held": dict(Counter(h.payload.framework for h in cosine_10)),
            },
            "cosine_k": {
                "retained": len(cosine_k),
                "recall": recall_at([h.control_id for h in cosine_k], expected),
                "frameworks": frameworks(cosine_k),
            },
            "shipped": {
                "retained": cut.retained,
                "recall": recall_at([h.control_id for h in kept], expected),
                "frameworks": frameworks(kept),
                "held": dict(Counter(h.payload.framework for h in kept)),
                "band_width": cut.band_width,
                "band_extension": cut.band_extension,
                "ceiling_reached": cut.ceiling_reached,
                "cap_yielded": cut.cap_yielded,
                "displaced": len(cut.displaced),
                "dropped": cut.dropped,
                "near_ties_dropped": cut.near_ties_dropped,
                "first_dropped": (
                    {
                        "official_id": cut.first_dropped.official_id,
                        "framework": cut.first_dropped.framework.value,
                        "score": round(cut.first_dropped.score, 4),
                        "margin": cut.first_dropped.margin,
                        "dropped_by": cut.first_dropped.dropped_by.value,
                    }
                    if cut.first_dropped is not None
                    else None
                ),
            },
            "recovered": sorted(
                {h.control_id for h in kept} & expected
                - {h.control_id for h in cosine_10}
            ),
            "lost": sorted(
                {h.control_id for h in cosine_10} & expected
                - {h.control_id for h in kept}
            ),
        }
    return rows


def mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return statistics.fmean(present) if present else None


def summarize(rows: dict[str, Any]) -> dict[str, Any]:
    arms = ("cosine_10", "cosine_k", "shipped")
    summary: dict[str, Any] = {
        arm: {
            "recall": mean([row[arm]["recall"] for row in rows.values()]),
            "frameworks": mean([float(row[arm]["frameworks"]) for row in rows.values()]),
            "retained": mean([float(row[arm]["retained"]) for row in rows.values()]),
        }
        for arm in arms
    }
    summary["cut"] = {
        "band_extension": mean([float(r["shipped"]["band_extension"]) for r in rows.values()]),
        "displaced": mean([float(r["shipped"]["displaced"]) for r in rows.values()]),
        "dropped": mean([float(r["shipped"]["dropped"]) for r in rows.values()]),
        "near_ties_dropped": mean(
            [float(r["shipped"]["near_ties_dropped"]) for r in rows.values()]
        ),
        "ceiling_reached": sum(1 for r in rows.values() if r["shipped"]["ceiling_reached"]),
        "cap_yielded": sum(1 for r in rows.values() if r["shipped"]["cap_yielded"]),
        "capabilities_recovering_a_mapping": sum(1 for r in rows.values() if r["recovered"]),
        "capabilities_losing_a_mapping": sum(1 for r in rows.values() if r["lost"]),
    }
    return summary


def report(catalog: Catalog, rows: dict[str, Any], summary: dict[str, Any], build: float) -> None:
    policy = current_policy()
    print(f"\ncatálogo v{catalog.catalog_version} · {len(catalog.controls)} controles · "
          f"{len(catalog.capabilities)} capacidades · índice en {build:.1f} s")
    print(f"política: {policy.describe()}\n")

    print("== Las tres lecturas del mismo ranking (media de las capacidades)")
    print(f"{'arma':<24}{'mostrados':>11}{'recall':>10}{'marcos':>9}")
    names = {
        "cosine_10": "coseno@10 (lo anterior)",
        "cosine_k": "coseno@k (mismos huecos)",
        "shipped": "regla enviada",
    }
    for arm, name in names.items():
        row = summary[arm]
        print(
            f"{name:<24}{row['retained']:>11.1f}"
            f"{row['recall'] * 100:>9.1f}%{row['frameworks']:>9.2f}"
        )

    cut = summary["cut"]
    print("\n== Lo que el corte declara")
    print(f"  banda: +{cut['band_extension']:.1f} huecos de media sobre el suelo de {policy.floor}")
    print(f"  techo alcanzado en {cut['ceiling_reached']} de {len(rows)} capacidades")
    print(f"  el tope cedió en {cut['cap_yielded']} de {len(rows)} capacidades")
    print(f"  desplazados por el tope: {cut['displaced']:.1f} de media")
    print(f"  bajo el corte: {cut['dropped']:.1f} de media, "
          f"{cut['near_ties_dropped']:.1f} de ellos indistinguibles del último mostrado")

    print("\n== Efecto sobre los mapeos del autor")
    recovered = cut["capabilities_recovering_a_mapping"]
    print(f"  capacidades que recuperan un mapeo perdido: {recovered}")
    print(f"  capacidades que pierden uno que sí tenían: {cut['capabilities_losing_a_mapping']}")
    for capability_id, row in sorted(rows.items()):
        if row["recovered"] or row["lost"]:
            print(
                f"    {capability_id:<18} recupera {row['recovered'] or '—'} "
                f"pierde {row['lost'] or '—'}"
            )

    print("\n== Capacidades donde el tope más reordena")
    ranked = sorted(rows.items(), key=lambda kv: -kv[1]["shipped"]["displaced"])
    for capability_id, row in ranked[:6]:
        print(
            f"  {capability_id:<18} antes {row['cosine_10']['held']}\n"
            f"  {'':<18} ahora {row['shipped']['held']} "
            f"(desplazados {row['shipped']['displaced']})"
        )


def main() -> None:
    catalog = load_catalog()
    index = CatalogIndex(catalog=catalog)
    index.encoder.encode_query("warmup")
    started = time.perf_counter()
    index.ensure()
    build = time.perf_counter() - started

    rows = measure(index, catalog)
    summary = summarize(rows)
    report(catalog, rows, summary, build)

    RESULTS.write_text(
        json.dumps(
            {
                "catalog_version": catalog.catalog_version,
                "controls": len(catalog.controls),
                "policy": current_policy().model_dump(mode="json"),
                "summary": summary,
                "capabilities": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nresultados en {RESULTS.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
