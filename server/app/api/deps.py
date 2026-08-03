"""UCM-15 - What the five endpoints are given to work with.

Three kinds of collaborator, and they are wired differently for reasons that
matter more than the plumbing:

* **The ledger is per request.** `AuditService` is built around the request's
  `AsyncSession`, so a run and the human decisions taken on it are appended in one
  transaction and rolled back together if the request fails. A half-written trail
  is worse than no trail (`audit/repository.py`).
* **The engine's collaborators are per process.** The parse agent, the catalog
  index and the explanation agent are expensive to build and hold no request
  state: one embedding model per process, not one per call. `lru_cache` is what
  makes "per process" true; `Depends` is what makes it overridable, which is how
  the suite runs with no Ollama and no Qdrant.
* **The profile is resolved, never invented.** `requested_profile` accepts either
  an inline `AssetProfile` — the reviewed output of `POST /asset/parse` — or the
  id of one of the profiles frozen in the repo (UCM-1/UCM-2). Exactly one of the
  two: guessing which to use when both are given would mean the engine choosing
  its own input.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.loader import available_profiles, get_profile
from app.assets.schemas import AssetProfile
from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.candidates.service import CandidatesService
from app.core.database import get_db
from app.core.exceptions import AppException
from app.parse.service import AssetParseService


class ProfileRequestError(AppException):
    """The request named its asset profile in a way the engine cannot act on."""

    status_code = 422


def audit_service(db: Annotated[AsyncSession, Depends(get_db)]) -> AuditService:
    return AuditService(AuditRepository(db))


@lru_cache(maxsize=1)
def parse_service() -> AssetParseService:
    return AssetParseService()


@lru_cache(maxsize=1)
def candidates_service() -> CandidatesService:
    return CandidatesService()


AuditDep = Annotated[AuditService, Depends(audit_service)]
ParseDep = Annotated[AssetParseService, Depends(parse_service)]
CandidatesDep = Annotated[CandidatesService, Depends(candidates_service)]


def requested_profile(profile: AssetProfile | None, profile_id: str | None) -> AssetProfile:
    """The profile the request is about: the one it carried, or the one it named.

    The frozen profiles are addressable by id on purpose. They are the inputs the
    core was validated against (M1 gate) and the ones the evaluation measures
    (UCM-18), so a demo through Swagger — the declared plan B if the UI is cut —
    can reach the whole pipeline without pasting a profile into every request.
    """
    if profile is not None and profile_id is not None:
        raise ProfileRequestError(
            "Indique el perfil en línea ('profile') o el identificador de un perfil "
            "congelado en el repositorio ('profile_id'), pero no ambos: el motor no elige "
            "cuál de los dos es la entrada."
        )
    if profile is not None:
        return profile
    if profile_id is None:
        raise ProfileRequestError(
            "Falta el perfil del activo: indique 'profile' (perfil revisado por el operador) "
            f"o 'profile_id' (uno de {available_profiles()})."
        )
    try:
        return get_profile(profile_id)
    except (OSError, ValueError) as exc:
        raise ProfileRequestError(
            f"No hay ningún perfil congelado con identificador '{profile_id}'. "
            f"Disponibles: {available_profiles()}."
        ) from exc
