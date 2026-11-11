# ADR-0011: The admin console is the product's control panel
- Status: Accepted
- Date: 2026-11-11
- Spec references: §9.3 (M-01…M-13), §8.3, §11.2, §16 (F1, F3, F6); amends §9.3 and §13 (adds phase P0.5)

## Context
The founder wants every value that DCS staff decide (product name, prices, limits, launch countries, integration
API keys, e-mail settings, feature switches) to be changeable from the admin console, without a deploy. The spec
spreads such values over environment variables, code constants and a few M-pages, and only M-10 (pricing) and
M-13 (flags) were editable.

## Decision
1. **Control registry.** Every operator-owned value is a *setting* declared once in code (`control_api.config.catalog`):
   key, section, type, default, bounds, help text and the permission needed to change it. The *value* lives in the
   Control DB (`platform_setting`), is validated against the declaration, versioned (`platform_setting_history`,
   one row per change, with revert), and every change is written to the platform audit chain with old and new value.
   Effective value = panel value, else the environment variable named in the declaration, else the default. The
   panel shows which source is in force. Running services pick up a change within 5 s without a restart.
2. **Secrets are write-only.** API keys and passwords are settings of type `secret`. They are sealed with envelope
   encryption (`dcs_vault`, platform key `alias/dcs/t/platform`, AAD binds the setting key) in `platform_secret`.
   No API returns a secret value: the panel shows only *set / not set*, version, who changed it and when. In
   production the same interface can be backed by AWS Secrets Manager without changing callers.
3. **Deployment-owned values stay out of the panel.** Values needed before the panel itself can work stay in
   the environment or the secrets manager: Control DB URL, KMS / master key, OIDC issuers, Redis, Temporal and S3
   endpoints. The panel lists them read-only as "set by deployment" so nothing is hidden.
4. **Car layout.** The console is organised like the car in the spec's analogy (§0):

   | Car part | Console section | Controls |
   |---|---|---|
   | Dashboard | Instrument cluster (M-01) | Gauges and warning lights: tenants, health, failing audit chains, queues |
   | Cabin | Tenants (M-02, M-03) | The customers riding in the car |
   | Chassis | Platform | Regions, countries and launch markets, global limits |
   | Body | Brand | Product name, support contact, legal links, e-mail sender |
   | Electricals | Integrations & secrets | SMTP, and every provider API key as phases add them (LLM P2, OAuth apps P4, payments P8) |
   | Trims & options | Plans & pricing (M-10) | Concierge onboarding price (now); tiers, add-ons, regional prices, coupons (P8) |
   | Wheels | Floor 1 acquisition | Upload limits, e-mail-in, SFTP (P1); connectors M-04 (P4); Bridge M-06 (P5); recipes M-05 (P6) |
   | Fuel lines | Floor 2 shaping | CBM & mapping M-07, Model Gateway M-11 (P2); data quality (P7) |
   | Engine bay | Floor 3 | Tool registry M-09, assignment thresholds (P3) |
   | Switchgear | Feature flags (M-13) | Flags per tenant and plan, maintenance mode, sign-up switch |
   | Locks & keys | Security (M-12) | Staff actions, audit chain verification, break-glass (P9) |

5. **Every later phase adds its own settings to the registry** and its pages to the matching section. A phase gate
   now also checks: "every operator-owned value introduced in this phase is a registry setting or is listed as
   deployment-owned".
6. **Permissions.** `platform:config:read` (support, ops, admin), `platform:config:write` (ops, admin),
   `platform:secrets:write` and `platform:regions:write` (admin only). Staff always use MFA.

## Consequences
- Prices, names, limits and keys change without a release. Each change is attributable and reversible.
- A wrong panel change can break production as easily as a bad deploy. This is mitigated by type and bound
  validation, history with one-click revert, and audit. A two-person rule for critical settings is in the backlog.
- Settings that are security floors are not exposed as switches. MFA is always on (OPEN_QUESTIONS Q5).

## Alternatives considered
- Environment variables plus redeploys: no audit trail, needs engineers for every price or name change.
- A third-party feature-flag or config SaaS: one more sub-processor for secrets, and it splits the audit trail.
