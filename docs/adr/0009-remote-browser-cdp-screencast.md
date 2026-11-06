# ADR-0009: Remote browser via CDP screencast (no VNC)
- Status: Accepted
- Date: 2026-11-06
- Spec references: §4.1, §5.8

## Context
Assisted browser extraction shows the customer a remote Chromium session and relays their input.

## Decision
Use **Playwright + Chromium** in ephemeral per-session containers. Frames are streamed with CDP
`Page.startScreencast` over WebSocket to a canvas, and input events are relayed back. Downloads and network capture
stay inside the pod. Hosted browser services are not used, because data would leave our boundary.

## Consequences
- Lighter than VNC, with full control of downloads, network capture and isolation.
- Needs a dedicated `workers-browser` node pool.

## Alternatives considered
- VNC / noVNC: heavier, worse UX.
- Hosted browser APIs: data leaves the boundary.
