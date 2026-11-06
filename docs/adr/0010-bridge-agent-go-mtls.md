# ADR-0010: Bridge Agent in Go, outbound-only mTLS
- Status: Accepted
- Date: 2026-11-06
- Spec references: §4.1, §5.9

## Context
Legacy data (Tally, MS Access, DBF, local SQL, folders) lives on customer machines, often old Windows PCs behind NAT
with no inbound connectivity.

## Decision
The Bridge Agent is a single static **Go** binary (Windows service / systemd). It opens an **outbound-only**
gRPC-over-mTLS connection to the Bridge Relay (also Go). It accepts typed jobs only, uses tenant-scoped
certificates, verifies signed updates and can be revoked from S-07 / M-06.

## Consequences
- No runtime to install on client machines; small footprint.
- Windows 10+ is supported officially; older Windows is best-effort with a file-export fallback (§16 R5).

## Alternatives considered
- .NET: Windows-only.
- Python: heavy install on client machines.
