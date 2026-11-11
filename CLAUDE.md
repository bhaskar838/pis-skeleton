# CLAUDE.md — DCS-PIS Exoskeleton
Source of truth: docs/SPEC.md (this build specification). Current phase: see docs/PROGRESS.md.

## Rules
- Work ONLY on the current phase scope. Out-of-scope ideas → docs/ENGINE_BACKLOG.md or OPEN_QUESTIONS.md.
- Contracts in /contracts are versioned. Changing one requires an ADR + version bump.
- LLM output = specs only. Never execute LLM output as code. Never compute business figures with an LLM.
- Every data-access path must go through TenantContext. Add isolation tests for new routes.
- Never log secrets or raw PII. Never commit .env files.
- MFA is always enforced (all environments). Operator-owned values are panel settings (ADR-0011).
- Tests are mandatory (unit + integration minimum). Run `make test` before every commit.

## Commands
make dev | make reset | make seed | make test | make test-e2e | make lint | make codegen | make gate PHASE=N

## Style
Python: ruff + mypy strict, async SQLAlchemy, Pydantic v2. TS: strict, server components by default, shadcn/ui.
Commit format: conventional commits.

## Repo map (Phase 0 + 0.5)
- `packages/py/dcs_common` — settings, JSON logging with redaction, problem+json, ids, OIDC auth, audit hash chain, telemetry, tenant context
- `packages/py/dcs_authz` — RBAC policy engine; roles × permissions live in `policies.yaml`
- `packages/py/dcs_vault` — envelope encryption (AES-256-GCM) + KeyService (local dev / AWS KMS)
- `packages/py/dcs_cbm` — tenant DB migrations (Phase 0: schema baseline only; CBM tables arrive in Phase 2)
- `services/control_api` — FastAPI control plane + Control DB migrations + provisioning workflows (`control` task queue)
  - `config/` — control panel (ADR-0011): settings catalog + `ConfigRegistry` (panel > env > default, sealed
    secrets, history, audit). **Every new operator-owned value goes into `config/catalog.py`**, not env/constants.
  - `world.py` + `regions.py` — four-region world map and sign-up country rules (ADR-0012)
- `services/data_api` — tenant-scoped FastAPI; every request goes through `TenantContext`
- `services/realtime_gw` — WebSocket fan-out of org-scoped events from Redis
- `apps/web`, `apps/admin` — Next.js customer app and staff console; the admin console is the control panel,
  grouped by car part (Dashboard, Cabin, Chassis, Body, Electricals, Trims & options, Wheels, Fuel lines, Engine bay,
  Switchgear, Locks & keys). New phase pages go under their part in `apps/admin/lib/nav.ts`.
- `packages/ts/{ui,api-client,config}` — design system, generated API client, shared config
- `infra/keycloak` — realm-as-code; `infra/` compose support files

## Windows notes
`make` is not installed by default on Windows. Use `winget install ezwinports.make` (or run the equivalent
commands from the Makefile by hand). Python is managed by `uv`; Node packages by `pnpm` (`corepack enable`).
