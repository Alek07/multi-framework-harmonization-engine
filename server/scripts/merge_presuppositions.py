"""UCM-53 - Merge a reviewed premise proposal into the catalog sources.

The proposal written by `tag_presuppositions.py` is not the catalog and never
becomes it on its own. This script is the *human's* act: it takes the file the
reviewer has read, edited and pruned, and writes what survived into the versioned
sources, so that merging is one reviewable command instead of five JSON files
edited by hand.

Two things it deliberately does not do.

It does not reformat: the splice is textual (`app/tagging/merge.py`), so the diff
shows the handful of controls that gained a premise rather than 226 lines
rewritten to say what they already said.

And it does not decide. `--only` and `--exclude` exist because the reviewer's
verdict is per control, and the honest way to record "these yes, those no" is to
run the merge with that list rather than to edit the proposal until it agrees.

Run from `server/`, after reviewing the proposal:

    uv run python scripts/merge_presuppositions.py --dry-run
    uv run python scripts/merge_presuppositions.py
    uv run python scripts/merge_presuppositions.py --only CTL-CIS-1001,CTL-CIS-1003
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalog.loader import load_catalog  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.tagging.merge import (  # noqa: E402
    fragment,
    holds_key,
    is_one_line_entry,
    key_line,
    splice,
)
from app.tagging.schemas import TaggingRun  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROPOSAL = BACKEND_ROOT.parent / "docs" / "premisas-propuestas.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, default=DEFAULT_PROPOSAL)
    parser.add_argument("--only", help="comma-separated control ids to merge, and no others")
    parser.add_argument("--exclude", help="comma-separated control ids to leave out")
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    return parser.parse_args()


def wanted(run: TaggingRun, args: argparse.Namespace) -> dict[str, str]:
    """`{control_id: json fragment}` for the premises the reviewer is merging."""
    only = {c.strip() for c in args.only.split(",")} if args.only else None
    excluded = {c.strip() for c in args.exclude.split(",")} if args.exclude else set()

    chosen: dict[str, str] = {}
    for proposal in run.proposals:
        if not proposal.presupposes:
            continue
        if only is not None and proposal.control_id not in only:
            continue
        if proposal.control_id in excluded:
            continue
        chosen[proposal.control_id] = fragment(proposal.presupposes)
    return chosen


def merge_into(path: Path, premises: dict[str, str], dry_run: bool) -> list[str]:
    """Splice every matching control in one source file. Returns the ids touched."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    touched: list[str] = []

    # Walked backwards so an insertion never shifts an index still to be visited.
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index]
        for control_id, premises_json in premises.items():
            if f'"id": "{control_id}"' not in line:
                continue
            bare = line.rstrip("\r\n")
            ending = line[len(bare) :] or "\n"
            if is_one_line_entry(bare):
                lines[index] = splice(bare, premises_json) + ending
            else:
                # A pretty-printed entry (the NIS2 source): the key gets its own
                # line under the id, replacing one already there when the merge
                # is re-run.
                inserted = key_line(bare, premises_json) + ending
                after = index + 1
                if after < len(lines) and holds_key(lines[after]):
                    lines[after] = inserted
                else:
                    lines.insert(after, inserted)
            touched.append(control_id)
            break

    if touched and not dry_run:
        path.write_text("".join(lines), encoding="utf-8")
    return touched

def main() -> None:
    args = parse_args()
    run = TaggingRun.model_validate_json(args.proposal.read_text(encoding="utf-8"))
    catalog_path = BACKEND_ROOT / settings.CATALOG_PATH
    manifest = json.loads(catalog_path.read_text(encoding="utf-8"))

    if manifest["catalog_version"] != run.provenance.catalog_version:
        raise SystemExit(
            f"la propuesta se hizo sobre el catálogo v{run.provenance.catalog_version} y el "
            f"activo es v{manifest['catalog_version']}: revisa antes de mezclar."
        )

    premises = wanted(run, args)
    print(
        f"   propuesta: {args.proposal.name} · catálogo v{manifest['catalog_version']} · "
        f"{len(premises)} control(es) a mezclar"
    )

    merged: list[str] = []
    for source in manifest["sources"]:
        touched = merge_into(catalog_path.parent / source, premises, args.dry_run)
        if touched:
            print(f"   {source:22} {len(touched):3} control(es): {', '.join(sorted(touched))}")
        merged.extend(touched)

    missing = sorted(set(premises) - set(merged))
    if missing:
        raise SystemExit(f"controles no encontrados en ninguna fuente: {missing}")

    if args.dry_run:
        print("\n   (dry-run: no se ha escrito nada)")
        return

    catalog = load_catalog()
    declaring = [c for c in catalog.controls if c.presupposes]
    print(
        f"\n   el catálogo vuelve a validar: {len(catalog.controls)} controles, "
        f"{len(declaring)} con premisa declarada"
    )
    print("   revisa el diff antes de commitear: es el acto de autoría, no el script.")


if __name__ == "__main__":
    main()
