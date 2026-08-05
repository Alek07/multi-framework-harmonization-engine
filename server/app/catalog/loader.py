"""UCM-7 - Load the versioned catalog from JSON.

The catalog is read-only; it is loaded once and cached. The path is resolved
relative to the backend root so it does not depend on the current working dir.

**One catalog, one or many files.** A catalog is either a single JSON file or a
*manifest* — the same file, carrying `sources`: one path per framework, resolved
relative to the manifest itself. The manifest keeps what is framework-neutral
(the version, the notes, the capabilities); each source carries the controls of
one framework and the mappings that reach them. Nothing about the model changes:
the parts are merged here and `Catalog` validates the whole, so referential
integrity is still checked over the catalog as the engine reads it and a source
file on its own is deliberately not valid.

Splitting is an authoring convenience — a framework can be reviewed, or handed
to the CISO, without opening every other one — and it is invisible downstream.
Two consequences are worth stating, because both touch reproducibility:

* **A merged catalog is sorted; a single-file one is not.** With several files
  the order of the merged lists would otherwise be an artefact of the order the
  sources happen to be listed in, and that order reaches the Qdrant collection
  name (`app/retrieval/index.py` fingerprints the parsed model). Sorting makes
  the fingerprint depend on the content and on nothing else — as does keeping
  `sources` itself out of the model (see `schemas.Catalog`). A single file keeps
  its authored order untouched, so every catalog already shipped goes on parsing
  — and hashing — exactly as it did before this existed.
* **A source that contributes no control is an error**, not an empty file. The
  manifest lists its parts by hand; a path that resolves to nothing is a typo,
  and a typo that loads quietly would remove controls from a baseline in
  silence.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.catalog.schemas import Catalog
from app.core.config import settings

# app/catalog/loader.py -> parents[2] == backend root (server/)
BACKEND_ROOT = Path(__file__).resolve().parents[2]

MERGED_PARTS = ("capabilities", "controls", "mappings")


def load_catalog(path: str | Path | None = None) -> Catalog:
    """Read and validate the catalog. Raises if the JSON or its integrity fail."""
    manifest = Path(path) if path is not None else Path(settings.CATALOG_PATH)
    if not manifest.is_absolute():
        manifest = BACKEND_ROOT / manifest
    data = _read(manifest)
    if data.get("sources"):
        data = _merge(data, manifest)
    return Catalog.model_validate(data)


def _read(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"catalog file is not a JSON object: {path}")
    return data


def _merge(manifest_data: dict[str, Any], manifest: Path) -> dict[str, Any]:
    """Fold every source into the manifest, in a content-determined order."""
    merged: dict[str, list[Any]] = {
        part: list(manifest_data.get(part, [])) for part in MERGED_PARTS
    }

    for source in manifest_data["sources"]:
        path = manifest.parent / source
        if not path.is_file():
            raise ValueError(
                f"catalog {manifest.name} declares a source that does not exist: {source}"
            )
        data = _read(path)
        if not data.get("controls"):
            raise ValueError(f"catalog source contributes no control: {source}")
        for part in MERGED_PARTS:
            merged[part].extend(data.get(part, []))

    return {
        **manifest_data,
        # Capabilities keep their authored order: they are framework-neutral, they
        # live in the manifest, and that order is the one the operator reads them
        # in. Only what several files contribute is sorted.
        "capabilities": merged["capabilities"],
        "controls": sorted(merged["controls"], key=lambda c: str(c.get("id", ""))),
        "mappings": sorted(
            merged["mappings"],
            key=lambda m: (str(m.get("capability_id", "")), str(m.get("control_id", ""))),
        ),
    }


@lru_cache
def get_catalog() -> Catalog:
    """Cached catalog (a single load per process)."""
    return load_catalog()
