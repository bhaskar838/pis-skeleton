# DCS-PIS EXOSKELETON — MASTER BUILD SPECIFICATION

**Product:** DCS-PIS (Predictive Intelligence System) by Datachondria Systems
**Scope of this document:** The *Exoskeleton*: everything except the Intelligence Engine.
**Audience:** Claude Code (primary builder) and the DCS engineering team
**Document version:** 1.0 · 5 Nov 2026
**Status:** Approved for Phase 0 start
**Repo location:** commit this file as `docs/SPEC.md`. `CLAUDE.md` (§17.11) points to it.

> **The car analogy.** This spec builds a finished car with an empty engine bay. It covers the chassis, body, wheels, dashboard, fuel lines, electricals and the engine mounts, plus a small test motor for checking that the mounts work. The real engine (the Intelligence System: analysis tools, logic and ML models) is built separately by another team. It drops into the engine bay through the **Engine Runtime Interface (ERI)** in §7, and the car is then ready to drive.

---

## TABLE OF CONTENTS

0. [How Claude Must Use This Document](#0-how-claude-must-use-this-document)
1. [Product Context & Scope](#1-product-context--scope)
2. [Non-Negotiable Design Principles](#2-non-negotiable-design-principles)
3. [System Architecture](#3-system-architecture)
4. [Technology Stack & Decisions](#4-technology-stack--decisions)
5. [Floor 1: Data Acquisition Layer](#5-floor-1--data-acquisition-layer)
6. [Floor 2: Transformation & Intelligence Database](#6-floor-2--transformation--intelligence-database)
7. [Floor 3: Engine Bay (Socket, Marketplace, Assignment)](#7-floor-3--engine-bay)
8. [Multi-Tenancy, Security & Compliance](#8-multi-tenancy-security--compliance)
9. [Frontend: Complete Page Inventory (60 pages)](#9-frontend--complete-page-inventory)
10. [Service APIs](#10-service-apis)
11. [Database Schemas](#11-database-schemas)
12. [Repository Structure & Conventions](#12-repository-structure--conventions)
13. [Phased Build Plan (Phases 0–9)](#13-phased-build-plan)
14. [Global Testing Strategy](#14-global-testing-strategy)
15. [Environments, DevOps & Observability](#15-environments-devops--observability)
16. [Risks, Constraints & Open Decisions](#16-risks-constraints--open-decisions)
17. [Appendices: Contracts, Schemas, Templates](#17-appendices)

---

## 0. HOW CLAUDE MUST USE THIS DOCUMENT

### 0.1 Prime directives

1. **Build one phase at a time.** Phases are defined in §13. Never start Phase N+1 until Phase N's **Exit Gate** passes and is recorded in `docs/PROGRESS.md`.
2. **Do not build the Intelligence Engine.** Build only the socket (§7), the reference test tools (§7.7), and the Tool SDK. Any request to put real analytics or ML logic inside the exoskeleton is out of scope; record it in `docs/ENGINE_BACKLOG.md`.
3. **Contracts are law.** The JSON contracts in §17 (Ingestion Manifest, Mapping Spec, Data Readiness Profile, Tool Manifest, ToolRunRequest, InsightResult) are versioned interfaces shared with other teams. Changing one needs an ADR in `docs/adr/` and a version bump. Never make a silent breaking change.
4. **LLMs propose and deterministic code executes.** No LLM call may compute a business figure, transform rows directly, or make a final irreversible decision. LLMs output *specs* (mappings, classifications, recipes). Validated deterministic code then executes those specs. (See §2, P2.)
5. **Tests are part of the feature.** A feature without tests is not done. Every phase states the test suites it needs, and CI must be green.
6. **Ask, don't guess, on contract-level ambiguity.** If the spec is ambiguous about a contract, a security boundary or data retention, stop. Write the question to `docs/OPEN_QUESTIONS.md` and pick the conservative default (less access, less retention, more review) until a human answers.
7. **Never commit secrets.** Use `.env.example` with placeholders. Real credentials come only from the secrets manager.
8. **Keep the tree runnable.** `make dev` must boot the whole system locally at every commit on `main`.

### 0.2 Phase execution protocol (repeat for every phase)

```
STEP 1  READ      Read §13.<phase> fully + every section it references.
STEP 2  PLAN      Write docs/phases/PHASE_<N>_PLAN.md:
                  - task breakdown (≤1 day each), files to create/modify,
                  - migrations, contracts touched, test list, risks.
STEP 3  BUILD     Implement in small commits on branch phase-<N>/<topic>.
                  Conventional commits: feat:, fix:, test:, chore:, docs:.
STEP 4  TEST      Unit → integration → contract → e2e → security → perf
                  (as required by the phase). Coverage thresholds in §14.
STEP 5  DEMO      Run the phase "Demo Script" end-to-end on a clean `make reset && make dev`.
STEP 6  GATE      Fill docs/phases/PHASE_<N>_GATE.md using the template in §17.10.
                  Every Acceptance Criterion must be ✅ with evidence
                  (test name, screenshot path, or log excerpt).
STEP 7  RECORD    Update docs/PROGRESS.md (phase status, date, known issues,
                  deferred items). Tag release v0.<N>.0.
```

### 0.3 Global Definition of Done (applies to every task)

- [ ] Code compiles with zero lint and type errors (ruff + mypy --strict for Python; eslint + tsc --noEmit for TS)
- [ ] Unit tests written and passing; coverage of touched modules at or above threshold (§14.3)
- [ ] Integration test for every new endpoint, workflow and DB migration
- [ ] Tenant isolation test for every new data-access path (§14.6)
- [ ] Audit event emitted for every state-changing user or staff action
- [ ] OpenAPI spec regenerated; TS client regenerated (`make codegen`)
- [ ] Every new UI page has loading, empty, error and permission-denied states
- [ ] Docs updated (README of the module + any affected section of `docs/`)
- [ ] No TODO without a linked issue ID

### 0.4 How to read the floors

The founder's original numbering and this document's numbering differ, because this document follows the direction the data flows:

| Founder's part | Name in this spec | Built where |
|---|---|---|
| Part 3: Data acquisition from business owners | **Floor 1 — Acquire** | Exoskeleton (this spec) |
| Part 2: Data transformation & database creation | **Floor 2 — Shape** | Exoskeleton (this spec) |
| Part 1: Complete analysis system | **Floor 3 — Engine** | **Separate team.** The exoskeleton builds only the *Engine Bay*: socket, registry, marketplace, assignment, runner, results UI |

---

## 1. PRODUCT CONTEXT & SCOPE

### 1.1 What DCS-PIS is

DCS-PIS is an intelligent system that collects **all** of a business's data, whatever form it is in and wherever it lives (CRM, accounting, ads, sales, payments, HR, support, spreadsheets, legacy desktop software). It reshapes that data into one **Intelligence Database** with a canonical structure, works out which analyses, tools and models from its library apply to *that particular business*, and runs them to deliver insights. It answers five questions: *what happened, why it happened, what is likely to happen, what to do, and whether AI can do it.*

### 1.2 The core problem the exoskeleton solves

Before onboarding, **neither DCS nor the software knows**:
- which software or services the business uses,
- what form its data is in (API, database, file, a legacy desktop app, or paper exported to Excel),
- which analyses are relevant to it.

So the exoskeleton must:
1. **Acquire unknown data** through whatever channel works (Floor 1).
2. **Make it known** by profiling, classifying and mapping it into a canonical model with LLM help and human review (Floor 2).
3. **Describe what is now known** in a machine-readable *Data Readiness Profile* (Floor 2 → 3).
4. **Assign tools** from the library like a marketplace: **Primary** tools (included in the subscription) and **Secondary** tools (paid add-ons). Then run them in an isolated, secure environment and display the results (Floor 3 shell).

### 1.3 In scope (exoskeleton)

| Area | Included |
|---|---|
| Identity & tenancy | Orgs, users, roles, MFA, tenant provisioning, DB-per-tenant |
| Floor 1 | API connectors, OAuth broker, credential vault, DB connectors, file ingestion (all formats), assisted remote browser extraction, on-prem Bridge Agent, legacy adapters, schedules, raw zone |
| Floor 2 | Profiling, semantic typing, Canonical Business Model, LLM-assisted mapping, mapping review, deterministic transform compiler, entity resolution, data quality, business graph, event catalogue, lineage, Tenant Pipeline Spec, Data Readiness Profile |
| Floor 3 shell | Tool Registry, Tool Manifest, Assessment & Assignment Engine, Marketplace UI, entitlement checks, sandboxed Tool Runner, Results store, Insight rendering, Tool SDK, reference test tools |
| Commercial | Plans, subscriptions, add-ons, invoices (Stripe + Razorpay) |
| Ops | Admin console, observability, audit, compliance (export/erasure/retention) |

### 1.4 Out of scope (do NOT build)

- Real analysis tools, statistical logic, ML/forecasting/causal models (that is the Engine)
- Executing actions in third-party systems (writing back to CRMs, sending messages). The exoskeleton stores *Action Proposals* only. Execution belongs to future agents and DCS VoiceOS.
- Public marketing website (datachondria.com already exists)
- Mobile native apps (the web app must be responsive)

### 1.5 Glossary

| Term | Meaning |
|---|---|
| **Tenant** | One customer business (org). Gets its own Postgres database and its own encryption key. |
| **Source** | One connected system of a tenant (e.g., their HubSpot, their Tally, an uploaded folder). |
| **Channel** | *How* a source is acquired: `API`, `DATABASE`, `FILE`, `BROWSER`, `BRIDGE`, `CONCIERGE`. |
| **Connector** | Reusable code that knows how to read a specific system (e.g., `hubspot`, `postgres`, `tally`). |
| **Stream** | One logical collection inside a source (e.g., HubSpot `contacts`, Tally `vouchers`). |
| **Ingestion Batch** | One immutable unit of acquired data plus its manifest (§17.1). |
| **Raw Dataset** | A registered stream or file-sheet in the raw zone, ready to be profiled. |
| **CBM** | Canonical Business Model: the fixed, versioned target schema of the Intelligence DB (§6.3). |
| **Mapping Spec** | Declarative, versioned description of how a Raw Dataset becomes CBM rows (§17.2). |
| **TPS** | Tenant Pipeline Spec: the complete versioned pipeline definition for one tenant (§6.5). |
| **DRP** | Data Readiness Profile: a machine summary of what data a tenant has, its quality and history depth (§6.11, §17.3). |
| **Tool** | An engine unit (analysis, logic or model) packaged as an OCI image with a Tool Manifest (§17.4). |
| **Primary tool** | A tool assigned as core for this business, included in the subscription. |
| **Secondary tool** | A tool that is relevant but not core, offered as a paid add-on. |
| **Locked tool** | A tool that is relevant but whose data requirements are not yet met ("connect X to unlock"). |
| **ERI** | Engine Runtime Interface: the socket contract between the exoskeleton and the Engine. |
| **InsightResult** | The standard output envelope every tool must return (§17.6). |
| **Recipe** | A deterministic browser-automation script that exports data from a specific vendor UI. |
| **Bridge Agent** | A small DCS program installed on a client's machine or server to reach local and legacy data. |

---

## 2. NON-NEGOTIABLE DESIGN PRINCIPLES

| # | Principle | What it means in code |
|---|---|---|
| P1 | **Unknown in, known out** | Floor 1 never assumes a schema. It stores data *as received* plus a manifest. Meaning is added only in Floor 2. |
| P2 | **LLM proposes, deterministic code executes** | LLM outputs (mappings, classifications, browser steps) are typed specs validated by Pydantic or JSON Schema. A compiler turns them into SQL or Python that runs without the LLM. Business numbers are never produced by a model. |
| P3 | **Raw is immutable and replayable** | Landing and Bronze objects are write-once (S3 Object Lock in prod). All of Silver, Gold and Graph can be rebuilt from Raw plus the TPS version. |
| P4 | **Database-level tenant isolation** | One Postgres database per tenant, separate DB roles, a per-tenant KMS key, and per-tenant object-store prefixes encrypted with that key. No shared tenant tables anywhere in the data plane. |
| P5 | **Every tenant pipeline is a versioned artifact** | The TPS is stored as JSON with semver and a content hash. Every Gold row records the `tps_version` and `batch_id` that produced it. |
| P6 | **The Engine is a plug** | The exoskeleton depends only on the ERI contracts. Swapping the reference tools for real tools needs zero exoskeleton code changes. |
| P7 | **Human-in-the-loop by confidence** | Every automated decision carries a confidence score. Low-confidence results go to a review queue for the customer first, then DCS concierge. |
| P8 | **Least privilege and explicit consent** | Read-only access to source systems by default. Consent is captured per source and per processing purpose (including LLM processing). Browser sessions never store passwords. |
| P9 | **Everything audited** | Append-only, hash-chained audit log for every user, staff and system action that changes state or touches credentials. |
| P10 | **Idempotent, resumable work** | Every job is a Temporal workflow with deterministic IDs. Re-running a batch never duplicates data (upsert on `(source_id, stream, source_pk)`). |
| P11 | **Prefer official export paths** | API first, then the vendor's own export feature, then direct DB access, then UI extraction. Choose the most stable, sanctioned path available. |
| P12 | **Fail visible** | No silent drops. Every rejected record goes to quarantine with a reason, and the UI shows it. |

---

## 3. SYSTEM ARCHITECTURE

### 3.1 High-level view

```
                         ┌───────────────────────────────────────────────┐
                         │                CUSTOMER BROWSER               │
                         │  Next.js Web App (app.*)   Admin Console (admin.*)│
                         └───────────────┬───────────────────────────────┘
                                         │ HTTPS (OIDC session / JWT)
                         ┌───────────────▼───────────────┐
                         │   EDGE: Traefik/nginx + WAF   │
                         └──┬─────────────┬───────────┬──┘
                            │             │           │ WebSocket (browser stream, live status)
               ┌────────────▼──┐  ┌───────▼──────┐ ┌──▼──────────────┐
CONTROL PLANE  │  control-api  │  │  data-api    │ │ realtime-gw     │
               │  (FastAPI)    │  │  (FastAPI)   │ │ (WS fan-out)    │
               └──┬─────┬──────┘  └──┬───────────┘ └──┬──────────────┘
                  │     │            │                │
        ┌─────────▼┐ ┌──▼─────────┐  │    ┌───────────▼────────────┐
        │Control DB│ │ Keycloak   │  │    │ Redis (cache, pubsub,  │
        │(Postgres)│ │ (OIDC/MFA) │  │    │  rate limits, locks)   │
        └──────────┘ └────────────┘  │    └────────────────────────┘
                  │                  │
          ┌───────▼──────────────────▼──────────────────────────────┐
          │                 TEMPORAL (orchestration)                │
          └──┬──────────┬──────────┬──────────┬──────────┬──────────┘
DATA PLANE   │          │          │          │          │
   ┌─────────▼──┐ ┌─────▼────┐ ┌───▼──────┐ ┌─▼────────┐ ┌▼───────────┐
   │ acquire-   │ │ parse-   │ │ browser- │ │ shape-   │ │ engine-bay │
   │ worker     │ │ worker   │ │ worker   │ │ worker   │ │ worker     │
   │ (API, DB,  │ │ (files,  │ │ (remote  │ │ (profile,│ │ (assess,   │
   │  bridge)   │ │  OCR)    │ │ Chromium)│ │ map, ER, │ │  run tools)│
   └─────┬──────┘ └────┬─────┘ └────┬─────┘ │ DQ,graph)│ └──┬─────────┘
         │             │            │       └──┬───────┘    │
   ┌─────▼─────────────▼────────────▼──────────▼────────────▼─────────┐
   │  OBJECT STORE (S3/MinIO)        TENANT DBs (Postgres, 1 per tenant)│
   │  landing/ bronze/ (per-tenant    raw_registry · stg_* · core · graph│
   │  prefix, SSE-KMS tenant key)     events · engine_api_v1 · results   │
   └──────────────────────────────────────────────────────────────────┘
         ▲                                                   │
         │ outbound-only mTLS                                │ read-only views
   ┌─────┴─────────┐   ┌───────────────┐            ┌────────▼─────────────┐
   │ Bridge Relay  │   │ Model Gateway │            │ TOOL SANDBOX         │
   │ (gRPC/WS)     │   │ (LLM access,  │            │ (gVisor K8s Jobs,    │
   └─────▲─────────┘   │  PII masking) │            │  no egress) ◄─ ENGINE│
         │             └───────────────┘            │  TOOLS PLUG IN HERE  │
   ┌─────┴──────────────┐                           └──────────────────────┘
   │ CLIENT PREMISES    │
   │ DCS Bridge Agent   │──► Tally :9000, MS Access, DBF, local SQL, folders
   └────────────────────┘
```

### 3.2 The three planes

| Plane | Responsibility | Components |
|---|---|---|
| **Control plane** | Identity, orgs, billing, catalog, registry, configuration, orchestration state | web, admin, control-api, Keycloak, Control DB, Temporal, Redis |
| **Data plane** | Moving and shaping tenant data; it never mixes tenants | acquire/parse/browser/shape workers, data-api, Object Store, Tenant DBs, Bridge Relay, Model Gateway |
| **Engine plane** | Executing tools in isolation | engine-bay-worker (runner), Tool Sandbox, Tool Registry (images in a private OCI registry) |

### 3.3 Service catalogue

| Service | Lang | Responsibility | Scales by |
|---|---|---|---|
| `web` | TS / Next.js | Customer app (47 pages) | Stateless replicas |
| `admin` | TS / Next.js | DCS staff console (13 pages) | Stateless |
| `control-api` | Python / FastAPI | Orgs, users, RBAC, sources config, catalog, registry, plans, entitlements, audit | Stateless |
| `data-api` | Python / FastAPI | Tenant-scoped reads and writes: dataset previews, profiles, mapping workbench, ER review, DQ, graph, results | Stateless; per-request tenant DB pool |
| `realtime-gw` | Python (FastAPI WS) or Node | WebSocket fan-out of job status and browser stream relay | Connections |
| `acquire-worker` | Python | API connector runs (dlt-based SDK), DB snapshot and incremental pulls, Bridge job dispatch | Temporal task queue `acquire` |
| `parse-worker` | Python | File detection, parsing, OCR, archive expansion, legacy file restoration | Queue `parse` (CPU) |
| `browser-worker` | Python + Playwright | Ephemeral Chromium sessions, CDP screencast, recipes, AI navigator | Queue `browser`; one pod per session |
| `shape-worker` | Python | Profiling, classification, LLM mapping proposals, transform compile and execute, ER, DQ, graph build, events, DRP | Queue `shape` |
| `engine-bay-worker` | Python | Assessment and assignment, tool-run orchestration, result validation | Queue `engine` |
| `model-gateway` | Python | Provider-agnostic LLM calls, PII masking, prompt registry, cost metering, caching | Stateless |
| `bridge-relay` | Go | Terminates Bridge Agent mTLS tunnels and routes jobs to agents | Connections |
| `bridge-agent` | Go | Runs on client premises; executes local extraction jobs | n/a (client side) |
| `scheduler` | Temporal Schedules | Cron syncs, DRP refresh, re-assessment | n/a |

### 3.4 End-to-end data flow (happy path)

```
 1. Owner signs up → tenant provisioned (DB, KMS key, buckets, roles)          [Phase 0]
 2. Onboarding: business profile + "which tools do you use?"                  [P1/P4]
 3. Acquisition Router picks a channel per tool → Acquisition Plan            [P4]
 4. Owner connects sources (OAuth / DB creds / files / browser / bridge)      [P1,P4–P6]
 5. Acquire → IngestionBatch (landing → bronze Parquet + manifest)            [P1]
 6. Register Raw Datasets → Profile (stats, semantic types, PII, keys)        [P1/P2]
 7. Classify dataset → CBM entity; propose field mappings (template or LLM)   [P2]
 8. Auto-accept high confidence; queue the rest → owner reviews in Workbench  [P2]
 9. Compile Mapping Spec → SQL → load stg_* → core (Gold)                     [P2]
10. Entity resolution → golden records; DQ rules; graph edges; events         [P7]
11. Build DRP → Assessment & Assignment → Toolkit (Primary/Secondary/Locked)  [P3]
12. Owner activates the toolkit (subscription + add-ons)                      [P3/P8]
13. Tool Runner executes tools in sandbox → InsightResults → UI               [P3]
14. Schedules keep sources fresh; changes propagate; DRP and assignment re-run [P4+]
```

### 3.5 Storage layout

| Store | Content | Isolation |
|---|---|---|
| **Control DB** (`dcs_control`) | Orgs, users (mirror of Keycloak IDs), memberships, sources config (no secrets), connector catalog, tool registry, plans, subscriptions, entitlements, audit log, workflow index | Shared, row-level `org_id` + Postgres RLS |
| **Tenant DB** (`t_<tenant_short_id>`) | All tenant business data across schemas (§11.2) | Separate database and roles per tenant; enterprise tier can get a dedicated cluster |
| **Object store** | `s3://dcs-data-<region>/tenants/<tenant_id>/{landing,bronze,exports,browser-artifacts}/…` | Prefix-scoped IAM plus SSE-KMS with the tenant CMK; Object Lock (compliance mode) on landing/bronze |
| **Secrets** | OAuth tokens, DB passwords, API keys, bridge certs | Envelope encryption: data key per tenant, wrapped by KMS CMK; stored in Control DB `credential` table as ciphertext only |
| **Redis** | Caches, rate-limit buckets, pub/sub for status, distributed locks | Keys prefixed `t:<tenant_id>:` |
| **OCI registry** | Tool images, connector images, worker images | Signed (cosign); runner verifies digest and signature |

---

## 4. TECHNOLOGY STACK & DECISIONS

### 4.1 Stack table

| Layer | Choice | Why | Rejected alternatives |
|---|---|---|---|
| Frontend | **Next.js (App Router, latest stable ≥14) + TypeScript + Tailwind + shadcn/ui** | Team's existing stack; server components; fast to build | Remix, SvelteKit |
| UI data | TanStack Query, TanStack Table (virtualized grids), react-hook-form + zod | Large data previews; typed forms | Redux |
| Visual editors | **React Flow** (lineage, mapping, graph explorer, pipeline) | Mature node-graph UI | Cytoscape (kept for very large graphs) |
| Charts (InsightResult render) | **Vega-Lite** renderer (react-vega) + ECharts fallback | Tools emit declarative chart specs; the UI renders them safely without running tool code | Tools shipping their own JS (unsafe) |
| Backend APIs | **Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2 (async) + Alembic** | The data plane is Python-heavy (dlt, DuckDB, Polars, Playwright, Splink, OCR). One backend language keeps context small for Claude and the team. | NestJS + Prisma for control (Prisma handles dynamic per-tenant DBs and schemas poorly) |
| API typing | OpenAPI → `openapi-typescript` + `openapi-fetch` generated client | End-to-end types | tRPC (TS-only) |
| Orchestration | **Temporal** (self-hosted; Python SDK) | Long-running, resumable, human-in-the-loop workflows (signals for review approvals), retries, schedules, full visibility | BullMQ (Node-only, no durable workflows); Airflow/Dagster (batch DAGs, weak at per-tenant interactive flows) |
| Control & tenant DB | **PostgreSQL 16+** with `pgcrypto`, `pg_trgm`, `pgvector` | One engine for relational, JSONB extension fields, full-text catalog search, embeddings for mapping memory | MySQL; a separate graph DB (Neo4j) for v1, which adds ops cost |
| Graph | Postgres `graph.nodes` / `graph.edges` tables plus recursive CTEs; optional **Apache AGE** later | Enough for v1 traversals | Neo4j (possible later, behind the same contract) |
| Object store | **S3** (prod) / **MinIO** (dev) | Standard; Object Lock | — |
| Columnar raw | **Parquet** (via PyArrow) in Bronze | Typed, compressed, replayable | Raw CSV only |
| Local compute | **DuckDB + Polars** | Fast profiling and transforms on Parquet without a warehouse | Spark (overkill for v1) |
| Connector runtime | **dlt** (Apache-2.0) wrapped by the DCS Connector SDK; REST API source for long-tail APIs | Permissive licence, schema inference, incremental state, pagination helpers | Airbyte Core (ELv2: cannot be offered as a managed service; legal risk for our model). See ADR-0003. |
| Airbyte compatibility | Optional adapter that runs Airbyte *protocol* (MIT) source images, **only** where that connector's own `metadata.yaml` licence allows it | Taps into the long tail without depending on Airbyte Core | — |
| OAuth & tokens | **DCS OAuth Broker** (built in-house on Authlib) + Credential Vault | Full control, no ELv2 dependency. Provider configs are data (YAML), not code. | Nango self-hosted (Elastic licence, limited features when self-hosted): evaluate in ADR-0004 |
| Secrets/KMS | **AWS KMS** (prod) / local AES key service (dev) | Per-tenant CMK, envelope encryption | HashiCorp Vault / OpenBao (an option for on-prem enterprise) |
| Identity | **Keycloak** (OIDC; orgs; MFA TOTP/WebAuthn; enterprise SSO later) with Keycloakify-themed login pages | Mature, self-hosted, supports SAML/OIDC federation for enterprise clients | Clerk/Auth0 (cost, data residency); Zitadel (good alternative, ADR-0005) |
| Remote browser | **Playwright + Chromium** in ephemeral containers, **CDP screencast** streamed over WebSocket to a canvas, with input relay | Lightweight; full control over downloads, network capture and isolation | Hosted browser services (data leaves our boundary); VNC (heavier, worse UX) |
| AI navigator | Vision-capable LLM via Model Gateway + Playwright actions | Handles unknown vendor UIs with human approval | — |
| Bridge Agent | **Go** single static binary (Windows service / systemd), gRPC over mTLS, outbound-only | Small footprint, easy install on old Windows PCs, no runtime needed | .NET (Windows-only), Python (heavy install) |
| File parsing | python-magic, charset-normalizer, openpyxl/calamine (`python-calamine`), xlrd (xls), pyreadstat, pyarrow, fastavro, lxml, `dbfread`, `mdbtools` (CLI), `pdfplumber`, **Docling** (layout and tables), Tesseract OCR, `ofxparse`, `mailbox`, `extract-msg`, `libpst` (readpst), `vobject`, `icalendar`, `py7zr`, `rarfile` | Covers modern and legacy formats (§5.7) | — |
| Entity resolution | **Splink** (probabilistic record linkage on DuckDB) | Scales; explainable match weights | Dedupe.io |
| Data quality | Pandera schemas + DCS rule engine (SQL assertions) | Lightweight, Python-native | Great Expectations (heavier) |
| Lineage | **OpenLineage** events emitted by workers, stored in Control DB; rendered in React Flow | Open standard | — |
| LLM providers | Through **Model Gateway**: Anthropic Claude (default for mapping quality), Groq (fast, cheap classification), OpenAI-compatible; **self-hosted vLLM** (open-weight model) for the privacy tier | Provider-agnostic, as stated on the website | Direct provider SDK calls in services (forbidden) |
| Structured LLM output | Pydantic models + JSON-schema-constrained output + automatic retry on validation failure | Enforces P2 | Free-text parsing |
| Tool sandbox | **Kubernetes Jobs with gVisor (`runsc`) RuntimeClass**, NetworkPolicy deny-all egress, read-only rootfs, CPU/mem/time limits. Dev: `docker run --network none --read-only`. | Strong isolation for third-party or engine code | Firecracker (later, for the enterprise tier) |
| Billing | **Stripe** (international) + **Razorpay** (India; GST invoices) behind a `BillingProvider` interface | Matches markets (India + EU/UK + global) | — |
| Email | AWS SES (prod) / Mailpit (dev) | — | — |
| Observability | OpenTelemetry SDKs → Grafana stack (Prometheus, Loki, Tempo) + Sentry | Traces across the API → Temporal → worker chain | — |
| Infra | Docker Compose (dev); **Kubernetes** (EKS or k3s on EC2) + Helm + Terraform (prod); GitHub Actions CI | Team knows EC2/nginx; K8s is needed for sandboxed Jobs and per-session browser pods | — |
| Regions | `ap-south-1` (Mumbai) default; `eu-west-2` (London) for UK/EU tenants; region pinned at tenant creation | Data residency (DPDP / UK-GDPR / GDPR) | — |
| Monorepo | **pnpm + Turborepo** (TS) and **uv workspaces** (Python); `Makefile` as the single entry point | One repo; fast CI with caching | Polyrepo |

### 4.2 Architecture Decision Records to create in Phase 0

| ADR | Title | Default decision |
|---|---|---|
| ADR-0001 | Single backend language (Python) | Accepted |
| ADR-0002 | Database-per-tenant isolation | Accepted |
| ADR-0003 | Connector runtime = dlt; Airbyte only via MIT protocol adapter, per-connector licence check | Accepted |
| ADR-0004 | In-house OAuth broker vs Nango self-host | In-house; revisit if >60 OAuth providers |
| ADR-0005 | Keycloak as IdP | Accepted; Zitadel as fallback |
| ADR-0006 | Temporal as the sole orchestrator | Accepted |
| ADR-0007 | LLM-proposes / compiler-executes mapping architecture | Accepted |
| ADR-0008 | Tool sandbox = gVisor K8s Jobs | Accepted |
| ADR-0009 | Remote browser via CDP screencast (no VNC) | Accepted |
| ADR-0010 | Bridge Agent in Go, outbound-only mTLS | Accepted |

---

## 5. FLOOR 1 — DATA ACQUISITION LAYER

**Goal:** Get *all* of a tenant's data out of *any* system it lives in, with the owner's consent, into the immutable Raw Zone, without assuming any schema.

### 5.1 The six acquisition channels

| Channel | Code | When used | Examples | Built in |
|---|---|---|---|---|
| **A. Native API** | `API` | Vendor has a documented API exposing the data | HubSpot, Shopify, Razorpay, Zoho, Meta Ads, QuickBooks Online | Phase 4 |
| **B. Direct database** | `DATABASE` | Business runs its own DB (self-hosted app, custom software) | Postgres, MySQL, MSSQL, Oracle, MongoDB | Phase 5 |
| **C. Files** | `FILE` | Exports, spreadsheets, dumps, documents | xlsx, csv, .db, .sql, .bak, .mdb, .dbf, PDF, Tally XML | Phase 1 |
| **D. Assisted browser** | `BROWSER` | SaaS with no usable API, or an API that is gated or paywalled, but the owner can log in through the web | Niche vertical SaaS, regional POS/CRM portals, bank portals with export | Phase 6 |
| **E. Bridge Agent** | `BRIDGE` | Data sits on the client's premises behind a firewall: desktop or legacy software, LAN databases, shared folders | Tally Prime, Busy, Marg, MS Access, FoxPro, on-prem SQL Server, AS/400 via ODBC | Phase 5 |
| **F. Concierge** | `CONCIERGE` | Nothing above works (paper, a dead vendor, exotic mainframe) | DCS staff run a guided extraction or data-entry project | Phase 6 (workflow only) |

**Priority order (P11):** `API` → vendor export through `BROWSER` recipe → `DATABASE` / `BRIDGE` → `FILE` (manual export) → `BROWSER` AI navigator → `CONCIERGE`.

### 5.2 Acquisition Router

During onboarding the owner lists the tools they use (catalog search, plus free text for unlisted tools). For each one, the **Acquisition Router** produces an **Acquisition Plan Item**:

```
input:  tool name (catalog match or free text), deployment hint (cloud/desktop/self-hosted),
        tenant region, plan tier
logic:
  1. catalog match? ──no──► fuzzy match (pg_trgm) + LLM normalization ("Zoho Bks" → zoho_books)
                             still unknown → create CatalogCandidate (admin triage) and
                             offer: FILE export guide | BROWSER (AI navigator) | CONCIERGE
  2. catalog entry has connector with coverage FULL/PARTIAL and auth supported?
        yes → channel API (show coverage gaps; if PARTIAL also schedule complementary
              BROWSER recipe or FILE export for the missing objects)
  3. entry.deployment == desktop/on-prem → channel BRIDGE (if supported adapter) else FILE guide
  4. entry has published browser recipe → channel BROWSER (recipe mode)
  5. else → FILE (show vendor-specific export guide if present) + BROWSER (AI navigator) option
output: AcquisitionPlanItem {tool, channel, connector_id?, recipe_id?, guide_id?,
        coverage, missing_objects[], effort: LOW|MED|HIGH, status}
```

The plan is shown on page **O-03** as a checklist and stored in the Control DB (`acquisition_plan_item`).

### 5.3 Connector Catalog (registry)

Every known system is stored in `connector_catalog`, which is seeded from `catalog/seed/*.yaml`:

```yaml
id: hubspot
display_name: HubSpot
vendor_url: https://www.hubspot.com
categories: [crm, marketing]
deployment: cloud            # cloud | desktop | self_hosted | hybrid
regions_common: [global, in, eu, us]
channels:
  api:
    connector: hubspot        # connector package id
    auth: [oauth2]
    coverage: FULL            # FULL | PARTIAL | EVENTS_ONLY | EXPORT_ONLY | NONE
    objects: [contacts, companies, deals, pipelines, owners, line_items, products, quotes,
              tickets, engagements, emails, calls, meetings, notes, tasks, forms, campaigns]
    gaps: []                  # objects NOT reachable via API
    rate_limits: "per-app daily + 10s burst; respect headers"
    plan_requirements: null   # e.g. "Salesforce: API access needs Enterprise or add-on"
    incremental: true
    webhooks: true
  browser:
    recipe: null
  file:
    export_guide: guides/hubspot_export.md
cbm_template: templates/hubspot_v1.yaml   # pre-built mapping → no LLM needed
verified_at: null              # set when Phase-4 research spike verifies
notes: ""
```

**Coverage definitions**

| Coverage | Meaning |
|---|---|
| `FULL` | Every business-relevant object the owner can see in the UI is retrievable, with history |
| `PARTIAL` | Core objects available; some objects or fields missing, or history limited |
| `EVENTS_ONLY` | API gives only events from the moment of connection onwards (no history backfill) |
| `EXPORT_ONLY` | No data API; the product has a built-in export (CSV, Excel) usable via recipe or file |
| `NONE` | No API and no export → Bridge, AI navigator, or Concierge |

#### 5.3.1 Seed catalog: systems to research and verify in Phase 4

> ⚠️ **Claude:** the coverage values below are *initial hypotheses*. Phase 4 includes a **Catalog Research Spike** (§13, P4-T1). For every entry, verify against the vendor's current API docs: auth method, objects, history limits, plan or edition gates, rate limits. Record the evidence URL in `verified_source`. Never mark `FULL` without evidence.

| Category | Systems (connector id) | Expected coverage / known gotchas |
|---|---|---|
| **CRM** | hubspot, salesforce, zoho_crm, pipedrive, freshsales (Freshworks CRM), leadsquared, microsoft_dynamics_365 (Dataverse), zendesk_sell, close, copper, bitrix24, kylas, odoo_crm | Salesforce: API needs Enterprise, Unlimited or Performance edition, or the API add-on for Professional. Use the Bulk API 2.0 for big objects. |
| **Accounting / ERP** | quickbooks_online, xero, zoho_books, freshbooks, sage_business_cloud, netsuite (SuiteTalk REST/SuiteQL), sap_business_one (Service Layer), sap_s4hana (OData), odoo (XML-RPC/JSON-RPC: FULL), microsoft_business_central, tally_prime (**BRIDGE**: XML over HTTP :9000 / ODBC), busy (**BRIDGE/FILE**), marg_erp (**BRIDGE/FILE**), vyapar (**FILE/BROWSER**), quickbooks_desktop (**BRIDGE**: QBXML / IIF export) | Tally has no cloud REST API. It needs a running TallyPrime instance with the HTTP/ODBC server enabled, so it is BRIDGE. |
| **Payments** | stripe, razorpay, razorpayx, paypal, cashfree, phonepe_business (verify), paytm_business (verify), square, adyen, payu | Razorpay: payments, orders, refunds, settlements, invoices, subscriptions over REST with key auth |
| **E-commerce / marketplaces** | shopify (GraphQL Admin: FULL), woocommerce (REST), magento_adobe_commerce, bigcommerce, wix_stores, squarespace_commerce, amazon_seller (SP-API: developer registration and approval required), flipkart_seller (restricted access: verify), meesho (verify), etsy, dukaan (verify) | Marketplaces often gate API access. Fall back to a BROWSER recipe for the seller-portal report exports. |
| **Advertising** | meta_ads (Marketing API), google_ads (developer token required), linkedin_ads (partner program approval), microsoft_ads, tiktok_ads, snapchat_ads, x_ads, amazon_ads, criteo, taboola | Ads APIs return aggregated performance reports, so store them at daily grain per ad. |
| **Web / product analytics** | google_analytics_4 (Data API = aggregated reports; raw events only via the BigQuery export), google_search_console, mixpanel (raw export API), amplitude (export API), hotjar (limited), plausible, matomo (self-hosted DB or API), youtube_analytics | GA4: say clearly in the UI that it is aggregated. Offer the BigQuery connector for raw events. |
| **Marketing / email / messaging** | mailchimp, klaviyo, brevo (sendinblue), activecampaign, sendgrid, moengage, clevertap, webengage, whatsapp_business_cloud (**EVENTS_ONLY**: no message-history retrieval API; capture via webhooks from connection time), interakt, wati, gupshup, aisensy (verify each) | WhatsApp history before connection → FILE (chat export) or the BSP's export |
| **Support / helpdesk** | zendesk, freshdesk, intercom, zoho_desk, hubspot_service, help_scout, gorgias, jira_service_management | Generally FULL |
| **HR / payroll** | keka (verify API scope), zoho_people, greythr, darwinbox (verify), razorpay_payroll (verify), bamboohr, gusto, deel, rippling, personio, workday (enterprise; verify) | HR data is PII-heavy. Default to aggregated or pseudonymized ingestion (see §8.6). |
| **Project / work mgmt** | jira, asana, clickup, monday, trello, notion, linear, basecamp, airtable | Generally FULL |
| **Productivity / storage** | google_sheets, google_drive (file discovery → FILE pipeline), microsoft_excel_online, onedrive, sharepoint, dropbox, box | Drive and OneDrive feed the File pipeline (Channel C) |
| **Communication / telephony** | slack, microsoft_teams (Graph), exotel, knowlarity, twilio, ozonetel, gmail (Graph/Gmail API: metadata-first), outlook | Email bodies are off by default (privacy). Metadata and threads only, unless the owner opts in. |
| **POS / hospitality / retail** | petpooja (partner API: verify), posist (Restroworks), lightspeed, square_pos, toast, shopify_pos, gofrugal (verify), loyverse | Often BROWSER/FILE in India |
| **Gym / clinic / vertical SaaS** | mindbody, glofox, zenoti, practo (verify), gymbrain (DCS-internal), fitness_force (verify), wodify | Vertical SaaS often EXPORT_ONLY → recipes |
| **Logistics** | shiprocket, delhivery, shipway, easypost, aftership | Generally PARTIAL |
| **Banking / finance data** | Account Aggregator (India AA framework, via a licensed FIU partner: Phase 9+, legal review), bank statement files (PDF/CSV/OFX) via FILE | Never scrape netbanking. Use statements as files, or AA consent through a licensed partner. |
| **Data warehouses (if the client has one)** | bigquery, snowflake, redshift, databricks_sql, clickhouse | Channel DATABASE (warehouse adapters) |
| **Databases** | postgres, mysql, mariadb, mssql, oracle, sqlite (file), mongodb, db2 / ibm_i (ODBC/JDBC jt400), firebird, sybase_ase, informix (ODBC) | Channel DATABASE or BRIDGE |

Target for the end of Phase 4: **≥ 25 production API connectors** (listed in §13 P4) and **≥ 150 catalog entries** with a researched coverage value. Everything else routes to the other channels.

### 5.4 DCS Connector SDK (Channel A & B)

Package: `packages/py/dcs_connector_sdk`. Each connector is a Python package under `connectors/<id>/`.

```python
class Connector(Protocol):
    id: str
    version: str                          # semver
    def spec(self) -> ConnectorSpec: ...  # JSON Schema of config + auth type(s)
    def check(self, cfg: ResolvedConfig) -> CheckResult: ...        # test connection, scopes
    def discover(self, cfg: ResolvedConfig) -> list[StreamDescriptor]: ...
    def read(self, cfg: ResolvedConfig, streams: list[StreamSelection],
             state: SyncState) -> Iterator[RecordBatch | StateCheckpoint | LogEvent]: ...
```

- **StreamDescriptor:** name, primary key(s), cursor field(s), supports_incremental, json_schema (best effort), estimated_rows.
- **Implementation:** dlt `@dlt.source` / `@dlt.resource` underneath; long-tail REST APIs use dlt's declarative REST API source config (YAML) and need no Python.
- **Output:** the SDK writes `RecordBatch` as Parquet to `bronze/<source_id>/<stream>/batch=<batch_id>/part-*.parquet`. It also writes the raw JSON pages to `landing/…/*.jsonl.zst`, so raw bytes are always replayable. Finally it writes the **Ingestion Manifest** (§17.1).
- **State:** cursors are checkpointed through Temporal activity heartbeats plus `sync_state` (Control DB) after every committed batch, so a resumed sync never re-reads committed pages.
- **Rate limits:** a token bucket in Redis per `(connector, tenant, credential)`; the SDK honours `Retry-After` and backs off exponentially with jitter.
- **Backfill vs incremental:** the first run is a full historical backfill (configurable look-back; default all), followed by incremental runs on the cursor. A weekly full-reconcile job catches hard deletes where the API exposes them.
- **Webhooks:** `control-api /hooks/{connector}/{source_id}` verifies the signature, enqueues a micro-batch and treats it like a normal batch.
- **Testing:** every connector ships VCR cassettes (recorded HTTP with secrets scrubbed) and a contract test suite generated from `spec()` (§14.4).

### 5.5 OAuth Broker & Credential Vault

- Provider configs live in `oauth_providers/*.yaml` (auth URL, token URL, scopes per object, PKCE support, refresh semantics, token lifetime).
- Flow: UI → `GET /oauth/{provider}/start?source_id` → state (signed, 10-min TTL, bound to the user session) → vendor consent → `/oauth/callback` → token exchange → **Vault.store(tenant_id, source_id, secret)**.
- **Vault:** each tenant has a Data Encryption Key (DEK). The DEK is wrapped by the tenant's KMS CMK and cached in memory for ≤5 min. Secrets are AES-256-GCM encrypted with `aad = tenant_id|source_id|kind`. Only `acquire-worker` and `bridge-relay` hold the IAM permission to decrypt.
- Token refresh runs as a scheduled workflow 10 minutes before expiry. Refresh failure → source status `NEEDS_REAUTH` → notification.
- API-key and basic-auth sources use the same Vault. The UI never re-displays secrets (write-only fields).

### 5.6 Direct Database connectors (Channel B)

| Concern | Design |
|---|---|
| Drivers | Postgres (psycopg3), MySQL/MariaDB (PyMySQL/asyncmy), MSSQL (pyodbc + msodbcsql18), Oracle (python-oracledb thin), MongoDB (pymongo), DB2 / IBM i (ODBC), SQLite (file), warehouses (official connectors) |
| Network | (1) Public host + IP allowlist of DCS **static egress IPs** (NAT gateway per region); (2) **SSH tunnel** (bastion, key stored in Vault); (3) **Bridge Agent** if the DB is not reachable from the internet (the preferred option for SMEs) |
| Least privilege | The UI generates a copy-paste SQL snippet to create a read-only user for each engine |
| Discovery | Schemas, tables, views, columns, types, PKs, FKs, row-count estimates, `updated_at`-like columns (heuristic) |
| Extraction | Snapshot via keyset pagination (chunked by PK); incremental via a cursor column; CDC (Debezium/logical replication) is deferred to Phase 9+ for the enterprise tier |
| Safety | Statement timeout, read-only transaction, max-rows guard, sampling mode for very large tables, no DDL ever |

### 5.7 File ingestion (Channel C)

**Entry points:** (1) resumable browser upload (tus protocol → S3 multipart, up to 20 GB per file); (2) a unique **email-in** address per tenant (`<tenant>.<token>@in.dcs-pis.app`, sender allowlist); (3) **SFTP** drop (per-tenant chrooted user); (4) Google Drive, OneDrive or Dropbox picker; (5) Bridge Agent folder watch.

**Processing pipeline (`IngestFileWorkflow`):**
```
landing (as-received, Object Lock) → ClamAV scan → magic-byte sniff (don't trust extension)
→ archive? recurse (limits: depth 5, ratio 100:1, 10k entries, 50 GB expanded)
→ format router → parser → normalized tables (Arrow) → bronze Parquet
→ manifest → register RawDataset(s) → trigger ProfileWorkflow
```

**Format registry (`parse-worker/formats/`). Every row is a parser plugin with fixtures and tests.**

| Family | Extensions / types | Parser approach | Output |
|---|---|---|---|
| Delimited | .csv .tsv .txt .psv | Delimiter and quote sniffing; encoding via charset-normalizer (UTF-8/16, Windows-1252, ISO-8859-x, Shift-JIS, etc.); header-row detection; ragged-row repair → quarantine | 1 table |
| Spreadsheet | .xlsx .xlsm .xls .xlsb .ods .numbers | `python-calamine` (fast, all formats); openpyxl for merged cells and formulas; **multi-table detection inside one sheet** (blank-row/column islands); header detection (multi-row headers flattened as `Parent / Child`); hidden sheets flagged; formulas → cached values plus formula text kept | N tables per sheet |
| Structured data | .json .ndjson .jsonl .xml .yaml | JSON: flatten to the root array with child tables for nested arrays (keys propagate a parent_id); XML: XPath record-path inference; very large files streamed | N tables |
| Columnar / binary data | .parquet .avro .orc .feather .arrow | pyarrow / fastavro | 1+ tables |
| Statistical | .sav .sas7bdat .dta .xpt | pyreadstat (keeps value labels) | 1 table + label dict |
| Embedded DB files | .db .sqlite .sqlite3 | Open read-only; every table becomes a dataset | N tables |
| SQL dumps | .sql (MySQL/Postgres dialects) .dump (pg_dump custom) | Restore into an **ephemeral DB container** (postgres/mysql) inside an isolated pod; then treat it as a Channel B snapshot; destroy the container | N tables |
| MSSQL backups | .bak .bacpac | Restore into an ephemeral `mssql` container (licence check: Developer edition for non-prod transforms; ADR) | N tables |
| MS Access | .mdb .accdb | `mdbtools` (mdb-tables, mdb-export) | N tables |
| dBase / FoxPro / Clipper | .dbf (+ .fpt/.cdx memo) | `dbfread` with codepage detection | 1 table each |
| Accounting exports | Tally XML/JSON exports, Tally `.900` data folders (via Bridge only), QuickBooks .iif, .qbo, Busy/Marg export formats | Dedicated parsers mapping vouchers, ledgers, stock items, parties | N tables |
| Bank & finance | .ofx .qfx .qif .mt940 .camt.053 (XML), bank-statement PDFs | ofxparse, mt940 lib, camt XML parser; PDFs via the document pipeline plus bank-specific templates | transactions table |
| Documents | .pdf .docx .doc .rtf .odt .pptx .html | Docling (layout + table structure), pdfplumber fallback; scanned → Tesseract OCR (eng + hin + regional language packs); tables → datasets; free text → `documents` store (searchable, not mapped) | tables + text |
| Images | .png .jpg .jpeg .tiff .heic .webp | OCR; invoice/receipt template detection → key-value extraction (LLM-assisted extraction is a *proposal* checked against arithmetic rules: line totals = invoice total) | kv rows |
| Email | .eml .msg .mbox .pst .ost | `mailbox`, `extract-msg`, `readpst`; attachments re-enter the pipeline | messages + attachments |
| Contacts / calendar | .vcf .ics | vobject, icalendar | 1 table |
| Fixed-width & mainframe | .dat .txt + COBOL copybook (.cpy), EBCDIC | User uploads the copybook → parser compiles a record layout → decodes EBCDIC (cp037/cp500) → packed decimal (COMP-3) support | 1+ tables |
| Logs / misc | .log .gz .bz2 .zst | Decompress → re-route; logs get line-level regex templates (low priority) | 1 table |
| Archives | .zip .7z .rar .tar .tgz .gz | Recursive with bomb limits | (children) |
| Unknown | anything else | Stored in landing, flagged `UNSUPPORTED_FORMAT`, sent to the concierge queue; never silently dropped | — |

**Rules:** files are kept as received; parsed output always keeps a `__dcs_row_number` and `__dcs_source_locator` (e.g., `sheet=Sales!A2:K9001`, `page=4,table=2`) for full traceability back to the original cell or page.

### 5.8 Assisted Browser Extraction (Channel D)

**Purpose:** reach data in web-based tools that have no usable API, by letting the **owner sign in to their own account inside an isolated DCS remote browser**. Once signed in, the system exports the data, preferably through the vendor's own export or report features.

#### 5.8.1 Architecture
```
Web UI (S-06)  ◄── WebSocket (JPEG/WebP frames via CDP Page.screencastFrame) ── browser-worker pod
     │  ──► input events (mouse, keyboard, paste, scroll, resize) ──────────────►  Playwright/Chromium
     │                                                                            │  - fresh profile per session
     │                                                                            │  - downloads → quarantine dir → S3 landing
     │                                                                            │  - HAR/network capture (opt-in, JSON only)
     │                                                                            │  - egress via per-session proxy with domain allowlist
     └──── session controls: pause, hand-over to automation, stop, kill ──────────┘
```
- One Kubernetes pod per session (resource-limited, ephemeral). Max session duration 60 min; idle timeout 10 min.
- **Domain allowlist** per session: the catalog entry's domains plus SSO and identity domains (e.g., accounts.google.com, login.microsoftonline.com). Everything else is blocked.
- Clipboard: paste-in allowed (for passwords and OTPs typed by the user); copy-out disabled.
- Recording: every automated action is logged (selector, URL, screenshot hash) to the audit log. Live frames are **not** stored by default.

#### 5.8.2 Modes

| Mode | Who drives | How it works |
|---|---|---|
| **Guided** | Owner | The owner signs in and navigates to the export themselves. DCS captures every download and routes it to the File pipeline. Always available. |
| **Recipe** | Automation (deterministic) | After the owner signs in (the session is detected as authenticated by recipe-specific selectors or cookies), a published **Recipe** runs: navigate to the export or report page → set date range and all objects → trigger export → wait for the download or email-link → capture. |
| **AI Navigator** | LLM agent + owner approval | For unknown tools. A vision LLM sees screenshots plus a simplified DOM and proposes the next action ("click 'Reports'", "choose 'Export all customers (CSV)'"). Each action needs owner approval ("approve step / approve next 5 / take over"). Successful paths are saved as a **Draft Recipe** and go to the admin review queue (M-05). Once published, future tenants get Recipe mode. *The connector library grows by itself.* |

#### 5.8.3 Recipe format (`recipes/<catalog_id>/<version>.yaml`)
```yaml
id: example_vertical_saas.customers_export
catalog_id: example_vertical_saas
version: 1.2.0
auth_detect: { url_matches: "^https://app\\.example\\.com/dashboard", selector: "[data-test=user-menu]" }
params: { date_from: "{{tenant.history_start}}", date_to: "{{today}}" }
steps:
  - goto: "https://app.example.com/reports/customers"
  - click: { role: button, name: "Export" }
  - select: { label: "Format", value: "CSV" }
  - fill: { label: "From", value: "{{params.date_from}}" }
  - click: { role: button, name: "Download" }
  - expect_download: { timeout_s: 300, pattern: "*.csv" }
outputs: [{ stream: customers, file_glob: "*.csv" }]
health_check: weekly synthetic run on DCS demo account (if available)
```

#### 5.8.4 Scheduled re-sync
- Default: **one-shot** (the owner must be present for each extraction).
- Opt-in "keep me connected": the session's storage state (cookies only, **never passwords**) is encrypted in the Vault with a TTL that matches the vendor's session. Scheduled runs reuse it. When the session has expired, or MFA is needed, the owner is notified to sign in again.

#### 5.8.5 Guard-rails (must be implemented and tested)
1. A consent screen before every new browser source states what will be accessed, that the owner uses their own credentials, and that the owner is responsible for complying with the vendor's terms.
2. Read-only intent: recipes and AI navigator steps that match destructive patterns (`delete|remove|cancel|pay|transfer|send|submit order`) are blocked by a policy engine unless explicitly allowlisted per recipe by a DCS admin.
3. No payment pages, no netbanking: the catalog flags `browser_prohibited: true` for banks and payment-transfer UIs.
4. CAPTCHA and bot challenges are handed to the human. No solving services, ever.
5. Kill switch per catalog entry (admin) and per session (owner).

### 5.9 Bridge Agent (Channel E) and legacy systems

**Installation:** the owner downloads a signed installer (Windows MSI / Linux .deb/.rpm) from page S-07 and enters a **pairing code** (8 chars, 15-min TTL). The agent generates a key pair, the relay issues a tenant-scoped client certificate (mTLS), and the agent connects **outbound only** over 443 (gRPC over HTTP/2, with WebSocket fallback). No inbound firewall ports are needed.

**Capabilities (adapters inside the agent):**

| Adapter | Reaches | Notes |
|---|---|---|
| `tally` | TallyPrime / Tally.ERP 9 HTTP-XML gateway on `localhost:9000` (or LAN IP) | Exports masters (ledgers, groups, stock items, units, cost centres), vouchers (sales, purchase, receipt, payment, journal, credit/debit notes) with date-range chunking per company; needs the Tally HTTP/ODBC server enabled (setup guide in UI) |
| `odbc` | Any ODBC DSN (MS Access, FoxPro, IBM i/AS400, Sybase, Informix, Pervasive/Btrieve, Busy/Marg if ODBC exists) | Read-only queries; table discovery |
| `sql` | Local MSSQL/MySQL/Postgres/Oracle | Same as Channel B, executed locally |
| `files` | Watched folders, network shares (SMB) | Upload new or changed files to the File pipeline; checksum dedupe |
| `qbxml` | QuickBooks Desktop via QBXML SDK (Windows) | Phase 9+ unless a client needs it |
| `report_spool` | Folders where legacy apps print reports (PDF/TXT/PRN) | Feeds the document parser with report templates |

**Agent internals:** a job pull loop (the relay pushes job descriptors; the agent acknowledges); a local encrypted spool (SQLite + AES) for offline buffering; CPU and IO throttling (default ≤ 20% CPU, business-hours aware); signed auto-update with staged rollout; local log viewer; uninstall wipes the keys. The agent **never** accepts arbitrary code. It runs only typed job types with validated parameters.

**Legacy playbook (used by the router and by the concierge):**

| Legacy situation | Strategy |
|---|---|
| Tally / Busy / Marg desktop accounting | Bridge `tally` or `odbc`; fallback: guided XML/Excel export upload |
| MS Access / FoxPro apps | Bridge `odbc` or file upload of .mdb/.dbf |
| Old on-prem ERP with SQL backend | Bridge `sql` (read-only user) |
| AS/400 / IBM i | Bridge `odbc` (IBM i Access ODBC) or DB2 JDBC via a small JVM sidecar (Phase 9+) |
| Mainframe | Flat-file extracts + COBOL copybooks via File channel (§5.7) |
| Desktop app with no DB access, only reports | `report_spool` + document parsing templates |
| Green-screen terminal only | Concierge (screen-scraping TN3270/5250 is out of scope for v1) |
| Paper / handwritten | Concierge OCR project (out of the self-serve path) |

### 5.10 Concierge channel (Channel F)
A workflow, not technology. It creates a `concierge_case`, which DCS staff handle in M-08. Staff can attach files on the tenant's behalf (audited, tenant-visible) and create catalog candidates or recipes.

### 5.11 Scheduling & freshness
- Per-source schedule (default: API hourly, DB every 6 h, Bridge nightly, browser on-demand or weekly). Plan tier caps the minimum interval.
- **Freshness SLO** per source is shown in S-01. A stale source triggers a notification and lowers the DRP freshness score.

### 5.12 Floor 1 output contract
Every channel ends in exactly the same artifact, so Floor 2 never cares *how* data arrived:
1. Landing object(s), immutable
2. Bronze Parquet table(s)
3. **Ingestion Manifest** (§17.1)
4. Rows in `raw_registry.raw_dataset` and `raw_registry.ingestion_batch` in the tenant DB
5. Event `ingestion.batch.committed` → Floor 2 workflows start

---

## 6. FLOOR 2 — TRANSFORMATION & INTELLIGENCE DATABASE

**Goal:** Turn *raw unknown* data into *known, canonical, trustworthy* data in the tenant's Intelligence Database. The LLM helps with understanding; deterministic, versioned code does the transforming.

### 6.1 Data zones

```
LANDING  (object store)  as-received bytes, immutable              ← Floor 1
   │
BRONZE   (object store)  tabular Parquet, all columns as string + inferred typed shadow,
   │                     __dcs_* lineage columns; immutable
   │
SILVER   (tenant DB: stg_<source>)  typed, cleaned, standardized per source,
   │                     still source-shaped (one table per raw dataset)
   │
GOLD     (tenant DB: core)    Canonical Business Model entities (golden records after ER)
   │     (tenant DB: graph)   nodes/edges between core entities
   │     (tenant DB: events)  declared business events
   │
ENGINE API (tenant DB: engine_api_v1)  stable, versioned READ-ONLY views for tools
RESULTS    (tenant DB: results)        tool outputs (written only by the Tool Runner)
```

### 6.2 Profiling (`ProfileWorkflow`)

Per raw dataset, computed with DuckDB over Bronze Parquet (full scan up to 50M rows, sampled above that):

| Profile item | Detail |
|---|---|
| Column stats | count, null %, distinct count (HLL), min/max, mean/std (numeric), length stats, top-20 values, histogram |
| Type inference | int, decimal (precision), bool, date, datetime (with format strings detected, e.g., `%d/%m/%Y`, `%d-%b-%y`, Excel serials, epoch), time, currency-amount (symbols ₹ $ € £, Indian lakh/crore grouping `1,00,000`), percentage, JSON |
| Semantic type | email, phone (E.164 normalization, IN default), person name, company name, address, city, state, PIN/ZIP, country, GSTIN, PAN (flag only), IFSC, URL, IP, UUID, SKU-like, invoice-no-like, currency code, status/enum, free text, ID/key |
| PII classification | `NONE / PII / SENSITIVE_PII` (PAN, Aadhaar-like patterns, bank account numbers, health terms) → drives masking (§8.6) |
| Keys | candidate primary keys (uniqueness ≥ 99.9%), composite key search (≤3 cols) |
| Relationships | inclusion dependencies across datasets of the same tenant (FK candidates, e.g., `orders.cust_code ⊆ customers.code`), with a containment score |
| Temporal | candidate event-time and update-time columns; history span (first/last date); granularity |
| Dataset domain | classification into a CBM entity (§6.3) with confidence: rules first (connector templates, column-name dictionaries in English plus common Hinglish and regional variants such as `party_name`, `bill_no`, `narration`, `vch_type`), then embeddings similarity against the CBM field dictionary (pgvector), then an LLM tie-break |

Output: `raw_registry.dataset_profile` (JSONB) + `raw_registry.column_profile` rows.

### 6.3 Canonical Business Model (CBM) v1

The CBM is the **fixed target structure** of every Intelligence Database. It is defined once in `packages/py/dcs_cbm/` as Pydantic models, which generate (a) Alembic migrations for `core`, (b) the JSON field dictionary for mapping, (c) the `engine_api_v1` views, and (d) TS types for the UI.

**Common columns on every core table**

| Column | Type | Purpose |
|---|---|---|
| `id` | uuid (v7) | DCS golden ID |
| `source_refs` | jsonb | `[{"source_id","stream","source_pk"}]` – all source records merged into this row |
| `attributes` | jsonb | Unmapped but retained source fields (extension, no data loss) |
| `src_created_at`, `src_updated_at` | timestamptz | From source |
| `valid_from`, `valid_to`, `is_current` | timestamptz/bool | SCD-2 history for dimension entities |
| `ingested_at` | timestamptz | — |
| `tps_version`, `batch_id` | text/uuid | Lineage (P5) |
| `dq_score` | numeric(4,3) | Row-level quality |
| `is_deleted` | bool | Soft delete from source |

**Money:** `amount_minor bigint` + `currency char(3)`, plus `fx_rate_to_base` and `amount_base_minor` computed from `core.fx_rate`. **Time:** stored UTC; the tenant timezone lives in the org profile.

**Entities (grouped by domain)**

| Domain | Entities (table) | Key fields (abridged) |
|---|---|---|
| **Party** | `party` (customer/account/organisation counterparties), `person` (contacts, individuals), `party_person_role`, `address`, `identifier` (GSTIN, VAT, external IDs) | party: name, type (B2B/B2C/vendor/both), segment, industry, lifecycle_stage, owner_employee_id, first_seen_at |
| **Sales/CRM** | `lead`, `opportunity`, `pipeline`, `pipeline_stage`, `opportunity_stage_history`, `activity` (call/email/meeting/task/note), `quote` | opportunity: party_id, amount, stage_id, probability, expected_close, won_at, lost_reason, source_campaign_id |
| **Commerce** | `product`, `product_variant`, `price_list`, `order`, `order_line`, `return`, `cart` (if available), `subscription`, `subscription_event` | order: party_id, channel, status, ordered_at, totals (sub, tax, discount, shipping, grand) |
| **Finance** | `invoice`, `invoice_line`, `payment`, `refund`, `credit_note`, `bill` (payables), `bill_line`, `expense`, `ledger_account` (chart of accounts), `journal_entry`, `journal_line`, `tax_line` (GST CGST/SGST/IGST, VAT), `bank_transaction`, `settlement`, `fx_rate` | invoice: party_id, number, issued_at, due_at, status, totals, balance_due; payment: method, gateway, fee_minor, invoice allocations |
| **Marketing** | `campaign`, `ad_account`, `ad_group` (ad set), `ad`, `ad_performance_daily`, `marketing_touch` (attribution touchpoints), `audience_segment`, `email_campaign`, `email_event` | ad_performance_daily: date, ad_id, impressions, clicks, spend_minor, conversions, conversion_value_minor |
| **Web/Product** | `web_traffic_daily`, `web_session` (if raw), `product_event` | — |
| **Support** | `ticket`, `ticket_event`, `csat_response` | ticket: party_id, person_id, channel, priority, status, opened_at, first_response_at, resolved_at |
| **People/HR** | `employee`, `department`, `role`, `employment_event`, `attendance_daily`, `payroll_run`, `payroll_line` (aggregated by default) | employee: pseudonymous by default (§8.6) |
| **Operations** | `location` (branch/store/warehouse), `inventory_item`, `stock_level_daily`, `stock_movement`, `purchase_order`, `purchase_order_line`, `shipment`, `appointment`/`booking` (service businesses), `membership` (gyms, clubs) | — |
| **Communication** | `conversation`, `message` (metadata; body opt-in) | — |
| **Generic** | `custom_entity_def`, `custom_entity_row` (jsonb), `document` (text and metadata from PDFs/docs) | Anything that fits no CBM entity is still preserved and queryable |

**CBM governance:** CBM changes are additive within a major version (new tables, new nullable columns). Breaking changes require `core_v2` plus migration of `engine_api` views, and need an ADR.

### 6.4 LLM-assisted mapping (`MappingWorkflow`)

```
            ┌─────────────────────────────────────────────────────────────┐
RawDataset ─►1 Template lookup: connector has cbm_template? → use it (no LLM) │
            │2 Else Classification: rules → embeddings → LLM (entity + conf) │
            │3 Field proposals: for each target CBM field pick source col(s) │
            │  + transform expression in Transform DSL + confidence          │
            │4 Validate: DSL type-check, dry-run on 1,000-row sample,        │
            │  DQ assertions (e.g., totals reconcile, dates parse ≥98%)       │
            │5 Decide: conf ≥ τ_auto(0.90) AND dry-run pass → AUTO_ACCEPTED │
            │          else → REVIEW queue (D-03/D-04)  ─── human ───┐       │
            │6 Compile: MappingSpec(v) → SQL (DuckDB for bronze→silver,     │
            │  Postgres for silver→core) — deterministic, no LLM            │
            │7 Execute + record lineage; store accepted mapping in          │
            │  Mapping Memory (pgvector) for future suggestions             │
            └─────────────────────────────────────────────────────────────┘
```

**What the LLM sees (privacy):** dataset name, column names, inferred types, semantic types, column stats, and **≤ 20 sample values per column, masked** (PII columns are replaced by format-preserving tokens, e.g., `name_7f3a`, `+91XXXXXX1234`). Tenants on the privacy tier route to the self-hosted model. Every prompt and response is logged (masked) with its prompt version.

**Transform DSL (the only thing the LLM may output for transforms):**

```
expr := col("Bill No") | lit(value) | fn(args...)
fns  := cast(expr, type) | parse_date(expr, fmt[, tz]) | parse_datetime(...) | excel_serial_to_date(expr)
        | trim | lower | upper | title | regex_extract(expr, pattern, group) | regex_replace(...)
        | split_part(expr, sep, n) | concat(expr...) | coalesce(expr...) | nullif(expr, v)
        | map_values(expr, {src: dst, ...}, default) | to_minor(expr, currency_expr)
        | parse_amount(expr, locale)   # handles 1,00,000.50 / 1.000,50 / (500) negatives / Cr Dr
        | phone_e164(expr, default_region) | email_norm(expr) | gstin_norm(expr)
        | lookup(dataset, key_expr, value_col) | if_(cond, a, b) | sum_cols(expr...)
        | date_trunc(unit, expr) | hash_id(expr...)   # deterministic source PK when none exists
```
- The DSL is parsed by a Lark grammar and type-checked against the CBM field type. It **compiles to SQL**. There is no `eval` and no arbitrary Python.
- Row-level rules: `filter` (e.g., drop subtotal rows: `regex_match(col("Particulars"), "^(Total|Grand Total)")`) and `unpivot` (wide monthly columns → long rows) are first-class operations.

**Mapping Spec:** see §17.2. It is versioned per raw dataset, with status `DRAFT | AUTO_ACCEPTED | ACCEPTED | REJECTED | SUPERSEDED`.

**Mapping Memory:** accepted mappings are embedded as `(column name, stats signature, semantic type) → CBM field`. They are retrieved as few-shot examples for the next tenant (cross-tenant learning that uses **only metadata, never values**; tenant opt-out lives in G-05).

### 6.5 Tenant Pipeline Spec (TPS)

A per-tenant JSON document (§17.8) that composes: sources and schedules, raw dataset → mapping spec versions, ER config, DQ rule set, graph build config, event derivation config, and the CBM version. Properties:
- semver + content hash; every change creates a new version (an auto-commit by the system or a user action)
- **Replay:** `ReplayWorkflow(tps_version, from_batch)` rebuilds silver and gold from bronze, so a bad mapping can be rolled back and recomputed
- a diff view between versions in D-08

### 6.6 Entity resolution (`EntityResolutionWorkflow`)

- Applies to `party`, `person` and `product` (and `employee` when there are multiple HR sources).
- **Splink** on DuckDB. Blocking rules: email, normalized phone, GSTIN, (name soundex + city), domain. Comparisons: Jaro-Winkler names, exact email/phone/tax IDs, address token overlap.
- Thresholds: `p ≥ 0.95` auto-merge; `0.70–0.95` → review (D-05); `< 0.70` no-merge.
- **Survivorship rules** (configurable per field): most recent non-null, source priority (e.g., accounting wins for legal name, CRM wins for owner), longest value, or a manual override.
- Merges and splits are reversible: a cluster history is kept in `core.er_cluster` and `core.er_decision`.

### 6.7 Data quality (`DQWorkflow`)

| Rule class | Examples |
|---|---|
| Completeness | `invoice.issued_at` non-null ≥ 99% |
| Validity | currency is an ISO-4217 code; emails RFC-valid; GSTIN checksum |
| Consistency | Σ invoice_line.amount = invoice.subtotal (±1 minor unit); payment allocations ≤ invoice total |
| Uniqueness | invoice.number unique per party per fiscal year |
| Timeliness | source freshness within SLO |
| Referential | order.party_id resolves |
| Plausibility | no negative quantities unless return; dates not in the future beyond +1 day |

- Severity: `INFO / WARN / CRITICAL`. A CRITICAL failure **quarantines** the offending rows (`core_quarantine.<entity>`) and blocks DRP "ready" status for that domain until it is resolved or waived (the waiver is audited).
- Scores: row → entity → domain → tenant DQ score (0–1), shown in D-06 and included in the DRP.

### 6.8 Business graph

- `graph.nodes(id, entity_type, entity_id, label, props jsonb)` and `graph.edges(id, type, src_node, dst_node, props jsonb, valid_from, valid_to, confidence)`.
- Edge types v1: `PERSON_WORKS_AT_PARTY`, `OPPORTUNITY_FOR_PARTY`, `ORDER_BY_PARTY`, `ORDER_CONTAINS_PRODUCT`, `INVOICE_BILLS_PARTY`, `INVOICE_FOR_ORDER`, `PAYMENT_SETTLES_INVOICE`, `AD_IN_CAMPAIGN`, `TOUCH_ATTRIBUTED_TO_CAMPAIGN`, `LEAD_CONVERTED_TO_OPPORTUNITY`, `TICKET_RAISED_BY_PERSON`, `EMPLOYEE_OWNS_PARTY`, `EMPLOYEE_AT_LOCATION`, `MEMBERSHIP_OF_PERSON`.
- Built incrementally from core FKs plus inferred links (e.g., matching an invoice to an order by reference number, with a confidence score).

### 6.9 Event catalogue

- Declared in `packages/py/dcs_cbm/events.yaml` (name, entity, trigger rule, payload schema). **Undeclared events cannot be emitted** (the emitter validates against the catalogue).
- Derived from snapshots and diffs between syncs or from source webhooks: `lead.created`, `opportunity.stage_changed`, `opportunity.won`, `opportunity.lost`, `order.placed`, `order.cancelled`, `invoice.issued`, `invoice.paid`, `invoice.overdue`, `payment.received`, `refund.issued`, `subscription.started`, `subscription.churned`, `ticket.opened`, `ticket.resolved`, `campaign.started`, `ad.spend_spike` (threshold rule, not ML), `stock.below_reorder` (rule), `membership.expired`.
- Stored in `events.business_event` (append-only, partitioned monthly). These are for the Engine to consume. The exoskeleton does not act on them.

### 6.10 Incremental processing & schema drift

| Drift | Behaviour |
|---|---|
| New column in source | Profile it → try Mapping Memory/template → auto-map if confident, else store in `attributes` and open a low-priority review item |
| Column removed | Mapping marked `DEGRADED`; DQ completeness alert; the DRP domain may downgrade |
| Type change | Rows that fail the cast are quarantined; review item opened |
| New stream or table/sheet | Registered as a new raw dataset → full mapping flow |
| Renamed column (detected via stats similarity ≥ 0.9) | Proposed rename mapping → review |

All Floor 2 steps are **incremental by batch**: only new or changed rows (by `source_pk` + hash) are transformed, with upserts into core.

### 6.11 Data Readiness Profile (DRP): the Floor 2 → Floor 3 handshake

A JSON document (§17.3) regenerated after every committed pipeline run. It summarises, per CBM entity:
- present? row count, distinct parties, **history span** (first/last date, months covered, gaps)
- field completeness for each field that tools commonly require
- DQ score, freshness, sources contributing
- business signals: revenue model hints (subscription, transactional, project), B2B/B2C ratio, channel mix, location count, currency mix

The DRP is **the only thing** the Assignment Engine reads about the data (apart from the business profile). Tools declare requirements against DRP fields, which keeps the engine decoupled from raw tables.

---

## 7. FLOOR 3 — ENGINE BAY

**Goal:** Build everything around the engine so that real tools can be plugged in with zero exoskeleton changes: registry, marketplace, assignment, entitlements, sandboxed runner, results store and UI.

### 7.1 Built vs vacant

| Built in the exoskeleton | Vacant (engine team) |
|---|---|
| Tool Registry + Tool Manifest validation | The actual tool logic, models, statistics |
| Assessment & Assignment Engine (rule-based scorer + pluggable `AssignmentScorer` interface) | A smarter ML-based scorer (optional plug-in) |
| `engine_api_v1` read-only views | Feature engineering inside tools |
| Tool Runner + sandbox + scheduling + quotas | Training pipelines and model artifacts |
| InsightResult validation, storage, rendering | Narrative and insight content |
| Action Proposal storage and approval UI (no execution) | Agents that execute actions (future: DCS VoiceOS / agents) |
| Tool SDK (`dcs-tool-sdk`) + local harness + contract tests | — |
| **Reference tools** (test motor, §7.7) | — |

### 7.2 Tool Registry & Tool Manifest

- Tools are **OCI images** in the private registry, signed with cosign. Every image includes `/dcs/manifest.json` (§17.4).
- `POST /registry/tools` (admin, M-09) imports by image digest. The registry validates the manifest schema, signature, ERI version compatibility and requirement references (every referenced DRP path must exist in the DRP schema).
- Versioning: semver. A tenant pins a minor version; patch updates auto-apply; major updates need re-activation.
- Manifest highlights: `requirements` (hard, against DRP), `relevance` (business-type weights and signals), `tier_hint` (`primary_eligible`, `addon_price`), `outputs` (InsightResult types), `params_schema`, `schedule_default`, `compute` (cpu, mem, timeout), `reads` (which engine_api views), `writes` (always only results via the runner).

### 7.3 Assessment & Assignment Engine (`AssessmentWorkflow`)

Inputs: **Business Profile** (from onboarding O-01: industry (NAICS-like taxonomy with Indian SME verticals), business model, B2B/B2C, size band, locations, channels, goals chosen by the owner) + **DRP** + **Tool Registry** + **Plan**.

```
for tool in registry.active_tools:
    eligibility = evaluate(tool.requirements, DRP)            # all hard reqs → ELIGIBLE / NOT_ELIGIBLE
                                                              # missing list → "unlock hints"
    relevance   = scorer.score(tool, business_profile, DRP)   # 0..1, explainable factors
    if relevance < τ_relevant (0.35):           status = NOT_RELEVANT
    elif not eligibility.ok:                    status = LOCKED (unlock_hints = missing data → which connector)
    elif tool.tier_hint.primary_eligible and relevance ≥ τ_primary (0.70)
         and tool.category in core_categories(business_profile):
                                                status = PRIMARY_CANDIDATE
    else:                                       status = SECONDARY
primary = top-K(PRIMARY_CANDIDATE by relevance, K = plan.primary_tool_cap); overflow → SECONDARY
persist ToolkitRecommendation(version, items[], explanations[], drp_version, profile_version)
```

- `AssignmentScorer` is a Python Protocol. **v1 = `RuleScorer`**: a weighted sum of manifest-declared factors such as `industry_match`, `model_match`, `signal: has_subscriptions`, `history_months ≥ n`, and owner-selected goals. The engine team can register `MLScorer` later through the same interface.
- Explanations are templated from the scoring factors, e.g. *"Recommended because you have 26 months of invoices across 1,240 customers and run a subscription model."* An LLM may *rephrase* the explanation, never decide it.
- Re-assessment triggers: a DRP change (domain readiness changed), a new tool published, a plan change, or a profile edit. A diff shows owners what changed ("2 new tools unlocked after connecting Meta Ads").

### 7.4 Marketplace & entitlements
- **Primary** tools: included in the subscription (count capped by plan).
- **Secondary** tools: paid add-ons (monthly), purchasable in B-02.
- **Locked** tools: shown with "Connect X to unlock", which deep-links to the right connector.
- Entitlement service: `can_run(tenant, tool_id, version) → allow/deny + reason`, checked by the runner before every run and cached in Redis for 60 s.

### 7.5 Engine Runtime Interface (ERI v1): the socket

```
                 ┌───────────────── exoskeleton ─────────────────┐
 Scheduler/UI ──►│ ToolRunWorkflow                                │
                 │  1 entitlement check                           │
                 │  2 build ToolRunRequest (§17.5)                │
                 │  3 mint short-lived DB creds: role engine_ro    │
                 │    (SELECT on engine_api_v1.* only), TTL = timeout│
                 │  4 launch sandbox Job (image@digest)            │
                 │      env: DCS_RUN_REQUEST (path), DCS_DB_DSN     │
                 │      mounts: /dcs/in (request.json, ro)          │
                 │              /dcs/out (results dir, rw, size cap) │
                 │      network: deny all except tenant DB endpoint │
                 │  5 stream logs + progress (stdout JSON lines)    │
                 │  6 on exit: read /dcs/out/*.json → validate      │
                 │    InsightResult schema → store results.*        │
                 │  7 revoke creds, destroy sandbox, emit metrics   │
                 └────────────────────────────────────────────────┘
                                   ▲
                       ENGINE TOOL │ (built by engine team with dcs-tool-sdk)
```

- **Inputs to tools:** only the `engine_api_v1` views (a stable contract decoupled from core internals), plus parameters, plus the DRP snapshot.
- **Outputs from tools:** only files in `/dcs/out` that conform to InsightResult (§17.6), plus optional artifacts (Parquet tables ≤ 200 MB, model cards). Tools cannot write to the DB.
- **Progress protocol:** stdout JSON lines `{"type":"progress","pct":42,"msg":"…"}`, `{"type":"log","level":"info","msg":"…"}`.
- **Exit codes:** `0` success, `10` insufficient data (show as "needs more data", not an error), `20` invalid params, other → failure, retried per manifest policy.
- **Limits:** CPU, memory and wall-clock time from the manifest, capped by the plan; default 2 vCPU, 4 GiB, 15 min.
- **Model artifacts:** tools may read versioned model files from a read-only mount `/dcs/models/<tool_id>/<version>/`. This is supplied by the engine team's model store and stubbed in the exoskeleton.

### 7.6 Results & rendering
- `results.tool_run`, `results.insight`, `results.artifact`, `results.action_proposal`.
- The UI renders InsightResult blocks by type: `kpi`, `kpi_group`, `timeseries`, `table`, `bar/line/area/scatter` (Vega-Lite spec, validated against an allowlisted subset with no external data URLs), `segment_list`, `forecast` (with intervals), `anomaly_list`, `recommendation`, `narrative` (Markdown, sanitized), `action_proposal`.
- **Action proposals** carry a `governance_level` of 0–4 (aligned with the DCS Platform governance model: 0 = informational … 4 = high-impact, needs multi-approver). The exoskeleton supports *approve / reject / comment* and stores the decision. It **does not execute** anything (this is the future hand-off to agents).
- Evidence links: an insight can reference core record IDs, and the UI deep-links to D-07 (entity view).

### 7.7 Reference tools (the "test motor")

Located in `engine/reference_tools/`. They are **deliberately trivial** and exist only to prove the socket works:

| Tool id | Purpose | Requirements | Output |
|---|---|---|---|
| `ref.echo` | Contract smoke test | none | narrative echoing params + DRP summary |
| `ref.data_health` | Shows DQ and coverage | DRP present | kpi_group + table |
| `ref.revenue_by_month` | SUM(invoice totals) by month | invoice ≥ 1 month | timeseries + kpi |
| `ref.customer_count` | New parties per month | party ≥ 10 | timeseries |
| `ref.top_products` | Top 10 by order-line value | order_line ≥ 100 | table + bar |
| `ref.fail` | Always exits 1 | none | (tests failure path) |
| `ref.slow` | Sleeps past timeout | none | (tests timeout path) |
| `ref.insufficient` | Exits 10 | none | (tests "needs more data" path) |
| `ref.action` | Emits a governance-level-2 action proposal | none | action_proposal |

### 7.8 Tool SDK (`packages/py/dcs_tool_sdk`)
- `dcs_tool_sdk.run(handler)` decorator: parses the request, provides `ctx.db` (read-only SQLAlchemy engine), `ctx.params`, `ctx.drp`, `ctx.progress()`, and `ctx.emit(InsightResult)`.
- `dcs-tool validate manifest.json`, `dcs-tool run --fixture tenant_a`: a local harness that spins up a fixture tenant DB from the Messy Data Corpus (§14.5).
- `dcs-tool contract-test`: the same suite the registry runs on import. **The engine team must pass this before handing over a tool.**

---

## 8. MULTI-TENANCY, SECURITY & COMPLIANCE

### 8.1 Tenant provisioning (`ProvisionTenantWorkflow`)
1. Create an `org` row (Control DB) + Keycloak organization/group.
2. Create a KMS CMK `alias/dcs/t/<tenant_id>`, then a DEK (wrapped) stored in `tenant_key`.
3. Create database `t_<shortid>` on the regional cluster; create roles: `t_<id>_owner` (migrations), `t_<id>_rw` (workers), `t_<id>_ro` (data-api reads), `t_<id>_engine_ro` (NOLOGIN template; the runner mints temporary LOGIN users with `VALID UNTIL`).
4. Run tenant migrations (`raw_registry`, `stg` template, `core`, `graph`, `events`, `engine_api_v1`, `results`, `core_quarantine`, `audit_local`).
5. Create object-store prefixes with a bucket policy condition and default SSE-KMS = tenant CMK.
6. Register Temporal search attributes and the namespace mapping; create default schedules.
7. Emit `tenant.provisioned`. **Deprovisioning** (G-05 / M-03) reverses this: exports offered, then a crypto-shred (delete the CMK after a 7–30-day waiting period), DB drop, and prefix deletion via lifecycle rules.

### 8.2 Data-access enforcement
- data-api resolves `tenant_id` **only** from the authenticated session's active org (never from the request body). It obtains a connection from a per-tenant pool keyed by `tenant_id`. A wrong-tenant access is impossible by construction, and this is tested (§14.6).
- Workers receive `tenant_id` in workflow input. A `TenantContext` guard asserts that the DB name matches before any query.
- Control DB tables with `org_id` use Postgres RLS with `SET app.current_org` per transaction.

### 8.3 Roles & permissions

| Role | Key permissions |
|---|---|
| Owner | Everything including billing, deletion, data governance |
| Admin | Users, sources, mappings, tools; no tenant deletion |
| Data Manager | Sources, mappings, ER/DQ review, pipeline replay |
| Analyst | View data studio, run and view tools, approve level 0–1 action proposals |
| Viewer | View insights only |
| Billing | Billing pages only |
| **DCS Staff: Support** | Metadata only by default; **break-glass** access to tenant data needs an owner-approved or time-boxed ticket, fully audited and visible to the tenant in G-04 |
| DCS Staff: Ops / Admin | Platform config; no tenant data without break-glass |

Permissions are defined as strings (`sources:write`, `mapping:approve`, `tools:run`, …) in `packages/py/dcs_authz/policies.yaml`. The UI hides what the role cannot do, and the API enforces it.

### 8.4 Authentication
Keycloak OIDC (Authorization Code + PKCE). MFA is mandatory for Owner and Admin roles (TOTP / WebAuthn). Session cookies are httpOnly, SameSite=Lax, 12 h idle and 7 d absolute. API keys (for future programmatic access) are hashed with argon2 and scoped by permission.

### 8.5 Audit
- `audit_event(id, ts, org_id, actor_type, actor_id, action, target_type, target_id, ip, ua, details jsonb, prev_hash, hash)`. The hash chain is verified nightly, and a mismatch raises an alert.
- Covered: auth events, credential create/use/delete, source connect/disconnect, browser session start/stop and every automated step, mapping decisions, ER merges, DQ waivers, tool runs, action approvals, exports, deletions, every staff break-glass.

### 8.6 Privacy, PII & LLM processing
- PII classification comes from profiling. Policies per tenant: `llm_processing: masked (default) | off | self_hosted_only`.
- **Off** means templates and rules only, with mapping done fully by humans in the Workbench (still works, just slower).
- HR and payroll: default **pseudonymize** employee names and IDs in core (a keyed HMAC); the reversible mapping lives in a separate table with stricter permissions.
- Message bodies and email content: off by default; opt-in per source.
- Sensitive identifiers (PAN, Aadhaar-like, bank account numbers) are **field-level encrypted** in core with the tenant DEK and are not exposed in `engine_api` views unless a tool's manifest declares the need and the owner approves.

### 8.7 Compliance features (build list)
- Data residency: the region is chosen at signup and immutable (migration is a concierge process).
- Data-subject requests: export of all data for a person or party (JSON + CSV) and erasure (core and graph rows, plus a tombstone; raw-zone objects are crypto-shredded by tenant-wide deletion, or handled by a per-record rewrite job that rewrites the affected bronze files and is logged).
- Retention policies per zone (e.g., landing 90 d after successful parse, if the tenant chooses).
- Consent records: per source and per purpose, versioned (`consent_record`).
- Sub-processor list (cloud, LLM providers, email) shown in G-05; LLM providers used per tenant are visible.
- Applicable regimes to design for: India **DPDP Act 2023** (and its Rules as notified), **UK GDPR / EU GDPR** (the EU/UK go-to-market), and contractual DPAs. *Legal review required before launch (see §16).*

### 8.8 Threat model highlights

| Threat | Mitigation |
|---|---|
| Cross-tenant data leak | DB-per-tenant, per-tenant keys, context guards, isolation test suite, pen test |
| Malicious uploaded file | ClamAV, sandboxed parsers (non-root, seccomp, no network), archive bomb limits, ephemeral restore containers |
| Malicious tool image | Signed images, gVisor, no egress, read-only creds on views only, resource caps, output schema validation, Vega-Lite allowlist |
| Prompt injection through data (e.g., a cell containing "ignore instructions") | LLM output is constrained to a schema and only *proposes*; DSL is compiled with no code execution; sample values are masked; the AI navigator needs human approval and a destructive-action policy |
| Remote-browser abuse (SSRF, data exfiltration) | Per-session egress allowlist proxy, no copy-out, ephemeral pods, audit |
| Bridge Agent compromise | mTLS, typed jobs only, signed updates, tenant-scoped certs, revocation from S-07/M-06 |
| Credential theft | KMS envelope encryption, decrypt permission only in specific workers, no secret display, rotation |
| Staff misuse | Break-glass with approval, tenant-visible audit |

---

## 9. FRONTEND: COMPLETE PAGE INVENTORY

**Totals: 60 pages = 47 customer-app pages + 13 admin-console pages.**
Apps: `apps/web` (customer, `app.dcs-pis.app`) and `apps/admin` (staff, `admin.dcs-pis.app`, VPN/IP-restricted plus staff SSO).

### 9.1 Customer app navigation

```
┌ Sidebar ────────────────┐
│ ⌂  Home                 │  H-01
│ ⇄  Data Sources         │  S-01…S-09
│ ▦  Data Studio          │  D-01…D-09
│ ✦  Toolkit              │  T-01…T-05
│ ◉  Insights             │  T-06
│ ₹  Billing              │  B-01…B-03
│ ⚙  Settings             │  G-01…G-06
└─────────────────────────┘  Top bar: org switcher · search · notifications (X-01) · help (X-02) · profile
```

### 9.2 Customer app pages (47)

| ID | Route | Page | Purpose / key components | Phase |
|---|---|---|---|---|
| **AUTH (Keycloakify-themed)** |||||
| A-01 | `/auth/sign-in` | Sign in | Email+password, SSO buttons (later), MFA step | P0 |
| A-02 | `/auth/sign-up` | Sign up & create organisation | Name, email, company, country → region | P0 |
| A-03 | `/auth/reset` | Forgot / reset password | — | P0 |
| A-04 | `/auth/mfa` | MFA enrol & verify | TOTP QR, WebAuthn, recovery codes | P0 |
| A-05 | `/auth/invite/[token]` | Accept invitation | Join org with assigned role | P0 |
| **ONBOARDING** |||||
| O-01 | `/onboarding/profile` | Business profile | Industry picker, business model, B2B/B2C, size band, locations, currency, fiscal-year start, timezone, goals | P1 |
| O-02 | `/onboarding/tools` | Tool discovery: "What do you use?" | Catalog search with logos, category chips, "not listed" free text, desktop/legacy toggle, file-only option | P4 |
| O-03 | `/onboarding/plan` | Acquisition plan | Per tool: channel badge (API/DB/Browser/Bridge/File/Concierge), coverage, effort, "Connect" CTA, progress checklist | P4 |
| O-04 | `/onboarding/consent` | Consent & data processing | Purposes, LLM processing mode, retention defaults, DPA acceptance (versioned) | P1 |
| O-05 | `/onboarding/status` | Onboarding progress tracker | Live timeline: connected → ingesting → profiling → mapping (needs you: N) → readiness → toolkit ready | P4 |
| **HOME** |||||
| H-01 | `/` | Home dashboard | Pipeline health strip, freshness, DQ score, "Needs your attention" tasks (reviews, re-auth), toolkit summary, latest insights | P0 shell → P3 full |
| **DATA SOURCES (Floor 1)** |||||
| S-01 | `/sources` | Sources overview | Table: source, channel, status, last sync, freshness, rows, errors; filters; "Add source" | P1 |
| S-02 | `/sources/catalog` | Connector catalog | Searchable grid, categories, coverage badges, "Request a connector" | P4 |
| S-03 | `/sources/new/api/[connector]` | Connect: API / OAuth | Dynamic form from `spec()` JSON Schema, OAuth button, stream picker, schedule, test | P4 |
| S-04 | `/sources/new/database` | Connect: Database | Engine picker, host/port/db, SSL, SSH tunnel, "create read-only user" snippet, test, table picker | P5 |
| S-05 | `/sources/files` | File upload centre | Drag-drop (resumable, multi-file, folders), upload history and parse status, email-in address, SFTP credentials, cloud-drive pickers | P1 |
| S-06 | `/sources/browser/[sessionId]` | Assisted browser session | Live remote-browser canvas, mode switch (Guided/Recipe/AI), step approval panel, download tray, session timer, kill | P6 |
| S-07 | `/sources/bridge` | Bridge Agent: setup & devices | Download installers, pairing code, agent list (online, version, host), local adapters (Tally, ODBC, folders), revoke | P5 |
| S-08 | `/sources/[sourceId]` | Source detail | Tabs: Overview · Streams/Tables · Schedule · Sync history · Schema & drift · Settings (re-auth, disconnect, delete data) | P1 |
| S-09 | `/sources/[sourceId]/runs/[runId]` | Sync run detail | Timeline, per-stream counts, warnings, errors, quarantined rows, logs, retry | P1 |
| **DATA STUDIO (Floor 2)** |||||
| D-01 | `/studio/datasets` | Data inventory | All raw datasets by source; detected domain/entity; mapping status; rows; DQ | P1 |
| D-02 | `/studio/datasets/[id]` | Dataset explorer & profile | Virtualized grid preview, column profile panel (stats, semantic type, PII badge), source locator | P1 |
| D-03 | `/studio/mapping/[datasetId]` | Mapping workbench | Left: source columns · Centre: React Flow links · Right: CBM fields; confidence chips; DSL expression editor with autocomplete; dry-run preview (before/after); accept, edit, reject; version history | P2 |
| D-04 | `/studio/reviews` | Review queue | All pending items (mappings, drift, low-confidence classifications) with priority and bulk actions | P2 |
| D-05 | `/studio/entities/resolve` | Entity-resolution review | Candidate duplicate clusters, side-by-side compare, match-weight explanation, merge/split/not-duplicate | P7 |
| D-06 | `/studio/quality` | Data quality centre | Scores by domain, failing rules, quarantined rows, waive (with reason), trend | P7 |
| D-07 | `/studio/model` | Business model explorer | Browse CBM entities (tables, filters, record detail with source_refs) + graph view (P7: React Flow/Cytoscape neighbourhood explorer) | P2 → P7 |
| D-08 | `/studio/pipeline` | Pipeline & lineage | TPS versions + diff, run history, lineage graph (source → raw → silver → core → tool), replay/rollback | P7 |
| D-09 | `/studio/readiness` | Data readiness report | DRP visualised: domain coverage, history depth, completeness, "connect X to improve Y" | P2 basic → P7 full |
| **TOOLKIT / ENGINE BAY (Floor 3)** |||||
| T-01 | `/toolkit/recommendation` | Toolkit recommendation | Primary / Secondary / Locked columns, "why" explanations, unlock hints, activate toolkit CTA, diff since last assessment | P3 |
| T-02 | `/toolkit/marketplace` | Tool marketplace | All tools, category filters, eligibility badge per tenant, price, search | P3 |
| T-03 | `/toolkit/tools/[toolId]` | Tool detail | Description, data requirements vs your readiness (✓/✗), sample output preview, version, price, activate/add-on | P3 |
| T-04 | `/toolkit/mine` | My tools | Active tools, schedule, last run status, run now, pause, parameters | P3 |
| T-05 | `/toolkit/tools/[toolId]/runs/[runId]` | Tool workspace / results | Renders InsightResult blocks; run history; params; logs (for admins); evidence links. **This is the engine output slot.** | P3 |
| T-06 | `/insights` | Insights feed | Cross-tool insights, filters, pins, share link (internal), action proposals with approve/reject (no execution) | P3 |
| **BILLING** |||||
| B-01 | `/billing` | Plan & subscription | Current plan, primary-tool cap, usage meters, upgrade/downgrade | P8 |
| B-02 | `/billing/addons` | Add-ons & checkout | Secondary tools cart, pricing, tax (GST/VAT), checkout via Stripe/Razorpay | P8 |
| B-03 | `/billing/invoices` | Invoices, payment methods & usage | Invoice list (PDF), payment methods, billing details/GSTIN, usage history | P8 |
| **SETTINGS** |||||
| G-01 | `/settings/org` | Organisation profile | Edit business profile (re-triggers assessment), region (read-only), currency, timezone | P0 |
| G-02 | `/settings/team` | Team & roles | Invite, role assignment, remove, pending invites | P0 |
| G-03 | `/settings/security` | Security | MFA policy, active sessions, API keys, IP allowlist (enterprise) | P0 |
| G-04 | `/settings/audit` | Audit log | Filterable audit events incl. DCS staff access | P0 |
| G-05 | `/settings/governance` | Data governance | LLM processing mode, PII settings, retention, cross-tenant learning opt-out, sub-processors, export all data, DSR tools, delete organisation | P9 |
| G-06 | `/settings/notifications` | Notification preferences | Email/in-app per event type | P0 |
| **SYSTEM** |||||
| X-01 | `/notifications` | Notification centre | All notifications, mark read, deep links | P0 |
| X-02 | `/help` | Help & concierge request | Guides, "Request DCS help" (creates concierge case), case status | P6 |
| X-03 | `/(system)` | System pages | 404, 403, 500, maintenance, session-expired | P0 |

### 9.3 Admin console pages (13)

| ID | Route | Page | Purpose | Phase |
|---|---|---|---|---|
| M-01 | `/` | Platform dashboard | Tenants, active syncs, queue depth, failure rates, LLM spend, sandbox utilisation | P0 shell → P9 |
| M-02 | `/tenants` | Tenants list | Search, plan, region, health, onboarding stage | P0 |
| M-03 | `/tenants/[id]` | Tenant detail | Profile, sources, pipeline status, DRP, toolkit, billing, break-glass request, deprovision | P0 → P9 |
| M-04 | `/connectors` | Connector registry | Catalog entries, coverage evidence, versions, enable/disable, per-connector health and error rates, catalog candidates triage | P4 |
| M-05 | `/recipes` | Browser recipe library | Draft recipes from AI Navigator, step replay, test run, publish, health checks | P6 |
| M-06 | `/bridge` | Bridge agent fleet | Agents by tenant, version, online status, staged update rollout, revoke | P5 |
| M-07 | `/model` | CBM & mapping templates | CBM versions, field dictionary, connector mapping templates, Mapping Memory stats | P2 |
| M-08 | `/concierge` | Concierge queue | Escalated reviews, onboarding help cases, unsupported formats | P2 → P6 |
| M-09 | `/tools` | Tool registry | Import by digest, manifest view, contract-test result, assignment thresholds, rollout/retire | P3 |
| M-10 | `/plans` | Plans & pricing | Tiers, primary-tool caps, add-on prices, regional pricing, coupons | P8 |
| M-11 | `/llm` | Model Gateway & LLM usage | Providers, routing rules, prompt versions, cost by tenant and task, error rates | P2 |
| M-12 | `/security` | Audit & staff access | Staff actions, break-glass approvals, hash-chain verification status | P0 |
| M-13 | `/settings` | System settings & feature flags | Flags per tenant/plan, maintenance mode, global limits | P0 |

### 9.4 UI standards
- Design tokens in `packages/ui` (shadcn/ui + Tailwind). Light and dark themes. WCAG 2.1 AA.
- Every list: server-side pagination, filters synced to the URL, empty state with the next action.
- Long operations show **live status over WebSocket** with no manual refresh.
- Numbers formatted by tenant locale (Indian grouping for INR tenants), dates in the tenant timezone.
- i18n-ready (English first; strings in `messages/en.json`).

---

## 10. SERVICE APIs

All APIs: REST + JSON, OpenAPI 3.1, `/v1` prefix, cursor pagination, idempotency keys on POSTs that start work, and RFC 9457 problem+json errors.

### 10.1 control-api (selected)

| Method & path | Purpose |
|---|---|
| `GET /v1/me`, `GET /v1/orgs/{id}`, `PATCH /v1/orgs/{id}/profile` | Session, org, business profile |
| `POST /v1/orgs/{id}/invites`, `PATCH /v1/memberships/{id}` | Team |
| `GET /v1/catalog?q=&category=`, `GET /v1/catalog/{id}` | Connector catalog |
| `POST /v1/acquisition-plan` (tools[]) → items | Acquisition Router |
| `POST /v1/sources`, `GET /v1/sources`, `GET/PATCH/DELETE /v1/sources/{id}` | Source config |
| `POST /v1/sources/{id}/check`, `POST /v1/sources/{id}/discover`, `POST /v1/sources/{id}/sync` | Connector ops |
| `GET /v1/oauth/{provider}/start`, `GET /v1/oauth/callback` | OAuth broker |
| `POST /v1/uploads` (tus endpoint `/v1/tus/*`) | Resumable uploads |
| `POST /v1/browser-sessions`, `DELETE /v1/browser-sessions/{id}`, `WS /v1/browser-sessions/{id}/stream` | Remote browser |
| `POST /v1/bridge/pairing-codes`, `GET /v1/bridge/agents`, `DELETE /v1/bridge/agents/{id}` | Bridge |
| `GET /v1/registry/tools`, `GET /v1/registry/tools/{id}` | Tool registry (read) |
| `POST /v1/assessments`, `GET /v1/toolkit/recommendation` | Assignment |
| `POST /v1/toolkit/activate`, `POST /v1/tools/{id}/runs`, `GET /v1/tools/{id}/runs` | Tool lifecycle |
| `GET /v1/billing/plans`, `POST /v1/billing/checkout`, `POST /v1/billing/webhooks/{provider}` | Billing |
| `GET /v1/audit` | Audit |
| `GET /v1/notifications`, `WS /v1/events` | Notifications and live status |
| `POST /v1/hooks/{connector}/{sourceId}` | Inbound vendor webhooks |
| `/v1/admin/*` | Admin console endpoints (staff scope) |

### 10.2 data-api (tenant-scoped, selected)

| Method & path | Purpose |
|---|---|
| `GET /v1/datasets`, `GET /v1/datasets/{id}`, `GET /v1/datasets/{id}/rows?cursor` | Inventory, preview |
| `GET /v1/datasets/{id}/profile` | Profiles |
| `GET /v1/mappings?status=`, `GET/PUT /v1/mappings/{datasetId}` | Mapping specs |
| `POST /v1/mappings/{datasetId}/dry-run`, `POST /v1/mappings/{datasetId}/accept` | Validate and accept |
| `POST /v1/dsl/validate` | DSL type-check + autocomplete |
| `GET /v1/reviews`, `POST /v1/reviews/{id}/decision` | Review queue |
| `GET /v1/er/clusters`, `POST /v1/er/clusters/{id}/decision` | ER |
| `GET /v1/dq/summary`, `GET /v1/dq/failures`, `POST /v1/dq/waivers` | DQ |
| `GET /v1/core/{entity}?filters`, `GET /v1/core/{entity}/{id}`, `GET /v1/graph/neighbourhood/{nodeId}` | Model explorer |
| `GET /v1/tps`, `GET /v1/tps/{v}/diff/{v2}`, `POST /v1/tps/replay` | Pipeline |
| `GET /v1/lineage?node=` | Lineage |
| `GET /v1/drp` | Readiness |
| `GET /v1/results/runs/{runId}`, `GET /v1/insights`, `POST /v1/action-proposals/{id}/decision` | Results |
| `POST /v1/dsr/export`, `POST /v1/dsr/erase` | Data-subject requests |

---

## 11. DATABASE SCHEMAS

### 11.1 Control DB (`dcs_control`), main tables

```sql
org(id uuid pk, name, slug unique, region, status, plan_id, business_profile jsonb,
    profile_version int, created_at)
app_user(id uuid pk, keycloak_sub unique, email citext unique, name, created_at)
membership(id, org_id fk, user_id fk, role, status, invited_by, created_at)
tenant_key(org_id pk, kms_key_arn, wrapped_dek bytea, created_at, rotated_at)
tenant_db(org_id pk, cluster, db_name, status, cbm_version, created_at)
connector_catalog(id text pk, display_name, categories text[], deployment, spec jsonb,
                  coverage jsonb, verified_source text, verified_at, enabled bool, search tsvector)
catalog_candidate(id, org_id, raw_name, normalized_guess, status, created_at)
connector_version(connector_id, version, image_digest, released_at, status)
source(id uuid pk, org_id, catalog_id, channel, name, config jsonb /* non-secret */,
       status, schedule jsonb, last_sync_at, freshness_slo interval, created_by, created_at)
credential(id, org_id, source_id, kind, ciphertext bytea, nonce bytea, aad text,
           expires_at, rotated_at, created_at)            -- never plaintext
sync_state(source_id, stream, cursor jsonb, updated_at, pk(source_id, stream))
sync_run(id, org_id, source_id, workflow_id, status, started_at, finished_at, stats jsonb, error jsonb)
acquisition_plan_item(id, org_id, tool_label, catalog_id, channel, coverage, missing jsonb,
                      effort, status, source_id)
consent_record(id, org_id, source_id null, purpose, version, granted_by, granted_at, revoked_at)
bridge_agent(id, org_id, hostname, os, version, cert_fingerprint, last_seen_at, status, adapters jsonb)
browser_session(id, org_id, source_id, mode, status, started_by, started_at, ended_at, pod, recipe_id)
recipe(id, catalog_id, version, status /*DRAFT|REVIEW|PUBLISHED|RETIRED*/, body jsonb,
       created_from_session, reviewed_by, published_at)
tool(id text pk, name, category, latest_version, status)
tool_version(tool_id, version, image_digest, manifest jsonb, eri_version, contract_test jsonb,
             status, published_at)
toolkit_recommendation(id, org_id, version, drp_version, profile_version, items jsonb, created_at)
tool_activation(id, org_id, tool_id, pinned_version, tier /*PRIMARY|ADDON*/, status, schedule jsonb)
plan(id, name, primary_tool_cap, limits jsonb, prices jsonb)
subscription(id, org_id, plan_id, provider, provider_ref, status, current_period_end)
addon_subscription(id, org_id, tool_id, provider_ref, status)
entitlement(org_id, key, value jsonb, source, updated_at)
concierge_case(id, org_id, kind, status, assignee, payload jsonb, created_at)
notification(id, org_id, user_id, type, payload, read_at, created_at)
audit_event(id bigserial, ts, org_id, actor_type, actor_id, action, target_type, target_id,
            ip inet, ua, details jsonb, prev_hash bytea, hash bytea)
lineage_event(id, org_id, run_id, job, inputs jsonb, outputs jsonb, ts)   -- OpenLineage
llm_call(id, org_id, task, provider, model, prompt_version, tokens_in, tokens_out,
         cost_micros, latency_ms, status, ts)
feature_flag(key, scope, scope_id, value jsonb)
```

### 11.2 Tenant DB (`t_<id>`), schemas

| Schema | Tables / objects |
|---|---|
| `raw_registry` | `ingestion_batch` (manifest jsonb, checksums, status), `raw_dataset` (source_id, stream/sheet, bronze_uri, schema_snapshot, row_count, status), `dataset_profile`, `column_profile`, `review_item` |
| `mapping` | `mapping_spec` (dataset_id, version, status, spec jsonb, compiled_sql text, confidence, decided_by), `tps_version` (version, hash, body jsonb, created_by, created_at) |
| `stg_<source_slug>` | One table per raw dataset (typed, source-shaped), created by the compiler |
| `core` | CBM tables (§6.3) + `er_cluster`, `er_decision`, `fx_rate`, `pii_vault` (pseudonym map, restricted) |
| `core_quarantine` | Mirror tables of rejected rows + reason codes |
| `dq` | `rule`, `rule_result`, `waiver`, `score_snapshot` |
| `graph` | `nodes`, `edges` |
| `events` | `business_event` (partitioned by month) |
| `drp` | `snapshot` (version, body jsonb, created_at) |
| `engine_api_v1` | Read-only views over core/graph/events/drp, with explicit column lists; no PII columns unless approved |
| `results` | `tool_run`, `insight`, `artifact`, `action_proposal`, `action_decision` |
| `documents` | `document`, `chunk` (text + pgvector embedding) for unstructured content |

---

## 12. REPOSITORY STRUCTURE & CONVENTIONS

```
dcs-pis/
├─ CLAUDE.md                     # rules for Claude Code (template §17.11)
├─ Makefile                      # dev, test, lint, codegen, reset, seed, e2e
├─ docker-compose.yml            # full local stack
├─ apps/
│  ├─ web/                       # Next.js customer app
│  └─ admin/                     # Next.js admin console
├─ services/
│  ├─ control_api/               # FastAPI
│  ├─ data_api/                  # FastAPI
│  ├─ realtime_gw/
│  ├─ model_gateway/
│  └─ bridge_relay/              # Go
├─ workers/
│  ├─ acquire/  parse/  browser/  shape/  engine_bay/
├─ connectors/                   # one package per connector (dlt-based)
│  └─ hubspot/ shopify/ razorpay/ ...
├─ recipes/                      # browser recipes (yaml)
├─ oauth_providers/              # provider yaml
├─ catalog/seed/                 # connector catalog seed yaml
├─ bridge_agent/                 # Go agent + installers (msi, deb, rpm)
├─ engine/
│  ├─ reference_tools/           # test motor tools
│  └─ README.md                  # how the engine team plugs in
├─ packages/
│  ├─ py/dcs_common  dcs_cbm  dcs_connector_sdk  dcs_tool_sdk  dcs_dsl  dcs_authz  dcs_vault
│  └─ ts/ui  api-client  config
├─ infra/
│  ├─ terraform/  helm/  k8s/   # gVisor runtimeclass, network policies
├─ fixtures/
│  └─ corpus/                    # Messy Data Corpus (§14.5)
├─ tests/
│  ├─ e2e/ (Playwright)  isolation/  contract/  load/ (k6)  security/
└─ docs/
   ├─ PROGRESS.md  OPEN_QUESTIONS.md  ENGINE_BACKLOG.md
   ├─ adr/  phases/  guides/  runbooks/
```

**Conventions**
- Python: ruff (lint + format), mypy strict, pytest + pytest-asyncio, hypothesis for DSL and parser property tests. Settings via pydantic-settings.
- TS: eslint, prettier, vitest, Playwright. No `any` without a comment.
- Migrations: Alembic for both control (`services/control_api/migrations`) and tenant (`packages/py/dcs_cbm/migrations`, applied to every tenant DB by `TenantMigrateWorkflow` with a canary-first rollout).
- Workflows: name `<Thing>Workflow`; activities idempotent; IDs `wf:<kind>:<tenant>:<natural-key>`.
- Logging: structured JSON with `tenant_id`, `trace_id`, `workflow_id`. **Never log secrets or raw PII values.**

---

## 13. PHASED BUILD PLAN

### 13.0 Phase map and why this order

```
P0 Foundations ─► P1 Files+Raw ─► P2 Shape core ─► P3 Engine Bay ══► ROLLING CHASSIS (end-to-end MVP)
                                                                      │
      ┌───────────────────────────────────────────────────────────────┘
      ▼
P4 API connectors ─► P5 DB+Bridge+Legacy ─► P6 Assisted Browser ─► P7 Shape advanced ─► P8 Billing ─► P9 Hardening & Launch
```

**Why not strictly floor by floor?** Building a thin vertical slice first (files → shape → engine bay) proves every contract (Manifest, Mapping Spec, DRP, ERI, InsightResult) end-to-end by Phase 3. Each later acquisition channel then only has to produce a valid Ingestion Manifest, and everything downstream already works and is tested. This avoids building five acquisition channels into a pipeline that doesn't exist yet.

| Phase | Name | Indicative duration* | Pages delivered |
|---|---|---|---|
| P0 | Foundations | 2 weeks | 18 |
| P1 | Floor 1a: Files & Raw Zone | 3 weeks | 8 |
| P2 | Floor 2a: Profiling, CBM, LLM Mapping, Transform | 4 weeks | 7 |
| P3 | Floor 3: Engine Bay & Marketplace (MVP milestone) | 3 weeks | 7 |
| P4 | Floor 1b: API Connectors, OAuth, Catalog, Onboarding | 4 weeks | 6 |
| P5 | Floor 1c: Databases, Bridge Agent, Legacy | 3 weeks | 3 |
| P6 | Floor 1d: Assisted Browser & Concierge | 4 weeks | 3 |
| P7 | Floor 2b: ER, DQ, Graph, Events, Lineage, Drift | 3 weeks | 3 (+2 upgrades) |
| P8 | Commercial: Billing & Entitlements | 2 weeks | 4 |
| P9 | Hardening, Compliance, Launch | 3 weeks | 1 (+ completion) |
| | **Total** | **~31 weeks** | **60** (H-01, D-07, D-09, M-01, M-03 are upgraded in later phases) |

\*For 3–4 engineers working with Claude Code. These are planning estimates, not commitments.

---

### PHASE 0: FOUNDATIONS

**Objective:** A secure, multi-tenant, observable skeleton. You can sign up, a tenant is provisioned with its own DB and key, and you see an empty app shell.

**Scope (in):** monorepo, CI, docker-compose stack (Postgres, Temporal, Redis, MinIO, Keycloak, Mailpit, ClamAV, Grafana stack), control-api skeleton, data-api skeleton, realtime-gw, Keycloak realm + Keycloakify theme, org/user/membership/RBAC, `ProvisionTenantWorkflow`, Vault (dev KMS), audit log with hash chain, notifications (in-app + email), feature flags, web and admin shells with navigation, design system, codegen, ADRs 0001–0010, CLAUDE.md, PROGRESS.md.
**Scope (out):** any data ingestion.

**Tasks**
| ID | Task |
|---|---|
| P0-T1 | Monorepo scaffolding (pnpm/turbo + uv), Makefile targets, pre-commit (ruff, mypy, eslint, gitleaks) |
| P0-T2 | docker-compose with healthchecks; `make dev`, `make reset`, `make seed` |
| P0-T3 | GitHub Actions: lint, type-check, unit, integration (services), build images, SBOM (syft), vuln scan (grype/trivy) |
| P0-T4 | Keycloak realm-as-code (export JSON), Keycloakify theme for A-01…A-05, MFA policies |
| P0-T5 | control-api: auth middleware (OIDC JWT validation), org context, RBAC policy engine (`dcs_authz`), problem+json errors, OpenAPI |
| P0-T6 | Control DB schema v1 (org, app_user, membership, tenant_key, tenant_db, audit_event, notification, feature_flag) + RLS |
| P0-T7 | `ProvisionTenantWorkflow` + `DeprovisionTenantWorkflow` (dev: local key service; prod: KMS adapter interface) |
| P0-T8 | `dcs_vault` envelope-encryption library + tests (incl. AAD tamper tests) |
| P0-T9 | Audit library: `audit.emit()` + hash chain + nightly verification job |
| P0-T10 | data-api skeleton with `TenantContext` + per-tenant pool + isolation guard |
| P0-T11 | realtime-gw WebSocket with org-scoped channels |
| P0-T12 | web shell: layout, sidebar, org switcher, H-01 placeholder, G-01…G-04, G-06, X-01, X-03 |
| P0-T13 | admin shell: staff SSO realm, M-01, M-02, M-03 (basic), M-12, M-13 |
| P0-T14 | OpenTelemetry tracing across web → API → Temporal → worker; Sentry |
| P0-T15 | Write ADR-0001…0010, CLAUDE.md, docs/PROGRESS.md |

**Pages:** A-01…A-05, H-01 (shell), G-01, G-02, G-03, G-04, G-06, X-01, X-03, M-01, M-02, M-03, M-12, M-13 (18)

**Tests required**
- Unit: RBAC policy matrix (every role × permission), vault encrypt/decrypt/rotate/tamper, audit hash chain
- Integration: signup → provisioning creates DB, roles, key and prefixes; invite flow; role change takes effect immediately
- Isolation: two tenants created; tenant A's token cannot read tenant B through any data-api route (generated test across all routes)
- E2E (Playwright): sign-up → MFA enrol → land on home; invite a user → accept → limited role sees limited nav
- Security: gitleaks clean, dependency scan with no criticals, headers (CSP, HSTS) present

**Acceptance criteria**
- [ ] `make reset && make dev` boots all services healthy in under 5 minutes on a 16 GB laptop
- [ ] New signup gets a provisioned tenant (DB, 4 roles, key, prefixes) in under 30 s; visible in M-02
- [ ] Deprovisioning removes the DB and prefixes and marks the key for deletion; audit shows every step
- [ ] Audit chain verification passes; a tampered row is detected by the job
- [ ] All 18 pages render with loading, empty, error and forbidden states
- [ ] CI green; coverage ≥ thresholds (§14.3)

**Demo script:** sign up "Northwind Fitness" → enable MFA → invite an analyst → show tenant DB in psql → show audit trail → show M-02.

---

### PHASE 1: FLOOR 1a, FILES & RAW ZONE

**Objective:** Any file in any supported format becomes immutable raw data plus registered, previewable raw datasets with traceability back to the cell or page.

**Scope (in):** resumable uploads (tus → S3 multipart), email-in, SFTP drop, ClamAV, magic-byte sniffing, archive recursion with bomb limits, the full **format registry** from §5.7 (all families except bank-PDF templates, which reach v1 in P1 and are improved later), Bronze Parquet writer, Ingestion Manifest v1, raw_registry tables, basic profile (row counts, column names, inferred types), dataset preview API, O-01 business profile, O-04 consent.
**Scope (out):** semantic mapping (P2), cloud-drive pickers (P4, which need OAuth), Bridge folder watch (P5).

**Tasks**
| ID | Task |
|---|---|
| P1-T1 | Upload service (tus server in control-api or tusd sidecar) + S3 multipart + checksum (SHA-256) |
| P1-T2 | `IngestFileWorkflow` (scan → sniff → route → parse → bronze → manifest → register) |
| P1-T3 | Parser plugin framework (`FormatParser` protocol: `detect()`, `parse()` → Arrow tables + locators) |
| P1-T4 | Parsers: delimited, spreadsheet (multi-table detection, multi-row headers), JSON/XML/YAML, columnar, statistical, SQLite |
| P1-T5 | Parsers: SQL dumps & MSSQL .bak via **ephemeral restore containers** (sandboxed, no network) |
| P1-T6 | Parsers: MS Access (mdbtools), DBF/FoxPro, Tally XML exports, QuickBooks IIF/QBO, OFX/QIF/MT940/CAMT |
| P1-T7 | Parsers: documents (Docling + pdfplumber + Tesseract with eng/hin), images OCR, email (eml/msg/mbox/pst), vcf/ics, fixed-width + COBOL copybook/EBCDIC |
| P1-T8 | Archive handler + bomb protection; unsupported-format quarantine + concierge case stub |
| P1-T9 | Email-in (SES inbound → S3 → workflow; dev: Mailpit + MinIO) with sender allowlist; SFTP (per-tenant chroot, SSH keys) |
| P1-T10 | Ingestion Manifest v1 JSON Schema (§17.1) + validator + writer |
| P1-T11 | data-api: datasets list, detail, rows (cursor pagination from Parquet via DuckDB), basic profile |
| P1-T12 | Pages: O-01, O-04, S-01, S-05, S-08 (file-source variant), S-09, D-01, D-02 |
| P1-T13 | Build **Messy Data Corpus v1** (§14.5): ≥ 120 fixture files across all families, each with an expected-output snapshot |

**Pages:** O-01, O-04, S-01, S-05, S-08, S-09, D-01, D-02 (8)

**Tests required**
- Unit/property: each parser against corpus snapshots (golden tests); hypothesis fuzzing of CSV dialects and encodings; header detection accuracy ≥ 95% on corpus
- Security: zip bomb, nested archive depth, path traversal in archives (`../../`), EICAR test file, malformed XLSX and PDF must not crash the worker (it is isolated, and errors are quarantined)
- Integration: upload 2 GB CSV resumable (kill connection mid-way → resume); email-in with attachment; SFTP drop
- Idempotency: the same file uploaded twice → deduplicated by checksum (user may force re-ingest)
- E2E: upload a ZIP with xlsx + csv + pdf → all datasets appear in D-01 with correct locators in D-02

**Acceptance criteria**
- [ ] 100% of corpus files either parse to the expected snapshot or are quarantined with a correct reason code
- [ ] Every Bronze row traces back to the file and to its sheet/row or page/table (`__dcs_source_locator`)
- [ ] Landing objects are immutable (Object Lock in staging/prod; MinIO retention in dev)
- [ ] A 1M-row CSV is ingested and previewable in under 3 minutes on the dev stack
- [ ] Parsers run without network and as non-root (verified by test)

**Demo script:** upload `northwind_members.xlsx` (merged headers, two tables in one sheet), `tally_daybook.xml`, `old_billing.mdb`, `scan_invoice.jpg` → show datasets, profiles, and locators.

---

### PHASE 2: FLOOR 2a, PROFILING, CBM, LLM MAPPING, TRANSFORM

**Objective:** Raw datasets become rows in the canonical `core` schema through templates or LLM-proposed, human-reviewed, compiled mappings. A basic DRP is produced.

**Scope (in):** full profiling (§6.2), `dcs_cbm` package (CBM v1 models → migrations, field dictionary, TS types, `engine_api_v1` views), Model Gateway (providers, masking, prompt registry, metering, cache), classification, field-mapping proposals, Transform DSL (grammar, type-checker, compiler → SQL), dry-run, review queue, Mapping Workbench, Mapping Memory, silver/core loaders (upsert), basic TPS, basic DRP v1, CBM admin and templates, LLM usage admin, concierge queue (mapping escalations).
**Scope (out):** ER, DQ beyond basic dry-run checks, graph, events (P7).

**Tasks**
| ID | Task |
|---|---|
| P2-T1 | `ProfileWorkflow` full (§6.2), incl. semantic detectors (email, phone, GSTIN, amounts with Indian grouping, date formats, Excel serials) |
| P2-T2 | `dcs_cbm`: entity models for all v1 entities (§6.3); generators for migrations, field dictionary (with synonyms in English + Hinglish + regional variants), `engine_api_v1` views, TS types |
| P2-T3 | Model Gateway: provider adapters (Anthropic, Groq, OpenAI-compatible, vLLM), JSON-schema-constrained output with retry, PII masking, prompt registry (versioned files), cost metering to `llm_call`, response cache keyed by (prompt version, input hash) |
| P2-T4 | Classification: rules → embeddings (pgvector) → LLM tie-break; confidence calibration on corpus |
| P2-T5 | `dcs_dsl`: Lark grammar, AST, type checker against CBM types, compiler → DuckDB SQL and Postgres SQL; 100% function coverage tests |
| P2-T6 | Field-mapping proposer (LLM) → MappingSpec draft; filter/unpivot detection |
| P2-T7 | Dry-run engine on a 1,000-row sample with before/after diff + basic assertions |
| P2-T8 | Auto-accept policy (τ_auto) + review item creation; human decisions update Mapping Memory |
| P2-T9 | Loaders: bronze → `stg_<source>` (DuckDB → Postgres COPY) → `core` (upsert by `(source_id, stream, source_pk)`; `hash_id` when there is no PK) |
| P2-T10 | Connector mapping template format (used in P4) + 3 templates for file-based common exports (Tally day book, generic invoice register, generic customer list) |
| P2-T11 | TPS v1 (sources + mappings) + versioning + replay from bronze |
| P2-T12 | DRP v1 generator (presence, counts, history span, completeness) + JSON Schema (§17.3) |
| P2-T13 | Pages: D-03, D-04, D-07 (entity browse), D-09 (basic); admin M-07, M-08, M-11 |

**Pages:** D-03, D-04, D-07, D-09, M-07, M-08, M-11 (7)

**Tests required**
- Unit: DSL grammar and type checker (property tests: generated valid ASTs compile; invalid ones are rejected with precise errors); amount and date parsers (Indian grouping, `Cr/Dr`, parentheses negatives)
- **Mapping accuracy benchmark** on the corpus with a labelled ground truth: entity classification top-1 ≥ 90%; field mapping F1 ≥ 0.85 before review; 0 incorrect auto-accepts on the "trap" datasets (look-alike columns)
- Privacy: snapshot tests that prompt payloads contain no raw PII values (scanner over every logged prompt)
- Prompt-injection corpus: cells containing instructions must not change output beyond the schema; the DSL never executes code
- Determinism: same TPS version + same bronze → byte-identical core rows (hash compare)
- Replay: change a mapping → replay → core is updated; the old version can be restored
- E2E: upload a customer xlsx → auto-mapped → one field needs review → owner accepts in the Workbench → rows visible in D-07

**Acceptance criteria**
- [ ] Every corpus dataset reaches `ACCEPTED` (auto or after scripted review) and loads into core without errors
- [ ] No LLM is involved in executing transforms (verified: the compile/execute path has no Model Gateway dependency, enforced by an import-linter rule)
- [ ] Workbench supports accept/edit/reject, DSL autocomplete, and a live dry-run in under 3 s for 1,000 rows
- [ ] DRP v1 is generated and validates against the schema
- [ ] LLM cost per dataset is logged; median cost and latency are reported in the gate doc

**Demo script:** continue "Northwind Fitness": members.xlsx → Party + Person + Membership; Tally day book → Invoice + Payment via template; show review of the ambiguous "Amt" column; show the core rows and the DRP.

---

### PHASE 3: FLOOR 3, ENGINE BAY & MARKETPLACE (ROLLING-CHASSIS MILESTONE)

**Objective:** Plug in the reference tools through the ERI, assign a toolkit (Primary/Secondary/Locked) from the DRP, run tools in a sandbox, and render the results. **At the end of P3 the car drives with the test motor.**

**Scope (in):** Tool Manifest schema + registry import + contract tests; `dcs_tool_sdk` + local harness; reference tools (§7.7); `AssessmentWorkflow` with RuleScorer + `AssignmentScorer` interface; entitlement service (stubbed plan: primary cap 5, add-ons free in dev); `ToolRunWorkflow` + sandbox (dev docker; staging K8s gVisor); results store; InsightResult renderer (all block types); action-proposal approval (no execution); schedules; H-01 complete.
**Scope (out):** real billing (P8).

**Tasks**
| ID | Task |
|---|---|
| P3-T1 | JSON Schemas: Tool Manifest, ToolRunRequest, InsightResult (§17.4–17.6) + Pydantic models + TS types |
| P3-T2 | Registry import (digest, cosign verify, manifest validate, DRP-path validation, contract test run) |
| P3-T3 | `dcs_tool_sdk` (decorator, ctx, progress, emit, exit codes) + `dcs-tool` CLI (validate, run, contract-test) |
| P3-T4 | Reference tools ×9 (§7.7) packaged as images |
| P3-T5 | `AssessmentWorkflow`: eligibility evaluator (requirements DSL over DRP paths), RuleScorer, classification, explanations, recommendation versioning and diff |
| P3-T6 | Entitlement service + Redis cache |
| P3-T7 | `ToolRunWorkflow`: ephemeral DB creds (`engine_ro`, VALID UNTIL), sandbox launcher (docker / K8s Job w/ gVisor + NetworkPolicy), log/progress streaming, output validation, storage, cleanup |
| P3-T8 | Insight renderer (Vega-Lite allowlist validator, sanitised Markdown) + action-proposal approval |
| P3-T9 | Pages: T-01…T-06, H-01 full; admin M-09 |
| P3-T10 | `engine/README.md`: the engine team's integration guide (build, test, submit a tool) |

**Pages:** T-01, T-02, T-03, T-04, T-05, T-06, M-09 (+H-01 completed) (7 new)

**Tests required**
- Contract: every reference tool passes `dcs-tool contract-test`; a tool with an invalid manifest or output is rejected with clear errors
- Sandbox security: a tool attempting network egress, a write outside `/dcs/out`, reading `core` directly (not views), or a fork bomb → blocked or killed; tests assert each one
- Assignment: table-driven tests: (profile, DRP) fixtures → expected Primary/Secondary/Locked sets; cap overflow → secondary; unlock hints are correct
- Failure paths: `ref.fail` (retries then failed), `ref.slow` (timeout), `ref.insufficient` ("needs more data" UI)
- Credential lifecycle: engine DB user exists only during the run (asserted before, during and after)
- E2E: from a fresh tenant: upload corpus files → mapping → DRP → assessment → activate toolkit → run → see the revenue chart

**Acceptance criteria**
- [ ] A new tool image (with no exoskeleton code changes) can be imported, assigned, activated and run: proven by building a 10th dummy tool during the gate
- [ ] All InsightResult block types render correctly (visual regression snapshots)
- [ ] Assessment re-runs automatically when the DRP changes, and T-01 shows a diff
- [ ] The sandbox has no egress (verified with a network test) and runs under gVisor in staging
- [ ] **Rolling chassis demo passes** end-to-end on staging

**Demo script:** "Northwind Fitness" → toolkit shows `ref.revenue_by_month` and `ref.customer_count` as Primary, `ref.top_products` as Locked ("connect your POS/sales data"). Run it → chart. Approve a `ref.action` proposal (level 2) → stored, not executed.

---

### PHASE 4: FLOOR 1b, API CONNECTORS, OAUTH, CATALOG, ONBOARDING DISCOVERY

**Objective:** Owners pick their tools, get an Acquisition Plan, and connect ≥ 25 SaaS systems via API with OAuth or keys, incremental syncs and webhooks. Each lands in raw and flows through the existing pipeline with pre-built mapping templates.

**Scope (in):** Catalog Research Spike; catalog (≥ 150 researched entries); Acquisition Router; Connector SDK on dlt; OAuth broker; key/basic-auth flows; scheduler; rate limiting; webhooks; cloud-drive pickers (Drive, OneDrive, Dropbox → File pipeline); 25 connectors with CBM templates; onboarding O-02, O-03, O-05.

**Connector set for P4 (25):** hubspot, salesforce, zoho_crm, pipedrive, freshsales, leadsquared · quickbooks_online, xero, zoho_books, odoo · stripe, razorpay, paypal · shopify, woocommerce, amazon_seller · meta_ads, google_ads, linkedin_ads · google_analytics_4, google_search_console · mailchimp, klaviyo · freshdesk, zendesk · *(+ google_sheets, google_drive, onedrive, dropbox as file-feeders)*. If a vendor's developer approval blocks testing (e.g., Amazon SP-API, LinkedIn Ads), swap it for the next in the catalog and record this in OPEN_QUESTIONS.

**Tasks**
| ID | Task |
|---|---|
| P4-T1 | **Catalog Research Spike:** verify the coverage of every seed entry (§5.3.1) with evidence URLs; produce `docs/research/connector_coverage.md` |
| P4-T2 | Catalog DB + search (pg_trgm + tsvector) + admin M-04 + candidate triage |
| P4-T3 | Acquisition Router (§5.2) incl. LLM name normalisation (proposal only) |
| P4-T4 | `dcs_connector_sdk` on dlt: spec/check/discover/read, state, rate limits, Parquet + landing writers, manifest |
| P4-T5 | OAuth broker + provider YAMLs + refresh workflow + NEEDS_REAUTH handling |
| P4-T6 | Scheduler (Temporal Schedules), freshness tracking, webhook ingress |
| P4-T7 | 25 connectors + VCR cassettes + CBM mapping templates (so no LLM is needed for known connectors) |
| P4-T8 | Cloud-drive pickers feeding `IngestFileWorkflow` |
| P4-T9 | Pages: O-02, O-03, O-05, S-02, S-03; admin M-04 |
| P4-T10 | Optional: Airbyte-protocol adapter spike (licence check per connector) → ADR-0011 go/no-go |

**Pages:** O-02, O-03, O-05, S-02, S-03, M-04 (6)

**Tests required**
- Connector contract suite (auto-generated from spec): check/discover/read behaviour, pagination end, cursor monotonicity, schema stability, rate-limit backoff (simulated 429s), token refresh on 401
- VCR replay tests for every connector stream (no live calls in CI); a nightly live-sandbox job against vendor developer accounts where available
- Resume test: kill the worker mid-sync → resume from checkpoint, no duplicates (row-hash compare)
- Template tests: cassette data → core rows equal golden snapshots
- OAuth security: state tampering, replayed callbacks, cross-tenant callbacks rejected
- E2E: onboarding → select HubSpot + Razorpay + an unknown tool → plan shows API/API/FILE+AI options → connect HubSpot (mock OAuth in CI) → data in core → toolkit updates

**Acceptance criteria**
- [ ] 25 connectors pass the contract suite; each has a template mapping ≥ 90% of its streams to the CBM
- [ ] Catalog has ≥ 150 entries with verified coverage + evidence
- [ ] Incremental syncs read only changed data (verified by cassette cursor tests)
- [ ] A token expiry → auto-refresh; a revoked token → NEEDS_REAUTH + notification within 5 min
- [ ] The owner sees the full Acquisition Plan for a mixed list of tools in under 5 s

---

### PHASE 5: FLOOR 1c, DATABASES, BRIDGE AGENT, LEGACY

**Objective:** Reach data in client databases and on-premise legacy software (Tally, Access, FoxPro, local SQL, AS/400 via ODBC) safely, without inbound firewall changes.

**Scope (in):** DB connectors (Postgres, MySQL/MariaDB, MSSQL, Oracle, MongoDB, SQLite, BigQuery, Snowflake); static egress IPs; SSH tunnels; read-only user snippets; snapshot + incremental; Bridge Relay (Go); Bridge Agent (Go) with adapters `tally`, `odbc`, `sql`, `files`, `report_spool`; installers (MSI signed, deb, rpm); pairing; auto-update; Tally CBM template (masters + vouchers); pages S-04, S-07, M-06.

**Tasks**
| ID | Task |
|---|---|
| P5-T1 | DB connectors on the SDK (keyset pagination, cursor detection, statement timeouts, read-only tx) |
| P5-T2 | SSH tunnel support + Vault-stored keys; static NAT egress documented in the UI |
| P5-T3 | bridge-relay (gRPC/mTLS, job routing, agent registry, revocation) |
| P5-T4 | bridge-agent core (service install, pairing, mTLS, job loop, spool, throttling, logs, auto-update with signature check) |
| P5-T5 | Adapters: tally (XML collections for masters + date-chunked vouchers, multi-company), odbc, sql, files (watch + checksum), report_spool |
| P5-T6 | Installers + code signing pipeline (Windows Authenticode; Linux GPG) |
| P5-T7 | Tally and generic ODBC CBM templates |
| P5-T8 | Pages: S-04, S-07; admin M-06 |

**Pages:** S-04, S-07, M-06 (3)

**Tests required**
- DB: testcontainers for each engine with seeded schemas (incl. weird types, 10M-row table sampling); guard tests prove that DDL and writes are impossible
- Bridge: agent ↔ relay integration in CI (Linux); a Windows VM job (GitHub Actions windows runner) for the MSI install/uninstall and service lifecycle
- Tally: a **Tally simulator** (a mock HTTP server replaying recorded XML from real TallyPrime exports in the corpus), plus a manual verification step against a real TallyPrime educational-mode instance, documented in the gate
- Security: an agent cannot run untyped jobs; revoked certificates are refused; update with a bad signature is refused; relay isolation between tenants
- Chaos: agent offline mid-job → spool → resume on reconnect

**Acceptance criteria**
- [ ] The owner installs the agent on Windows 10/11 and Windows Server 2016+ in under 5 minutes, pairs it, and sees Tally companies listed
- [ ] Tally ledgers and vouchers for 3 financial years land in core via the template
- [ ] Zero inbound ports needed (documented with a network test)
- [ ] A DB connector against a 10M-row table runs without degrading the source (respects the chunk size and statement timeout)

---

### PHASE 6: FLOOR 1d, ASSISTED BROWSER EXTRACTION & CONCIERGE

**Objective:** The owner can sign in to any web tool inside an isolated DCS browser. DCS captures the exports (Guided), runs a published Recipe, or explores with an approved AI Navigator that produces new recipes.

**Scope (in):** browser-worker pods, CDP screencast streaming + input relay, per-session egress proxy + allowlist, download capture → File pipeline, Guided mode, Recipe engine + format (§5.8.3), AI Navigator with step approvals + destructive-action policy, Draft-recipe → review → publish lifecycle, optional storage-state vault for re-sync, consent screen, concierge workflow + help page; pages S-06, M-05, X-02.

**Tasks**
| ID | Task |
|---|---|
| P6-T1 | browser-worker: pod-per-session lifecycle, Chromium hardening flags, fresh profile, download dir quarantine |
| P6-T2 | Streaming: CDP `Page.startScreencast` → WS → canvas; input relay (mouse, keys, IME, paste); adaptive quality; latency target < 150 ms p50 in-region |
| P6-T3 | Egress proxy with per-session allowlist (catalog domains + IdP domains) |
| P6-T4 | Recipe runtime (YAML → Playwright), parameter templating, `expect_download`, email-link capture (via the tenant email-in) |
| P6-T5 | AI Navigator: screenshot + accessibility-tree summary → Model Gateway (vision) → proposed action (schema) → policy check → owner approval → execute; trace → Draft Recipe |
| P6-T6 | Destructive-action policy engine + `browser_prohibited` catalog flag |
| P6-T7 | Storage-state vault (cookies only, TTL) + scheduled recipe runs + re-auth notifications |
| P6-T8 | Recipe admin (M-05): replay a trace, test against a demo account, publish, health checks |
| P6-T9 | Concierge cases end-to-end (X-02 → M-08 → resolution) |
| P6-T10 | Pages: S-06, X-02, M-05 |

**Pages:** S-06, X-02, M-05 (3)

**Tests required**
- A local **mock SaaS** app (a fixture web app with login, MFA, a reports page, a CSV export, an async email export, and a "Delete all" trap button) for deterministic E2E tests
- Recipe E2E against the mock SaaS: login (by a test user) → recipe → CSV → core
- AI Navigator: scripted LLM responses (cassettes) → it must stop at the "Delete all" trap (policy block) and at CAPTCHA (hand-over)
- Isolation: a session cannot reach non-allowlisted domains (SSRF test to the metadata IP 169.254.169.254 and to internal services); no clipboard exfiltration; the pod is destroyed after the session
- Load: 20 concurrent sessions on staging with stable frame rates

**Acceptance criteria**
- [ ] Guided mode works on any site in the allowlist; downloads appear in D-01 within 60 s
- [ ] Recipe mode completes the mock-SaaS export unattended after login
- [ ] AI Navigator produces a Draft Recipe that, after publishing, replays successfully
- [ ] Passwords never touch DCS storage (verified by inspecting what is stored + code review checklist)
- [ ] Every automated step is in the audit log

---

### PHASE 7: FLOOR 2b, ENTITY RESOLUTION, DATA QUALITY, GRAPH, EVENTS, LINEAGE, DRIFT

**Objective:** Make the Intelligence DB trustworthy and connected: one golden customer across sources, quality scored, relationships materialised, events derived, full lineage, graceful handling of schema drift.

**Scope (in):** §6.6–6.10 entirely; full TPS (ER/DQ/graph/events config); DRP v2 (DQ, freshness, business signals); pages D-05, D-06, D-08, plus D-07 graph view and D-09 full.

**Tasks**
| ID | Task |
|---|---|
| P7-T1 | Splink ER pipeline (blocking, comparisons, thresholds), clusters, survivorship rules, reversible decisions |
| P7-T2 | DQ rule engine + default rule pack per entity + quarantine + waivers + scores |
| P7-T3 | Graph builder (FK edges + inferred edges with confidence) + neighbourhood API |
| P7-T4 | Event catalogue + derivation (diff- and webhook-based) + validator |
| P7-T5 | OpenLineage emission from all workers + lineage graph API |
| P7-T6 | Schema drift detection + handling (§6.10) |
| P7-T7 | DRP v2 + Assessment re-trigger rules |
| P7-T8 | Pages: D-05, D-06, D-08; upgrade D-07 (graph), D-09 (full) |

**Pages:** D-05, D-06, D-08 (3 new) + upgrades of D-07 (graph view) and D-09 (full DRP)

**Tests required**
- ER benchmark on corpus Tenant E (planted duplicates with typos, transliterations such as "Sharma Traders" / "Sharma Trdrs" / "शर्मा ट्रेडर्स", phone formats): precision ≥ 0.97 at auto-merge, recall ≥ 0.85
- DQ: each rule class has positive and negative fixtures; CRITICAL failures block DRP readiness
- Drift: scripted source changes (add, remove, rename, type change) → expected behaviours (§6.10)
- Lineage: any core row → trace back to the landing object + locator in ≤ 2 API calls
- Performance: ER on 1M parties completes in under 20 min on staging workers

**Acceptance criteria**
- [ ] Merges and splits are reversible and audited; downstream tools see the updated golden IDs after the next run
- [ ] Every core row has lineage to raw
- [ ] Events conform to the catalogue (undeclared events rejected)
- [ ] DRP v2 includes DQ and freshness; Assessment reacts to changes

---

### PHASE 8: COMMERCIAL, BILLING & ENTITLEMENTS

**Objective:** Real subscriptions with Primary tools included, Secondary tools as add-ons, regional pricing and tax-correct invoices.

**Scope (in):** `BillingProvider` interface + Stripe + Razorpay adapters; plans (configurable in M-10); checkout; webhooks (idempotent); proration; dunning (grace period → read-only mode, never data deletion); GST invoices (GSTIN capture, place of supply) via Razorpay/own invoice PDF; VAT for UK/EU via Stripe Tax; entitlements wired to the runner and to the marketplace UI; usage meters (rows ingested, tool runs, LLM spend) for future usage-based pricing; pages B-01…B-03, M-10.

**Tests required:** provider sandbox E2E (Stripe test clocks, Razorpay test mode); webhook replay and out-of-order events; downgrade below the primary cap → user chooses which tools to keep; failed payment → grace → restricted → recovered.

**Acceptance criteria**
- [ ] An INR tenant pays via Razorpay with a GST invoice; a GBP tenant pays via Stripe with VAT
- [ ] Add-on purchase → tool runnable within 10 s (entitlement cache invalidation)
- [ ] No billing state can delete tenant data

**Pages:** B-01, B-02, B-03, M-10 (4)

---

### PHASE 9: HARDENING, COMPLIANCE, ADMIN COMPLETION & LAUNCH

**Objective:** Production-ready: secure, compliant, observable, recoverable, performant.

**Scope (in):** G-05 data governance (LLM mode, retention, DSR export/erasure, delete org); break-glass flow; key rotation; backups (PITR for Postgres, S3 versioning) + **restore drills**; DR runbook (RPO 15 min / RTO 4 h targets); load tests; third-party pen test + fixes; threat-model review; runbooks; SLOs and alerting; cost dashboards per tenant; M-01/M-03 completion; documentation for customers (export guides, Bridge setup, browser consent FAQ); legal review checklist (DPA, ToS, privacy policy, sub-processors).

**Tests required:** k6 load (500 concurrent users, 200 concurrent syncs, 50 tool runs/min); soak 24 h; chaos (kill Temporal worker / Postgres failover / S3 latency); DSR erase verified by a search across all zones; restore drill from backup into a clean environment.

**Acceptance criteria**
- [ ] Pen-test criticals and highs closed
- [ ] Restore drill meets RPO/RTO
- [ ] SLO dashboards and on-call alerts live
- [ ] All 60 pages pass accessibility checks (axe) and visual regression
- [ ] Launch checklist signed off by the founder

**Pages:** G-05 (1) + completion of M-01, M-03

---

## 14. GLOBAL TESTING STRATEGY

### 14.1 Test pyramid & tooling

| Level | Tooling | Runs |
|---|---|---|
| Unit | pytest, hypothesis, vitest | Every commit |
| Integration | pytest + testcontainers (Postgres, MinIO, Temporal test server, Redis, Keycloak) | Every PR |
| Contract | JSON-Schema contract suites (manifest, mapping spec, DRP, tool manifest, InsightResult), connector contract suite, `dcs-tool contract-test` | Every PR |
| Isolation | Generated cross-tenant access tests over every data-api and control-api route | Every PR (blocking) |
| E2E | Playwright (web + admin) against the full docker-compose stack with the seeded corpus | Every PR (smoke) + nightly (full) |
| Visual regression | Playwright screenshots (InsightResult blocks, key pages) | Nightly |
| Security | gitleaks, trivy/grype, semgrep, ZAP baseline, sandbox escape tests, SSRF tests | PR + nightly |
| Performance | k6 (API), Locust (workers), DuckDB benchmarks | Weekly + phase gates |
| Chaos | Kill workers, network partitions (toxiproxy), DB failover | Phase gates P4+ |

### 14.2 Rules
- Never call live vendor APIs in CI. Use VCR cassettes. Live checks run in a separate nightly job with developer accounts.
- Never send real PII to LLMs in tests. Use a deterministic **fake LLM provider** in the Model Gateway that replays cassettes; live-LLM accuracy benchmarks run nightly on synthetic data only.
- Every bug fix adds a regression test.

### 14.3 Coverage thresholds
`packages/py/*` ≥ 90% · `dcs_dsl` and `dcs_vault` and `dcs_authz` ≥ 95% (branch) · services ≥ 80% · workers ≥ 80% · web ≥ 70% (components + hooks).

### 14.4 Connector contract suite (auto-generated)
For every connector: spec is valid JSON Schema; `check` fails gracefully on bad credentials; `discover` is stable; `read` paginates to the end; the cursor never goes backwards; the checkpoint/resume yields no duplicates; schema matches the declared one ±new columns; 429/5xx are retried with backoff; 401 triggers refresh; the manifest is valid.

### 14.5 Messy Data Corpus (fixtures/corpus/)
Synthetic but realistic businesses. **All data is fake** (generated with Faker using the en_IN and en_GB locales plus hand-crafted edge cases):

| Tenant | Business | Sources simulated | Edge cases planted |
|---|---|---|---|
| A: Northwind Fitness | Multi-branch gym (B2C, memberships) | Members Excel (merged headers), Razorpay cassettes, Meta Ads cassettes, WhatsApp chat export | Duplicate members, DD/MM vs MM/DD dates, phone formats |
| B: Kesari Naturals | D2C e-commerce (India) | Shopify, Razorpay, Meta Ads, Google Sheets, Zoho Books cassettes; Shiprocket CSV | Refunds, partial payments, GST lines, multi-currency |
| C: Arjun Traders | Wholesale trader (legacy) | Tally XML (3 FYs), MS Access .mdb, FoxPro .dbf, scanned invoices (JPG), PDF bank statements | Cr/Dr amounts, Hindi party names, subtotal rows, lakh grouping |
| D: Brightpath Agency | UK B2B services agency | HubSpot, QuickBooks Online, Google Ads, LinkedIn Ads, Jira cassettes; MSSQL .bak | VAT, GBP/EUR/USD, long sales cycles |
| E: Chaos Co. | Adversarial | Broken encodings, zip bombs (safe), prompt-injection cells, look-alike columns, 2 tables per sheet, EBCDIC file + copybook, schema drift sequences | Everything that should be quarantined or flagged |

Each fixture has `expected/` snapshots (bronze schema, mapping ground truth, core rows, DRP, toolkit).

### 14.6 Tenant isolation test generator
At test start, introspect the OpenAPI specs. For every route with tenant-scoped data, create tenants A and B, seed an object in B, then call the route as A using B's object IDs in path, query and body. **Expect 404/403, never data.** The build fails if any route is not covered, so new routes must declare their isolation behaviour.

---

## 15. ENVIRONMENTS, DEVOPS & OBSERVABILITY

| Env | Purpose | Infra |
|---|---|---|
| `local` | Development | docker-compose; MinIO; local key service; fake LLM default (switch with `LLM_MODE=live`) |
| `ci` | Automated tests | GitHub Actions + testcontainers |
| `staging` | Gate demos, E2E, load | K8s (EKS or k3s on EC2) in ap-south-1; gVisor node pool; real KMS; sandbox vendor accounts |
| `prod-in` | Production India | ap-south-1, Multi-AZ RDS/Aurora Postgres (or self-managed with Patroni), S3 Object Lock, KMS |
| `prod-uk` | Production UK/EU | eu-west-2, same topology |

- **Deploy:** GitHub Actions → build → sign (cosign) → push to ECR → Helm upgrade via Argo CD (GitOps). Migrations run as pre-upgrade Jobs; tenant migrations canary on 5% of tenants, then all.
- **Node pools:** `system`, `api`, `workers-cpu`, `workers-browser` (sized for Chromium), `sandbox-gvisor` (tainted, tool runs only).
- **Observability:** RED metrics per service; Temporal metrics; per-tenant pipeline SLOs (time from ingestion to core, sync success rate); LLM cost per tenant per day; alerts to on-call (PagerDuty/Opsgenie or Slack).
- **Backups:** Postgres PITR (7–35 days by plan), daily logical dumps of tenant DBs to S3 (encrypted with the tenant key); S3 versioning + cross-region replication *within the same legal jurisdiction only*.
- **Cost guards:** per-tenant quotas (storage, rows/month, LLM spend/day, sandbox minutes) enforced by the entitlement service; alert at 80%.

---

## 16. RISKS, CONSTRAINTS & OPEN DECISIONS

| # | Risk / constraint | Impact | Mitigation / decision needed |
|---|---|---|---|
| R1 | **Browser extraction vs vendor Terms of Service.** Some SaaS terms restrict automated access even with the account owner's consent. | Legal and account-suspension risk for clients | Prefer official exports; owner consent + responsibility notice; per-vendor legal review before publishing a recipe; `browser_prohibited` flag; kill switch. **Founder + counsel decision before P6 GA.** |
| R2 | **"All data via API" is rarely literal.** APIs often have plan gates (Salesforce editions), aggregation (GA4), no history (WhatsApp), or approval gates (Amazon SP-API, LinkedIn). | Coverage gaps | The coverage model (§5.3) is shown honestly in the UI; complementary channels are auto-planned |
| R3 | **LLM processing of client data** | Trust and compliance | Masking by default, self-hosted option, per-tenant consent, sub-processor disclosure |
| R4 | **Licensing of integration tooling** (Airbyte Core and Nango are under Elastic licences) | Inability to offer as a service | dlt (Apache-2.0) as the runtime; per-connector licence checks; ADR-0003/0004 |
| R5 | **Bridge Agent on old client PCs** (Windows 7/8, low RAM) | Install failures | Support Windows 10+ officially; best-effort build for older Windows; file-export fallback |
| R6 | **Mapping errors propagating to insights** | Wrong decisions | Confidence thresholds, dry-runs, DQ gates, lineage, reversible TPS, owner review |
| R7 | **Cost per tenant** (LLM, browser pods, sandbox) | Margin | Templates first (no LLM for known connectors), caching, quotas, usage metering |
| R8 | **Engine team contract drift** | Integration pain | ERI is versioned; contract test is mandatory; a shared CI job runs the engine team's tools against exoskeleton staging nightly |
| R9 | **Account Aggregator / bank data** | Regulatory | Out of scope until a licensed FIU partner + legal review (Phase 9+) |

**Open decisions for the founder (log answers in `docs/OPEN_QUESTIONS.md`):**
1. Plan tiers: how many Primary tools per tier, and add-on price bands (INR / GBP / USD)?
2. Default LLM provider for mapping (quality vs cost) and whether a self-hosted model is offered at launch.
3. Is DCS concierge onboarding a paid service or included for some tiers?
4. Launch regions: India + UK simultaneously, or India first?
5. Does the Engine team need `features` (a precomputed feature store) from the exoskeleton, or do tools compute their own? (The default is that tools compute their own; the ERI is extensible.)
6. Brand/product naming of this exoskeleton within DCS-PIS (internal codename `EXO`).

---

## 17. APPENDICES

### 17.1 Ingestion Manifest v1 (`contracts/ingestion_manifest.v1.json`, example)
```json
{
  "manifest_version": "1.0",
  "batch_id": "0193f0e2-7a1c-7c3e-9a51-2b6f1d9e4a10",
  "tenant_id": "t_9x2k",
  "source_id": "src_hubspot_01",
  "channel": "API",
  "connector": { "id": "hubspot", "version": "1.4.2" },
  "extracted_at": "2026-11-05T10:12:00Z",
  "window": { "from": "2026-11-05T09:00:00Z", "to": "2026-11-05T10:12:00Z", "mode": "incremental" },
  "streams": [
    {
      "stream": "contacts",
      "primary_key": ["id"],
      "cursor_field": "updatedAt",
      "landing_uris": ["s3://…/landing/src_hubspot_01/contacts/batch=…/page-0001.jsonl.zst"],
      "bronze_uri": "s3://…/bronze/src_hubspot_01/contacts/batch=…/",
      "row_count": 1834,
      "schema_snapshot_hash": "sha256:…",
      "checksums": { "bronze": "sha256:…" },
      "state_after": { "updatedAt": "2026-11-05T10:11:58Z" },
      "warnings": []
    }
  ],
  "consent_record_id": "cr_…",
  "producer": { "service": "acquire-worker", "version": "0.4.0", "workflow_id": "wf:sync:t_9x2k:src_hubspot_01:…" }
}
```
For files, `streams[]` holds one entry per extracted table, with `"source_locator": {"file":"members.xlsx","sheet":"Jan","range":"A3:K412"}`.

### 17.2 Mapping Spec v1 (example)
```yaml
mapping_spec_version: "1.0"
dataset_id: rds_7f2a              # members.xlsx / sheet "Members" / table 1
target_entity: person
also_creates: [membership]
version: 3
status: ACCEPTED
confidence: 0.93
row_filters:
  - exclude: regex_match(col("Name"), "^(Total|TOTAL)$")
source_pk: hash_id(col("Member ID"))
fields:
  full_name:      { expr: 'title(trim(col("Name")))', confidence: 0.99 }
  phone_e164:     { expr: 'phone_e164(col("Mobile No"), "IN")', confidence: 0.97 }
  email:          { expr: 'email_norm(col("Email"))', confidence: 0.98 }
  date_of_birth:  { expr: 'parse_date(col("DOB"), "%d/%m/%Y")', confidence: 0.88, decided_by: user_12 }
  attributes.branch_code: { expr: 'col("Branch")', confidence: 1.0 }
child_mappings:
  membership:
    fields:
      person_id:   { expr: 'ref(person)' }
      plan_name:   { expr: 'col("Plan")' }
      start_date:  { expr: 'parse_date(col("Joined"), "%d-%b-%y")' }
      amount_minor:{ expr: 'to_minor(parse_amount(col("Fee"), "en_IN"), lit("INR"))' }
provenance: { proposer: "llm:claude:mapping-prompt@v7", reviewed_by: "user_12", reviewed_at: "2026-11-05T11:00:00Z" }
```

### 17.3 Data Readiness Profile v1 (abridged)
```json
{
  "drp_version": "1.0",
  "tenant_id": "t_9x2k",
  "generated_at": "2026-11-05T12:00:00Z",
  "tps_version": "1.7.0",
  "cbm_version": "1.0",
  "business_signals": {
    "revenue_model": ["subscription", "transactional"], "b2c_ratio": 0.96,
    "locations": 4, "currencies": ["INR"], "channels": ["offline", "online"]
  },
  "entities": {
    "invoice": {
      "present": true, "rows": 18234, "parties": 1240,
      "history": { "first": "2024-08-01", "last": "2026-11-04", "months": 27, "gap_months": 0 },
      "completeness": { "issued_at": 1.0, "total_minor": 1.0, "party_id": 0.98, "due_at": 0.41 },
      "dq_score": 0.94, "freshness_hours": 2.1, "sources": ["src_tally_01", "src_razorpay_01"]
    },
    "ad_performance_daily": { "present": false }
  },
  "domains": { "finance": "READY", "sales": "PARTIAL", "marketing": "MISSING", "people": "MISSING" }
}
```

### 17.4 Tool Manifest v1 (example)
```json
{
  "manifest_version": "1.0",
  "eri_version": "1.0",
  "id": "ref.revenue_by_month",
  "name": "Revenue by Month",
  "version": "0.1.0",
  "category": "finance.revenue",
  "kind": "analysis",
  "description": "Monthly invoiced revenue (reference tool).",
  "requirements": {
    "all": [
      { "path": "entities.invoice.present", "op": "eq", "value": true },
      { "path": "entities.invoice.history.months", "op": "gte", "value": 1 },
      { "path": "entities.invoice.completeness.total_minor", "op": "gte", "value": 0.9 }
    ]
  },
  "relevance": {
    "base": 0.5,
    "factors": [
      { "when": { "path": "business_signals.revenue_model", "op": "contains_any", "value": ["transactional", "subscription"] }, "weight": 0.3 },
      { "when": { "path": "entities.invoice.history.months", "op": "gte", "value": 12 }, "weight": 0.2 }
    ],
    "core_for_industries": ["*"]
  },
  "tier_hint": { "primary_eligible": true, "addon_price": null },
  "reads": ["engine_api_v1.invoice", "engine_api_v1.party"],
  "params_schema": { "type": "object", "properties": { "months": { "type": "integer", "default": 12, "maximum": 60 } } },
  "outputs": ["kpi", "timeseries"],
  "schedule_default": "0 6 * * *",
  "compute": { "cpu": "1", "memory": "1Gi", "timeout_s": 300, "retries": 1 },
  "unlock_hints": { "entities.invoice.present": ["zoho_books", "tally_prime", "quickbooks_online", "razorpay"] }
}
```

### 17.5 ToolRunRequest v1
```json
{
  "eri_version": "1.0", "run_id": "run_…", "tenant_id": "t_9x2k",
  "tool": { "id": "ref.revenue_by_month", "version": "0.1.0" },
  "params": { "months": 12 },
  "drp_snapshot_version": "drp_…",
  "db": { "dsn_env": "DCS_DB_DSN", "schema": "engine_api_v1" },
  "locale": { "currency": "INR", "timezone": "Asia/Kolkata", "number_format": "en_IN", "fiscal_year_start": "04-01" },
  "trigger": { "type": "schedule|manual|event", "by": "user_12" },
  "deadline": "2026-11-05T12:05:00Z"
}
```

### 17.6 InsightResult v1
```json
{
  "eri_version": "1.0", "run_id": "run_…", "tool_id": "ref.revenue_by_month", "status": "ok",
  "generated_at": "2026-11-05T12:01:10Z",
  "insights": [
    {
      "id": "ins_1", "title": "Invoiced revenue, last 12 months", "importance": "medium",
      "blocks": [
        { "type": "kpi", "label": "Total (12m)", "value": 48230000, "unit": "INR_minor", "delta": { "value": 0.12, "period": "yoy" } },
        { "type": "chart", "spec": { "$schema": "vega-lite-v5", "mark": "line",
            "data": { "values": [ { "month": "2025-12", "revenue": 3920000 } ] },
            "encoding": { "x": { "field": "month", "type": "temporal" }, "y": { "field": "revenue", "type": "quantitative" } } } },
        { "type": "narrative", "markdown": "Revenue grew **12%** year-on-year." }
      ],
      "evidence": [ { "entity": "invoice", "ids_query": "issued_at >= '2025-11-01'" } ],
      "confidence": 1.0
    }
  ],
  "action_proposals": [
    { "id": "ap_1", "title": "Send reminders for 23 overdue invoices", "governance_level": 2,
      "target": { "entity": "invoice", "ids": ["…"] }, "rationale": "…", "expires_at": "…" }
  ],
  "artifacts": []
}
```

### 17.7 Connector `spec()` (example: Razorpay)
```json
{
  "connector": "razorpay", "version": "1.0.0",
  "auth": [ { "type": "api_key_pair", "fields": ["key_id", "key_secret"] } ],
  "config_schema": { "type": "object", "properties": {
      "start_date": { "type": "string", "format": "date" },
      "streams": { "type": "array", "items": { "enum": ["payments", "orders", "refunds", "settlements", "invoices", "customers", "subscriptions", "plans", "disputes"] } } },
    "required": ["start_date"] },
  "rate_limit": { "strategy": "header_retry_after", "default_rps": 5 }
}
```

### 17.8 Tenant Pipeline Spec (TPS) skeleton
```json
{
  "tps_version": "1.7.0", "hash": "sha256:…", "cbm_version": "1.0",
  "sources": [ { "source_id": "src_tally_01", "schedule": "0 1 * * *" } ],
  "datasets": [ { "dataset_id": "rds_7f2a", "mapping_spec_version": 3 } ],
  "entity_resolution": { "party": { "blocking": ["email", "phone_e164", "gstin"], "auto_merge": 0.95, "review": 0.70,
                          "survivorship": { "legal_name": ["src_tally_01", "most_recent"] } } },
  "dq_rule_pack": "default@1.2", "dq_overrides": [],
  "graph": { "inferred_edges": ["INVOICE_FOR_ORDER"] },
  "events": { "enabled": ["invoice.paid", "invoice.overdue", "membership.expired"] }
}
```

### 17.9 Event catalogue entry
```yaml
- name: invoice.overdue
  entity: invoice
  trigger: "status != 'paid' AND due_at < now() AND previous(due_at >= now())"
  payload: { invoice_id: uuid, party_id: uuid, balance_due_minor: int, currency: str, days_overdue: int }
  version: 1
```

### 17.10 Phase Gate report template (`docs/phases/PHASE_<N>_GATE.md`)
```markdown
# Phase <N> Gate — <name>
Date: … | Commit: … | Tag: v0.<N>.0 | Reviewer: …
## Acceptance criteria
| # | Criterion | Status | Evidence (test id / screenshot / log) |
## Test summary
unit: x passed / coverage y% · integration: … · contract: … · isolation: … · e2e: … · security: … · perf: …
## Demo script result
steps → outcome (screenshots in docs/phases/assets/P<N>/)
## Contracts changed (with ADR links)
## Known issues / deferred (with issue IDs)
## Go / No-Go: ☐ GO ☐ NO-GO   — signed: …
```

### 17.11 `CLAUDE.md` template (place at repo root in Phase 0)
```markdown
# CLAUDE.md — DCS-PIS Exoskeleton
Source of truth: docs/SPEC.md (this build specification). Current phase: see docs/PROGRESS.md.
## Rules
- Work ONLY on the current phase scope. Out-of-scope ideas → docs/ENGINE_BACKLOG.md or OPEN_QUESTIONS.md.
- Contracts in /contracts are versioned. Changing one requires an ADR + version bump.
- LLM output = specs only. Never execute LLM output as code. Never compute business figures with an LLM.
- Every data-access path must go through TenantContext. Add isolation tests for new routes.
- Never log secrets or raw PII. Never commit .env files.
- Tests are mandatory (unit + integration minimum). Run `make test` before every commit.
## Commands
make dev | make reset | make seed | make test | make test-e2e | make lint | make codegen | make gate PHASE=N
## Style
Python: ruff + mypy strict, async SQLAlchemy, Pydantic v2. TS: strict, server components by default, shadcn/ui.
Commit format: conventional commits.
```

### 17.12 `docs/PROGRESS.md` template
```markdown
| Phase | Status | Started | Gate passed | Tag | Notes |
|---|---|---|---|---|---|
| P0 Foundations | ⬜ not started / 🟨 in progress / ✅ passed | | | | |
…
## Deferred items
## Open questions awaiting founder
```

### 17.13 Kick-off prompts for Claude Code (copy per phase)
```
PHASE START: "Read docs/SPEC.md §0, §13 Phase <N>, and every section it references.
Produce docs/phases/PHASE_<N>_PLAN.md. Do not write code until I approve the plan."

PHASE BUILD: "Implement PHASE_<N>_PLAN.md task by task. After each task: run make test,
commit, update the plan checklist. Stop and ask if a contract or security boundary is unclear."

PHASE GATE: "Run the full Phase <N> test suites and the demo script on a clean stack.
Fill docs/phases/PHASE_<N>_GATE.md with evidence. List anything failing. Do not mark GO
unless every acceptance criterion has evidence."
```

---

*End of specification. Engine team: start with `engine/README.md` (created in Phase 3), §7 and §17.4–17.6.*
