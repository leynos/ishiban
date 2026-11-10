# Logical session families

## Status

Accepted and implemented for the proof of concept. Full repository gates and
browser acceptance remain pending.

## Context

One task may have several Lody sessions linked through `parentSessionId`.
Showing every linked session as a separate board mark duplicates its repository
and pull-request context. The root session carries that stable task context,
while child tabs can have newer runtime activity, errors, agent details, and
CLI identities. The existing journal and APIs also use each actual session ID
as an independent identity.

## Decision

Group sessions by following `parentSessionId` links to the authoritative root.
Do not infer family membership from `openedBySessionId`, which is creator
metadata rather than a containment link. Render one board entry per root, using
the root's pull-request association, branch, title, and workflow context. Keep
every actual session as a member of a separate `SessionFamily` view with
`rootId`, `context`, `activity`, and `members`. Grouping is a presentation
projection: journal rows, API session records, cache identities, and CLI
requests continue to use the original session IDs.

The root supplies stable family context. The selected member supplies the tab
title shown in the inspector and its runtime state, turn errors, agent details,
and copyable Lody CLI ID. Inspector URLs retain the root workspace/session
route and identify a selected child with `?tab=session:<selected-session-id>`.
A family selection must remain stable across refreshes and reorderings; React
keys and selection identity use the family root and actual member IDs, not
array positions.

Root archival is explicit intent to archive the logical task. Hide that family
by default even if Lody retains an unarchived child tab; the existing include
archived control reveals it. A catalogue `removed` marker is different: retain
the saved root context and visible child when the root is no longer present.

Recency is the exact `latestHistoryAt` returned for each member's own
`lody session show` result. Never propagate a child timestamp onto the root
record or use `lastMessageAt`, read time, or heartbeat time as a substitute.
While any member's read is pending or unavailable, a running tab is the
provisional activity member under the assumption that each logical family has
one active tab at a time. When every member is available, choose the exact
newest history timestamp. For a successfully read session with no history, use
`createdAt` as its effective comparison time. Break ties and handle malformed
links deterministically. Resolve roots only through parent records present in
the current projection. If a parent record is missing, that session becomes the
root of its present-record chain; otherwise unrelated children of the same
missing ID remain separate families. Cycles are resolved deterministically.

Enrich only visible real-session families, batching no more than eight IDs in
an 8,192-byte `POST /api/v1/sessions/recency` request. The NDJSON result is per
member and includes workspace, session ID, execution watermark, outcome, and
`latestHistoryAt` (`null` means a successful read with no history). Unavailable
reads are represented separately from successful empty history. Discard late
results when workspace, member identity, or execution watermark no longer
matches. A new member or newer execution watermark invalidates the family's
prior selection facts. Recency-only updates are quiet; meaningful runtime
changes pulse the visible family, with initial replay establishing a quiet
baseline.

The request contains only `sessionIds`; workspace scope stays in request
ownership and response validation. Transport failures pause further batch
submissions for 30 seconds independently of the per-member cache, preventing
rejected requests from creating a retry storm.

Use one bounded `SessionShowReader` for recency and inspector agent metadata.
It verifies workspace and session identity, shares reads by actual session ID
and execution watermark, admits at most two CLI children, and bounds cache
size, queue-inclusive read lifetime, and shutdown cleanup. Successful reads
cache for five minutes and failures for 30 seconds. The configuration display
name is fetched only when the inspector is open. These metadata results stay in
the API process cache: API restart causes visible families to be enriched
again, while the existing durable activity sidecar remains unchanged.

The batch activity recovery route uses a query parameter so bounded opaque
session IDs containing path syntax do not depend on web path normalization:
`GET /api/v1/session-activity?sessionId=<encoded-id>&includeKnown=true`. Keep
the existing path-based route for compatible IDs. Both routes use the same
exact identity validation and preserve the existing response, body,
cancellation, and revision limits.

## Consequences

The board can show one stable task context while exposing the tab whose runtime
facts are current. Search covers every member ID and title; board counts and
PR-workflow filters operate on logical families. API snapshots, durable
activity facts, and raw journal replay remain session-scoped and are not
collapsed by presentation grouping.

Family recency depends on bounded on-demand metadata reads and is therefore
ephemeral. An API restart can temporarily return a family to its provisional
activity choice until visible members are read again. Successful empty history
remains distinct from lookup failure. Provisional selection assumes one active
tab at a time in each logical family. Restart both the API and collector to
load the parent metadata and routes introduced by this work. The added parent
and creation-time JSON fields are optional and nullable, so no database
migration is required.

The query-based recovery route preserves compatibility for the existing
path-based endpoint while supporting IDs that path normalization could alter.
It does not expand the accepted identity alphabet or relax workspace and
session checks.

## References

- [Observation proof-of-concept plan](execplans/initial-spike.md) tracks the
  implementation milestone and its pending validation.
- [Batched activity and update cues](adr-005-batched-activity-and-update-cues.md)
  defines the existing bounded activity transport and quiet update baseline.
- [Persisted on-demand activity](adr-004-persist-on-demand-activity.md)
  defines the separate durable runtime sidecar.
