"""UCM-15 - The closed surface, assembled in one place and declared as data.

Invariant 4 of the project says the API is exactly five endpoints and that any
sixth is scope creep unless justified in writing. A rule like that is easy to
state and easy to erode one convenient route at a time, so it is written here as
`SURFACE` — a literal list — and checked against the routes FastAPI actually
mounted (`tests/api/test_surface.py`). Adding an endpoint without editing this
list breaks the suite; editing the list is a visible, reviewable act.

`/health` is deliberately not in it. It is a liveness probe for the compose
healthcheck (UCM-20), not a function of the engine: it tells a started container
from a serving one and says nothing about a baseline. Counting it as part of the
surface would be as wrong as hiding a sixth engine endpoint behind it.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.baseline.router import router as baseline_router
from app.candidates.router import router as candidates_router
from app.delta.router import router as delta_router
from app.parse.router import router as parse_router

# (method, path) of every endpoint of §7.4, without the API prefix. The order is
# the pipeline's: parse the asset, see the options, compose and sign, read the
# trail, compare regions.
SURFACE: tuple[tuple[str, str], ...] = (
    ("POST", "/asset/parse"),
    ("POST", "/candidates"),
    ("POST", "/baseline/compose"),
    ("GET", "/baseline/{baseline_id}/audit-log"),
    # Was `GET /delta` in UCM-15/UCM-17, and the change is deliberate rather than
    # convenient: taking the profile only by id made the delta the one endpoint
    # that could not be asked about the asset the operator had just composed. It
    # now names the profile the way the other two engine endpoints do. Five
    # endpoints still — this replaces the GET, it does not join it.
    ("POST", "/delta"),
)


def api_router() -> APIRouter:
    """The five endpoints, mounted under the versioned prefix by `create_app`."""
    router = APIRouter()
    router.include_router(parse_router)
    router.include_router(candidates_router)
    router.include_router(baseline_router)
    router.include_router(delta_router)
    return router
