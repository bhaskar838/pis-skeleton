# Build Progress

| Phase | Status | Started | Gate passed | Tag | Notes |
|---|---|---|---|---|---|
| P0 Foundations | ✅ passed | 2026-11-06 | 2026-11-11 | v0.0.0 | GO signed by the founder; evidence in `docs/phases/PHASE_0_GATE.md` |
| P0.5 Control Panel (founder-inserted, ADR-0011/0012) | 🟦 in progress | 2026-11-11 | | | Plan: `docs/phases/PHASE_0_5_PLAN.md` |
| P1 Floor 1a: Files & Raw Zone | ⬜ not started | | | | |
| P2 Floor 2a: Profiling, CBM, LLM Mapping, Transform | ⬜ not started | | | | |
| P3 Floor 3: Engine Bay & Marketplace | ⬜ not started | | | | |
| P4 Floor 1b: API Connectors, OAuth, Catalog | ⬜ not started | | | | |
| P5 Floor 1c: Databases, Bridge Agent, Legacy | ⬜ not started | | | | |
| P6 Floor 1d: Assisted Browser & Concierge | ⬜ not started | | | | |
| P7 Floor 2b: ER, DQ, Graph, Events, Lineage, Drift | ⬜ not started | | | | |
| P8 Commercial: Billing & Entitlements | ⬜ not started | | | | |
| P9 Hardening, Compliance, Launch | ⬜ not started | | | | |

## Deferred items
- Keycloakify theme JAR: source + Vite build verified locally; the JAR is built by the `keycloak-theme` CI job
  (needs Maven + Java). Default Keycloak theme until `DCS_KC_LOGIN_THEME=dcs`.
- WebAuthn as a login factor: TOTP is the enforced second factor in P0 (see PHASE_0_GATE known issues) → P9.
- Per-tenant default Temporal schedules / search attributes (§8.1 step 6): none needed in P0; P2 (DRP refresh) and
  P4 (source syncs) register theirs in `ProvisionTenantWorkflow`.
- Nonce-based CSP for the Next.js apps → P9.
- Break-glass access flow (M-03 / M-12 show empty states) → P9.

## Open questions
See `docs/OPEN_QUESTIONS.md`. All resolved (F2: Claude Haiku 5.5 on Bedrock, editable in the panel). Deferred by
the founder: Q7's retention period (after app completion), F6's final product name.
