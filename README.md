# DCS-PIS Exoskeleton

The exoskeleton of the DCS-PIS Predictive Intelligence System: identity and tenancy, data acquisition (Floor 1),
transformation into the Intelligence Database (Floor 2) and the Engine Bay that hosts analysis tools (Floor 3).
The specification is [`docs/SPEC.md`](docs/SPEC.md); progress per phase is in [`docs/PROGRESS.md`](docs/PROGRESS.md).

**Current phase: 0 — Foundations.** Sign up → a tenant is provisioned with its own Postgres database, four DB roles,
an encryption key and object-store prefixes → an empty, permission-aware app shell.

## Quick start

Requirements: Docker (≥ 8 GB RAM for the VM), Python via [uv](https://docs.astral.sh/uv/), Node 22 with pnpm
(`corepack enable` or `npx pnpm@9`), GNU make (Windows: `winget install ezwinports.make`).

```bash
make env       # .env with random local secrets (never committed)
make dev       # builds images, boots everything, waits until healthy
make seed      # default feature flags
```

| URL | What |
|---|---|
| http://localhost:3000 | Customer web app (sign up here) |
| http://localhost:3001 | Staff console (user `staff@dcs.local`, password `DCS_KC_STAFF_PASSWORD` from `.env`, OTP enrolment on first login) |
| http://keycloak.localhost:8080 | Keycloak (realms `dcs`, `dcs-staff`) |
| http://localhost:8025 | Mailpit — verification and invitation e-mails |
| http://localhost:8088 | Temporal UI — provisioning workflows |
| http://localhost:3002 | Grafana (traces, logs, metrics) |
| http://localhost:8001/docs | control-api OpenAPI |

`keycloak.localhost` resolves to 127.0.0.1 in Chromium, Firefox and Edge; inside Docker it is a network alias, so
browser and services share one OIDC issuer URL.

Dev notes:
- Identities persist in Postgres (database `keycloak`). Keycloak imports `infra/keycloak/realms/*.json` only when a
  realm does not exist yet, so after changing realm JSON run `make reset && make dev`.
- `make test-e2e` expects a fresh stack: the staff journey performs the staff user's first login (password change +
  TOTP enrolment).
- Phase 0 gate evidence: [`docs/phases/PHASE_0_GATE.md`](docs/phases/PHASE_0_GATE.md).

## Repository map

```
apps/web               Next.js customer app (A-*, H-01, G-01…G-04, G-06, X-01, X-03)
apps/admin             Next.js staff console (M-01, M-02, M-03, M-12, M-13)
apps/keycloak-theme    Keycloakify login theme (JAR built in CI; needs Maven)
services/control_api   Control plane API + Control DB migrations + provisioning workflows (control-worker)
services/data_api      Tenant-scoped API; every request goes through TenantContext
services/realtime_gw   WebSocket fan-out of org-scoped live events
packages/py/*          dcs_common · dcs_authz (RBAC) · dcs_vault (envelope encryption) · dcs_cbm (tenant migrations)
packages/ts/*          ui (design system) · api-client (generated from OpenAPI) · auth (session policy) · config
infra/                 docker images, Keycloak realms-as-code
tests/isolation        Cross-tenant access tests generated from the OpenAPI specs (blocking)
tests/e2e              Playwright journeys against the compose stack
docs/                  SPEC, ADRs, phase plans and gates, open questions
```

## Everyday commands

```bash
make test             # lint + types + unit + integration + isolation + web tests
make test-integration # needs Docker (testcontainers: Postgres + S3)
make test-e2e         # Playwright against `make dev`
make codegen          # OpenAPI → TypeScript client
make reset            # stop and DELETE local data
```

## Ground rules

See [`CLAUDE.md`](CLAUDE.md): contracts are versioned, LLMs only propose specs, every data path goes through
TenantContext, never log secrets or raw PII, tests are part of every feature.
