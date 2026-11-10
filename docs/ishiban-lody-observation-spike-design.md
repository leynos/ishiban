# Ishiban: single-workspace Lody observation spike

**Status:** Accepted design; proof of concept implemented and validated
locally, including the follow-up interface refinements. Reported review
findings are addressed; the acceptance record documents one CodeScene advisory
and an unexplained CodeRabbit completion warning.

**Date:** 9 November 2026  
**Scope:** Read-only observation of one Lody Cloud workspace  
**Reference interface:**
[Ishiban panorama mockup](../reference/ishiban-mockup.html)

## 1. Decision and hypothesis

Build a thin observational vertical slice: a supervised `lody session observe`
process feeds an append-only SQLite event journal and materialized session/turn
projections. A Falcon ASGI API exposes an atomic snapshot and a
cursor-resumable Server-Sent Events (SSE) feed. A React + TypeScript
application uses Effect v4 for typed decoding and connection lifecycle, with
Tailwind CSS v4 and daisyUI v5 for semantic presentation.

**Hypothesis:** Lody's existing versioned observation protocol can drive a
responsive, restart-tolerant, read-only fleet view across a single workspace
without subscribing to raw Loro documents or introducing a second orchestration
control plane.

**Boundary:** The observer feed alone cannot establish workflow stage or task
success. The accepted PR conventions now use explicit catalogue associations
and read-only GitHub title/status enrichment. CI conclusions, issue progress,
and task-success inference remain outside this spike. See
[ADR 002](adr-002-workflow-evidence.md).

### Questions the spike must settle

1. Can we run one Lody observer continuously, even with hundreds of historical
   sessions, without excessive memory, synchronization or process churn?
2. Can we persist every accepted observer message and update the queryable
   projection in one transaction?
3. Can a browser disconnect, reconnect, reload or survive a collector restart
   without losing *recorded* Ishiban events or silently fabricating Lody
   outcomes?
4. Can the panorama remain useful and responsive with 120+ repository rows and
   uneven numbers of sessions?
5. What operational gaps remain in Lody's CLI contract, especially local-only
   operation, repository association and live progress?

## 2. Scope and explicit exclusions

### In scope

- Exactly one configured Lody Cloud workspace, identified by stable workspace
  ID where possible.
- Read-only execution of
  `lody session observe --workspace <selector> --all --jsonl --follow`.
- Durable local ingestion of the v1 JSONL envelope and independently recorded
  source-health transitions.
- Materialized session and turn projections, retaining evidence provenance and
  freshness.
- A local SQLite database via async SQLAlchemy and `aiosqlite`.
- Falcon ASGI snapshot, detail, health and resumable SSE endpoints.
- React/Effect v4 live fleet view, activity ledger and the supplied Ishiban
  visual language.
- **Optional, read-only catalogue enrichment:**
  `lody session list --workspace <selector> --all --json` on startup and at a
  configurable low frequency to obtain repo/project/branch, agent
  type/configuration and PR *metadata*. This is not a PR event feed.

### Out of scope

- Writing to Lody, acknowledging unread messages, cancelling agents, answering
  permissions or dispatching tasks.
- Direct Loro/Flock replication or modification of Lody's daemon or its
  internal schema.
- General GitHub/Ghillie and Linear ingestion; PR checks, review outcomes,
  issue progress, dependency resolution or task orchestration. Read-only
  associated PR title/status lookup is the sole GitHub exception.
- Inferring a work item's workflow stage from an agent's running/idle state.
- Multi-workspace aggregation, multi-user access, general-purpose event
  brokerage or horizontal API scaling.
- Full transcript or tool-output streaming. `session observe` is a state
  projection, not a token-level event log.

The SQLite database is **written by Ishiban**, but all interactions with Lody
remain read-only.

## 3. Grounded upstream contract

The Lody OSS implementation defines `SessionObserveEnvelope` with `version: 1`,
`streamId`, process-local `sequence`, `observedAt` (Unix milliseconds),
`workspaceId`, `type`, and event-specific fields.

| Lody event        | Consumer interpretation                                                                              |
| ----------------- | ---------------------------------------------------------------------------------------------------- |
| `snapshot`        | Baseline for a session, possibly metadata-only.                                                      |
| `ready`           | Initial workspace catalogue enumeration is complete; not all session histories are necessarily open. |
| `session.changed` | A meaningful *projected session field* changed.                                                      |
| `turn.started`    | A transition to running was observed.                                                                |
| `turn.finished`   | Durable outcome of `completed`, `failed` or `canceled`; not proof that code or tests succeeded.      |
| `session.removed` | Metadata confirms deletion, unlike archive.                                                          |

A session projection contains `sessionId`, optional `machineId` and `title`,
`archived`, `state`, `freshness`, `source`, optional `latestTurn`, and
`activeTurns`. Session state is `idle | pending | running | waiting | unknown`.
A turn's state can also be `completed | failed | canceled`.

**Non-negotiable semantics:**

- `source: metadata` means a cheap catalogue projection with unknown execution
  state. It has no completed-turn proof, even when `freshness: synced`.
- `source: persisted` means history/control scalars have been read.
  `freshness: synced` is data-read freshness, **not** proof of daemon or
  machine liveness.
- Existing turns establish a baseline; the observer does not replay old
  `turn.started` or `turn.finished` events. A completed turn may first appear in
  `latestTurn`.
- A turn can finish between reads without a corresponding observed start. An
  assistant turn may also reopen with the same IDs.
- `sequence` orders messages **within one observer process**. It is not a
  durable or globally comparable cursor; `streamId` changes across launches.
- Source errors may appear as an **unversioned** `{type:"error", error:"..."}`
  line. Nonzero exit, EOF and stderr are separate failure signals.
- Workspace follow watches one metadata catalogue and selectively opens
  candidate history rooms, with four concurrent opens. Historical idle rooms
  generally remain unopened. Body-only edits in unopened idle rooms are not
  guaranteed to appear.
- `session observe` currently follows the authenticated Cloud CLI path, **not**
  a local-only daemon attachment. Do not silently fall back to direct CRDT
  reads.
- The observer projection does **not** contain repo, branch, PR association, CI
  or workflow stage. PR-only metadata changes may produce no observation event.

References:

- [Lody observation specification](https://github.com/LodyAI/Lody/blob/main/specs/cli-session-observe.md)
- [Event types and projection](https://github.com/LodyAI/Lody/blob/main/apps/cli/src/commands/session-observe.ts)
- [Workspace observation](https://github.com/LodyAI/Lody/blob/main/apps/cli/src/commands/session-observe-workspace.ts)

## 4. Proposed topology and ownership

```text
Lody Cloud / Streams
        |
        | one authenticated CLI reader, JSONL stdout
        v
+-------------------------+         +---------------------------+
| Ishiban collector       |         | Falcon ASGI API            |
| asyncio subprocess      |         | snapshot / sessions / SSE  |
| validate / project      |         | read-only SQLAlchemy       |
| single SQLite writer    |         | SQLite reader              |
+------------+------------+         +------------+--------------+
             |                                   |
             +---------- SQLite WAL -------------+
                                                 |
                                      HTTP snapshot + SSE
                                                 |
                                        React / Effect v4
                                        Ishiban panorama
```

Use **two OS processes** in the spike: `python -m ishiban.collector` and a
single-worker Granian/Falcon ASGI service. The collector exclusively owns the
`lody` child process and writes to SQLite. The API only reads the database.
This isolates collector restarts from active browser connections and avoids the
complexity of Falcon lifespan task ownership or an extra broker.

For a handful of browser clients, the API can tail SQLite every 250 ms in
bounded batches per open SSE connection. The database is the synchronization
boundary. Do not introduce Redis, Valkey, NATS, a broker or in-process
cross-worker pub/sub yet. Run **one** API worker for the spike and reject a
second collector using a local process lock. If eventual fan-out becomes
material, revisit it using measurements.

Implementation layout is recorded in [Repository layout](repository-layout.md).
Python tests stay in the top-level `tests/` tree; the Bun frontend uses `src/`.

## 5. Collector protocol and lifecycle

1. Load exactly one workspace selector and SQLite URL from configuration. Reuse
   existing authenticated Lody CLI credentials; do not put authentication
   tokens in the SQLite file or browser.
2. Acquire the collector lock and create a new **local ingestion generation**;
   set collector health to `connecting` and distinguish all previous
   projections as *not yet revalidated in this generation*.
3. Spawn `lody` with `asyncio.create_subprocess_exec`, not a shell. Read stdout
   line by line with a maximum line size and bounded pending work. Drain stderr
   separately, with size limits and secret redaction.
4. Decode and validate v1 events; verify `workspaceId`, `streamId`, sequential
   `sequence` within a process and required payload fields. Do not reinterpret
   unknown schema versions as v1.
5. In one SQL transaction: insert the raw received event, apply the projection,
   and commit. Use `UNIQUE(workspace_id, source_stream_id, source_sequence)`
   for idempotency. The API can see the event only after the projection commit.
   Persist the **post-event public projection** with the journal row so
   reconnect replay does not reconstruct old events from the database's newest
   state.
6. On `ready`, mark *catalogue enumeration* ready, not every session fully
   synchronized. Fetch the optional read-only catalogue snapshot for repository
   enrichment.
7. On EOF, nonzero exit, parse failure or unrecoverable protocol error, record
   source health and last known valid event. Mark the collector disconnected;
   **do not** convert running turns to failed or idle. Restart with bounded
   exponential backoff and jitter.
8. On graceful shutdown, terminate the child, await cleanup, flush committed
   work and release the lock.

For malformed JSON, oversized lines, foreign workspace IDs, invalid ordering or
unexpected version changes, preserve a bounded redacted diagnostic, stop that
observer generation and restart or fail closed according to error category.
Never drop malformed lines and continue as if the stream were gap-free.

**Reconnect reconciliation:** A restarted Lody observer emits fresh snapshots.
Merge them with the stored projections while retaining previously proven
outcomes. When a new snapshot is metadata-only, update title/archive/machine
identity but do not erase a previously persisted terminal turn or pretend that
it was freshly verified. Store `last_evidence_generation` (last confirmed
persisted-state observation), `last_metadata_generation` (last catalogue
observation), `last_observed_at`, `source`, and `freshness` independently. A
metadata-only update must not advance the persisted-evidence generation. No
synthetic `turn.finished` event should result from reconciliation; the snapshot
is evidence of the current materialized state.

**Read-only catalogue enrichment:** `session list --all --json` supplies
repository/project and branch context, and possibly associated PR summaries.
Reconcile those fields under a separate provenance marker (`lody.catalogue`)
and only emit local `catalogue.changed` events when the stored projection
actually changes. The catalogue is eventually consistent with observation;
joining by stable Lody session ID is mandatory. Lody session catalogue entries
are not a complete repository inventory: a repository with no Lody session is
invisible to this spike unless separately supplied as demonstration data. Never
mistake a missing item in a partial/error response for a deletion. A periodic
interval around five minutes is a starting configuration, not a claimed
performance result.

## 6. SQLite persistence model

Use SQLAlchemy 2.x async sessions with `sqlite+aiosqlite:///...`, Alembic
migrations, SQLite WAL mode, `busy_timeout`, foreign keys enabled and an
explicitly tested transaction-isolation configuration. The single writer keeps
SQLite's write-serialization limit simple; short API read transactions avoid
WAL checkpoint starvation.

| Table             | Purpose and essential columns                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `source_events`   | Append-only Ishiban journal: `id INTEGER PRIMARY KEY AUTOINCREMENT`, `workspace_id`, `source` (`lody.observe`, `lody.catalogue`, `collector`), `source_stream_id?`, `source_sequence?`, `event_type`, `session_id?`, `observed_at_ms?`, `received_at`, `payload_json`, `public_projection_json?` (the post-event session/collector projection as emitted to SSE). Unique Lody `(workspace_id, source_stream_id, source_sequence)` where present. `id` is **Ishiban's durable SSE cursor**. |
| `sessions`        | `(workspace_id, session_id)` key; `machine_id`, `title`, `agent_type?`, `cli_type?`, `agent_config_id?`, `archived`, `removed`, `state`, `source`, `freshness`, `latest_turn_json`, `active_turns_json`, `last_event_id`, `last_evidence_generation`, `last_metadata_generation`, `last_observed_at`, `last_materialized_at`; optional `repo_full_name`, `project_json`, `branch_name`, `pull_requests_json`, `catalogue_refreshed_at`.                                                    |
| `turns`           | `(workspace_id, session_id, user_turn_id)` key; `assistant_turn_id?`, `state`, `duration_ms?`, `last_event_id`. It is a **latest-known projection**; reopened turn transitions remain in `source_events`.                                                                                                                                                                                                                                                                                  |
| `collector_state` | Singleton per workspace: `generation`, `state` (`connecting`, `catalogue_ready`, `following`, `disconnected`, `error`, `stopped`), `started_at`, `last_received_at`, `last_error_summary`, `last_event_id`.                                                                                                                                                                                                                                                                                |

All timestamps are UTC or original Lody Unix milliseconds, with explicit
conversion. Never use `observedAt` as the underlying turn execution time: it is
the observer's timestamp. `source_events.id` increases on each committed local
update, including catalogue enrichment and source-health events; it does not
attempt to preserve Lody process sequence across generations.

Store the original validated JSON payload for inspection and forward
compatibility, but expose only bounded, normalized fields via the public API.
This is an append-only spike with **no retention pruning**; document that
database growth needs a later policy.

### Projection merge rules

- `snapshot` / `session.changed` with `source: persisted`: update current
  session state and reconcile `latestTurn` and `activeTurns` into `turns`.
- Metadata-only projection: apply display metadata and retain last durable
  outcome, marking its evidence as not freshly revalidated when appropriate. A
  never-observed session remains `unknown`.
- `turn.started` / `turn.finished`: update the named turn (by user turn ID),
  recording the transition without requiring its counterpart. Subsequent
  `session.changed` is authoritative for the overall session state.
- `session.removed`: tombstone the session in the materialized view; retain its
  journal and turn history.
- `ready`: update collector catalogue-readiness, not per-session history
  completeness.
- Distinguish `waiting` on permission from **workflow blocked**. They are
  different concepts.

## 7. Falcon read API and SSE contract

All endpoints are versioned under `/api/v1`. For the local spike, bind to
loopback by default and serve the UI from the same origin. A deployment beyond
loopback needs authentication and transport security before it is shared.

| Endpoint                            | Purpose                                                                                                                                        |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /api/v1/snapshot`              | Consistent list of session projections, collector health and the highest committed `cursor`. Read all in one explicit SQLite read transaction. |
| `GET /api/v1/sessions/{session_id}` | Latest materialized record, associated turns and bounded recent provenance.                                                                    |
| `GET /api/v1/events?after=<cursor>` | SSE replay of committed `source_events` after a cursor, then continuous tail. Supports `Last-Event-ID` on automatic reconnect.                 |
| `GET /health`                       | Process liveness.                                                                                                                              |
| `GET /ready`                        | Database readable and migrations present. **Does not** claim the Lody source is connected.                                                     |

Example `GET /api/v1/snapshot` shape (illustrative data):

```json
{
  "version": 1,
  "workspaceId": "w1",
  "cursor": 8124,
  "collector": {"state": "following", "generation": 3},
  "sessions": [{
    "sessionId": "s1", "machineId": "m1", "repoFullName": "leynos/diapason",
    "state": "waiting", "source": "persisted", "freshness": "synced",
    "lastEvidenceGeneration": 3, "latestTurn": {"userTurnId": "u1", "state": "running"}
  }]
}
```

Example SSE item (the **SSE** `id` is Ishiban's `source_events.id`, not Lody's
`sequence`):

```text
id: 8125
event: observation
data: {"cursor":8125,"source":"lody.observe","eventType":"turn.finished","workspaceId":"w1","sessionId":"s1","projection":{"sessionId":"s1","state":"idle","latestTurn":{"userTurnId":"u1","state":"completed"}},"evidence":{"userTurnId":"u1","outcome":"completed"}}

```

The example omits the other required projection fields for readability. Use
Falcon's `falcon.asgi.Response.sse` and `falcon.asgi.SSEvent`; do not hand-roll
HTTP chunk framing. Emit heartbeats as SSE comments approximately every 15-25
seconds, with `Cache-Control: no-store`, disabled proxy buffering and a
suitable reverse-proxy idle timeout. Close the generator cleanly on client
cancellation. A slow client receives **bounded batches** from SQLite; if it
falls too far behind, close the connection and let it resume, rather than
accumulating unbounded memory.

### No-gap bootstrap and reconnection

1. UI requests `/snapshot` and receives one transactionally consistent state
   and cursor `N`.
2. UI opens `EventSource('/api/v1/events?after=N')`.
3. API streams every persisted row with `id > N`, ordered by `id`, then tails
   new commits. It must re-query SQLite after setting up the tail, closing the
   race between last query and new writes.
4. On an automatic reconnect, `Last-Event-ID` overrides the original query's
   `after` parameter when valid. The browser applies events idempotently and in
   order, ignoring already-applied cursors.
5. On a complete page reload, take a fresh snapshot before creating a new
   `EventSource`.
6. On a future retention gap or invalid cursor, return an explicit
   `reset_required` signal or a documented HTTP error; the client closes the
   old stream and restarts from `/snapshot`. For this unpruned spike, a normal
   old cursor remains replayable.

Source health is a separate persisted event category, not an assumption
inferred from missing session transitions. Every SSE `observation` carries the
session projection as it stood **after that exact transaction**, while `source`
events carry the collector projection. The frontend only applies validated
projections in cursor order: it does not duplicate the Python
turn-classification logic.

## 8. React + Effect v4 presentation

The [TypeScript tooling decision](adr-001-typescript-tooling.md) records the
imported quality gates and Bun runtime used for bundling and testing.

Use React + TypeScript (Bun 1.4.x for bundling and testing), Effect **v4 core**
for typed effects, lifecycle management, retry policy and runtime validation,
plus the browser's native `EventSource` for the transport. Wrap it in a scoped
Effect service: acquisition installs listeners; finalization closes the
connection and removes listeners. Validate snapshot and event envelopes at the
boundary with `Schema`; report malformed events as source errors rather than
silently discarding them. Avoid making Ishiban's API depend on the experimental
`effect/encoding/Sse` module unless there is a measured advantage over native
`EventSource`.

Keep an external normalized projection store keyed by
`(workspaceId, sessionId)` and turn identity. SSE updates replace the relevant
session projection directly; the source event is evidence for the inspector,
not an instruction to re-run the server's reducer in TypeScript. React
components subscribe through `useSyncExternalStore` or an equivalent stable
selector adapter. Apply SSE batches with a small coalescing window (for
example, one animation frame) to avoid re-rendering every cell on every update.
Effect owns connection and decoding lifetimes; React owns selection, search,
filters and presentation.

### Reference UI and density

Preserve the supplied mockup's understated, high-density styling: warm paper
background, pine/oxide accents, compact status glyphs, grouped repositories,
inspector, search, matrix/list/panorama modes and accessible larger-target
inspection. The mockup establishes **five workflow columns**: `Planning`,
`Ready`, `Building`, `Refine` and `Merged`, using the user conventions in ADR
002. Each column is five marks wide and wraps to as many rows as necessary. At
overview density, target a 120-repository panorama of four banks of roughly 30
rows. Provide Overview, Compact, Balanced, Roomy, and Comfortable mark sizes.
Keep the repository column `12rem` wide at every density, allowing horizontal
scrolling when bank widths exceed the viewport. Preserve the 6/10/13-item
wrapping behaviour and avoid truncation.

Compact hides evidence glyphs while preserving activity glyphs and complete
accessible labels. Constrain the main area to its grid track so table overflow
belongs to the scroll pane rather than widening the document. Every pulse has a
positioned task owner; list buttons clip their pulse to prevent pane-sized
overlays. Reduced-motion preferences apply to both table and list pulses.

The inspector is an initially hidden, nonmodal right-hand dock. Selecting a
task opens it while the board remains interactive. Its reserved space must
leave a horizontal scroll viewport through which every table column can be
reached. Close and Escape return focus appropriately; opening the panel does
not trap keyboard focus or lock document scrolling.

Use solid oxide with a tonal border for a failed latest turn, and the
reference's oxide/amber candy cane for waiting (blocked) activity. Preserve
non-colour labels and glyphs. A brief, reduced-motion-aware pulse marks newly
received session updates; empty placeholders have no pointer feedback.

**Live workflow evidence:** A successful catalogue with no PR association is
Planning. A uniquely associated active PR with a `Plan:` title is Ready; a
non-plan draft is Building, and a non-plan ready-for-review PR is Refine.
Merged and closed-unmerged PRs are terminal groups. Multiple active PRs,
missing titles, or conflicting lifecycle facts remain Unclassified. Historical
terminal PRs do not override one active association. The installed Lody CLI
omits PR titles, so a bounded read-only GitHub lookup supplies them. Source
outages and cached metadata remain visible. The original mockup's synthetic
workload is explicitly labelled **Demo data** in an isolated mode.

Distinguish visually and semantically:

- Agent activity: pending, running, waiting for permission, idle, unknown.
- Evidence quality: metadata-only, persisted/synced, persisted/unavailable, or
  carried forward from an earlier collector generation.
- Collector health: following, reconnecting, unavailable.
- Workflow stage: justified only by explicit PR association and lifecycle
  facts. Never equate `waiting` with a dependency or `turn.finished` with
  Merged.

Use daisyUI 5 for application-level controls and semantic tokens, and Tailwind
4 for layout and responsive density. Use native buttons for the mark grid and a
labelled complementary region for the docked inspector. Add Radix Primitives
only when an interaction needs them; this inspector has no modal lifecycle.
Keyboard selection and screen-reader labels must identify session title,
repository when known, runtime state, and evidence freshness; support reduced
motion.

CSS bootstrap:

```css
@import "tailwindcss";
@plugin "daisyui";
/* Define Ishiban-specific paper/pine/oxide semantic variables here. */
```

## 9. Verification plan and acceptance criteria

### Contract and unit tests

- Fixtures for every Lody event type, metadata-only snapshots, missing optional
  fields, `ready` semantics, unversioned error records, unknown versions,
  duplicates and invalid ordering.
- Turn finished without observed start; quick completion represented only in
  `latestTurn`; failure/cancellation without an Assistant; same IDs reopened;
  metadata update after durable completion.
- Crash after parse but before commit, and restart after commit: no duplicate
  journal rows, no partial projection, stable Ishiban event cursor.
- Collector source disconnect: previously running turns remain last-known, with
  explicit stale/disconnected evidence; no invented terminal events.
- Simulated catalogue refresh changes a repository association without
  inventing a Lody observer event.

### Integration and UI tests

- Run a deterministic fake Lody CLI executable against a temporary SQLite
  database and real Falcon ASGI app; verify append, projection and SSE replay
  end to end. A real authenticated Cloud workspace smoke test is a separate,
  explicitly recorded acceptance step, not assumed by fixture success.
- Bootstrap race: an event committed between snapshot and EventSource
  connection appears exactly once in the UI.
- Browser disconnect/reconnect/reload, `Last-Event-ID`, out-of-order delivery,
  duplicate events, slow reader and graceful shutdown.
- 1,000 historical metadata-only sessions without proportional history-room
  consumption (validate Lody observer behaviour separately), and a synthetic
  workload of 120 repository rows with uneven mark counts.
- Visual regression for 5, 6, 10, 11 and 13 marks per stage in demo mode;
  keyboard focus, the docked inspector, and responsive panorama.
- Confirm *no* endpoint, CLI invocation or UI control mutates Lody.
  Source-health failures remain visible while the API itself stays healthy.

**Spike exit criteria:**

1. Real Cloud observer can attach to the configured workspace, ingest v1
   messages and persist a durable local journal.
2. The collector restarts cleanly without duplicate processing or false
   terminal outcomes.
3. A user can refresh or reconnect the live board and recover the same
   materialized session state from snapshot plus SSE replay.
4. An inspector shows source event provenance and distinguishes fresh durable
   evidence, metadata-only unknowns and stale observations.
5. Panorama handles the 120-repository demonstration without stage truncation
   or misleading live-data classification.
6. The final spike report records measured latency, CPU, RSS and
   file-descriptor growth (including the `lody` child), SQLite write
   throughput, SSE fan-out cost, observed failure cases and the specific
   missing Lody metadata fields.

Do not set arbitrary performance thresholds as passing evidence before
measuring a real workload. Record latency from **local SQLite commit to
rendered UI** separately from upstream Lody/GitHub observation latency.

## 10. Suggested implementation sequence

**Increment A: durable observer.** Implement schema fixtures, subprocess
supervisor, protocol validation, SQLite WAL, transactional journal and
session/turn projections. Prove failure and restart semantics before adding a
UI.

**Increment B: query and replay.** Implement Falcon snapshot/detail/SSE APIs,
transactionally consistent cursor hand-off, replay and source-health events.
Test with a synthetic observer and actual HTTP client.

**Increment C: live interface.** Port the mockup's design system into React
components, wire an Effect-managed EventSource client, implement the session
fleet and inspector, then run the 120-repository density regression. Keep
synthetic and live datasets unmistakably separate.

**Increment D: operational smoke and findings.** Test one authenticated Cloud
workspace; document gaps, resource usage and the next narrow upstream change
worth proposing. No production hardening without evidence from the spike.

## 11. Risks, trade-offs and follow-on decisions

| Risk                                                            | Containment in the spike                                                                                                                  |
| --------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Lody CLI observation cannot attach to local-only OSS deployment | Declare Cloud authentication prerequisite; track local daemon adapter as a future upstream request.                                       |
| Observer misses history-only changes of unopened idle rooms     | Preserve its documented limits; use targeted single-session observation later if needed.                                                  |
| Source has no durable replay cursor                             | Store Ishiban-local append-only log; reconcile new Lody snapshots after every restart. Historical unseen transitions are not recoverable. |
| Repository/task/stage associations absent                       | Catalogue and associated GitHub PR metadata bridge, explicit Unclassified group, no activity-based stage inference.                       |
| SQLite lock contention or SSE polling overhead                  | One writer, short reads, WAL, one API worker and measured fan-out; use a broker only when justified.                                      |
| Native EventSource reconnect masks a lost source                | Persist explicit collector-health events; surface observation generation and staleness.                                                   |
| Lody auth expiry or provider failures                           | Distinguish auth errors from transient outages; bound retries; never put credentials in logs or frontend.                                 |
| CI/PR visibility not covered                                    | Later Ghillie feed or Lody PR metadata enhancement; do not silently repurpose execution state as PR state.                                |

**Future integration seam:** Ghillie can eventually provide independent GitHub
PR, review and CI projections; another adapter can supply df12 work-item and
workflow-stage mappings. Join those facts to Lody sessions using explicit
identifiers and provenance. That is a follow-on design, not part of this spike.

## 12. Sources and verification boundary

- [Lody CLI observation specification](https://github.com/LodyAI/Lody/blob/main/specs/cli-session-observe.md)
- [Lody observer implementation](https://github.com/LodyAI/Lody/blob/main/apps/cli/src/commands/session-observe.ts)
- [Lody workspace observer](https://github.com/LodyAI/Lody/blob/main/apps/cli/src/commands/session-observe-workspace.ts)
- [Lody session CLI catalogue implementation](https://github.com/LodyAI/Lody/blob/main/apps/cli/src/commands/session.ts)
- [Falcon ASGI SSE API](https://falcon.readthedocs.io/en/stable/api/request_and_response_asgi.html)
- [Effect v4 documentation](https://effect.website/docs/v4/onboarding)
- [daisyUI React/Tailwind installation](https://daisyui.com/docs/install/react/)
- [Radix Primitives](https://www.radix-ui.com/primitives)
- Supplied `reference/ishiban-mockup.html`, specifically its five-stage schema,
  120-repository panorama, density toggle, inspector and wrapping logic.

**Source-derived claims** above concern the current Lody implementation and
published library APIs. **Proposed contracts** such as `/api/v1/events`, the
SQLite tables, `Unclassified sessions`, cursor handling and test plan are
Ishiban design choices, not features Lody already provides.
