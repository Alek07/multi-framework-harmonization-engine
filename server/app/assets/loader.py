"""UCM-8 - Load the hand-written asset profiles from JSON.

The two validation profiles (UCM-1/UCM-2) are inputs frozen in Git so the core
can be run end to end without the AI layer (M1 gate) and so the M4 evaluation
always measures against the same profiles. From M2 on, the same schema is what
the LLM parse produces and the operator reviews.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.assets.schemas import AssetProfile
from app.core.config import settings

# app/assets/loader.py -> parents[2] == backend root (server/)
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _profiles_dir() -> Path:
    raw = Path(settings.PROFILES_DIR)
    return raw if raw.is_absolute() else BACKEND_ROOT / raw


def load_profile(path: str | Path) -> AssetProfile:
    """Read and validate a profile from an explicit path."""
    raw = Path(path)
    if not raw.is_absolute():
        raw = BACKEND_ROOT / raw
    return AssetProfile.model_validate(json.loads(raw.read_text(encoding="utf-8")))


@lru_cache
def get_profile(profile_id: str) -> AssetProfile:
    """Cached profile by ID (`PROFILE-A` -> `data/profiles/profile-a.json`)."""
    return load_profile(_profiles_dir() / f"{profile_id.lower()}.json")


def available_profiles() -> list[str]:
    """IDs of the profiles frozen in the repo, in deterministic order."""
    return sorted(p.stem.upper() for p in _profiles_dir().glob("*.json"))
