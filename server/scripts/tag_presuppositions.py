"""UCM-53 - Propose what each catalog control presupposes of a zone, for review.

This is catalog authorship, not a request path. It walks the versioned catalog
once, asks the model what each control needs to be true of a place, screens every
answer against the control's own text (`app/tagging/guard.py`), and writes a
**proposal** file. It never touches the catalog: a human reads the proposal,
corrects it, and merges what survives into `data/catalog/v<version>/*.json`.

Why once and offline rather than per request: the blindness being fixed is
structural in a bi-encoder and the reading that fixes it is the same for every
asset, zone and run (UCM-51 measured -14 to -19 points of recall for folding the
zone into the query). Doing it once, under review, buys a deterministic answer
forever — and keeps the 7B off the path of a baseline.

Resumable on purpose. 226 controls is a long conversation with a local model, and
a run that died at 180 should not start over: pass `--resume` and the controls
already carried in the output file are kept as they are.

Run from `server/`, with Ollama up and the pinned model pulled:

    uv run python scripts/tag_presuppositions.py
    uv run python scripts/tag_presuppositions.py --resume --limit 20
    uv run python scripts/tag_presuppositions.py --framework CIS
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalog.loader import get_catalog  # noqa: E402
from app.catalog.schemas import Catalog, FrameworkControl  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.parse.ollama import verify_model  # noqa: E402
from app.retrieval.index import catalog_digest  # noqa: E402
from app.tagging.prompt import PROMPT_VERSION  # noqa: E402
from app.tagging.schemas import (  # noqa: E402
    ControlProposal,
    TaggingProvenance,
    TaggingRun,
    TagStatus,
)
from app.tagging.service import ControlTaggingService  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "docs" / "premisas-propuestas.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--framework", help="only controls of this framework (CIS, CSF, ...)")
    parser.add_argument("--limit", type=int, help="stop after this many controls")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="keep the controls already carried in the output file",
    )
    return parser.parse_args()


def existing(path: Path, resume: bool) -> dict[str, ControlProposal]:
    """What a previous run already answered, keyed by control id."""
    if not resume or not path.exists():
        return {}
    run = TaggingRun.model_validate_json(path.read_text(encoding="utf-8"))
    done = {
        proposal.control_id: proposal
        for proposal in run.proposals
        if proposal.status is not TagStatus.UNAVAILABLE
    }
    print(f"   reanudando: {len(done)} controles ya respondidos en {path.name}")
    return done


def selected(controls: list[FrameworkControl], args: argparse.Namespace) -> list[FrameworkControl]:
    chosen = controls
    if args.framework:
        chosen = [c for c in chosen if c.framework.value == args.framework]
    if args.limit:
        chosen = chosen[: args.limit]
    return chosen


def report(proposals: list[ControlProposal]) -> dict[str, int]:
    """The reading a reviewer needs before opening the file itself."""
    by_status = Counter(p.status.value for p in proposals)
    by_premise = Counter(pre.premise.value for p in proposals for pre in p.presupposes)
    by_framework = Counter(p.framework.value for p in proposals if p.presupposes)
    rejected = Counter(r.reason.split(".")[0] for p in proposals for r in p.rejected)

    print(f"\n== Propuesta sobre {len(proposals)} controles")
    for status, count in sorted(by_status.items()):
        print(f"   {status:14} {count:4}")

    print("\n== Premisas propuestas (tras el guard)")
    if not by_premise:
        print("   ninguna")
    for premise, count in by_premise.most_common():
        print(f"   {premise:22} {count:4}")

    print("\n== Controles con alguna premisa, por marco")
    for framework, count in by_framework.most_common():
        print(f"   {framework:12} {count:4}")

    print("\n== Premisas rechazadas por el guard")
    if not rejected:
        print("   ninguna")
    for reason, count in rejected.most_common():
        print(f"   {count:4}  {reason}.")

    print(
        "\nNada de esto es todavía catálogo. Revisa el fichero, corrige lo que haga falta "
        "y mezcla a mano lo que sobreviva en data/catalog/v<version>/*.json."
    )
    return {
        **{f"status_{k}": v for k, v in by_status.items()},
        **{f"premise_{k}": v for k, v in by_premise.items()},
        "rejected": sum(rejected.values()),
    }


async def main() -> None:
    args = parse_args()
    catalog = get_catalog()
    controls = selected(list(catalog.controls), args)
    done = existing(args.out, args.resume)

    digest = None
    try:
        digest = await verify_model()
    except Exception as exc:  # noqa: BLE001 - reported, and every control then fails open
        print(f"   aviso: no se pudo verificar el modelo ({exc})")

    print(
        f"   catálogo {catalog.catalog_version} · {len(controls)} controles a preguntar · "
        f"modelo {settings.LLM_MODEL} · temp {settings.LLM_TEMPERATURE} · seed {settings.LLM_SEED}"
    )

    service = ControlTaggingService()
    proposals: list[ControlProposal] = []
    for index, control in enumerate(controls, start=1):
        if control.id in done:
            proposals.append(done[control.id])
            continue
        proposal = await service.tag(control)
        proposals.append(proposal)
        premises = ", ".join(p.premise.value for p in proposal.presupposes) or "—"
        print(
            f"   [{index:3}/{len(controls)}] {control.id:22} "
            f"{proposal.status.value:12} {premises}"
        )
        args.out.write_text(
            _run(catalog, digest, proposals).model_dump_json(indent=2), encoding="utf-8"
        )

    run = _run(catalog, digest, proposals)
    run.counts = report(proposals)
    args.out.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    print(f"\n   escrito: {args.out}")


def _run(catalog: Catalog, digest: str | None, proposals: list[ControlProposal]) -> TaggingRun:
    return TaggingRun(
        provenance=TaggingProvenance(
            model=settings.LLM_MODEL,
            model_digest=digest,
            prompt_version=PROMPT_VERSION,
            temperature=settings.LLM_TEMPERATURE,
            seed=settings.LLM_SEED,
            top_p=settings.LLM_TOP_P,
            num_predict=settings.LLM_NUM_PREDICT,
            catalog_version=catalog.catalog_version,
            catalog_digest=catalog_digest(catalog),
        ),
        proposals=proposals,
    )


if __name__ == "__main__":
    asyncio.run(main())
