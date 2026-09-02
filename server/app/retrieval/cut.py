from __future__ import annotations

from app.core.config import settings
from app.retrieval.index import IndexHit
from app.retrieval.schemas import (
    CutPolicy,
    CutReason,
    DroppedCandidate,
    RetrievalCut,
    RetrievalRelation,
)

# Bumped when the rule's shape changes; its parameters travel in `CutPolicy`.
CUT_POLICY_VERSION = "v1"


def current_policy(depth: int | None = None) -> CutPolicy:
    """The shipped cut, read from the settings that declare it."""
    return CutPolicy(
        version=CUT_POLICY_VERSION,
        depth=depth if depth is not None else settings.RAG_RETRIEVAL_DEPTH,
        floor=settings.RAG_TOP_K,
        tie_epsilon=settings.RAG_CUT_TIE_EPSILON,
        ceiling=settings.RAG_MAX_K,
        framework_cap=settings.RAG_FRAMEWORK_CAP,
    )


def band_width(scores: list[float], policy: CutPolicy) -> int:
    """How many slots the band opens: the floor, extended over ties, capped by the ceiling."""
    if not scores:
        return 0
    k = min(policy.floor, len(scores))
    if k == 0:
        return 0
    limit = min(policy.ceiling, len(scores))
    while k < limit and scores[k] >= scores[k - 1] - policy.tie_epsilon:
        k += 1
    return k


def apply_cut(
    hits: list[IndexHit],
    *,
    capability_name: str,
    indexed_controls: int,
    policy: CutPolicy | None = None,
) -> tuple[list[IndexHit], RetrievalCut]:
    """Bound the widening `hits` by the rule; return what is kept and the report.

    Confirmations are never passed here: the catalog already offers them.
    """
    policy = policy if policy is not None else current_policy()
    scores = [hit.score for hit in hits]
    k = band_width(scores, policy)

    kept: list[IndexHit] = []
    dropped: list[tuple[IndexHit, CutReason]] = []
    per_framework: dict[str, int] = {}

    for hit in hits:
        if len(kept) == k:
            dropped.append((hit, CutReason.RANK))
            continue
        framework = hit.payload.framework
        if per_framework.get(framework, 0) >= policy.framework_cap:
            dropped.append((hit, CutReason.FRAMEWORK_CAP))
            continue
        per_framework[framework] = per_framework.get(framework, 0) + 1
        kept.append(hit)

    kept, dropped, cap_yielded = _cap_yields_to_the_floor(hits, kept, dropped, policy)
    last_kept = kept[-1].score if kept else 0.0
    near_ties = sum(
        1 for hit, _ in dropped if hit.score >= last_kept - policy.tie_epsilon
    )
    # The ceiling bound only if the band would have gone further.
    ceiling_reached = (
        k == policy.ceiling
        and len(scores) > k
        and scores[k] >= scores[k - 1] - policy.tie_epsilon
    )

    reported = [
        _dropped(hit, reason, last_kept, capability_name, policy)
        for hit, reason in dropped
    ]
    displaced = [d for d in reported if d.dropped_by is CutReason.FRAMEWORK_CAP]

    cut = RetrievalCut(
        policy=policy,
        evaluated=len(hits),
        retained=len(kept),
        band_width=k,
        band_extension=max(0, k - policy.floor),
        ceiling_reached=ceiling_reached,
        cap_yielded=cap_yielded,
        dropped=len(dropped),
        near_ties_dropped=near_ties,
        not_returned=max(0, indexed_controls - len(hits)),
        first_dropped=reported[0] if reported else None,
        displaced=displaced,
        rationale=_rationale(
            capability_name, policy, k, kept, reported, near_ties, ceiling_reached, cap_yielded
        ),
    )
    return kept, cut


def _cap_yields_to_the_floor(
    hits: list[IndexHit],
    kept: list[IndexHit],
    dropped: list[tuple[IndexHit, CutReason]],
    policy: CutPolicy,
) -> tuple[list[IndexHit], list[tuple[IndexHit, CutReason]], int]:
    """Give cap-displaced slots back until the floor is met. The extension is not restored."""
    floor = min(policy.floor, len(hits))
    if len(kept) >= floor:
        return kept, dropped, 0

    displaced = [hit for hit, reason in dropped if reason is CutReason.FRAMEWORK_CAP]
    reinstated = {hit.control_id for hit in displaced[: floor - len(kept)]}
    if not reinstated:
        return kept, dropped, 0

    order = {hit.control_id: position for position, hit in enumerate(hits)}
    kept = sorted(
        kept + [hit for hit in displaced if hit.control_id in reinstated],
        key=lambda hit: order[hit.control_id],
    )
    dropped = [(hit, reason) for hit, reason in dropped if hit.control_id not in reinstated]
    return kept, dropped, len(reinstated)


def _margin_words(margin: float) -> str:
    """Where a candidate sits relative to the last one shown. A cap displacement reads above it."""
    if margin < 0:
        return f"{abs(margin):.3f} por encima del último mostrado"
    return f"a {margin:.3f} del último mostrado"


def _dropped(
    hit: IndexHit,
    reason: CutReason,
    last_kept: float,
    capability_name: str,
    policy: CutPolicy,
) -> DroppedCandidate:
    payload = hit.payload
    margin = round(last_kept - hit.score, 6)
    if reason is CutReason.FRAMEWORK_CAP:
        rationale = (
            f"Desplazado por el tope de marco ({policy.framework_cap} por marco) en «"
            f"{capability_name}»: {payload.framework} ya ocupaba sus huecos con candidatos de "
            f"mayor similitud, y el que quedaba libre lo tomó la lectura de otro marco. Se "
            f"registra con su similitud ({hit.score:.3f}, {_margin_words(margin)}) para que el "
            "corte sea auditable — desplazar no es descartar, y el tope es una regla sobre un "
            "dato declarado del control, no una preferencia por ningún marco."
        )
    else:
        rationale = (
            f"Bajo el corte por rango en «{capability_name}»: similitud {hit.score:.3f}, "
            f"{_margin_words(margin)}. Se cuenta y se nombra en vez de desaparecer — la "
            "regla que lo dejó fuera está declarada y lo que retuvo no es un umbral de "
            "puntuación, sino un número de candidatos."
        )
    return DroppedCandidate(
        control_id=hit.control_id,
        official_id=payload.official_id,
        framework=payload.framework,  # type: ignore[arg-type]
        jurisdiction=payload.jurisdiction,  # type: ignore[arg-type]
        score=hit.score,
        relation=RetrievalRelation.WIDENS,
        dropped_by=reason,
        margin=margin,
        rationale=rationale,
    )


def _rationale(
    capability_name: str,
    policy: CutPolicy,
    k: int,
    kept: list[IndexHit],
    dropped: list[DroppedCandidate],
    near_ties: int,
    ceiling_reached: bool,
    cap_yielded: int,
) -> str:
    head = (
        f"«{capability_name}»: {len(kept) + len(dropped)} sugerencia(s) evaluada(s), "
        f"{len(kept)} retenida(s). {policy.describe()}."
    )
    extension = k - policy.floor
    if extension > 0:
        band = (
            f" El suelo son {policy.floor}; la banda añadió {extension} porque seguían a menos "
            f"de {policy.tie_epsilon:.2f} del último, que es la distancia a la que el "
            "recuperador ya no distingue."
        )
    else:
        band = (
            f" La banda no extendió el suelo de {policy.floor}: el siguiente candidato estaba "
            f"a más de {policy.tie_epsilon:.2f} del último retenido."
        )
    if ceiling_reached:
        band += (
            f" El techo ({policy.ceiling}) detuvo la extensión con empates todavía por debajo: "
            "se declara aquí en vez de dejar que el número parezca una decisión de la banda."
        )
    displaced = [d for d in dropped if d.dropped_by is CutReason.FRAMEWORK_CAP]
    if displaced:
        frameworks = sorted({d.framework.value for d in displaced})
        cap = (
            f" El tope por marco desplazó {len(displaced)} candidato(s) de "
            f"{', '.join(frameworks)}, listado(s) uno a uno con su similitud: en un catálogo "
            "desequilibrado, un corte por número fijo gasta la atención del operador en el marco "
            "que más enumera, no en la lectura que más aporta."
        )
    else:
        cap = f" Ningún marco llegó al tope de {policy.framework_cap}."
    if cap_yielded:
        cap += (
            f" El tope cedió {cap_yielded} hueco(s) para no bajar del suelo de {policy.floor}: "
            "no había bastantes marcos distintos en el vecindario, y el suelo es una garantía "
            "sobre cuántas opciones recibe el operador, mientras que el tope solo es una "
            "preferencia sobre cuáles."
        )
    elif len(kept) < k:
        cap += (
            f" La banda abrió {k} huecos y se llenaron {len(kept)}: ningún otro marco tenía "
            f"candidatos con los que ocupar el resto sin pasar de {policy.framework_cap}. Se "
            f"sigue por encima del suelo de {policy.floor}, que es lo garantizado; la extensión "
            "de la banda no lo es."
        )
    if dropped:
        first = dropped[0]
        tail = (
            f" El primero descartado es {first.official_id} ({first.framework.value}) con "
            f"similitud {first.score:.3f}, {_margin_words(first.margin)}; {near_ties} de los "
            f"descartados siguen a menos de {policy.tie_epsilon:.2f} del último mostrado y el "
            "recuperador no los distingue de él."
        )
    else:
        tail = (
            " No quedó nada bajo el corte: la consulta devolvió menos candidatos de los que la "
            "regla podía retener."
        )
    return head + band + cap + tail
