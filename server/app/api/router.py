"""The declared API surface, assembled in one place and declared as data.

The API is a closed surface (invariant 4): any endpoint beyond it is scope creep
unless justified in writing. `SURFACE` is that list, checked against the routes
FastAPI actually mounted (`tests/api/test_surface.py`), so adding an endpoint
without editing this list breaks the suite.

Two additions beyond the five of §7.4, justified here as the invariant asks:

**The sixth, `GET /baselines`.** The five §7.4 endpoints all take one composition
as their subject, and the two that mention a baseline take its id — which the
client that signed it has and a later client does not. Without it the record of
what was composed would live wherever the browser kept it. A read: no state, no
table, no writer (`baseline/listing.py`).

**The seventh, `GET /baseline/{id}/statement`.** None of the others answers the
question a reviewer arrives with — *what applies to this asset, what does not, and
on whose word?* — a declaration of applicability (one row per required capability,
with its inclusions, justified exclusions, tier, jurisdiction, gap and signature).
That document is the artefact the disciplines this engine implements are
recognised by (SoA of ISO/IEC 27001, tailoring of SP 800-53B, the CRS of
IEC 62443-3-2), and it is what the memoir cites. It is the same kind of read as
the sixth — a projection of the ledger, no table, no writer
(`baseline/statement.py`) — and it carries the OSCAL export on the same route
(`?format=oscal`), one document in two spellings.

`/health` is deliberately not in the list: it is a liveness probe for the compose
healthcheck, not a function of the engine.
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
# trail, emit the document, compare regions — then the list, which is about all of
# them at once and so comes last.
SURFACE: tuple[tuple[str, str], ...] = (
    ("POST", "/asset/parse"),
    ("POST", "/candidates"),
    ("POST", "/baseline/compose"),
    ("GET", "/baseline/{baseline_id}/audit-log"),
    # The seventh, justified in this module's docstring.
    ("GET", "/baseline/{baseline_id}/statement"),
    # A POST rather than a GET on purpose: taking the profile only by id made the
    # delta the one endpoint that could not be asked about the asset just composed.
    # It now names the profile the way the other two engine endpoints do.
    ("POST", "/delta"),
    # The sixth, justified in this module's docstring.
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
