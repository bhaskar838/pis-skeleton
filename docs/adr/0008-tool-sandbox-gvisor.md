# ADR-0008: Tool sandbox = gVisor Kubernetes Jobs
- Status: Accepted
- Date: 2026-11-06
- Spec references: §4.1, §7, §8.8

## Context
From the exoskeleton's point of view, Engine tools are third-party code. They must not reach the network, other
tenants or the host.

## Decision
Tools run as **Kubernetes Jobs with the gVisor (`runsc`) RuntimeClass**, a deny-all egress NetworkPolicy, a
read-only root filesystem and CPU/memory/time limits, on a tainted `sandbox-gvisor` node pool. Images must be
signed (cosign) and are pulled by digest. Dev uses `docker run --network none --read-only`.

## Consequences
- Tool reads use temporary LOGIN users minted from `t_<id>_engine_ro` with `VALID UNTIL`.
- Firecracker can replace gVisor later for the enterprise tier, behind the same runner interface.

## Alternatives considered
- Plain containers: insufficient isolation.
- Firecracker: stronger but heavier to operate; later.
