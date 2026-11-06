# Phase 0 Plan — Foundations

Spec references: §0, §2, §3, §4, §8, §9 (A-*, H-01, G-01…G-04, G-06, X-01, X-03, M-01…M-03, M-12, M-13), §10.1,
§11.1, §11.2, §12, §13 Phase 0, §14, §15, §17.10–17.12.

**Objective:** a secure, multi-tenant, observable skeleton. Signing up provisions a tenant with its own Postgres
database, four DB roles, an encryption key and object-store prefixes, and the user sees an empty app shell.

**Out of scope:** any data ingestion (Phase 1+).

## 1. Architecture decisions made while planning

| Decision | Why |
|---|---|
| Provisioning workflows live in `services/control_api` (`control_api.workflows`) and run in a separate `control-worker` process on Temporal task queue `control`. Control DB migrations ship inside the package (`src/control_api/migrations`) so images carry them (spec path: `services/control_api/migrations`). | They read and write Control DB tables owned by control-api. The §3.3 worker list covers data-plane work only. |
| OIDC validation, problem+json, logging, audit hash chain and telemetry live in `dcs_common`. | Shared by control-api, data-api, realtime-gw and workers. |
| Control DB RLS: the app connects as `dcs_control_app` (NOBYPASSRLS). Each transaction sets `app.current_org` (tenant routes) or `app.scope = 'platform'` (staff routes and system workflows only). | §8.2. Platform scope can only be set by code paths that hold a staff token or run inside a workflow. |
| Audit hash chain is **per org** (platform events use the nil UUID chain). Appends take `pg_advisory_xact_lock` on the chain key. UPDATE/DELETE are blocked by a trigger and revoked from the app role. | Tenants can verify their own chain; a deprovisioned tenant does not break other chains. |
| Tenant DB role passwords (`_owner`, `_rw`, `_ro`) are random, sealed with the tenant DEK and stored in the `credential` table (`kind = tenant_db_role`, AAD binds org + role). | No shared "gateway" login that can reach every tenant DB (P4). |
| Local key service (dev) keeps one random KEK per tenant in a key directory, each KEK wrapped by `DCS_LOCAL_MASTER_KEY`. Deleting a key file is a real crypto-shred. | Lets dev exercise the same lifecycle (create → wrap → schedule deletion) as AWS KMS. |
| Web auth: Auth.js (next-auth v5) with the Keycloak provider. Access tokens stay server-side; the browser calls `/api/proxy/{control,data}/*` route handlers that attach the token. Session cookie: httpOnly, SameSite=Lax, 12 h sliding idle, 7 d absolute cap enforced in the JWT callback. | §8.4, and tokens never reach browser JavaScript. |
| `X-DCS-Org` header selects the active org; every request re-validates membership. | See OPEN_QUESTIONS Q1. |

## 2. Task breakdown (each ≤ 1 day)

| ID | Task | Main files | Status |
|---|---|---|---|
| P0-T1 | Monorepo: uv workspace, pnpm + Turborepo, Makefile, pre-commit (ruff, mypy, eslint, gitleaks), `.env.example`, `.gitignore` | `pyproject.toml`, `package.json`, `pnpm-workspace.yaml`, `turbo.json`, `Makefile`, `.pre-commit-config.yaml` | ✅ |
| P0-T2 | docker-compose with healthchecks (Postgres+pgvector, Temporal + UI, Redis, MinIO + init, Keycloak, Mailpit, ClamAV, Grafana LGTM, services, apps); `make dev / reset / seed` | `docker-compose.yml`, `infra/postgres/`, `infra/minio/`, `scripts/seed.py` | ✅ |
| P0-T3 | GitHub Actions: lint, type-check, unit, integration, build images, SBOM (syft), vuln scan (grype/trivy), gitleaks | `.github/workflows/ci.yml` | ✅ |
| P0-T4 | Keycloak realm-as-code (`dcs` customer realm, `dcs-staff` staff realm), MFA (TOTP + WebAuthn) and step-up flow, user-profile attributes `company` + `country`; Keycloakify theme for A-01…A-05 | `infra/keycloak/*.json`, `apps/keycloak-theme/` | ✅ |
| P0-T5 | control-api: OIDC JWT validation (two issuers), org context, `dcs_authz` policy engine, problem+json, OpenAPI, security headers, idempotency keys | `packages/py/dcs_authz`, `packages/py/dcs_common`, `services/control_api` | ✅ |
| P0-T6 | Control DB schema v1 + RLS: `org`, `app_user`, `membership`, `invite`, `tenant_key`, `tenant_db`, `credential`, `audit_event`, `audit_verification_run`, `notification`, `notification_preference`, `feature_flag`, `idempotency_record` | `services/control_api/migrations/versions/0001_control_v1.py` | ✅ |
| P0-T7 | `ProvisionTenantWorkflow` + `DeprovisionTenantWorkflow` (dev local key service; KMS adapter behind the `KeyService` interface) | `services/control_api/src/control_api/workflows/` | ✅ |
| P0-T8 | `dcs_vault` envelope encryption + tests (encrypt / decrypt / rotate / AAD tamper / wrong tenant / truncation) | `packages/py/dcs_vault` | ✅ |
| P0-T9 | Audit: `audit.emit()`, hash chain, verification + nightly `AuditVerifyWorkflow` schedule | `dcs_common/audit.py`, `control_api/audit.py`, `workflows/audit_verify.py` | ✅ |
| P0-T10 | data-api skeleton: `TenantContext`, per-tenant pool keyed by tenant, DB-name guard on every checkout | `services/data_api` | ✅ |
| P0-T11 | realtime-gw: WebSocket with org-scoped channels via Redis pub/sub | `services/realtime_gw` | ✅ |
| P0-T12 | web shell: layout, sidebar, org switcher, H-01 placeholder, A-01…A-05, G-01…G-04, G-06, X-01, X-03 | `apps/web` | ✅ |
| P0-T13 | admin shell: staff SSO, M-01, M-02, M-03 (basic + deprovision), M-12, M-13 | `apps/admin` | ✅ |
| P0-T14 | OpenTelemetry web → API → Temporal → worker; Sentry (enabled when DSN is set) | `dcs_common/telemetry.py`, `apps/*/instrumentation.ts` | ✅ |
| P0-T15 | ADR-0001…0010, CLAUDE.md, PROGRESS.md, OPEN_QUESTIONS.md | `docs/` | ✅ |

## 3. Migrations

- Control DB `0001_control_v1`: tables above, extensions (`pgcrypto`, `citext`, `pg_trgm`), roles `dcs_control_app`,
  RLS policies on every table with `org_id`, append-only trigger on `audit_event`.
- Tenant DB `0001_tenant_baseline` (in `dcs_cbm`): schemas `raw_registry`, `mapping`, `core`, `core_quarantine`,
  `dq`, `graph`, `events`, `drp`, `engine_api_v1`, `results`, `documents`, `audit_local`; table
  `audit_local.event`; grants for `_owner` / `_rw` / `_ro` / `_engine_ro`. CBM tables are added in Phase 2.

## 4. Contracts touched

None of the §17 JSON contracts change in Phase 0. Internal API contracts are the OpenAPI specs generated from
control-api and data-api (`make codegen`).

## 5. Test list

| Suite | Tests |
|---|---|
| Unit | RBAC matrix (every role × every permission against an expected table); vault encrypt/decrypt/rotate/tamper (AAD, ciphertext bit-flip, nonce, wrong DEK, wrong key ref); audit hash chain (append, verify, tamper, reorder, deletion); id generation; log redaction; problem+json; JWT validation (good, expired, wrong issuer, wrong audience, bad signature, staff vs customer realm); region mapping; flag resolution |
| Integration (testcontainers Postgres) | migrations up/down; RLS blocks cross-org reads; signup → provisioning creates DB, 4 roles, key, prefixes (MinIO stubbed with moto); deprovision drops DB/roles, schedules key deletion, audits each step; invite → accept → membership; role change takes effect on the next request; audit append-only trigger; tampered row detected by verification |
| Isolation | Generator introspects the control-api and data-api OpenAPI specs; every tenant-scoped route is called as tenant A with tenant B's IDs and must return 403/404. The build fails if a route is not classified. |
| E2E (Playwright) | sign-up → MFA enrol → home; invite → accept → limited role sees limited nav (runs against the compose stack) |
| Security | gitleaks; trivy/grype with no criticals; CSP + HSTS headers asserted on web, admin and APIs |

## 6. Risks

| Risk | Mitigation |
|---|---|
| Keycloak realm JSON drift between versions | Pin the Keycloak image (26.x); realm import validated in CI by booting Keycloak |
| Keycloakify needs Maven/Java for the theme JAR | Build the JAR in the Keycloak image's multi-stage build and in CI only |
| Windows developer machines lack `make` | Documented in CLAUDE.md; all targets are thin wrappers around `uv`, `pnpm` and `docker compose` |
| Repo lives in a OneDrive folder | `node_modules`/`.venv` churn slows sync; consider moving the repo outside OneDrive or excluding those folders |

## 7. Demo script

Sign up "Northwind Fitness" → enable MFA → invite an analyst → show the tenant DB in psql → show the audit trail →
show M-02.

## 8. Deviations recorded during the build

| Item | Spec | Built | Why |
|---|---|---|---|
| Dev object store | MinIO | RustFS (S3-compatible, Apache-2.0) | MinIO stopped publishing community images in 2025; pulls are denied. Prod remains S3. See OPEN_QUESTIONS Q8. |
| Tailwind | latest | 4.1.x pinned | Tailwind 4.3 pulls an ESM-only `magic-string` that Next 15's webpack CSS loader cannot `require()`. |
| Keycloakify JAR | built in P0 | source + Vite build verified; JAR built in CI (`keycloak-theme` job) | `keycloakify build` needs Maven + Java, not present on developer laptops. Default Keycloak theme is used until `DCS_KC_LOGIN_THEME=dcs`. |
| Per-tenant Temporal schedules / search attributes (§8.1 step 6) | at provisioning | none in P0 | No schedulable tenant jobs exist yet; added with source syncs (P4) and DRP refresh (P2). |
