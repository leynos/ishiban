# Ishiban initial observation proof of concept

Status: implementation and persistent on-demand observations are complete and
validated through `6d0ddd5`, with the final fixture and acceptance record
below. The full implementation review starts at `bbb1bee`. No remote
publication or Lody writes are authorized.

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
native controls, Falcon ASGI, async SQLAlchemy, SQLite WAL and a single
collector writer. Keep all code files below 400 lines, respect the repository
gates, and expose bounded projections rather than transcripts or raw
credentials.

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

M5: incorporate the user's follow-up interface requirements. Provide Overview,
Compact, Balanced, Roomy, and Comfortable mark sizes. Empty placeholders have
no pointer feedback. Accepted session updates pulse once, with reduced-motion
support and no pulse on initial render or duplicate replay. A failed latest
turn uses solid oxide and a tonal border; Lody `waiting` activity uses the
reference's oxide/amber candy cane. Replace the modal with an initially hidden
right-hand dock, keeping the board interactive and horizontally scrollable. The
first table column is `12rem` in every density. These cues preserve workflow
stage and observed activity as separate facts.

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
- [x] M4 assessment: authenticated CodeRabbit reviewed all 78 changed files;
  CodeScene completed the same commit delta.
- [x] M4 convergence: address five CodeRabbit findings and seven CodeScene
  complexity alerts, validate, and reassess the resulting implementation.
- [x] M5: add intermediate mark sizes, inert empty cells, update pulses, and
  evidence-based failed/blocked styling, a docked nonmodal inspector, and
  `12rem` repository columns; validate keyboard and browser behaviour.

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

Initial agent-browser and css-view checks verified four panorama banks at
1,280px, seven-pixel marks, keyboard interaction, live/demo subscription
cleanup, and a 390px mobile viewport without document overflow. Automated
accessibility inspection reported zero violations; four contrast checks
required manual inspection because the component theme uses background effects.
Computed colour checks, including a conservative 20% black or white texture
overlay, gave contrast ratios of at least 6.39:1 for those controls. Browser
testing exposed incorrect inspector focus restoration; a DOM regression test
covers returning to the initiating mark and a removed-mark fallback. A fresh
browser confirmed the fix, while an older tab retained stale JavaScript through
heuristic caching. A failing asset-header regression test now passes with
response caching disabled for the spike's unversioned assets. Mobile testing
also found hidden fieldset legends positioned relative to the page instead of
the scroller; a positioned scroll container keeps the page width at 390px while
retaining 934px of horizontally scrollable board content.

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
exposing secrets. The authenticated follow-up below supersedes that initial
review limitation.

The final live sample contained 2,764 sessions, including 571 active sessions
across 65 repositories. Collector shutdown retained every session and persisted
`stopped` health. The validation collector, upstream observer, API, temporary
fixture server, and browser sessions were stopped after inspection; the private
journal remains available for a later run.

Revision note: initial plan records the user-authorized design, new stage
conventions, observed catalogue limitations, and end-to-end acceptance.

## Authenticated review follow-up

CodeRabbit 0.9.3 completed the `bbb1bee..0037581` committed review with 78
reviewed files. Its findings concerned cached active PR facts overriding newer
terminal catalogue facts, lost partial GraphQL data after a nonzero CLI exit,
failed batch isolation, exhausted browser retries, and repeated catalogue
buffer parsing. Regression tests demonstrated the functional failures before
their corrections.

CodeScene 1.0.36 completed the same delta. It identified complex protocol
validators and journal dispatch, plus nested PR normalization and SSE polling.
Validation responsibilities were separated and control flow flattened in a
commit following the functional fixes. Existing and expanded boundary tests
passed before and after the refactors. Health thresholds and suppressions
remain unchanged.

## Final follow-up acceptance

Commits `7800ffb`, `aac3329`, `06e0b71`, and `3994e65` separate reliability
fixes, interface changes, catalogue framing, and behaviour-preserving
refactoring. Follow-up commits `19e1535` and `ee829f9` address terminal PR
normalization, permanently closed EventSource recovery, standalone Alembic, the
documentation index, and cursor-only SSE startup. All five original CodeRabbit
findings have regression coverage; the seven original CodeScene
function-complexity and nesting alerts are absent from reassessment. CodeScene
1.0.36 reports one remaining overall-complexity advisory for `protocol.py`:
mean 6.22 against threshold 4, with code health 9.38, improved from 8.72.
Retain explicit, ordered trust-boundary checks rather than introduce a generic
validation framework solely to change that metric. No health threshold or
suppression was changed.

Final gates pass: browser build, formatting, full Python and TypeScript lint,
dead-code and duplication checks, workflow validation, type checking, 98 Python
tests, 43 Bun tests, Markdown lint and spelling. Mermaid validation, dependency
audits and Makefile validation also pass; their results were reused because
those inputs did not change during the final formatting and lint corrections.

Actual agent-browser checks measured every first table column at 192px with the
default 16px font across Overview, Compact, Balanced, Roomy, and Comfortable.
The fixed width is `12rem`; horizontal scrolling intentionally replaces the
initial requirement to fit four banks within 1,280px. Computed CSS from
css-view confirms solid oxide failed-turn marks and the reference's 135-degree
oxide/amber blocked pattern. The dock reserves a right-hand column without a
modal, body scroll lock, or inaccessible final workflow column. A 390px
viewport stacks the inspector and retains horizontal board scrolling without
document overflow. Empty placeholders have no hover feedback.

Real-browser fault injection also supplied non-SSE responses to EventSource.
The client fetched 14 fresh snapshots while responses remained invalid, then
reached Connected on its fifteenth snapshot once normal service resumed. This
confirms permanent browser transport failure recovers without reloading.

A real local fixture update retained the same task button and displayed one
900ms pulse; reduced-motion emulation hid its animation. Automated interaction
tests cover initial snapshots, duplicate revisions, moves, expiry, filters,
focus restoration and connection cancellation. Accessibility inspection found
zero automated violations and one incomplete contrast category requiring manual
inspection; this does not establish complete WCAG conformance.

The fresh read-only `leynos` catalogue contained 2,764 sessions and completed
in 8.269 seconds without an observer. Follow-up runtime validation used the
existing private live journal plus an isolated synthetic journal. Only the
validation-owned API and browser processes were stopped afterwards; private
journals remain available. No Lody session or PR was changed.

On 10 November 2026, CodeRabbit 0.9.3 completed the follow-up
`3994e65..ee829f9` committed review of 16 files. It emitted zero findings, but
reported `completed_with_warnings` and “Review completed with unverified
findings”. The output supplied no finding or explanation for that warning. This
is a completed assessment with a service limitation, not a verified clean
review. The preceding full `bbb1bee..3994e65` review covered 87 files; its five
reported follow-ups are addressed in the two later implementation commits.

CodeScene 1.0.36 reassessed the full `bbb1bee..ee829f9` committed range and
confirmed the same single documented protocol advisory, with no new concerns.
The implementation and follow-up commits pass the required quality gates. The
final documentation-only commit updates this acceptance record and design
status; its Markdown, spelling, formatting and Mermaid gates pass separately.

## Run-feedback corrections, 10 November 2026

A subsequent live run exposed three CSS boundary failures. Compact evidence and
activity glyphs overlapped. Automatic inline margins allowed the main grid item
to exceed its track, so the table pane had no horizontal overflow despite the
document becoming wider than the window. List task buttons were not positioned
ancestors, allowing their absolutely positioned pulses to cover the scroll pane.

Three real Chromium regressions failed before the fixes and passed afterwards.
Compact now hides the evidence glyph while retaining its accessible label. An
explicit main width keeps horizontal overflow inside the pane, with and without
the docked inspector. Positioned list buttons clip their pulse locally, and
reduced-motion preferences suppress list pulses as well as table pulses. The
opt-in browser suite serves synthetic snapshots and real SSE from Bun; it does
not modify Lody data or depend on the authenticated catalogue.

Validation passes for commit `4ac4653`: browser build, formatting, full lint,
type checking, 43 Bun tests, 98 Python tests, Markdown/spelling, and Mermaid.
The three opt-in Chromium regressions also pass. On the authenticated live
page, css-view confirms a 1,280px main area and scroll pane; opening the
inspector reduces the pane to 880px while retaining horizontal scroll. All five
densities retain a 192px first column at the default font size. A 390px
viewport keeps document width at 390px and scrolls the pane independently.

CodeScene's `e110801..4ac4653` committed delta completed with no new issues.
CodeRabbit completed the same seven-file review with four test-harness
findings. Follow-up changes include command arguments, exit status and output
in browser errors; stop the fixture server even if browser cleanup fails; check
the pulse's computed clipping and positioned owner; and match each pulse to its
exact task and event revision after media preferences settle. All three browser
regressions pass again with these stricter checks. The review service reported
`completed_with_warnings` and “unverified findings”; the reported findings were
checked against the implementation and addressed locally.

## Inspector navigation and failure diagnostics, 10 November 2026

The inspector now links real sessions to Lody and shows a named latest-turn
error section. The web route was verified in the public app router as
`/$workspaceName/sessions/$sessionId`; the CLI verifies the fallback native
`lody://session/<id>?workspace=<id>` form. API navigation metadata retains the
configured selector separately from the durable workspace ID.

Read-only inspection of the installed observer and a failed `leynos` session
confirmed an upstream limitation: failed outcomes are present, but provider
error messages are omitted from both observer projections and visible CLI
history. Ishiban therefore accepts and retains an optional source-supplied
error, bounds it to 4,096 characters, and explains missing diagnostics rather
than inventing them. Tests cover snapshot and incremental persistence/replay,
reopened turns, plain-text rendering, web/native links and synthetic sessions.

## Signed interface state and lazy activity, 10 November 2026

The user's additional requirements extend the current work: persist density and
presentation in one itsdangerous-signed cookie containing a MessagePack state
dictionary, restore it in new windows, and disclose the cookie in the footer.
Keep this state independent of the observation journal. Validate enum values,
ignore invalid or expired signatures, serialize browser writes, and persist the
signing key privately in the local state directory.

Unknown activity should resolve lazily for visible real sessions. Limit
concurrent read-only per-session CLI observations and deduplicate/cache them.
Keep the API a journal reader: lazy results are browser-local enrichment, not
fabricated durable events or a second journal writer. Match workspace, session
and revision before applying enrichment; late responses must not overwrite a
newer event. Preserve the event cursor so lazy resolution does not create a
pulse. Metadata-only or failed lookups remain unknown rather than inventing
activity. Validate these invariants with deterministic fakes and a real browser.

The sticky-column feedback was reproduced in Chromium: a selected planning
mark's stacking layer covered the repository label after horizontal scrolling.
Task-cell stacking isolation keeps selection and pulse layers beneath the
sticky column. Zero bank inline padding removes its initial horizontal jump.
The browser regression checks the topmost painted element and stable heading
position while scrolling.

The inspector also needs the Lody CLI session ID, agent type and configuration
display name. Live read-only metadata confirms `acpSessionId` is the provider
conversation identity, distinct from the Lody session ID. Read session metadata
and the referenced configuration only when the inspector opens, cache
whitelisted results with a TTL, and never request configuration secrets. Copy
the exact Lody session ID accepted by the CLI through the clipboard API, with
accessible success/failure feedback. Missing IDs or names remain explicitly
unavailable.

Follow-up feedback clarified that the copyable identifier must be the Lody ID
accepted by the CLI, not the provider's ACP ID. Agent metadata is collected
only on inspector demand, with cached type/configuration labels and no
configuration secret request. PR-first headings are linked, retain the session
subtitle, and show grey numbers beside PR links. A separate title cache
resolves missing names for merged/closed PRs without reclassifying them.

A browser-store regression showed metadata-only unknown projections replacing
cached on-demand state. Retention now carries those runtime facts through
metadata events and same-workspace reconnect snapshots while preserving new
metadata and cursor values. New durable evidence and foreign workspaces still
replace the cache. Focused regressions cover these boundaries.

Inspector links use daisyUI's hover-only underline styling. Desktop Chromium
inspection confirms no underline at rest, an underline on the hovered link, and
neutral grey PR numbers after their links. The browser uses an explicit
mouse-hover capability for this check; touch emulation does not activate the
hover media query.

## Inspector refinement acceptance, 10 November 2026

Commits `621c8ed`, `33ec4c5`, and `be2bd5e` deliver the sticky-column fix,
signed interface preferences, lazy activity retention, and inspector
navigation, metadata and diagnostics. PR links show grey numbers and underline
on hover. Blank or whitespace-only PR titles retain accessible fallback labels.

The complete candidate passes build, formatting, lint, type checking,
dependency audit, Markdown/spelling, Mermaid and Makefile validation. Bun
reports 71 passed, six skipped, and zero failed; pytest reports 154 passed. All
four opt-in Chromium regressions pass separately. The size check covers 106
source files; none exceeds 400 lines.

Browser validation against an isolated Falcon journal confirms signed-cookie
restoration in new tabs and after an API restart, quiet unknown-to-known
activity enrichment, and retained runtime facts through metadata refreshes and
reconnect snapshots. Inspector checks confirm linked PR headings and session
subtitles, copied Lody identities, cached agent labels, plain-text errors,
muted PR numbers, and hover-only underlines. A real read-only `leynos` metadata
lookup returns Codex labels and a cached second lookup. Validation-owned API
and browser processes are stopped; the user's API and private journal are
preserved.

CodeRabbit 0.9.4 completes the `9941a88..33ec4c5` review of 59 files with five
minor findings. Follow-up regression tests reproduce blank PR link labels and
delayed rediscovery of dropped queued work before their fixes. Commit `be2bd5e`
also strengthens the enrichment wait and aligns British spelling. Its focused
`33ec4c5..be2bd5e` review completes across all eight changed files with one
trivial clock-injection suggestion. Both retry-time reads already use the same
browser `Date.now()` timebase. That implementation is retained; dedicated clock
injection can accompany future virtual-time retry-window tests.

CodeScene 1.0.36 completes the full `9941a88..be2bd5e` delta and retains
advisories in eight files. Threshold-level test, hook and validation
complexity, subprocess ownership, cache guards and distinct metadata decoders
remain explicit. The DOM observer owner has complexity 12 against threshold 9;
keeping its observers, subscription and cleanup together preserves one
lifetime. Its module mean falls from 5.88 to 5.20 against threshold 4. The
inspector mean is 4.22 against threshold 4 after naming its fallback values.
These advisories are accepted for this proof of concept. CodeScene thresholds
and suppressions are unchanged.

## Persistent on-demand observations, 10 November 2026

The latest run exposed a lifetime mismatch: on-demand failures existed only in
the current browser store, so a full refresh erased them. Retention also
excluded persisted-source unknown projections produced at collector startup.
The user now requires collected outcomes to survive page refreshes and process
restarts. [ADR 004](../adr-004-persist-on-demand-activity.md) supersedes the
browser-only lifetime in ADR 003.

M1: reproduce refresh loss through the actual Falcon API, then persist minimal
runtime facts in a bounded workspace/session SQLite sidecar. Reopening an API
store must restore failures and errors while raw journal snapshots, events and
cursors remain unchanged. Store ownership and schema initialization belong to
the sidecar module; no journal migration or Lody mutation is needed.

M2: add an execution watermark to projections. Known persisted observations and
turn transitions advance it; metadata, unknown observations and generation
changes preserve it. Restore cached outcomes onto current metadata only while
their base revision has not been superseded by actual execution. Check stale
lookup completion and older concurrent cache writes as separate boundaries.
Browser retention respects the same watermark and both kinds of unknown input.

M3: apply cache overlays consistently to snapshot, detail and SSE views, then
verify refreshes, API restarts and collector restarts in a real browser against
an isolated journal. New execution must replace the failure, and another
unknown projection must not resurrect it. Run the repository gates and local
reviews, record advisory dispositions, commit completed work, and run the stop
hook.

Progress: all three milestones are complete. Existing public raw journal
readers remain unchanged. The helper manifest and installed agent roles remain
those recorded in the conformance basis above.

### Persistence acceptance

Commit `60f3a8e` persists on-demand runtime observations, and `6d0ddd5` makes
fresh sidecar startup safe under contention. Inspection of the installed Lody
CLI confirms that `projectSessionCatalog` emits unknown metadata for historical
sessions. Those startup snapshots do not invalidate collected execution facts.

Real Chromium validation against an isolated Falcon API and deterministic CLI
retains the failure and its diagnostic after refresh, API restart, a new tab,
and collector-generation changes with metadata and persisted unknown input. The
raw journal still contains unknown state while the API restores the cached
failure. No additional CLI observation is made for those reloads. A newer known
running turn replaces the failure. API and property tests also verify that a
subsequent unknown update cannot resurrect superseded failures.

The full runtime candidate passes formatting, lint, type checking, dependency
audits, Markdown/spelling, Mermaid and Makefile validation. There are 169
passing Python tests, 76 passing Bun tests, six skipped default Bun cases, and
four passing opt-in Chromium regressions. The size check covers 111 source
files; none exceeds 400 lines. Validation-owned processes are stopped, the
user's API is preserved, and no Lody session is mutated.

CodeRabbit 0.9.4 completes the `84e8998..60f3a8e` review of 22 files with two
findings: concurrent table creation and the scope of the eviction test clock. A
new concurrent-startup test also exposes WAL setup contention before table
creation. SQL-level `IF NOT EXISTS` and bounded SQLite busy/locked retries make
the test pass. The `60f3a8e..6d0ddd5` focused review completes across three
files with one trivial clock-fixture suggestion. The final eviction fixture
uses fixed timestamps written directly to the sidecar, leaving all clocks
unchanged.

CodeScene 1.0.36 completes the full `84e8998..6d0ddd5` delta. Four files retain
advisories: cache initialization and writes have complexity 9 at threshold 9,
with a module mean of 4.07 against 4; the SSE owner has complexity 9 and nested
branches; activity lookup has nested branches; and two retention tests have
similar scope-reset scaffolding. Explicit lifecycle ownership, selective SQLite
retry policy and independent demo/removal assertions are retained. CodeScene
thresholds and suppressions are unchanged.

Restart both the API and collector once to load these changes. Existing
browser-only observations require a fresh read; subsequent collected outcomes
survive restarts. The journal schema does not require a migration.

### Batched activity and restart pulse follow-up

The browser now coalesces visible unknown marks into two progressive streams of
four members. The API accepts up to eight IDs, returns cached members first and
emits pending results in completion order. Four shared Lody observers and 64
unique pending reads bound work across callers. Metadata replay shares
in-flight reads and permits a checked rebase while the execution watermark is
unchanged. New execution still rejects stale results. The installed CLI
requires a separate observation for each uncached historical session.

Pulse tracking ignores revision-only and bookkeeping changes and establishes a
quiet baseline through collector startup. Runtime enrichment remains quiet;
meaningful task changes after startup still pulse. The raw journal retains
restart observations. ADR 005 records transport ownership and these policies.

Focused verification covers streamed early results, per-member isolation, input
and response bounds, disconnect cleanup, four-way concurrency, queue limits and
metadata rebase versus execution invalidation. The rebase regression failed
before the Store change and passes afterwards. Final gates and local reviews
are recorded below when complete.
