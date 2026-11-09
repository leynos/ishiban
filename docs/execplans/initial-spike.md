# Ishiban initial observation proof of concept

Status: implemented and committed; deterministic and browser validation pass.
Local review completion is blocked by authentication. The user authorized the
existing design on 9 November 2026, including the additional PR classification
rules. No remote publication or Lody writes are authorized.

## Purpose

Run a local read-only board against the authenticated `leynos` Lody workspace.
The board preserves the supplied HTML's paper/pine/oxide visual language,
repository panorama, five-wide wrapping marks, filters, density control, and
inspectable session evidence. A Falcon API and an independent collector share
an append-only SQLAlchemy/SQLite journal; React receives snapshots and
resumable server-sent events through an Effect v4 client.

## Conformance basis

The baseline is commit `bbb1bee`, the observation design in
`docs/ishiban-lody-observation-spike-design.md`, ADR 001, the supplied
reference HTML, and the user's current PR-stage rules. The existing design's
ban on stage inference is narrowed only for explicit PR metadata. No execution
status is used as workflow evidence. User authorization to proceed overrides
the generic plan approval pause. The supervisor retains architecture and
integration; small independent implementation packets may be delegated under
the implementation skill. The installed helper manifest at
`/data/leynos/Projects/agent-helper-scripts/agents/subagents.yml` defines the
artisan and scrutineer roles; installed role tools have shell and filesystem
access. The helper revision is `45994f51547ca1f46b57401fba2f1c5f88ed20e9`.

## Constraints

Only observe and list Lody sessions; never chat, mark read, rename, or cancel.
Bind the proof of concept to loopback. Keep private catalogue and observation
captures out of Git. Use Bun 1.4.x, Effect v4, React, Tailwind v4, daisyUI v5,
Radix, Falcon ASGI, async SQLAlchemy, SQLite WAL and a single collector writer.
Keep all code files below 400 lines, respect the repository gates, and expose
bounded projections rather than transcripts or raw credentials.

## Tolerances (exception triggers)

The scope is one local workspace and one API worker. No external writes,
production deployment, multi-user authentication, task orchestration, or direct
Loro access. Stop dependent work and report evidence if authenticated read-only
Lody observation is unavailable; continue deterministic fixture verification.
Do not weaken correctness or lint gates to fit a milestone. ExecPlans are
excluded from change-size accounting; ordinary implementation documentation is
not. No artificial code-line budget limits this authorized proof of concept.

## Risks

The live catalogue has PR URLs and status but no PR title. A bounded cached
read-only GitHub enrichment supplies titles; unavailable metadata produces an
unclassified stage. The Lody CLI can produce a complete JSON catalogue before
its transport closes, so catalogue acquisition must have bounded time and
validated completion. Historical metadata-only sessions must not appear to have
freshly observed durable outcomes. A collector restart cannot replay upstream
events missed while disconnected.

## Implementation milestones

M1: establish fixtures, PR-stage classification and the durable transactional
journal. Dedupe source stream/sequence, preserve durable evidence during
metadata updates, and persist collector health and generation. Check these
invariants with named cases and generated transitions before accepting the
storage layer.

M2: supervise the read-only CLI, reconcile catalogue and PR enrichment, and
serve snapshot, session detail, health, readiness and resumable SSE. Verify
snapshot/replay ordering, reconnect precedence and recovery using a temporary
database and deterministic fake CLI before live acceptance.

M3: build the real React board with semantic daisyUI/Tailwind styles, Effect
schema validation and scoped EventSource lifetime. Keep a labelled synthetic
120-repository mode separate from live data. Verify filtering, inspector,
wrapping and keyboard/mobile behaviour with tests and the actual browser.

M4: validate `leynos`, record resource and replay observations, run all quality
gates, local CodeRabbit and local CodeScene, remediate consequential findings,
and commit the result. User/developer guides must contain executable run steps
and honest limitations. No PR or remote publication is part of this assignment.

## Verification plan

Red-green tests must first expose missing projection, persistence, API or UI
behaviour. Invariants: one local cursor per committed change; no duplicate
source event; no fabricated terminal outcome on disconnect; metadata does not
advance durable-evidence generation; stage depends only on explicit complete PR
metadata; replay applies only cursors newer than the consistent snapshot.
Fixtures include reopened turn IDs, malformed envelopes, metadata-only
snapshots, invalid versions, conflicting PRs, 6/10/13 wrapped marks, stale
collector generations and CLI failure/restart. Property tests cover stage
independence from activity and journal replay ordering. Negative controls are
invalid envelopes and conflicting PRs which must be rejected or classified
unknown rather than silently admitted.

Treat Falcon, SQLAlchemy, browser EventSource and Effect documented APIs as
external assumptions; exercise the repository-owned boundaries against their
real implementations. Use agent-browser for interactions, screenshots and axe;
use css-view for actual semantic tokens, grid dimensions and mobile layout. Run
local `coderabbit review --agent` and `cs delta` against the actual
implementation base. Capture full transient logs in `/tmp`, with concise,
non-secret evidence in this plan. No formal proof is required for this bounded
proof of concept; tests must not claim upstream historical completeness.

## Progress

- [x] 2026-11-09: inspect authenticated workspace and actual v1 CLI shapes.
- [x] M1: durable projection and classification; 15 focused store tests pass,
  including raw retention, reader-only opening, duplicate/restart and
  generation reconciliation. PR classification has named boundary cases.
- [x] M2: CLI supervisor, read API and ordered replay; 33 integrated backend
  tests pass, including a real fake CLI, explicit reader mode, API cursor
  precedence, and pytest-bdd metadata-only restart.
- [x] M3: reference-based board and isolated demo; four renderer tests plus two
  generated/immutable replay tests pass. The actual live view receives running
  observations and PR stages from the authenticated workspace.
- [x] M4 validation: authenticated live/browser checks, documentation and
  implementation commit `e022847`; all deterministic gates pass.
- [ ] M4 review: CodeRabbit and CodeScene authentication must be repaired before
  either assessment can complete; review convergence remains pending.

## Surprises & discoveries

The `leynos` catalogue contains 2,762 sessions, with 1,663 sessions associated
with at least one PR. PR records expose URLs and statuses; title enrichment is
required for the user's Ready rule. The observer emits one metadata snapshot
per known session and then `ready`; metadata readiness is not history coverage.

## Decision log

2026-11-09: retain the reference's fifth Merged column and add a Closed group
for closed unmerged PRs. Use Planning when a successful catalogue explicitly
has no PR, Ready for one Plan-prefixed open PR, Building for a non-Plan draft,
and Refine for a non-Plan ready-for-review PR. Ambiguous or incomplete PR facts
remain Unclassified. Archived/removed sessions are retained but hidden by
default. These are product workflow conventions, separate from activity.

2026-11-09: accept omitted observer machine identity as unknown rather than
rejecting the historical snapshot; the complete live v1 corpus validates with
this correction. Add API reader initialization that verifies the Alembic head
without upgrading, and retain original validated source bytes privately while
public provenance exposes only normalized bounded projections.

2026-11-09: browser inspection found oversized overview marks and a single
panorama bank. Correct the CSS cascade to four banks at 1,280px, seven-pixel
marks, five-column wrapping, compact repository labels, and an accessible
larger-target List mode. Native screenshot and css-view verify the rendered
styles; source declarations alone were insufficient.

2026-11-09: a real-process shutdown test exposed indefinite waiting on an open
SSE client. Bound Falcon/Uvicorn graceful shutdown to three seconds; the test
fails with the original configuration and passes after the correction.

2026-11-09: use GitHub CLI read-only API queries for titles because the
installed Lody catalogue lacks them. Cache lookups and surface failures; never
parse session titles to infer PR titles.

## Outcomes & retrospective

Live validation used the authenticated `leynos` workspace without changing
sessions or PRs. The catalogue initially contained 2,762 sessions, including
569 active sessions. Activity observations and PR workflow stages remained
independent in the rendered board. The isolated demo contains 965 sessions
across 120 repositories; cells with 6, 10, and 13 sessions wrap into 2, 2, and
3 rows without truncation.

Agent-browser and css-view verified four panorama banks at 1,280px, seven-pixel
marks, keyboard interaction, live/demo subscription cleanup, and a 390px mobile
viewport without document overflow. Automated accessibility inspection reported
zero violations; four contrast checks required manual inspection because the
component theme uses background effects. Computed colour checks, including a
conservative 20% black or white texture overlay, gave contrast ratios of at
least 6.39:1 for those controls. Browser testing exposed incorrect inspector
focus restoration; a DOM regression test covers returning to the initiating
mark and a removed-mark fallback. A fresh browser confirmed the fix, while an
older tab retained stale JavaScript through heuristic caching. A failing
asset-header regression test now passes with response caching disabled for the
spike's unversioned assets. Mobile testing also found hidden fieldset legends
positioned relative to the page instead of the scroller; a positioned scroll
container keeps the page width at 390px while retaining 934px of horizontally
scrollable board content.

An isolated loopback fixture measured committed journal updates through two
animation frames after DOM rendering at 190.1, 253.3, and 225.8 milliseconds.
These three samples exclude upstream Lody latency and establish no service
level guarantee. A real HTTP replay request with `Last-Event-ID: 4` and
`after=0` resumed at event 5, confirming header precedence.

Resource sampling after live hydration measured approximately 87 MiB collector
RSS, 91 MiB API RSS, and 4.4 GiB for the upstream Lody observer. The journal
contained 20,914 rows and occupied approximately 36 MiB. Upstream observer
memory dominates this proof of concept; longer-duration resource behaviour is
unverified.

Implementation commit `e022847` passes the full repository gates: browser
build, formatting, Python and JavaScript linting, dead-code and duplication
checks, action validation, type checking, 70 Python tests, 28 Bun tests,
Markdown/spelling, Mermaid validation, dependency audits, and Makefile
validation. Reasoned duplication exceptions preserve independently versioned
contracts and explicit boundary assertions after shared implementations were
extracted; their native matching limits are documented in the developer guide.

CodeRabbit 0.7.6 attempted the committed implementation from `bbb1bee` through
`e022847` with `--agent --committed --base-commit`. The service rejected its
saved session or Git provider authentication, exiting before assessment.
CodeScene 1.0.36 attempted the same delta and refused analysis because
`CS_ACCESS_TOKEN` is unavailable. Neither tool produced review findings or a
completed assessment. Credential configuration has been requested without
exposing secrets; these reviews remain pending, rather than waived.

The final live sample contained 2,764 sessions, including 571 active sessions
across 65 repositories. Collector shutdown retained every session and persisted
`stopped` health. The validation collector, upstream observer, API, temporary
fixture server, and browser sessions were stopped after inspection; the private
journal remains available for a later run.

Revision note: initial plan records the user-authorized design, new stage
conventions, observed catalogue limitations, and end-to-end acceptance.
