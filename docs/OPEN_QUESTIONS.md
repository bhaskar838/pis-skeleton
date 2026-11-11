# Open Questions

Rule (SPEC §0.1.6): when the spec is ambiguous about a contract, a security boundary or data retention, record the
question here and apply the **conservative default** until a human answers.

Status values: **resolved** = decision in force · **proposed** = builder recommendation, founder to confirm before the
phase that needs it · **open** = founder decision, nothing built depends on it yet.

On 2026-11-06 the founder asked the builder to settle the engineering and security questions (Q1–Q8, F5). On
2026-11-11 the founder answered F1, F3, F4, F6 and revised Q3, Q5 and Q7. Founder principle (ADR-0011): every value
DCS staff decide is editable from the admin console.

## Founder decisions (SPEC §16)

| # | Question | Decision / current default | Needed by | Status |
|---|---|---|---|---|
| F1 | Plan tiers: Primary tools per tier, add-on price bands (INR / GBP / USD)? | **Founder:** prices are set by staff in the admin console (Trims & options, M-10), not in code. Actual amounts are entered there when billing ships | P8 | resolved (amounts: set in panel) |
| F2 | Default LLM provider for mapping; self-hosted model at launch? | **Founder (2026-11-11):** a cheap and strong model on Amazon Bedrock; no self-hosted model. Default **Claude Haiku 5.5** (`anthropic.claude-haiku-5-5`, effort `medium`): Anthropic's low-cost tier for classification/extraction, structured outputs and prompt caching supported on Bedrock (list price $0.10 / $0.50 per MTok in/out; Bedrock bills its own rates). Both are panel settings (Fuel lines → `fuel_lines.mapping_model`, `fuel_lines.mapping_effort`); `anthropic.claude-sonnet-5-5` is the upgrade if the P2 mapping evaluation needs it. **Before P2:** confirm with `aws bedrock list-foundation-models` that the model is served in `ap-south-1` and `eu-west-2`, and that any inference profile used keeps data inside India / Europe (Bedrock has no `inference_geo`). Refusals (no server-side fallback on Haiku) go to human review. Dev and CI keep the fake provider. | P2 start | resolved |
| F3 | Is concierge onboarding paid or included for some tiers? | **Founder:** free at the start; editable in the panel (setting `trims.concierge_onboarding`) | P6 | resolved |
| F4 | Launch regions: India + UK simultaneously, or India first? | **Founder:** India and Europe first. `ap-south-1` and `eu-west-2` active; sign-up enabled for India and legal Europe (ADR-0012); more countries are switched on in the panel | P9 | resolved |
| F5 | Does the Engine need a precomputed feature store? | **No** for the exoskeleton: Engine tools compute their own features (spec default). If the Engine team needs one, it goes through `ENGINE_BACKLOG.md` | — | resolved |
| F6 | Product naming of the exoskeleton (codename `EXO`)? | **Founder:** "DCS-PIS" for now; final name later; editable in the panel (setting `body.product_name`) | P9 | resolved (final name later) |

## Phase 0 questions (raised by the builder)

| # | Area | Question | Decision | Status |
|---|---|---|---|---|
| Q1 | Security boundary | How is the "active org" carried on API calls? The spec says it comes from the session, never the body. | The web app sends `X-DCS-Org`; **every** request re-checks an *active* membership for (user, org) in the Control DB. Unknown or non-member org → 404, so org IDs cannot be probed. | resolved |
| Q2 | Security boundary | Does the Admin role get billing write access? §8.3 lists billing only under Owner. | No. Admin gets `billing:read` only; `billing:write` is Owner + Billing role (least privilege, matches §8.3). | resolved |
| Q3 | Data residency | Which region do countries outside India/UK/EU map to? | **Founder (2026-11-11):** nearest AWS region, with as few regions as possible. Four regions cover the world: Mumbai `ap-south-1`, London `eu-west-2`, N. Virginia `us-east-1`, Singapore `ap-southeast-1` (ADR-0012). Places legally in the EU/UK always map to London. The map lives in the Control DB and is edited in the panel; a tenant's region is immutable after sign-up. | resolved |
| Q4 | Security boundary | Must an invite be accepted by a login whose email matches the invited address? | Yes. Emails compared case-insensitively; a mismatch is rejected and audited. Invites expire after 7 days and are single-use. | resolved |
| Q5 | Security boundary | How is MFA "mandatory for Owner and Admin" enforced, given org roles live in the Control DB and not in Keycloak? | control-api and data-api reject owner/admin (and all staff) requests whose token lacks an MFA authentication (`acr` = `mfa` level or `amr` contains `otp`/`webauthn`) with problem type `mfa-required`; the web app sends the user to A-04 (Keycloak step-up with `acr_values=mfa`). **Founder (2026-11-11):** always on in every environment, including local and CI, so testing is production-level. There is no switch. | resolved |
| Q6 | Data retention | Deprovision waiting period for the tenant CMK (KMS allows 7–30 days). | 30 days by default; staff may choose 7–30 in M-03 (validated by the API). | resolved |
| Q7 | Data retention | Audit events of a deprovisioned tenant: keep or delete? | **Keep** (append-only, no FK to `org`), so a deprovisioning stays provable. **Founder (2026-11-11):** the retention period is decided after the whole app is complete (with legal review under DPDP Act / UK GDPR, §16). Until then nothing is purged. | resolved (period: after app completion) |
| Q8 | Tooling | MinIO community images are no longer published. Which S3-compatible store for local/CI? | RustFS (Apache-2.0) in docker-compose and testcontainers; production stays on AWS S3 with Object Lock. Swappable via `DCS_TEST_S3_IMAGE` / compose `s3` service. | resolved |
