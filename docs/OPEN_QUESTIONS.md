# Open Questions

Rule (SPEC §0.1.6): when the spec is ambiguous about a contract, a security boundary or data retention, record the
question here and apply the **conservative default** until a human answers.

Status values: **resolved** = decision in force · **proposed** = builder recommendation, founder to confirm before the
phase that needs it · **open** = founder decision, nothing built depends on it yet.

On 2026-11-06 the founder asked the builder to settle these. Engineering and security questions (Q1–Q8, F5) are
resolved below; the business questions (F1, F3, F4, F6) stay with the founder.

## Founder decisions (SPEC §16)

| # | Question | Decision / current default | Needed by | Status |
|---|---|---|---|---|
| F1 | Plan tiers: Primary tools per tier, add-on price bands (INR / GBP / USD)? | Pricing is a commercial call; no code depends on it yet | P8 | open |
| F2 | Default LLM provider for mapping; self-hosted model at launch? | **Recommendation:** Claude through Amazon Bedrock, called in the tenant's own region behind the pluggable provider interface; **no** self-hosted model at launch. Choose the exact model with the P2 mapping evaluation set. Before P2 starts, check in the AWS docs that the model runs inside `ap-south-1` and `eu-west-2` without cross-region routing that moves data out of the region. Dev and CI keep the fake provider. | P2 start | proposed |
| F3 | Is concierge onboarding paid or included for some tiers? | Commercial call; ties to F1 | P6 | open |
| F4 | Launch regions: India + UK simultaneously, or India first? | Code supports both regions today (see Q3); this is a go-to-market and legal-entity decision | P9 | open |
| F5 | Does the Engine need a precomputed feature store? | **No** for the exoskeleton: Engine tools compute their own features (spec default). If the Engine team needs one, it goes through `ENGINE_BACKLOG.md` | — | resolved |
| F6 | Product naming of the exoskeleton (codename `EXO`)? | `EXO` stays the internal codename; customer-facing name is a branding call | P9 | open |

## Phase 0 questions (raised by the builder)

| # | Area | Question | Decision | Status |
|---|---|---|---|---|
| Q1 | Security boundary | How is the "active org" carried on API calls? The spec says it comes from the session, never the body. | The web app sends `X-DCS-Org`; **every** request re-checks an *active* membership for (user, org) in the Control DB. Unknown or non-member org → 404, so org IDs cannot be probed. | resolved |
| Q2 | Security boundary | Does the Admin role get billing write access? §8.3 lists billing only under Owner. | No. Admin gets `billing:read` only; `billing:write` is Owner + Billing role (least privilege, matches §8.3). | resolved |
| Q3 | Data residency | Which region do countries outside India/UK/EU map to? | **London (`eu-west-2`):** UK, Crown Dependencies (GG, JE, IM) and Gibraltar; EU-27 including the outermost regions and Åland that have their own ISO codes (GF, GP, MQ, RE, YT, MF, AX); EEA (IS, LI, NO); Switzerland; Andorra and the Faroe Islands (EU adequacy). **Mumbai (`ap-south-1`):** India and every other country. Region is immutable after signup. Revisit the Americas (lower latency to London) together with F4; a change would only affect new signups. | resolved |
| Q4 | Security boundary | Must an invite be accepted by a login whose email matches the invited address? | Yes. Emails compared case-insensitively; a mismatch is rejected and audited. Invites expire after 7 days and are single-use. | resolved |
| Q5 | Security boundary | How is MFA "mandatory for Owner and Admin" enforced, given org roles live in the Control DB and not in Keycloak? | control-api and data-api reject owner/admin requests whose token lacks an MFA authentication (`acr` = `mfa` level or `amr` contains `otp`/`webauthn`) with problem type `mfa-required`; the web app sends the user to A-04 (Keycloak step-up with `acr_values=mfa`). `DCS_MFA_ENFORCE=false` is accepted only when `DCS_ENV` is `local` or `ci`; services refuse to start with it in `staging`/`prod`. | resolved |
| Q6 | Data retention | Deprovision waiting period for the tenant CMK (KMS allows 7–30 days). | 30 days by default; staff may choose 7–30 in M-03 (validated by the API). | resolved |
| Q7 | Data retention | Audit events of a deprovisioned tenant: keep or delete? | **Keep** (append-only, no FK to `org`), so a deprovisioning stays provable. The *retention period* (when they may finally be purged) needs legal review under DPDP Act / UK GDPR (§16); until then nothing is purged. | resolved (period: legal review) |
| Q8 | Tooling | MinIO community images are no longer published. Which S3-compatible store for local/CI? | RustFS (Apache-2.0) in docker-compose and testcontainers; production stays on AWS S3 with Object Lock. Swappable via `DCS_TEST_S3_IMAGE` / compose `s3` service. | resolved |
