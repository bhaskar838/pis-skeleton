# ADR-0006: Temporal as the sole orchestrator
- Status: Accepted
- Date: 2026-11-06
- Spec references: §2 P10, §4.1

## Context
Background work is long-running, per tenant, and often waits for humans (mapping review, browser sessions). It must
be resumable and idempotent.

## Decision
All background work is a **Temporal** workflow (self-hosted, Python SDK). Workflow IDs are deterministic:
`wf:<kind>:<tenant>:<natural-key>`. Activities are idempotent. Cron jobs are Temporal Schedules.

## Consequences
- Human-in-the-loop steps use signals.
- Starting a workflow twice with the same ID never duplicates work.
- Temporal is another stateful service (backed by Postgres).

## Alternatives considered
- BullMQ: Node-only, no durable workflows.
- Airflow / Dagster: batch DAGs, weak at per-tenant interactive flows.
