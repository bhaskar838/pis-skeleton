"""RFC 9457 problem+json errors for every DCS API (SPEC §10)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_BASE = "https://errors.dcs-pis.app/"

log = logging.getLogger(__name__)

_DEFAULT_SLUGS = {
    400: ("bad-request", "Bad request"),
    401: ("unauthenticated", "Authentication required"),
    403: ("forbidden", "Forbidden"),
    404: ("not-found", "Not found"),
    405: ("method-not-allowed", "Method not allowed"),
    409: ("conflict", "Conflict"),
    410: ("gone", "Gone"),
    415: ("unsupported-media-type", "Unsupported media type"),
    422: ("validation-error", "Validation error"),
    429: ("rate-limited", "Too many requests"),
    503: ("unavailable", "Service unavailable"),
}


class Problem(BaseModel):
    """Problem details object. Extra members are allowed (RFC 9457 §3.2)."""

    model_config = ConfigDict(extra="allow")

    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


class ProblemError(Exception):
    """Raise anywhere in request handling to return a problem+json response."""

    def __init__(
        self,
        status: int,
        slug: str | None = None,
        title: str | None = None,
        detail: str | None = None,
        headers: dict[str, str] | None = None,
        **extensions: Any,
    ) -> None:
        default_slug, default_title = _DEFAULT_SLUGS.get(status, ("error", "Error"))
        self.status = status
        self.slug = slug or default_slug
        self.title = title or default_title
        self.detail = detail
        self.headers = headers
        self.extensions = extensions
        super().__init__(f"{status} {self.slug}: {detail or self.title}")

    def to_problem(self, instance: str | None = None) -> Problem:
        return Problem(
            type=PROBLEM_BASE + self.slug,
            title=self.title,
            status=self.status,
            detail=self.detail,
            instance=instance,
            **self.extensions,
        )


def unauthorized(detail: str = "A valid bearer token is required.") -> ProblemError:
    return ProblemError(401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def forbidden(detail: str = "You do not have permission to perform this action.", **ext: Any) -> ProblemError:
    return ProblemError(403, detail=detail, **ext)


def not_found(detail: str = "The resource does not exist or you do not have access to it.") -> ProblemError:
    return ProblemError(404, detail=detail)


def conflict(detail: str, **ext: Any) -> ProblemError:
    return ProblemError(409, detail=detail, **ext)


def mfa_required() -> ProblemError:
    return ProblemError(
        403,
        slug="mfa-required",
        title="Multi-factor authentication required",
        detail="Your role requires multi-factor authentication. Sign in again with MFA.",
        step_up_acr="mfa",
    )


def problem_response(problem: Problem, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        problem.model_dump(exclude_none=True),
        status_code=problem.status,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def install_problem_handlers(app: FastAPI) -> None:
    async def _problem(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ProblemError)  # noqa: S101 - registered for ProblemError only
        return problem_response(exc.to_problem(instance=request.url.path), exc.headers)

    async def _http(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)  # noqa: S101
        err = ProblemError(exc.status_code, detail=str(exc.detail) if exc.detail else None)
        return problem_response(err.to_problem(instance=request.url.path), getattr(exc, "headers", None))

    async def _validation(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)  # noqa: S101
        errors = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")}
            for e in exc.errors()
        ]
        err = ProblemError(422, detail="The request is invalid.", errors=errors)
        return problem_response(err.to_problem(instance=request.url.path))

    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", extra={"path": request.url.path})
        err = ProblemError(500, slug="internal", title="Internal server error")
        return problem_response(err.to_problem(instance=request.url.path))

    app.add_exception_handler(ProblemError, _problem)
    app.add_exception_handler(StarletteHTTPException, _http)
    app.add_exception_handler(RequestValidationError, _validation)
    app.add_exception_handler(Exception, _unhandled)


PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": Problem, "content": {PROBLEM_MEDIA_TYPE: {}}, "description": title}
    for code, (_, title) in _DEFAULT_SLUGS.items()
    if code in (400, 401, 403, 404, 409, 422)
}
