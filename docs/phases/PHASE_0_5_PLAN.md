# Phase 0.5 Plan — Control Panel

Inserted by the founder on 2026-11-11, after the Phase 0 gate and before Phase 1 (ADR-0011, ADR-0012). It goes
first because every later phase adds its settings to the control panel, so the panel has to exist before them.

**Objective:** the admin console becomes the product's control panel, laid out like the car in §0. Operator-owned
values are edited there, take effect without a deploy, are audited and can be reverted. Secrets can be written
but never read back. Sign-up follows a world-wide, editable country → region map with India and Europe enabled.

**Out of scope:** Plans & pricing editor (M-10, P8: designed to be panel-edited, per F1); per-phase settings of P1+
(each phase adds its own); region infrastructure-as-code (P9); two-person approval for critical settings
(backlog).

## Founder decisions applied (2026-11-11)

| Ref | Decision | Where |
|---|---|---|
| Q5 | MFA is always on in every environment, including local and CI ("prod-level testing"). The switch is removed. | `dcs_common.settings`, `deps.py`, data-api |
| Q3 + F4 | Four regions cover the world (nearest region); launch with India and Europe | ADR-0012, `region` / `country` tables |
| Q7 | Audit retention decided after the whole app is complete; nothing is purged until then | OPEN_QUESTIONS |
| F1 | Pricing must be editable from the panel | M-10 in P8 (Trims & options) |
| F3 | Concierge onboarding is free at the start, editable | setting `trims.concierge_onboarding` |
| F6 | Product name "DCS-PIS" for now, editable | setting `body.product_name` |
| — | The admin console is the central control panel, styled like the car | ADR-0011 |

## Tasks

| ID | Task | Main files | Status |
|---|---|---|---|
| P05-T1 | Remove the MFA switch (always enforced) | `dcs_common/settings.py`, `control_api/deps.py`, `data_api/main.py` | ⬜ |
| P05-T2 | Control DB migration 0002: `region`, `country`, `platform_setting`, `platform_setting_history`, `platform_secret` + RLS + grants; seed the world map | `migrations/versions/0002_control_panel.py`, `control_api/world.py` | ⬜ |
| P05-T3 | Settings catalog + validation (types: string, int, bool, enum, email, url, money, secret) | `control_api/config/catalog.py` | ⬜ |
| P05-T4 | `ConfigRegistry`: effective value (panel > environment > default), 3 s cache, set / reset / history / revert, sealed secrets, audit | `control_api/config/registry.py` | ⬜ |
| P05-T5 | Wire the registry into callers: org limit, invite TTL, deprovision window, SMTP mailer, product name in e-mails | `routers/orgs.py`, `routers/team.py`, `mailer.py`, `notifications.py` | ⬜ |
| P05-T6 | Region rules: sign-up resolves the country from the DB, refuses disabled countries; region / country editing rules | `control_api/regions.py`, `routers/admin_regions.py` | ⬜ |
| P05-T7 | Admin API: `/v1/admin/config*`, `/v1/admin/secrets/*`, `/v1/admin/regions*`, `/v1/admin/countries*`; public `/v1/public/brand`, `/v1/public/countries` | `routers/admin_config.py`, `routers/public.py` | ⬜ |
| P05-T8 | RBAC: `platform:config:read/write`, `platform:secrets:write`, `platform:regions:write` | `dcs_authz/policies.yaml` | ⬜ |
| P05-T9 | Admin UI in the car layout: nav groups, instrument-cluster dashboard, Chassis, Body, Electricals, Trims & options, Wheels / Fuel lines / Engine bay (what arrives when), Switchgear, Locks & keys; generic setting editor with history and revert; write-only secret editor | `apps/admin` | ⬜ |
| P05-T10 | Web: product name from `/v1/public/brand`; create-org country list from `/v1/public/countries`; "not available in your country yet" | `apps/web` | ⬜ |
| P05-T11 | OpenAPI export + regenerate `@dcs/api-client`; isolation classifier for the new routes | `packages/ts/api-client`, `tests/isolation` | ⬜ |
| P05-T12 | Tests: unit (catalog, world map, validation), integration (registry, secrets, audit, revert, sign-up rules, RBAC), isolation, E2E (rename product → visible; sign-up country gate) | `services/control_api/tests`, `tests/e2e` | ⬜ |
| P05-T13 | Docs: OPEN_QUESTIONS, PROGRESS, CLAUDE.md repo map, gate report | `docs/` | ⬜ |

## Acceptance criteria
- [ ] Every operator-owned value in the P0 code paths is either a registry setting or listed as deployment-owned
- [ ] A change in the panel reaches running services within 5 s without a restart
- [ ] No API returns a secret value; secrets are not logged (verified by tests)
- [ ] Every change is in the platform audit chain with before and after (secrets: version only); revert works
- [ ] Sign-up from a country that is not enabled is refused; enabling it in the panel allows sign-up immediately
- [ ] MFA is enforced in every environment; there is no setting that disables it
- [ ] All console sections render with loading, empty, error and forbidden states; CI green; coverage ≥ thresholds

## Demo script
Staff admin signs in → instrument cluster → Body: rename the product → the customer web app shows the new name →
Electricals: set the SMTP password (shown only as "set, v1") → Chassis: try to sign up from Singapore (refused) →
enable Singapore's region and country → sign-up works → Locks & keys: every change is in the audit trail → revert
the product name.
