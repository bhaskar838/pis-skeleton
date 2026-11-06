# Phase 0 Gate — Foundations
Date: 2026-11-06 | Commit: b332801 | Tag: v0.0.0 (after sign-off) | Reviewer: —

Environment for all evidence: Windows 11, Docker Desktop 28 (8 GB VM — half the spec's 16 GB laptop), Python 3.12.13
(uv), Node 22.12, pnpm 9.15. Raw outputs are referenced by the command that produces them.

## Acceptance criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | `make reset && make dev` boots all services healthy in < 5 min on a 16 GB laptop | ✅ | `docker compose down -v` then `docker compose up -d --wait`: **276 s**, exit 0, 15/15 services up, all healthchecks healthy (images pre-built; first build of images additionally takes ~15 min) |
| 2 | New signup gets a provisioned tenant (DB, 4 roles, key, prefixes) in < 30 s; visible in M-02 | ✅ | Real stack: `org.created` 12:36:48.885 → `tenant.provisioned` 12:36:59.834 (**11 s**) through Temporal + Keycloak + local KMS + S3. psql: database `t_iroj0dyd90`, roles `_owner/_rw/_ro` (LOGIN) + `_engine_ro` (NOLOGIN), 12 tenant schemas. M-02: E2E `staff console … M-02 lists the tenant` ✅. Integration: `test_signup_provisions_tenant_in_under_30s` ✅ |
| 3 | Deprovisioning removes DB and prefixes, marks key for deletion; audit shows every step | ✅ | `test_deprovision_removes_everything_and_audits_each_step`: DB + 4 roles gone, prefixes gone, key `pending_deletion` with date, org `deleted`, audit actions `requested → idp_group_deleted → database_dropped → prefixes_deleted → key_deletion_scheduled → deprovisioned` |
| 4 | Audit chain verification passes; a tampered row is detected by the job | ✅ | `test_audit_chain_verification_detects_tampering` (verify ok → superuser edits a row → job reports `first_bad_id` = edited row; dashboard `audit_chains_failing ≥ 1`). Unit: modified / deleted / re-ordered / recomputed-forgery / tail-truncation cases in `test_audit_chain.py`. Nightly schedule `audit-verify-nightly` created by control-worker (log) |
| 5 | All 18 pages render with loading, empty, error and forbidden states | ✅ | `next build` of web (A-01…A-05, H-01, G-01…G-04, G-06, X-01, X-03 = 404/403/500/maintenance/session-expired) and admin (M-01, M-02, M-03, M-12, M-13). Shared `LoadingState/EmptyState/ErrorState/ForbiddenState` + route `loading.tsx`/`error.tsx`; every data page checks its permission and maps API failures (`ApiState`). E2E: analyst sees forbidden state on G-02 |
| 6 | CI green; coverage ≥ thresholds (§14.3) | ✅ | GitHub Actions run #2 (`ci.yml`, commit `b332801`): **8/8 jobs green**: python-quality, python-unit, python-integration, web, keycloak-theme, security, images (build + syft SBOM + grype), e2e-smoke (compose stack booted on the runner in 287 s, then Playwright 17 s). Run #1 failures fixed in `b332801` (see commit message). Coverage: dcs_authz 100 %, dcs_vault 100 % (≥95 branch), dcs_common 97 % (≥90), services 86 % (≥80), web 73 % / admin 86 % / ui 88 % (≥70) |

## Test summary

unit: authz 432 ✓ · vault 56 ✓ · common 95 ✓ · control-api unit 24 ✓ · web 21 ✓ · admin 6 ✓ · ui 11 ✓ · api-client 4 ✓
integration (testcontainers Postgres 16 + pgvector, RustFS S3, Temporal test server): 111 ✓ incl. isolation
isolation: OpenAPI-generated; 29 control-api + 1 data-api routes classified; every tenant route attacked with tenant B's IDs and B's org header → 403/404, victim objects unchanged ✓
e2e (Playwright vs compose stack): 4/4 ✓ — sign-up → e-mail verification → TOTP enrolment → home (`active`); invite → register → accept → limited nav + forbidden; security headers; staff first login → M-02
security: gitleaks (staged tree) **no leaks** · trivy fs (uv.lock, pnpm-lock.yaml, theme lock) **0 CRITICAL, 0 HIGH** · CSP + HSTS asserted on APIs (unit) and web (E2E/curl)
ci: GitHub Actions run #2 — 8/8 jobs green
static: ruff + `mypy --strict` (72 files) clean · `tsc --noEmit` + eslint clean in 6 TS packages
perf: n/a in P0 (no load-bearing paths)

## Demo script result

1. Sign up "Northwind Fitness" → ✅ (E2E 1; Keycloak registration + Mailpit verification)
2. Enable MFA → ✅ owner redirected to A-04, TOTP enrolled via Keycloak step-up (`acr=mfa`)
3. Invite an analyst → ✅ invitation e-mail, accepted, analyst nav limited (E2E 2)
4. Show tenant DB in psql → ✅ `t_iroj0dyd90` with roles and schemas (see criterion 2)
5. Show audit trail → ✅ 9 hash-chained events: `org.created`, 5 provisioning steps, `tenant.provisioned`, `member.invited`, `member.joined`
6. Show M-02 → ✅ E2E 4 (staff password change + TOTP on first login, tenant listed)

## Contracts changed (with ADR links)

None of the §17 contracts are touched in Phase 0. ADR-0001…0010 written (`docs/adr/`).

## Known issues / deferred (issue IDs to be created when the tracker exists)

| Item | Detail |
|---|---|
| WebAuthn as login factor | TOTP enforced as the second factor. A flow with TOTP/WebAuthn as alternatives fails for users with neither (Keycloak does not enrol alternatives); WebAuthn needs a conditional enrol sub-flow → P9 hardening |
| Keycloakify theme JAR | Source + Vite build verified; JAR built in CI (Maven). Default theme until `DCS_KC_LOGIN_THEME=dcs` |
| Realm changes on an existing dev DB | Keycloak now persists in Postgres; `--import-realm` skips existing realms, so realm JSON changes need `make reset` (or an admin re-import) |
| Per-tenant Temporal schedules / search attributes | None needed in P0; added with P2 (DRP refresh) and P4 (syncs) |
| Dev object store | RustFS instead of MinIO (images withdrawn) — OPEN_QUESTIONS Q8 |
| CSP uses `'unsafe-inline'` scripts | Next.js hydration; move to nonce-based CSP in P9 |
| Break-glass flow | M-03/M-12 show the empty state; implemented with P9 |

## Go / No-Go: ☐ GO ☐ NO-GO   — signed: …

Builder's assessment: all six acceptance criteria have evidence. Recommend GO. Founder answers to OPEN_QUESTIONS
Q1–Q8 are still requested (conservative defaults are in place meanwhile). After sign-off: tag `v0.0.0`.
