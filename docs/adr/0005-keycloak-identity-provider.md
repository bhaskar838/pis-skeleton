# ADR-0005: Keycloak as the identity provider
- Status: Accepted (Zitadel as fallback)
- Date: 2026-11-06
- Spec references: §4.1, §8.4

## Context
We need OIDC with PKCE, MFA (TOTP and WebAuthn), self-hosting for data residency, and SAML/OIDC federation for
enterprise customers later.

## Decision
Use **Keycloak 26.x**, configured as code (realm JSON in `infra/keycloak/`). Two realms: `dcs` (customers,
`apps/web`) and `dcs-staff` (DCS staff, `apps/admin`). Login pages are themed with Keycloakify. Org membership and
roles are authoritative in the Control DB, not in Keycloak. MFA for Owner/Admin is enforced by control-api from the
token's `acr`/`amr` claims, with step-up through `acr_values` (see OPEN_QUESTIONS Q5).

## Consequences
- One more stateful service to operate and upgrade.
- Realm changes go through code review.

## Alternatives considered
- Clerk / Auth0: cost and data residency.
- Zitadel: a good alternative, kept as the fallback.
