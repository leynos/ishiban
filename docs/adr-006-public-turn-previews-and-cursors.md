# Public turn previews and fixed-size detail cursors

## Status

Accepted for the proof of concept.

## Context

The journal and materialized session projection retain every observed active
turn. The first public response copied that entire set into snapshots, detail,
replay, and lazy activity frames. Detail pagination bounded historical turn
rows, but its first continuation embedded the full workspace, session, and turn
identifiers. Long accepted identifiers could make the cursor itself unusable.

## Decision

Keep the journal, sidecar, and materialized projections complete. After runtime
cache restoration, shape each public session into a deterministic preview of at
most 100 active turns, ordered by user turn identity and semantic facts. Include
`activeTurnCount`, `activeTurnsTruncated`, and `activeTurnsRevision`. The
revision is a SHA256 digest of the sorted full set of
`(userTurnId, state, error-or-null)` facts. It ignores input order, observation
timestamps, and metadata. Preserve the full private set while deriving session
state and `latestTurn`; the preview does not filter pending, waiting, or
unknown turns. Apply the same shaping to snapshot, detail, SSE, and individual
and batched lazy activity responses.

Use version 2 detail continuations containing the SHA256 digest of a structured
`(workspace_id, session_id)` scope, a positive event ID, and a positive rank
within that event's turn group. Both numbers fit signed 64-bit SQLite limits.
The reader counts rows through the page's last user turn ID within that event
group, using the same workspace, session, transaction, and SQLite collation as
the ordered page query. Continuation reads start at that event ID, skip the
rank, and fetch at most 101 rows to detect another page. This keeps token size
independent of accepted identifier length without changing stored rows or
schema. Version 1 tokens are rejected; clients restart at the first page.

## Consequences

Public active-turn arrays have a fixed item-count bound, and a hidden
same-count turn error still changes the semantic revision used for update cues.
Lazy enrichment remains quiet. Detail pages retain access to every current
historical turn, while each page reads the current projection. Concurrent turn
updates can shift ranks or reorder later pages; this is not a frozen snapshot.
Counting the rank and applying an offset can scan an event group, so large
groups may cost more database work than the version 1 keyset query. The
response still loads at most 101 turn rows per page.

The digest and preview sort still inspect the complete decoded private active
set, so private JSON size, SQL decode work, and process memory are not bounded
by this decision. Individual turn text and other public fields also have no new
byte-size cap. A future retention or private working-set policy needs a
separate design.
