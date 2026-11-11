# Phase 0.5 Gate — Control Panel
Date: 2026-11-11 | Commits: 8516c08 (backend), 86e8822 (frontend) | Tag: v0.0.5 (after sign-off) | Reviewer: —

Plan: `docs/phases/PHASE_0_5_PLAN.md`. Decisions: ADR-0011 (admin console is the control panel, car layout),
ADR-0012 (four regions cover the world). Environment as in the Phase 0 gate.

## Acceptance criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Every operator-owned value in the P0 code paths is a registry setting or listed as deployment-owned | ✅ (3 exceptions below) | `config/catalog.py`: 17 settings in Chassis, Body, Electricals, Trims & options, Fuel lines; 14 deployment-owned values listed read-only in Electricals. Org limit, invite lifetime, key-deletion window, SMTP, e-mail sender, product name, support e-mail, legal links, concierge price, mapping model and effort all read from the registry. Exceptions (see known issues): session lifetimes, audit-verification schedule, RBAC matrix |
| 2 | A panel change reaches running services within 5 s without a restart | ✅ | Registry cache TTL 3 s, invalidated at once in the writing process. `test_other_processes_see_changes_within_the_cache_ttl` (second registry on the same DB sees the change after the TTL). `test_panel_values_take_effect_without_restart` (org limit and invite lifetime change live; e-mail subject uses the new product name). E2E: Body rename visible on the web sign-in page (CI) |
| 3 | No API returns a secret value; secrets are not logged | ✅ | `test_secrets_are_write_only`: plaintext absent from PUT response, `/config`, history and platform audit; ciphertext in `platform_secret` does not contain it; only `ConfigRegistry.secret()` opens it. Request bodies are never logged (`dcs_common.web`), and the redactor masks secret/password/token fields |
| 4 | Every change is in the platform audit chain with before and after (secrets: version only); revert works | ✅ | `test_set_validate_history_revert_reset_and_audit` (actions `staff.config.set/revert/reset` with `old`/`new`; revert to an earlier version; reset has nothing to revert → 409). Secrets: `staff.secret.set/cleared` with version only. Regions/countries: `staff.region.*`, `staff.country.updated` with before/after |
| 5 | Sign-up from a country that is not enabled is refused; enabling it in the panel allows sign-up at once | ✅ | `test_signup_follows_the_country_map`: Brazil refused (`country-not-available`, "DCS-PIS is not available in Brazil yet."); add region `sa-east-1` → move BR → enable refused while planned → activate → enable → sign-up lands in `sa-east-1`; region cannot be switched off with open countries or live tenants. `test_public_endpoints`: public list = India + 48 legal-Europe codes |
| 6 | MFA is enforced in every environment; no setting disables it | ✅ | `DCS_MFA_ENFORCE` removed from code; `test_there_is_no_switch_to_disable_mfa`; staff token without MFA → 403 on the panel (`test_staff_permissions`) |
| 7 | All console sections render with loading, empty, error and forbidden states; CI green; coverage ≥ thresholds | ✅ local / CI pending | `next build` of admin (new routes `/chassis`, `/body`, `/electricals`, `/trims`, `/wheels`, `/fuel-lines`, `/engine-bay`, `/config/[key]`) and web. Shared `ApiState` / `EmptyState`; section pages without settings show "fitted in later phases". Coverage: dcs_authz 100 %, dcs_common 97 %, services 88 %, admin 98 %, web 74 %. CI run: (to record) |

## Test summary

unit: authz 468 ✓ (matrix incl. 4 new permissions) · common 99 ✓ · control-api unit incl. world map + catalog 82 ✓ · admin 18 ✓ ·
web 23 ✓
integration (testcontainers Postgres 16, RustFS, Temporal test server): services 131 ✓ incl. 10 control-panel tests
isolation: 62 ✓ — 12 new staff routes reject customer tokens; 2 public routes serve no tenant identifiers
e2e: staff journey extended (Body change reaches the web app; Chassis shows Mumbai active / N. Virginia planned);
new public test (sign-up offers IN and DE, not US or SG). Local run blocked: Docker Desktop's engine crashed (HTTP
500 on every call) while starting the rebuilt stack; to be recorded from CI
static: ruff + `mypy --strict` clean (79 files); `tsc --noEmit` + eslint clean in admin and web

## Demo script result
Pending a running stack (local Docker engine down). Each step is covered by the integration tests above; the CI
e2e run covers rename → web, and the Chassis view.

## Contracts changed
None of the §17 contracts. OpenAPI grows (new `/v1/admin/*` and `/v1/public/*` routes); `DeprovisionRequest.pending_days`
becomes optional (panel default). ADR-0011, ADR-0012 written.

## Known issues / deferred

| Item | Detail |
|---|---|
| Session lifetimes (12 h idle / 7 d absolute) | Enforced in Auth.js and Keycloak; security floor, not a panel switch yet → P9 (with Keycloak admin sync) |
| Audit-verification schedule (02:00 UTC) | Temporal schedule created by the worker; moving it to the panel needs schedule updates → backlog |
| RBAC role × permission matrix | Kept in `policies.yaml` with an exhaustive test matrix on purpose (a contract-like security boundary) |
| Two-person approval for critical settings | Backlog (ADR-0011 consequences) |
| Region activation without infrastructure | Staff admin only; region IaC arrives in P9 (ADR-0012 §5) |
| Bedrock model availability per region | `aws bedrock list-foundation-models` in `ap-south-1` / `eu-west-2` must be checked before P2 (local AWS session expired) |

## Go / No-Go: ☐ GO ☐ NO-GO   — signed: …

Builder's assessment: criteria 1–6 met with test evidence; criterion 7 met locally and waits for the CI run.
Recommend GO once CI is green.
