"""Load the versioned catalog from JSON: read-only, loaded once and cached.

The path is resolved relative to the backend root so it does not depend on the
current working dir. A catalog is either a single JSON file or a *manifest*
carrying `sources` (one path per framework, resolved relative to the manifest).
The manifest keeps what is framework-neutral (version, notes, capabilities);
each source carries one framework's controls and the mappings that reach them.
The parts are merged here and `Catalog` validates the whole, so a source file on
its own is deliberately not valid.

Merged lists are sorted so the parsed model's fingerprint depends on content
alone, not on the order sources happen to be listed in (`app/retrieval/index.py`
fingerprints the parsed model); a single file keeps its authored order. A source
that contributes no control is an error, not an empty file — a silent typo would
remove controls from a baseline.
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
