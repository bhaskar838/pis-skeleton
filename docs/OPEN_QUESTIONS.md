# Open Questions

Rule (SPEC §0.1.6): when the spec is ambiguous about a contract, a security boundary or data retention, record the
question here and apply the **conservative default** until a human answers.

## Founder decisions (SPEC §16)

| # | Question | Default applied until answered | Status |
|---|---|---|---|
| F1 | Plan tiers: Primary tools per tier, add-on price bands (INR / GBP / USD)? | Not needed before P8 | open |
| F2 | Default LLM provider for mapping; self-hosted model at launch? | Fake provider in dev; not needed before P2 | open |
| F3 | Is concierge onboarding paid or included for some tiers? | Not needed before P6 | open |
| F4 | Launch regions: India + UK simultaneously, or India first? | Both regions supported in code; see Q3 | open |
| F5 | Does the Engine need a precomputed feature store? | Tools compute their own (spec default) | open |
| F6 | Product naming of the exoskeleton (codename `EXO`)? | `EXO` used internally | open |

## Phase 0 questions (raised by the builder)

| # | Area | Question | Conservative default applied | Status |
|---|---|---|---|---|
| Q1 | Security boundary | How is the "active org" carried on API calls? The spec says it comes from the session, never the body. | The web app sends `X-DCS-Org`; **every** request re-checks an *active* membership for (user, org) in the Control DB. Unknown or non-member org → 404, so org IDs cannot be probed. | open |
| Q2 | Security boundary | Does the Admin role get billing write access? §8.3 lists billing only under Owner. | Admin gets `billing:read` only. `billing:write` is Owner + Billing role. | open |
| Q3 | Data residency | Which region do countries outside India/UK/EU map to? | IN → `ap-south-1`; GB + EU/EEA + CH → `eu-west-2`; every other country → `ap-south-1`. Region is immutable after signup. | open |
| Q4 | Security boundary | Must an invite be accepted by a login whose email matches the invited address? | Yes. Emails are compared case-insensitively; a mismatch is rejected and audited. Invites expire after 7 days and are single-use. | open |
| Q5 | Security boundary | How is MFA "mandatory for Owner and Admin" enforced, given org roles live in the Control DB and not in Keycloak? | control-api rejects owner/admin requests whose token does not carry an MFA authentication (`acr` = `mfa` level or `amr` contains `otp`/`webauthn`) with problem type `mfa-required`; the web app then sends the user to A-04 (Keycloak step-up with `acr_values=mfa`). Can be relaxed per environment with `DCS_MFA_ENFORCE=false` (dev only). | open |
| Q6 | Data retention | Deprovision waiting period for the tenant CMK (KMS allows 7–30 days). | 30 days (maximum) unless staff choose a shorter window in M-03, minimum 7. | open |
| Q7 | Data retention | Audit events of a deprovisioned tenant: keep or delete? | Keep (append-only, no FK to `org`). Retention period to be set by legal review (§16). | open |
| Q8 | Tooling | MinIO community images are no longer published. Which S3-compatible store for local/CI? | RustFS (Apache-2.0) in docker-compose and testcontainers; production stays on AWS S3 with Object Lock. Swap via `DCS_TEST_S3_IMAGE` / compose `s3` service. | open |
