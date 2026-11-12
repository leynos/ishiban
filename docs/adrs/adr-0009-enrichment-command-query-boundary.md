# Architectural decision record (ADR) 0009: Enrichment command and query boundaries

## Status

Accepted on 12 November 2026 as the proof-of-concept boundary for on-demand
enrichment. This record reconciles the Unit Architecture finding retained from
[PR #9][pr-9] and its [saved review comment][saved-comment].
[Assessment 19][assessment-19] retained this accepted POC boundary.
Candidate-specific evidence and follow-up work are tracked in
[issue #11][issue-11].

This record does not claim that the original automated finding is a confirmed
defect, and it does not claim that any skipped check passed.

## Date

12 November 2026.

## Context and problem statement

The observation proof of concept exposes read APIs over one workspace. Some
session marks are retained as unknown because their collector projection has no
runtime outcome, even though Lody may hold a persisted observation. The board
resolves those marks on demand instead of inventing activity.

The [single-session activity route](../ishiban-lody-observation-spike-design.md)
therefore combines a retained-data read with a bounded, read-only
`lody session observe` child and a write to the separate activity sidecar.
Batch activity, session recency, inspector agent metadata and inspector
pull-request titles similarly start bounded, read-only upstream reads. All of
those requests use HTTP `GET`, except the batch routes, which use `POST` only
because they carry a JSON body.

The Unit Architecture check asks for an explicit separation between commands
for activity collection, sidecar writes and GitHub refresh, pure retained-data
queries, injected clocks and adapters, and typed partial outcomes. That is a
reasonable target for a larger or multi-user service. The question here is
whether it is required for this accepted, single-workspace POC, and, if not,
which boundary the POC actually promises.

The observation journal remains collector-owned. The API is started with
`Store.initialize(migrate=False)` and does not append events. The collector
holds an exclusive `fcntl.flock` on `collector.lock` in the shared state
directory. The API and collector share one SQLite database, so database
permissions do not enforce this ownership; the code paths and this record do.

## Decision drivers

- Upstream Lody and GitHub evidence must remain read-only.
- The collector must remain the sole source-journal writer.
- Only the disposable activity sidecar may receive API-derived runtime facts.
- The first render must not wait for a collector enrichment cycle that assumes
  knowledge of browser visibility.
- Process, output, time, cache and concurrency bounds must remain explicit.
- Partial results must not discard successful members.
- The POC has one local workspace, one API worker and no authentication or task
  dispatch.

## Requirements

### Functional requirements

- Retained-data queries return current committed metadata, turns, events,
  collector health and the durable cursor without starting upstream work.
- Unknown activity may be enriched only from bounded, read-only Lody
  observations and only into the activity sidecar.
- Inspector metadata and PR titles may use bounded, read-only Lody and GitHub
  reads without changing workflow classification or durable evidence.
- Each batch member has an independent, typed result; one failure must not
  discard successful siblings.
- Absent identities, stale identities and revision conflicts must be rejected
  or ignored explicitly.

### Technical requirements

- Do not add task dispatch, session mutation, transcript scraping or a generic
  command-execution API to the observer or the read API.
- Validate protocol version, workspace identity, session identity and state
  before using returned upstream data.
- Preserve the existing process, output, time, cache, batch and concurrency
  bounds.
- Preserve cancellation and child cleanup on disconnect and shutdown.
- Keep the journal append-only, its cursor durable and its evidence generations
  collector-owned.

## Operation classes

The POC classifies HTTP routes by effect rather than by HTTP method. The route
table is unchanged; this is a reading of the existing contract.

| Class                    | Routes                                                                                                                                                         | Upstream reads                                                                            | Durable effects                     |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ----------------------------------- |
| Retained-data query      | `GET /api/v1/snapshot`, `GET /api/v1/sessions/{session_id}`, `GET /api/v1/session-detail?sessionId=`, `GET /api/v1/events?after=`, `GET /health`, `GET /ready` | None                                                                                      | None                                |
| Bounded enrichment read  | Singular and batch activity, recency, agent details and pull-request title routes                                                                              | Bounded, read-only `lody session observe`, `lody session show` and `gh api graphql` reads | Activity sidecar only               |
| Collector command        | No HTTP route                                                                                                                                                  | Collector observer and catalogue children, GitHub refresh                                 | Source journal, projections, health |
| Interface preference I/O | `GET` and `POST /api/v1/interface-state`                                                                                                                       | None                                                                                      | Signed browser cookie only          |

_Table 1: Existing routes classified by their effects._

### Retained-data queries

A retained-data query reads committed journal projections, the committed event
tail, collector health, the durable cursor or browser-supplied interface state.
It may overlay a retained activity sidecar row onto the response, because that
overlay copies the current metadata and revision and does not append a journal
event. `GET /api/v1/snapshot` reads the journal snapshot and the sidecar
overlay. Session detail reads one projection and then restores cached runtime
facts. The events route overlays the sidecar onto each replay row without
changing the row's cursor or source payload.

### Bounded enrichment reads

A bounded enrichment read may start a fixed read-only upstream command and may
upsert the activity sidecar. It never writes the journal, never mutates an
upstream session and never creates collector evidence. The activity routes use
`lody session observe`; recency and agent details use `lody session show`;
inspector PR titles use `gh api graphql`. The sidecar is the only durable store
those routes update.

`POST` on the batch activity and recency routes is a body-carriage choice, not
an intent to mutate. Each request carries a bounded `sessionIds` array and
streams typed results. Their effects are the same class as the singular
enrichment reads.

### Collector commands

Collector commands are not HTTP routes. `ishiban collect` owns the observer
child, catalogue reads and GitHub refresh. It is the sole journal writer and
the only process that advances collector generations or writes evidence
generation fields. The API cannot express a collector command, dispatch a task
or request a collector restart.

### Interface preference I/O

`/api/v1/interface-state` reads and writes a signed MessagePack cookie. It does
not read or write the journal, the sidecar or an upstream process. It is
classified separately because it is neither retained server data nor enrichment.

## HTTP method and effect rationale

HTTP safe methods are expected not to change server state that the client
depends on. The API's `GET` enrichment routes are safe in the sense that
matters for this POC: they do not append journal events, change durable
projections, advance the cursor, invent evidence generations or request
upstream mutation. They may perform a bounded upstream read and replace one row
in a disposable, regenerable sidecar cache. That is analogous to a read-through
cache rather than a command.

`POST` is used for bounded batch reads because HTTP permits a request body on
`POST` and because the browser must submit a set of identities. Neither batch
route exposes a command, a job or a durable write.

`AGENTS.md` states that Lody observations and associated GitHub pull-request
lookups are read-only, and that task dispatch, session mutation and transcript
scraping must not be added to the observer. This ADR reads that invariant at
the function level: a bounded observation or metadata lookup is permitted; a
state-changing upstream call, a task dispatch or a journal write by the API is
not. The invariant constrains the effect, not the verb used to carry a read.

## Decision outcome / proposed direction

Option 1 is adopted: reconcile the finding with the accepted bounded
cache-enrichment design. Do not add command routes and do not move enrichment
into the collector. Record the boundary, preserve all existing guarantees and
add regression evidence for the retained-data query class.

The exact boundary is:

1. Retained-data queries are pure with respect to upstream processes and the
   journal. They may overlay the activity sidecar.
2. Bounded enrichment reads may start fixed, read-only upstream commands and may
   write only the activity sidecar.
3. Only collector commands may write the journal or advance collector evidence.
4. The API does not expose command routes for activity collection, sidecar
   writes or GitHub refresh.
5. Typed partial outcomes are per member. A failed member does not fail the
   collection.
6. Revision, workspace and identity checks precede every use of returned data.

### Pure policy and effect boundaries

`ishiban/runtime_evidence.py` owns pure runtime transition plans. Its frozen
results use Python field names and perform no storage, process, network, clock
or logging effects. `ishiban/storage/projections.py` is the adapter that
encodes those plans into public JSON. `ishiban/storage/activity_projection.py`
owns the sidecar overlay and its watermark checks. `ishiban/workflow.py` keeps
workflow classification separate from runtime evidence.

Existing effect boundaries stay where they are:

- `ishiban/activity_api.py` owns HTTP validation and orchestration. Its
  `resolve_activity` is an orchestration function, not a pure query: it reads a
  projection, consults the sidecar, optionally starts `LazyActivity.read`, and
  upserts the sidecar.
- `ishiban/lazy_activity.py` owns bounded `lody session observe` children and
  its process-local cache.
- `ishiban/session_show.py` and `ishiban/session_agent.py` own bounded
  `lody session show` children.
- `ishiban/pull_request_details.py` and `ishiban/lody.py` own bounded
  read-only GitHub lookups.
- `ishiban/storage/activity_cache.py` owns sidecar persistence and pruning.
- `ishiban/storage/store.py` owns journal reads, validation and the sidecar
  facade.

Injected clocks and readers already exist at these seams:
`ActivityResolutionOptions` accepts an epoch-nanosecond clock and an
`include_known` policy; readers accept executables and typed responses; tests
use `cmd-mox` and dedicated child fixtures. No new abstraction is required.

### Sidecar overlay and durable effects

The sidecar filename appends `.activity.sqlite3` to the journal filename. Its
key is workspace and session. It stores only state, latest and active turns,
source freshness, observation time and the base revision. It never stores
titles, repository metadata, pull requests, cursor values or evidence
generations.

`ActivityCache.merge` overlays eligible cached runtime onto the current
projection. `Store.remember_activity` re-reads the current projection, requires
`state == "unknown"` and an unchanged `lastActivityEventId`, writes the
sidecar, re-reads the projection, and returns a lazy overlay only if it is
still valid. A successful lazy response copies `machineId`, `title`, `archived`,
`removed` and `lastEvidenceGeneration` from the current projection and sets
`activitySource` to `lazy`.

### Evidence generation and workflow classification

The API never invents `lastEvidenceGeneration`. A lazy result copies the
current value, which may be `None`. `lastEventId` remains the durable journal
revision. Restoring a snapshot creates no pulse and does not fabricate a
collector generation. Workflow stage, stage reason and PR associations are
owned by the collector's explicit PR evidence under
[ADR 002](../adr-002-workflow-evidence.md). Inspector title reads may fill a
display title but cannot change the stored stage or stage reason.

### Typed partial results

The batch activity frame is one compact JSON object and newline. A resolved
member is:

```text
{"workspaceId": ..., "sessionId": ..., "session": {...}}
```

An unresolved member is:

```text
{"workspaceId": ..., "sessionId": ..., "session": null}
```

An oversized member is:

```text
{"workspaceId": ..., "sessionId": ..., "outcome": "response_too_large"}
```

The recency frame is either:

```text
{"workspaceId": ..., "sessionId": ..., "lastActivityEventId": N, "outcome": "available", "latestHistoryAt": ...}
```

or:

```text
{"workspaceId": ..., "sessionId": ..., "lastActivityEventId": N, "outcome": "unavailable"}
```

Neither `null` nor `unavailable` carries a cause field. For activity, `null`
means a known session without returned evidence, an absent identity, an
unavailable observer result or an operational storage failure in a pending
member. For recency, `unavailable` means an absent identity, a storage failure
or an unavailable show result. This is an accepted POC limitation; adding cause
codes would change the public frame contract and is deferred.

The singular activity route returns `{"workspaceId": ..., "session": ...}` with
`session` either an object or `null`; an absent identity is `HTTP 404`.

### Preserved bounds and guarantees

Revision and identity:

- Lazy observations validate `ok`, protocol version `1`, workspace identity and
  the requested session identity; only `source == "persisted"`, a known state
  and `freshness` in `{synced, unavailable}` are accepted.
- Turns must have a known state and a nonempty user turn ID.
- Team cache keys include the execution revision: `(session_id, revision)` for
  activity and `(session_id, basis)` for session show.
- The API resolves only `state == "unknown"` projections. A cache hit is used
  before any child starts. `includeKnown=true` returns current known evidence
  without a child.
- Sidecar writes require a matching workspace, nonempty session identity, a
  known state and a nonnegative base revision. An upsert cannot replace a row
  with a greater base revision.

Concurrency and caches:

- Activity uses four concurrent children and at most 64 unique in-flight
  observations; equal keys share one child.
- Session show uses two concurrent children and at most 32 in-flight reads.
- Both readers keep 256 process-local entries with a 300-second success TTL and
  a 30-second failure TTL.
- The sidecar keeps at most 10,000 rows per workspace and prunes the oldest
  saves after a write.

Time:

- A successful lazy read is stamped from an injected epoch-nanosecond clock,
  floored to milliseconds. An unavailable read does not call the clock.
- Cache expiry uses a separate monotonic clock.
- Each child has a 20-second read timeout. Activity and show loads have a
  45-second total lifetime that includes semaphore waiting.

Batch transport:

- Request bodies are limited to 8,192 bytes and at most eight session IDs.
- Identities are deduplicated in first-seen order.
- Each frame, including its newline, fits 1,048,576 UTF-8 bytes.
- An oversized member becomes a `response_too_large` marker; an identity too
  large for a marker is rejected with `HTTP 413` before streaming.
- Cached frames are emitted before pending reads; pending results arrive in
  completion order.

Cancellation:

- Closing an NDJSON stream cancels and reaps its member waiters while the
  shared service retains ownership of subprocess work.
- Closing a reader cancels and reaps its owned children.
- A cancelled waiter does not cancel a shared in-flight read.

## Options considered

### Option A: Reconcile and document the accepted boundary (chosen)

Keep the current routes and guarantees, record the effect-based classification,
and add regression evidence that retained-data queries start no upstream work
and change no retained state. This preserves the read-only upstream and
collector-only journal invariants without adding API surface.

### Option B: Add explicit command routes and pure query routes

Add, for example, `POST /api/v1/sessions/{id}/refresh` and make every GET pure.
The browser would issue a command, wait for it, then re-read. For this POC that
adds a job or acknowledgement contract, duplicate state for in-flight work and
new failure modes, while the render still waits for the same upstream read. It
also invites task-dispatch semantics that `AGENTS.md` excludes.

### Option C: Move enrichment into the collector

The collector could pre-resolve historical sessions or follow browser
visibility. It would then own the sidecar and the enrichment children. This
couples a durable, restartable ingestion process to ephemeral browser interest,
duplicates process and cache ownership, and makes API restarts and visibility
changes harder to bound.
[ADR 003](../adr-003-interface-state-and-lazy-activity.md) and
[ADR 004](../adr-004-persist-on-demand-activity.md) already selected API-owned
enrichment for these reasons.

### Option D: Persist enrichment results in the journal

Writing lazy results as journal events would mix on-demand, API-originated
evidence into the append-only collector record and would advance the public
cursor without a source event. It would also make cache expiry and deletion
observable as durable history. This contradicts the journal's provenance.

| Topic                | Option A       | Option B                   | Option C                        | Option D                |
| -------------------- | -------------- | -------------------------- | ------------------------------- | ----------------------- |
| First-render latency | Unchanged      | Adds a command round trip  | Depends on collector visibility | Unchanged               |
| Journal ownership    | Collector only | Collector only             | Collector only                  | Mixed                   |
| Durable contract     | None added     | Jobs and acknowledgements  | Collector-side visibility state | Journal history changes |
| Upstream mutation    | None           | None, but invites dispatch | None                            | None                    |
| POC complexity       | Lowest         | High                       | High                            | High                    |

_Table 2: Comparison of the considered boundaries._

## Goals and non-goals

- Goals:
  - Record the POC's command and query contract.
  - Preserve read-only upstream observations and collector-only journal writes.
  - Preserve typed per-member partial results and revision checks.
  - Provide regression evidence for the retained-data query class.
- Non-goals:
  - Add command routes, jobs, queues or task dispatch.
  - Add authentication, multi-user sharing or horizontal API scaling.
  - Change the journal schema, the sidecar schema or any public frame.
  - Add cause codes to `null` or `unavailable` results.
  - Move enrichment into the collector.

## Migration plan

No runtime migration is required. The route table, public frames, journal,
sidecar and collector remain unchanged. This decision becomes visible through
the design, developer guide and regression test updates.

## Known risks and limitations

- A `GET` enrichment route performs a bounded upstream read and a disposable
  sidecar write. Clients that assume every safe method is effect-free would
  observe a cache write, though not a journal or upstream mutation.
- Database permissions do not enforce collector-only journal ownership. The
  shared SQLite file is write-capable from the API process; code review and
  this record enforce the boundary.
- Process-local caches assume one API worker. A second worker would duplicate
  reads and caches.
- `null` and `unavailable` do not explain why a member has no result.
- The installed CLI has no bulk historical-state command, so each uncached
  session needs one child observation.
- The sidecar is disposable last-known evidence, not history. Its pruning can
  remove a retained outcome.
- The journal has no retention pruning.
- GitHub title lookups can return partial results; classification remains the
  collector's responsibility.

## Consequences

The public contract and runtime behaviour do not change. The finding is
reconciled with the accepted design rather than treated as a demonstrated
journal-write or task-dispatch defect.

Existing regression evidence maps to the guarantees as follows:

| Guarantee                                              | Existing regression evidence               |
| ------------------------------------------------------ | ------------------------------------------ |
| Single enrichment read is journal- and cursor-neutral  | `tests/test_activity_api.py`               |
| Sidecar survives restarts and supersession             | `tests/test_activity_persistence.py`       |
| Query fallback preserves identities without writes     | `tests/test_activity_query_api.py`         |
| Execution watermark controls eligibility               | `tests/test_activity_revision.py`          |
| Sidecar fields, revision guard, workspace scope, prune | `tests/test_activity_cache.py`             |
| Batch frames, partial members and cancellation         | `tests/test_batch_activity_api.py`         |
| Real ASGI-to-child batch path leaves the journal alone | `tests/test_batch_activity_end_to_end.py`  |
| Revision-scoped TTL cache, concurrency and cleanup     | `tests/test_lazy_activity.py`              |
| Inspector enrichment leaves the journal unchanged      | `tests/test_inspector_request_contract.py` |

_Table 3: Guarantees mapped to existing regression tests._

Additional focused coverage lives in `tests/test_session_show.py` for metadata
reads and cleanup, `tests/test_session_recency_api.py` for per-member recency
outcomes and `tests/test_pull_request_details.py` for bounded title lookup. The
new `tests/test_enrichment_boundary.py` supplies the retained-data query
regression: snapshot, path and query session detail, and event replay start no
upstream process, leave the sidecar row count unchanged, and leave journal
events and the cursor unchanged while restoring retained activity on the
overlaid session.

## Outstanding decisions

A future design with explicit command routes and pure query routes is warranted
when any of these triggers applies:

- the API runs more than one worker, or state must be shared across processes;
- a task dispatch, upstream mutation or write-capable refresh operation is
  required;
- refresh jobs need durable status, retries, cancellation or an audit trail;
- authentication or per-user authorization is added;
- journal ownership moves behind a separate service or restricted database
  credentials;
- retention or pruning of the journal becomes required;
- measurements show that enrichment latency or subprocess pressure exceeds the
  accepted bounds;
- cause codes for unresolved members become a product requirement;
- a future requirement makes every safe-method handler strictly effect-free.

## Architectural rationale

The decision keeps effects at existing boundaries and keeps policy separate
from transport. It preserves the two load-bearing invariants of the spike: Lody
and GitHub are read-only, and the collector is the sole journal writer. It also
keeps the browser's first render fast without giving the collector knowledge of
browser visibility. The accepted exception is explicit, bounded and disposable:
a safe-method enrichment route may read upstream and refresh a sidecar row, but
it cannot write the journal, advance a cursor, invent evidence or classify
workflow.

## References

- [PR #9][pr-9] records the implementation and review history.
- [Saved Unit Architecture comment][saved-comment] records the original
  finding.
- [Assessment 19][assessment-19] retained this accepted POC boundary.
- [Issue #11][issue-11] tracks the deferred decision.
- [ADR 002](../adr-002-workflow-evidence.md) defines PR-based workflow
  evidence.
- [ADR 003](../adr-003-interface-state-and-lazy-activity.md) defines interface
  preferences and lazy activity.
- [ADR 004](../adr-004-persist-on-demand-activity.md) defines the activity
  sidecar.
- [ADR 005](../adr-005-batched-activity-and-update-cues.md) defines batched
  activity and update cues.
- [ADR 007](../adr-007-session-tab-families.md) defines logical session
  families.
- [ADR 008](../adr-008-runtime-evidence-policy.md) separates pure transition
  policy from projections.
- [Observation spike design](../ishiban-lody-observation-spike-design.md)
  records the topology, persistence model and route table.

[pr-9]: https://github.com/leynos/ishiban/pull/9
[saved-comment]: https://github.com/leynos/ishiban/pull/9#issuecomment-6769534070
[assessment-19]: https://github.com/leynos/ishiban/pull/9#issuecomment-6804814809
[issue-11]: https://github.com/leynos/ishiban/issues/11
