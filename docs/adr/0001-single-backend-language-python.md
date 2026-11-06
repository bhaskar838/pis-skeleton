# ADR-0001: Single backend language (Python)
- Status: Accepted
- Date: 2026-11-06
- Spec references: §4.1, §3.3

## Context
The data plane depends on Python-native libraries: dlt, DuckDB, Polars, Playwright, Splink, PyArrow and OCR tooling.
The control plane could use another language (NestJS was considered), but two backend languages double the context
Claude Code and the team have to hold, and duplicate cross-cutting code (auth, audit, tenancy, vault).

## Decision
All backend services and workers use **Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2 (async) + Alembic**.
The only exceptions are the Bridge Agent and Bridge Relay (ADR-0010), which are Go for deployment reasons.

## Consequences
- Cross-cutting libraries (`dcs_common`, `dcs_authz`, `dcs_vault`) are written once.
- Strict typing is enforced with `mypy --strict` to offset Python's dynamic typing.
- CPU-heavy paths rely on native engines (DuckDB, Polars, PyArrow) rather than pure Python.

## Alternatives considered
- NestJS + Prisma for the control plane: rejected; Prisma handles dynamic per-tenant databases poorly.
