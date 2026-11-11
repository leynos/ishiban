# Runtime evidence transition policy

## Status

Accepted for the proof of concept. Candidate-specific implementation and
validation are tracked in [PR #9](https://github.com/leynos/ishiban/pull/9).

## Context

Source-journal ingestion and on-demand sidecar restoration share projection
merge rules. Keeping those decisions inside a public JSON projection builder
couples runtime policy to storage field names and makes the decision boundary
harder to test independently. Moving all validated records to a new model would
widen this refactor without improving the required merge contract.

Existing projections can also contain unrelated or malformed legacy fields.
Decoding every saved projection into a stricter domain record would change
their treatment even where current merge rules preserve them.

## Decision

Keep typed observer records in `ishiban/domain.py`. Define pure runtime
transition decisions in `ishiban/runtime_evidence.py`, using existing typed
observations and envelopes as inputs and frozen, Python-named plans as outputs.
Plans identify runtime replacement or preservation, evidence provenance, and
named-turn retirement and activation. They perform no database, process,
network, clock or logging effects and expose no public JSON field names.

Keep the existing `storage/projections.py` entrypoints as adapters. They copy
the current projection, apply the selected plan, encode optional turn fields,
and retain the existing treatment of missing or malformed saved values. Both
journal ingestion and sidecar restoration continue through this same adapter.
The policy and encoding are specific to session runtime evidence; they are not
a generic event framework or a replacement for protocol validation.

Metadata refreshes preserve known runtime state, turns, evidence generation and
observation time. Persisted observations replace those runtime facts. Starting
a turn retires previous active versions of its identity and activates the new
running version; finishing it records the terminal version even when no start
was observed. Turn events do not infer session activity or PR stage.

## Consequences

The transition decisions can be tested without storage or public JSON. Adapter
tests retain compatibility checks for legacy projections, optional fields,
input immutability and bounded failed-turn errors. Existing journal and sidecar
tests verify their shared externally observable results.

The public response, source journal, sidecar, workflow classification and
database schema remain compatible. Typed `msgspec` records retain their
existing serialization declarations; replacing those records is outside this
decision.

## References

- [Persisted on-demand activity](adr-004-persist-on-demand-activity.md) defines
  sidecar ownership and restoration.
- [Observation design](ishiban-lody-observation-spike-design.md) records the
  projection merge rules and journal invariants.
