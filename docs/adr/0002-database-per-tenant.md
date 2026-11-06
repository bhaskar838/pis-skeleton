# ADR-0002: Database-per-tenant isolation
- Status: Accepted
- Date: 2026-11-06
- Spec references: §2 P4, §3.5, §8.1, §8.2, §11.2

## Context
DCS-PIS stores the complete business data of each customer. A cross-tenant leak is the highest-impact failure.
Row-level security in shared tables depends on every query being correct.

## Decision
Each tenant gets its own Postgres database `t_<shortid>` with four roles: `_owner` (migrations), `_rw` (workers),
`_ro` (data-api reads) and `_engine_ro` (NOLOGIN template for sandboxed tool runs). `CONNECT` is revoked from
PUBLIC. Role passwords are random and sealed with the tenant DEK. Each tenant also has its own KMS CMK and its own
object-store prefix encrypted with that key. The shared Control DB holds metadata only and uses RLS on `org_id`.

## Consequences
- data-api keeps one connection pool per tenant, keyed by the tenant ID resolved from the session. A guard checks
  `current_database()` when each physical connection is opened and compares it on every checkout.
- Schema migrations must be applied to every tenant DB (`TenantMigrateWorkflow`, canary-first).
- Deprovisioning is a `DROP DATABASE` plus a crypto-shred of the tenant key.
- High tenant counts per cluster need connection monitoring (pgbouncer later).

## Alternatives considered
- Shared tables + RLS: rejected for the data plane (P4).
- Schema-per-tenant: weaker isolation (shared roles and catalog), harder crypto-shred.
