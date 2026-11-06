"""Request / job context carried through logs and traces."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

tenant_id_var: ContextVar[str | None] = ContextVar("dcs_tenant_id", default=None)
org_id_var: ContextVar[str | None] = ContextVar("dcs_org_id", default=None)
workflow_id_var: ContextVar[str | None] = ContextVar("dcs_workflow_id", default=None)
request_id_var: ContextVar[str | None] = ContextVar("dcs_request_id", default=None)


@contextmanager
def bind(
    *,
    tenant_id: str | None = None,
    org_id: str | None = None,
    workflow_id: str | None = None,
    request_id: str | None = None,
) -> Iterator[None]:
    """Bind context values for the duration of the block (only values that are not ``None``)."""
    tokens = []
    for var, value in (
        (tenant_id_var, tenant_id),
        (org_id_var, org_id),
        (workflow_id_var, workflow_id),
        (request_id_var, request_id),
    ):
        if value is not None:
            tokens.append((var, var.set(value)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)
