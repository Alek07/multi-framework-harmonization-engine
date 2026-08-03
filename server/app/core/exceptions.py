from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AppException(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND


class ConflictError(AppException):
    status_code = status.HTTP_409_CONFLICT


class NotImplementedYetError(AppException):
    """A declared endpoint of the closed surface whose logic lands in a later ticket.

    The surface is fixed at five endpoints (invariant 4), and it is declared in
    full — request schema, response schema, validation and OpenAPI — before every
    one of them has a body. `POST /baseline/compose` (UCM-16) and `GET /delta`
    (UCM-17) are blocked *by* UCM-15 precisely so they can be built against a
    contract that already exists. Answering 501 says exactly that: the endpoint is
    real, the request was accepted and validated, and the logic is the next ticket.
    A 404 would say the endpoint does not exist, which is false and would leave the
    surface looking open to change.
    """

    status_code = status.HTTP_501_NOT_IMPLEMENTED


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
