# Build Progress

| Phase | Status | Started | Gate passed | Tag | Notes |
|---|---|---|---|---|---|
| P0 Foundations | 🟨 gate pending CI | 2026-11-06 | | | All code + local suites done; `docs/phases/PHASE_0_GATE.md` — criteria 1–5 ✅, CI (6) awaits first GitHub run |
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

## Open questions awaiting founder
See `docs/OPEN_QUESTIONS.md` (F1–F6 from the spec, Q1–Q8 raised during Phase 0, each with the conservative default
currently applied).
