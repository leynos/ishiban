# Batched activity reads and meaningful update cues

## Status

Accepted for the proof of concept.

## Context

Historical Lody catalogue entries have unknown activity. Individual browser
requests and two observer slots make the first concrete state slow to arrive.
Collector restarts also assign new revisions to unchanged observations, which
can animate many tasks without any meaningful change.

## Decision

Expose `POST /api/v1/sessions/activity` with a JSON `sessionIds` array, limited
to eight entries and an 8,192-byte body. Deduplicate identities and stream one
newline-delimited JSON frame per identity with `workspaceId`, `sessionId` and
an optional `session`. Cached results precede pending reads; pending results
arrive in completion order. Missing or unavailable sessions produce null
members without preventing other results. Operational storage failures in a
pending member also produce a null result; unrelated programming errors
propagate. Disconnecting cancels request waiters; the shared service retains
ownership of subprocess work.

Encode each public frame before streaming and include its newline in a
1,048,576-byte UTF-8 limit. If a valid result exceeds that limit, send
`{workspaceId, sessionId, outcome: "response_too_large"}` for that member
without a `session` key, then continue other members. Reject an identity whose
marker itself cannot fit with HTTP 413 before opening the stream. The browser
keeps its frame, body, and concurrency limits, and fetches one marked member
through the existing single-session activity route under the batch request's
deadline and cancellation owner. The fallback can read a complete public
response up to the existing eight-MiB body limit. Its `includeKnown=true`
option also returns current known evidence if the session changed after batch
preparation, without starting another CLI observation. If recovery fails or
exceeds its bound, show a quiet activity transport notice, retaining known
runtime facts and the Lody session link.

The browser coalesces visible marks into batches of four with at most two
streams active. It validates each frame independently, bounds stream size and
accepts results only against the current workspace, identity and revision. It
retains one pending lookup per identity through metadata replay. Queued marks
that leave the viewport are discarded before requesting their state.

The existing lazy reader owns four concurrent observers and at most 64 unique
pending observations across callers. A 45-second total lifetime bounds queue
waiting and execution; each child retains its 20-second read timeout. Existing
in-flight reads and TTL cache entries are reused before rejecting overflow. The
installed CLI has no bulk historical-state command; batching reduces HTTP work
and increases bounded parallelism but still opens one CLI observation for each
uncached session.

Key read reuse by the execution watermark rather than the metadata revision. A
late read can rebase onto newer metadata only while `lastActivityEventId`
remains unchanged and current state is unknown. New execution invalidates it.
Persist only runtime fields and return current metadata and revision. This
refines [ADR 004](adr-004-persist-on-demand-activity.md).

Pulse tracking compares meaningful task facts, excluding observation times,
revisions, generation, source and freshness bookkeeping. A new generation or
connecting state establishes a quiet baseline, including the first following
snapshot. Lazy runtime enrichment stays quiet. Changed task metadata and
execution after startup retain their update cues.

## Consequences

The first resolved member need not wait for a slower neighbour. Resource use
remains bounded, with shared work across tabs. Cold reads retain CLI startup
cost, and overload or unavailable observations can leave activity unknown. The
durable journal retains restart observations and exact stream/sequence
deduplication; pulse suppression belongs to the browser presentation.

The transport notice describes delivery failure, not a Lody turn error. A
single-session result over eight MiB remains unavailable through this fallback;
the accepted private observation and cache entry are not trimmed.

Batch verification includes a real ASGI-to-subprocess path using CmdMox's
command shims. The dev-only dependency removes ordinary command-fixture setup;
specialized transport-lifetime tests retain explicit process fixtures.
