"""UCM-15 - The declared surface, assembled in one place and declared as data.

Invariant 4 of the project says the API is a closed surface and that any endpoint
beyond it is scope creep unless justified in writing. A rule like that is easy to
state and easy to erode one convenient route at a time, so it is written here as
`SURFACE` — a literal list — and checked against the routes FastAPI actually
mounted (`tests/api/test_surface.py`). Adding an endpoint without editing this
list breaks the suite; editing the list is a visible, reviewable act.

It has been edited once, and this is the justification in writing the invariant
asks for. The five endpoints of §7.4 all take one composition as their subject, and
the two that mention a baseline take its id — which the client that signed it has
and any later client does not. Without `GET /baselines` the record of what was
composed would live wherever the browser kept it. It is a read: no state, no table,
no writer (`baseline/listing.py`).

`/health` is deliberately not in the list. It is a liveness probe for the compose
healthcheck (UCM-20), not a function of the engine: it tells a started container
from a serving one and says nothing about a baseline. Counting it as part of the
surface would be as wrong as hiding an engine endpoint behind it.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.baseline.router import collection_router as baselines_router
from app.baseline.router import router as baseline_router
from app.candidates.router import router as candidates_router
from app.delta.router import router as delta_router
from app.parse.router import router as parse_router

# (method, path) of every declared endpoint, without the API prefix. The order is
# the pipeline's: parse the asset, see the options, compose and sign, read the
# trail, compare regions — then the list, which is about all of them at once and
# so comes last.
SURFACE: tuple[tuple[str, str], ...] = (
    ("POST", "/asset/parse"),
    ("POST", "/candidates"),
    ("POST", "/baseline/compose"),
    ("GET", "/baseline/{baseline_id}/audit-log"),
    # Was `GET /delta` in UCM-15/UCM-17, and the change is deliberate rather than
    # convenient: taking the profile only by id made the delta the one endpoint
    # that could not be asked about the asset the operator had just composed. It
    # now names the profile the way the other two engine endpoints do. This
    # replaced the GET, it did not join it.
    ("POST", "/delta"),
    # UCM-21. The sixth, and the reason it exists is in this module's docstring.
    ("GET", "/baselines"),
)


def api_router() -> APIRouter:
    """The declared endpoints, mounted under the versioned prefix by `create_app`."""
    router = APIRouter()
    router.include_router(parse_router)
    router.include_router(candidates_router)
    router.include_router(baseline_router)
    router.include_router(baselines_router)
    router.include_router(delta_router)
    return router
