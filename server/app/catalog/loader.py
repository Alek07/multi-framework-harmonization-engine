"""UCM-7 - Load the versioned catalog from JSON.

The catalog is read-only; it is loaded once and cached. The path is resolved
relative to the backend root so it does not depend on the current working dir.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.catalog.schemas import Catalog
from app.core.config import settings

# app/catalog/loader.py -> parents[2] == backend root (server/)
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def load_catalog(path: str | Path | None = None) -> Catalog:
    """Read and validate the catalog. Raises if the JSON or its integrity fail."""
    raw = Path(path) if path is not None else Path(settings.CATALOG_PATH)
    if not raw.is_absolute():
        raw = BACKEND_ROOT / raw
    data = json.loads(raw.read_text(encoding="utf-8"))
    return Catalog.model_validate(data)


@lru_cache
def get_catalog() -> Catalog:
    """Cached catalog (a single load per process)."""
    return load_catalog()
