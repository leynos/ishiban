# Logical session families

## Status

Accepted and implemented for the proof of concept. The core family browser
acceptance and the `b26d0ba` hosted CI and Act Validation runs passed. Three
newly assessed recency edge cases are repaired and pass full local gates and
focused follow-up validation. Assessment 5 identified refresh-status and
unsupported-ID cases now implemented and covered by full local gates and
rendered browser geometry checks. Assessment 6's warm budget-limited family
selection is repaired and passes full local gates. Candidate-specific hosted
checks and reassessment are tracked in
[PR #9](https://github.com/leynos/ishiban/pull/9).

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

Resolve a stored selection through current member aliases when parent metadata
arrives later. A selected standalone child must keep its inspector open as it
joins a root family; highlighting and focus restoration use the current root
mark without copying derived family identity into selection state.

Root archival is explicit intent to archive the logical task. Hide that family
by default even if Lody retains an unarchived child tab; the existing include
archived control reveals it. A catalogue `removed` marker is different: retain
the saved root context and visible child when the root is no longer present.

Recency is the exact `latestHistoryAt` returned for each member's own
`lody session show` result. Never propagate a child timestamp onto the root
record or use `lastMessageAt`, read time, or heartbeat time as a substitute.
While any member's read is pending or unavailable, or the family cannot fit the
current lookup budget, a running tab is the provisional activity member under
the assumption that each logical family has one active tab at a time. When
every member is available and the family is not budget-limited, choose the
exact newest history timestamp. For a successfully read session with no
history, use `createdAt` as its effective comparison time. Break ties and
handle malformed links deterministically. Resolve roots only through parent
records present in the current projection. If a parent record is missing, that
session becomes the root of its present-record chain; otherwise unrelated
children of the same missing ID remain separate families. A cycle uses its
smallest session ID under JavaScript string comparison as the root; paths
entering that cycle join the same root. This choice does not depend on the
input record order.

A lookup's current status is distinct from its last-known history timestamp. On
the next bounded revisit after a successful fact expires, mark it pending once,
including when its family is hidden or its inspector remains open. Start a
refresh only for a visible admitted member. A failed refresh retains only
same-watermark history for fallback ordering, and its status is unavailable.
Running-tab preference and provisional labelling continue until a successful
refresh resolves every required member. Recency enrichment stays quiet and does
not advance the journal cursor.

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

Admit every requestable member of a visible family together within a shared
512-member browser fact budget, in deterministic root order. Count only real
members whose IDs the lookup API accepts: nonempty, at most 256 Unicode code
points, with no NUL. Keep other source IDs and family membership unchanged, but
never queue them for recency or lazy activity. Their missing recency remains
provisional; valid siblings still resolve. Skip the supported members of a
family when they cannot all fit. Reading only a subset cannot establish the
latest tab. The inspector explicitly labels that family's selection
provisional. Hidden-family facts remain cached while room exists. Only
non-admitted facts can be evicted to make room for admitted work. When
visibility changes, release queued work and ignore in-flight results from
families that have lost admission. Derive budget status from current visible
families, without a persistent negative cache. This bound belongs to the
browser recency owner; the source catalogue and private journal are unchanged.
An open inspector stays provisional if a hidden family's facts are evicted to
make room for visible work. Previously settled facts can also remain in cache
when a warm family loses admission to an earlier-sorted visible family. That
warm family still prefers its running tab until admission returns; available
cached timestamps alone do not make its selection conclusive.

Pack each request by both member count and actual UTF-8 JSON bytes. Accepted
256-code-point IDs may occupy up to 1,024 UTF-8 bytes before JSON framing;
count-only batches could exceed the server's 8,192-byte limit. Valid siblings
from a streamed response remain usable, while malformed or missing members
trigger the same 30-second transport cooldown as HTTP failure. A normal
per-member `unavailable` result stays separate from malformed transport. A
valid response with an obsolete execution watermark settles only that member as
unavailable. It does not count as a missing transport member or start the
owner-wide cooldown.

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
cancellation, and revision limits. Inspector agent and PR-title requests, and
paged session details, expose equivalent query-carried identities through
`/api/v1/session-agent`, `/api/v1/session-pull-requests` and
`/api/v1/session-detail`, preserving their existing path routes. The Lody
website's root path is external: dot-segment root IDs receive an explicit
unavailable-link notice while the raw copyable ID remains usable. A selected
child ID stays safe in the web link's tab query.

Inspector PR selection retains the family root's associations and chooses a
stack tip from validated same-repository, non-fork branch relationships. GitHub
owner and repository identities compare case-insensitively; branch names retain
their case, and original URLs remain cache keys and link targets. Lifecycle,
merge-time and stable-URL ordering resolve remaining ambiguity, including
branches retargeted after a prerequisite merge. Missing or cyclic relationships
use that fallback; they do not invent dependency evidence. The chosen identity
is independent of which title arrives first. These facts are lazy inspector
metadata, shared with the existing title cache, and neither change workflow
classification nor enter the observation journal.

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
  implementation and candidate-specific validation.
- [Batched activity and update cues](adr-005-batched-activity-and-update-cues.md)
  defines the existing bounded activity transport and quiet update baseline.
- [Persisted on-demand activity](adr-004-persist-on-demand-activity.md)
  defines the separate durable runtime sidecar.
