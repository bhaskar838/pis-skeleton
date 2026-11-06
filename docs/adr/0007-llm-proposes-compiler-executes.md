# ADR-0007: LLM proposes, compiler executes
- Status: Accepted
- Date: 2026-11-06
- Spec references: §2 P2, §6.4, §8.8

## Context
LLMs help with understanding unknown data, but they are non-deterministic and can be prompt-injected through the
data itself. Business figures must be reproducible.

## Decision
LLM outputs are typed specs only (mappings, classifications, recipes), validated with Pydantic / JSON Schema and
retried automatically on validation failure. A deterministic compiler turns validated specs into SQL or Python that
runs without the LLM. No LLM computes a business figure, transforms rows directly or makes an irreversible
decision. All LLM calls go through the Model Gateway.

## Consequences
- Every Gold row is reproducible from Raw + TPS version.
- Prompt injection can at worst produce a bad *proposal*, which validation, confidence thresholds or human review
  catches.

## Alternatives considered
- Executing LLM-generated code directly: rejected (security and reproducibility).
