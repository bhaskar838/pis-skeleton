# ADR-0004: In-house OAuth broker vs Nango self-host
- Status: Accepted
- Date: 2026-11-06
- Spec references: §4.1, §5.5

## Context
API connectors need OAuth flows, token storage and refresh for many providers. Nango self-hosted is under the
Elastic licence and has limited features when self-hosted.

## Decision
Build the **DCS OAuth Broker** on Authlib. Provider configurations are data (`oauth_providers/*.yaml`), not code.
Tokens are stored only as ciphertext via `dcs_vault`. Revisit if the number of OAuth providers exceeds 60.

## Consequences
- Full control over token lifecycle, audit and tenant isolation.
- Provider quirks (refresh rotation, non-standard token responses) are handled per provider in configuration.

## Alternatives considered
- Nango self-hosted: licence and feature limits.
