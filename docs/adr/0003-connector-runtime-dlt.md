# ADR-0003: Connector runtime = dlt; Airbyte only via the MIT protocol adapter
- Status: Accepted
- Date: 2026-11-06
- Spec references: §4.1, §5.4, §16 R4

## Context
DCS-PIS is offered as a managed service. Airbyte Core is licensed under ELv2, which forbids offering it as a
managed service.

## Decision
Connectors are built on **dlt** (Apache-2.0), wrapped by the DCS Connector SDK. An optional adapter may run Airbyte
*protocol* (MIT) source images, but only where that connector's own `metadata.yaml` licence allows it. The licence
check is automated and blocks registration of a non-compliant image.

## Consequences
- dlt provides schema inference, incremental state and pagination helpers.
- The long tail is reached through the dlt REST API source and, where licensed, Airbyte protocol images.

## Alternatives considered
- Airbyte Core: rejected (licence).
- Singer taps: patchy maintenance; may be wrapped later behind the same SDK.
