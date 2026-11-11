# Ishiban initial observation proof of concept

Status: the original implementation and its local acceptance are complete. The
proof of concept is published in
[PR #9](https://github.com/leynos/ishiban/pull/9). Hosted CI and Act Validation
passed on `b26d0ba` and the assessment-4 repair head `461ea91`. The
assessment-5 refresh-status and unsupported-ID fixes now pass full local gates,
including 249 Python tests, 151 Bun tests and four Chromium geometry cases.
Current publication, hosted evidence and review convergence are tracked in the
PR. Assessment 6's warm capacity-limited selection repair passes full local
gates; its exact-head validation is tracked in the PR. The original publication
restriction is superseded by the user's PR creation and babysitting requests.
Lody writes remain forbidden; no merge has been authorized.

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
and honest limitations. PR publication was outside the original implementation
milestone; subsequent user instructions authorize publication and review
convergence.

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

### Batched activity acceptance

Commit `999f28c` adds progressive activity batches, four shared observer slots,
metadata-safe in-flight reuse and semantic restart pulse baselines. The final
candidate passes build, formatting, full lint, type checking, audit,
Markdown/spelling, Mermaid and Makefile validation. The full suites report 186
passing Python tests, 86 passing Bun tests and four passing opt-in Chromium
regressions. Six default Bun cases remain skipped. All 118 source files fit the
400-line limit.

An isolated Falcon API and deterministic read-only Lody fixture validate the
actual browser batch route. Four uncached observations start within about 12
milliseconds of one another; all eight fixture marks eventually resolve without
enrichment pulses. Unit and ASGI tests separately establish that a completed
member arrives before its blocked neighbour. These fixture timings are not a
latency benchmark for the live Lody workspace. Validation-owned processes and
the browser profile are stopped; the user's API is preserved.

CodeScene 1.0.36 reviews `996dc77..999f28c`. Retained advisories cover the
batch preparation phases and identifier validation, the lazy reader's ownership
guards, two streaming browser tests and independent invalid-request test
arrangements. The explicit cache/known/pending phases, trust-boundary checks,
cache/in-flight/overflow decisions and independent assertions remain useful at
these bounded sizes. CodeScene thresholds and suppressions are unchanged.

CodeRabbit 0.9.4 completes the same 27-file range with one minor documentation
finding and four trivial suggestions. The follow-up adds the missing acceptance
record, covers mixed cached/fresh/unavailable results and actual CLI subprocess
integration, shares test lifecycle setup, and bounds duplication exceptions. An
operational storage failure is contained within its pending batch member;
unrelated programming errors still propagate. Its regression fails before the
handler change and passes afterwards. HTTP body accumulation is shared between
preferences and activity batches while endpoint limits remain independent.

The follow-up commits `898a060`, `0dbeae3` and `49f166d` pass the required
runtime and documentation gates: 188 Python tests, 86 Bun tests, four opt-in
Chromium regressions and 35 Markdown documents. All 123 source files, including
stylesheets and HTML, remain within 400 lines. CmdMox 0.2.0 supplies ordinary
command-response fixtures while preserving real shim subprocesses. The updated
`AGENTS.md` records engineering practices and invariants from the two requested
starting points, without a host CLI inventory.

CodeRabbit 0.9.4 completes the 16-file `999f28c..49f166d` follow-up review with
zero findings. CodeScene 1.0.36 completes that range and reports one new
advisory: the mixed batch route test is 79 lines against a 70-line threshold.
Its cached, fresh, unavailable and missing-member assertions remain together as
one request contract; shared setup is already extracted. Production batch mean
complexity improves from 4.75 to 4.43. No CodeScene rules are weakened.

## Hosted delivery follow-up

The first published candidate passes its local gates, but hosted CI exposes
additional obligations. Act Validation needs the same pinned Bun runtime as the
browser tests. The existing coverage ratchet combines application and test
modules, counts cold assertion messages, and restores a cache identified only
by Python minor version. SlipCover 1.1.0 also cannot pre-instrument pytest 9.2
rewrites, and its xdist workers miss dynamic Alembic migration execution.

CodeRabbit investigation comment `6771868675` independently identifies those
limits; AST inspection and upstream research were available, codegraph was not.
Isolated measurements confirm that pytest 9.1 removes the compatibility warning
but does not repair the unscoped line-coverage decrease. With identical
production scope and serial instrumentation, base coverage is 97.37% and the
published head is 91.51%. All expected production files must remain measured;
the one-percentage-point ratchet tolerance must remain intact. Any substantial
coverage-infrastructure repair belongs in a prerequisite beneath this feature.

The full base-to-head CodeScene inventory has 24 diagnostics across 14 files.
The babysitting follow-up replaces previously retained advisories with cohesive
refactors and integrated validation. New CLI tests expose and repair missing
command context in startup validation errors. Collector recovery tests check
safe failure diagnostics, increasing backoff, cancellation and refresh health
without writing to Lody or changing the user's running service.

The user subsequently directs a reset of the cached Python baseline to zero.
That explicit policy decision supersedes the proposed baseline-migration
prerequisite. Both historical Python ratchet caches are removed; the next
coverage run bootstraps zero through the existing action. The ratchet remains
enabled with a tolerance of one percentage point, and a successful main
publisher will establish the new measured baseline. Measurement scope remains
unchanged. Coverage lanes use the verified compatible pytest 9.1.0/SlipCover
1.1.0 tuple and serial instrumentation so dynamic migration hits are retained.
New workflow contracts keep the PR and main publishers aligned. The unused
prerequisite worktree remains clean and unpublished; no stack rewrite is
required.

### Hosted assessment repairs

The first hosted completeness assessment at PR comment `6773725213` finds two
in-scope gaps. A known active PR alongside an unknown association could claim
Building or Refine, so workflow classification now requires known lifecycle
evidence for every association before selecting a definite stage. A collector
regression covers a valid draft alongside a rejected URL; the existing known
active plus historical terminal convention remains intact.

Session detail previously loaded every retained turn. It now returns at most
100 turns per request, with a workspace/session-bound continuation ordered by
last event ID and turn ID. A bounded lookahead detects another page; malformed
and foreign continuations return HTTP 400. The next request reads current
materialized state, so changes between requests can change later pages. A test
exercises tied event positions, the exact page boundary, full retained history
and invalid-cursor behaviour.

The coverage investigation also identifies that the shared action publishes the
measured baseline on a main push by default, but a manual main dispatch needed
after token-authored automerge would leave it at zero. The main coverage job
now accepts only `refs/heads/main` and explicitly publishes the baseline on
either main trigger. The PR lane retains its non-publisher policy. Focused
regressions passed red before their respective fixes and green afterwards; full
gates, hosted checks and reassessment of this repair candidate remain pending
until publication.

Local gate review found six new Nose overlap families and one anonymous
two-line null-guard match. Shared test setup now covers the actual repeated
fixtures and workflow-action loading. The null guards remain independent, with
the narrowest detector-supported file-pair exception documented in the
developers' guide; a stale store exception is removed. CodeScene's large-method
and complexity findings prompted bounded turn-page SQL and terminal-stage
classification helpers. The focused repair suite passes 65 tests, the Nose gate
passes, and local CodeScene reports 10.00 for each changed runtime and test
file checked. Full repository gates remain for the integration pass.

### Second hosted assessment bounds

The second hosted assessment at PR comment `6774674032` identifies two
remaining public-response bounds. A version 1 detail cursor embedded accepted
identifiers and could exceed its own parser limit. Version 2 instead carries a
fixed-width structured scope digest, event ID, and inclusive rank within that
event's turn group. The reader counts the rank in its existing read transaction
and resumes with bounded lookahead. Long turn and scope identifiers, malformed
and version 1 tokens, and issued-cursor round trips have focused regressions.
Concurrent updates can shift ranks because detail reads are not snapshots
across requests.

The journal and sidecar retain complete private active-turn facts. Public
snapshot, detail, SSE, and single and batch lazy activity responses now apply
the same 100-turn preview after activity restoration. They carry exact count,
truncation, and a semantic full-set revision so hidden same-count changes can
still produce a meaningful update cue. The inspector discloses a truncated
count while retaining its Lody session link. No database migration or private
working-set bound is claimed;
[ADR 006](../adr-006-public-turn-previews-and-cursors.md) records the boundary
and trade-off. Local red tests reproduced both unbounded behaviours; integrated
gates and hosted reassessment remain pending.

### Batched activity transport bound, 10 November 2026

**Progress and decision.** A hosted assessment found that a valid Lody
observation plus a catalogue title can make a 100-turn public preview exceed
the browser's one-MiB NDJSON frame limit. Preserve accepted private facts and
the browser's transport bounds. Pre-encode each batch member and substitute a
typed `response_too_large` marker for one oversized frame; continue its
siblings. Reject an identity too large for its marker with HTTP 413 before
streaming. The browser performs one owned bounded single-session fallback,
including a current known projection if the batch raced a metadata update.
Unrecoverable transport results display a quiet activity notice, not a turn
error. [ADR 005](../adr-005-batched-activity-and-update-cues.md) records the
boundary and [ADR 006](../adr-006-public-turn-previews-and-cursors.md) retains
the private working-set trade-off.

**Verification and outcome.** A real ASGI-to-CmdMox regression first failed
because a near-limit accepted observation and long catalogue title produced a
frame above 1,048,576 bytes. It now checks that the marker precedes a valid
small sibling, the single-session fallback retains the full result, and the
journal and cache remain intact. Focused Python activity tests pass; integrated
frontend, lint, type, documentation, browser, and review gates remain pending
for this repair.

### Logical session families and recency, 10 November 2026

**Decision.** Group board entries by authoritative `parentSessionId` roots,
retaining root PR, branch, title, and workflow context while each actual tab
keeps its runtime activity, errors, agent details, and CLI identity. Derive
family selection from per-member `latestHistoryAt`; do not copy recency onto
the root projection or use message, read, or heartbeat timestamps. Keep
presentation families separate from journal, API, and cache identities.
[ADR 007](../adr-007-session-tab-families.md) records the approved behaviour,
shared metadata-reader bounds, query fallback, and restart policy.

**Progress.** The nullable parent and creation-time fields, bounded per-member
recency endpoint, shared session-show reader, query-based activity fallback,
and board/resource integration are implemented in the current worktree. Focused
checks report Python 48 passed, board/fallback 32 passed, recency ownership 2
passed, and pure family model 10 passed. Twenty focused inspector component and
agent tests pass after an earlier run of 13 passed and 3 failed exposed an
inspector regression. Bun format, lint, and type checks are green for the
focused scope. Targeted complexity checks for both changed TypeScript modules
report 10.00; the shared timestamp helpers reuse the existing calendar helper.

**Focused acceptance evidence.** Tests cover one root-context board entry,
selected-child activity and identity, raw root pulses, quiet settling of
visible family recency, rejection of late facts from a prior workspace,
dropping queued off-screen reads, retaining a child when its root is removed,
and exact-ID query fallback. A missing-parent child becomes the root of its own
present-record chain; siblings are grouped only when a present parent connects
them. These focused checks accompany the passing component, agent, API, and
model counts above.

**Integrated acceptance.** The hotfix validation run passed 245 Python tests,
134 Bun tests with seven opt-in skips, and all four Chromium regressions.
Build, formatting, types, audit, documentation, diagrams, and Makefile checks
passed. Shared bounded caches, batch framing, request lifetimes, and test
fixtures replaced genuine duplication; the remaining detector matches have
reviewed exact-scope reasons in the developers' guide. Full lint passed after
the corresponding configuration updates. Source checks cover 158 code files,
all within 400 lines, and new code and test files have direct CodeScene scores
of 10.00 with no diagnostics.

The live 400 response exposed a browser/server request-shape mismatch. Both a
strict-body regression and a transport retry regression failed before the fix.
The real browser hook now emits only `sessionIds`; a Python integration test
executes that hook with Bun, then submits its actual bytes through Falcon and
the CmdMox resolver. Transport failures have a separate 30-second owner-wide
cooldown, preventing a retry storm across visible families.

**Interactive evidence.** An isolated Falcon/SQLAlchemy state used controlled
root PR/runtime facts with native `leynos` session identities and read-only
metadata. Agent-browser showed one Refine mark, the selected child CLI ID,
agent configuration, root PR heading, and correct Lody tab link. The copy
button reported success; browser clipboard readback was permission-restricted.
A controlled private-journal turn delivered over SSE pulsed the stable family
mark while keeping the inspector open. There were no browser page errors.
CSS-view confirmed a sticky 384-pixel inspector and an 880-pixel board pane
scrolling through 1,024 pixels of content. All five densities retain the
192-pixel repository column and zero horizontal bank padding. The sticky
heading stayed at x=0 after scrolling, and the selected mark remained behind
the repository column. Screenshots and computed-style captures are retained
under `/tmp/ishiban-family-browser-u8qcj7jy`; the owned browser and API exited
cleanly. User API and collector processes were not signalled or restarted.

**Local assessment.** A fresh local CodeRabbit pass inspected 62 files and
reported two minor findings. Activity path IDs now receive the same exact
validation as query IDs, with failing-then-passing invalid-path regressions.
Root archival remains intentional logical-task policy; the guide, ADR, and
hidden-then-revealed board regression make it explicit. The follow-ups pass
five affected Python tests and five grouped-board tests, with formatting,
types, lint, and direct CodeScene checks clear for their scope. Hosted checks
and assessments belong to the exact published candidate; the PR records their
current status. Do not treat the previous baseline's hosted checks as evidence
for this new scope.

### Late containment discovery selection

After publishing the family implementation, a focused review found that an
already selected child could close its inspector when its parent link arrived
from the catalogue. The failing regression selects the standalone child, then
groups it under its root. Selection now resolves through member aliases while
highlighting and focus use the current family root. Closing the inspector
focuses the surviving root mark. Twenty focused board tests pass, with Bun
types, lint, formatting, and direct CodeScene checks clear for both changed
files. The change preserves raw journal and CLI identities.

### Recency admission and stream integrity, 10 November 2026

**Surprise and decision.** Assessment 4 confirmed the query fallback for opaque
IDs but found three recency edge cases: a 513-member family can churn through
the 512-entry browser cache; eight accepted multibyte IDs can exceed the
8,192-byte request cap; and malformed or missing HTTP 200 members can bypass
the transport cooldown. Admit only complete visible families within a shared
512-member budget, label non-admitted selection provisional, pack requests by
actual encoded bytes, and cool down after an incomplete stream while retaining
valid siblings. [ADR 007](../adr-007-session-tab-families.md) records the
ownership, cache-retention policy, and user-visible limit.

**Progress and verification.** Red Bun regressions reproduced a 513-tab family
starting unfinishable reads, rejection of a byte-heavy accepted batch, and an
immediate third request after a malformed HTTP 200 member. The bounded repair
passes 24 focused family/recency Bun cases, including aggregate 300+300 member
pressure, release on hide, rejection of in-flight results after admission
changes, a provisional inspector notice, and subsequent cooldown recovery. The
browser-to-ASGI integration passes two Python cases, including actual multibyte
request bodies through Falcon and CmdMox without journal writes.

Full local gates subsequently passed: 248 Python tests, 144 Bun tests (with
eight opt-in skips), four Chromium layout cases, browser build, formatting,
lint, typecheck, dependency audit, Markdown/spelling, diagrams, and Makefile
validation. The working-tree CodeScene delta reports no issues; all changed
source and test files score 10.0 in direct reviews. A test-only cleanup derives
expected membership from raw parent links; its four focused cases pass.
Published candidate checks and reassessment are tracked in
[PR #9](https://github.com/leynos/ishiban/pull/9). No formal proof is
introduced.

### Refresh status and lookup ID admission, 10 November 2026

**Surprise and decision.** Assessment 5 found that a failed refresh retained an
`available` fact and could make a stale idle tab appear conclusive. It also
found that a 257-code-point source ID could reject valid siblings in an entire
Falcon batch. Keep current status separate from last-known history, mark
expired facts pending even for hidden families, and retain same-execution
history only as provisional fallback. Use one pure client predicate for both
recency and activity lookup admission; preserve raw catalogue and CLI IDs.
[ADR 007](../adr-007-session-tab-families.md) records these boundaries.

**Progress and verification.** Focused red regressions reproduced the expired
winner and unsupported recency/activity batches. The repaired candidate passes
43 focused Bun recency, activity, board and model cases. These include a hidden
inspector expiry and a generated timestamp property for provisional selection.
Three browser-to-Falcon/CmdMox contract cases pass, including actual wire bytes
for a 257-code-point source tab and valid sibling with no journal writes. Full
local validation completed on 11 November 2026: 249 Python tests, 151 Bun tests
(nine opt-in skips), and four Chromium cases with 24 geometry, scrolling and
pulse assertions. Build, formatting, lint, typecheck, dependency audit,
Markdown/spelling, diagrams and Makefile validation pass. The strict
working-tree CodeScene delta exits zero and its human report says no issues;
new helper and test files score 10.0 in direct reviews. These are local
results; exact-head hosted checks and reassessment are tracked in
[PR #9](https://github.com/leynos/ishiban/pull/9). No formal proof is
introduced.

### Warm family capacity and provisional selection, 11 November 2026

**Surprise and decision.** Assessment 6 found that a previously settled family
could lose admission when an earlier-sorted family entered the viewport. Its
cached facts remained available, so the selector chose an idle tab with a newer
timestamp despite a known running tab and a provisional budget label. Pass the
budget-limited flag into the pure family selector. Retain cached facts,
visible-only reads, and the existing 512-member admission policy.

**Progress and verification.** The warm 300-member B family regression failed
before the fix while A held the lookup slots. It now selects B's running tab
while B is limited and returns to its newer idle history winner when A hides. A
generated timestamp property exercises the selector with all facts available
and both budget states. The 16 focused family and pressure cases pass. Full
local validation passes 249 Python tests, 152 Bun tests with nine opt-in skips,
and four Chromium cases with 24 assertions. Build, formatting, lint, types,
audit, Markdown, spelling, diagrams and Makefile validation pass. The working
CodeScene delta reports no issues. Exact-head gate and review status belongs to
[PR #9](https://github.com/leynos/ishiban/pull/9).

### Inspector identity and timestamp boundaries, 11 November 2026

**Surprise and decision.** The broader assessment exposed two supported-input
boundaries: browser path normalization changed dot-segment inspector IDs, and
an observer timestamp beyond the JavaScript date limit could crash rendering.
Inspector metadata and paged detail now accept raw IDs in query parameters,
while preserving legacy routes. External Lody links cannot invent a query
contract for root identities, so dot-segment path IDs get an explicit
unavailable-link notice while the copyable CLI ID remains available. Child IDs
in the web link's tab query remain intact.

Validate new observer timestamps against the inclusive nonnegative JavaScript
date range before consuming a stream position. Guard rendering separately for
older retained values without changing journal history. The shared Bun capture
fixture serves the recency, inspector and timestamp cross-runtime contracts.
Its initial one-MiB stdout and capture-read limits retained a 20-second
deadline; the follow-up below replaces capture files with a FIFO bounded while
the child writes. Application subprocess adapters retain their separate
ownership.

**Progress and verification.** The inspector lookup regression failed with a
404 before the query aliases, and the retained timestamp regression failed with
a date-formatting exception. Focused browser-to-Falcon cases preserve dot,
slash and percent IDs, validate bad query identities, and leave journal
evidence unchanged. The timestamp contract carries the accepted maximum through
protocol validation, storage, schema decoding and the real inspector.
Candidate-specific final gates and review status are tracked in
[PR #9](https://github.com/leynos/ishiban/pull/9). No formal proof is
introduced.

### Remaining acceptance and diagnostic gaps, 11 November 2026

**Surprise and scope.** Assessment 9 confirmed the inspector runtime repairs
but found that a capture-file read limit did not bound a still-running writer.
A real child wrote two MiB then hung until the outer test deadline. The shared
fixture now uses a private POSIX FIFO, retaining at most one MiB plus the first
overflow byte, rejecting promptly and reaping the child. Tests cover empty and
exact-limit payloads, both overflow channels, cancellation and cleanup.

The first full run exposed duplicated multibyte capture bytes under FIFO
backpressure. Independent probes isolated Bun 1.4.3's `Bun.write` path and
excluded the tested final-drain ordering. An explicit byte-offset writer
preserved both probe payloads. A small-pipe real-child regression now uses
patterned content so repeated bytes cannot hide behind a zero-filled fixture;
the
[debugging record](../debugging/debugging-plan-2026-11-11-multibyte-capture.md)
retains the finite experiment's scope.

The published users' guide now supplies marked examples loaded by shared
integration and behaviour-driven tests. External setup and Act invocation are
mocked; collect and serve use the real command parser with isolated runtime
edges, and a bounded Make dry-run verifies the documented environment flag. The
guide corrects the Python baseline, serial coverage lane and sidecar path.
Stale developer instructions and two absent imported-reference links are
corrected without importing unrelated guides or inventing a release target.

A collector integration case now emits a distinct persisted activity event
following catalogue metadata, then checks both the live projection and durable
journal. A subprocess-local negative control that discards observer ingestion
fails this case. A finite generated test checks independent NDJSON records
across UTF-8 byte partitions and malformed siblings. Compile-only public
preference-callback assertions reject mismatched values. The existing board
status assertions now include a focused, stable snapshot of accessible labels
and failure/blocked attributes.

**Diagnostic boundary.** CodeRabbit confirmed that API-owned on-demand cache
writes and bounded read-only enrichment are the accepted architecture. It
withdrew the unplanned 0.2.0 migration and telemetry-stack requirements. Fixed
failure categories now distinguish capacity, CLI, deadline, protocol and
storage failures without identifiers, payloads or provider error text. PR-title
partial results retain successful siblings and emit a diagnostic; negative
cache hits do not repeat the source failure. Embedded migrations preserve host
logging handlers. Separate pure-policy alignment and the remaining measured
spike report precede final review convergence, as tracked in
[PR #9](https://github.com/leynos/ishiban/pull/9).

**Verification.** The completed deterministic run passed 298 Python tests, 160
Bun tests with 11 default opt-in skips, formatting, lint, type checking,
dependency audits, Markdown and spelling, diagrams, and Makefile validation.
The cross-runtime tests explicitly invoke the otherwise skipped capture cases.
CodeScene reported no new issues; all 20 changed code files scored 10.0
directly. The local review inspected the 30-path repair and identified platform
skipping, two documentation corrections and capacity-warning flooding. The
warning regression failed before its interval bound and passed afterwards;
warnings retain only a suppressed count. The forced small-pipe tests skip
explicitly when the Linux sizing operation is unavailable. No formal proof is
added.

### Pure runtime policy alignment, 11 November 2026

**Decision.** Move runtime replacement, metadata preservation and named-turn
transition decisions into `ishiban/runtime_evidence.py`. Frozen typed plans
carry the decision to the existing storage adapter, which retains public JSON
encoding and legacy-value handling. Journal ingestion and on-demand activity
resolution continue through the shared adapter; cached sidecar restoration
keeps its separate validated overlay and watermark checks.
[ADR 008](../adr-008-runtime-evidence-policy.md) records the session-specific
boundary; the database schema, public contract and PR workflow classification
are unchanged.

Pure policy tests cover metadata versus persisted evidence and turn start,
finish and reopen decisions. Adapter compatibility cases retain malformed
active-list handling, optional field omission, bounded failed-turn errors,
unrelated saved values and input immutability. Existing storage, journal,
turn-error and activity suites provide executable equivalence evidence.
Candidate-specific final validation and review remain tracked in
[PR #9](https://github.com/leynos/ishiban/pull/9). No formal proof is added.

**Verification.** The six focused policy, projection, journal, turn-error and
activity suites passed 22 tests. Full gates passed 302 Python tests and 160 Bun
tests with 11 default opt-in skips, plus lint, formatting, type checking,
audits and documentation checks. CodeScene reported no issues and scored the
three changed code files 10.0 directly. The local review inspected all nine
refactor paths and completed without findings.

### Measured observation spike, 11 November 2026

The bounded final-candidate run used backend
`10114716f303e9add6aeb9fc3ca10c33cdf88732`. A corrected 90-second live
observation sampled 52 `connecting` and 38 `following` health states, with 90
local readiness responses and no sampled source-error presence. Its final
snapshot had 2,788 sessions and cursor 5,647. The collector tree, including
Lody, accumulated 96.84 observed CPU core-seconds; sampled RSS peaked at
2,189,636 KiB and file descriptors at 62. The nested Lody child accounted for
56.15 observed CPU core-seconds. Sampling limitations and interpretation are
recorded in the [observation spike report](../observation-spike-report.md).

Synthetic ingestion committed 1,000 events at 131.62 events per second, with
7.56 ms median and 8.75 ms reported p95 commit-call duration. One, four, and
eight SSE readers each received all 100 events in their phase. The browser-only
run measured three local commit-to-render samples between 148.09 and 188.51 ms,
with approximately 29–30 ms clock uncertainty. A sequence-gap fault was
rejected without cursor movement; a finite paused-reader replay completed.
Seven owned process groups or sessions were clear after cleanup, including a
Lody child that disappeared after the immediate stop check.

These results do not establish upstream latency, a service-level objective,
production capacity, or arbitrary slow-client backpressure limits. The report
records the prior invalid sampler and initial browser selector correction,
source metadata gaps, and limits on CPU and RSS interpretation. The measurement
lane is complete; candidate-specific acceptance and review remain tracked in
[PR #9](https://github.com/leynos/ishiban/pull/9). No formal proof is added.

### Lifecycle and packing acceptance, 11 November 2026

The refreshed pre-merge checks identified additional test gaps. Native fake
Lody children are now tracked through the real process adapter. Completed
catalogue reads and collector cancellation assert termination and reaping; a
child that ignores SIGTERM before emitting valid JSON exercises the real
three-second SIGKILL fallback. A private cleanup-disabled negative control
fails the new assertion, and fixture cleanup reaps the owned child afterwards.

The recency packing property drives the actual hook over 50 generated
Unicode-ID cases and three fixed controls for member count, encoded bytes and
JSON escaping. Every intended ID appears exactly once, with no foreign member,
and each JSON request stays within eight members and 8,192 UTF-8 bytes. These
are finite executable checks, not a formal proof. The design topology now shows
collector journal ownership and API enrichment/sidecar ownership. No runtime
source changed in this test/report plateau; final assessment and review remain
tracked in [PR #9](https://github.com/leynos/ishiban/pull/9).

### PR-title dependency injection, 11 November 2026

The scoped pre-merge response accepted the API enrichment design, pure runtime
policy, public preference type tests and bounded diagnostics. It retained one
constructor testability criterion: PR-title clock and lookup dependencies must
be injectable. A separate atomic refactor adds optional constructor inputs,
resolving omitted values to the same monotonic clock and read-only adapter.

Cache, expiry, partial-result and deadline tests use those injected
dependencies instead of assigning a private clock or replacing a module
adapter. Response, journal, sidecar and frontend contracts remain unchanged.
The measured spike report remains explicitly scoped to runtime `1011471`; its
figures are not new measurements of this later refactor. Final candidate gates
and assessment remain tracked in
[PR #9](https://github.com/leynos/ishiban/pull/9).

### Foreign title results and turn histories, 11 November 2026

The refreshed pre-merge checks identified two further coverage gaps. Separate
PR-title cases now return a foreign workspace or foreign session, wait for the
response to be consumed and React to settle, then check that the current title
remains intact. Existing matching-identity coverage is the positive control.

A bounded Hypothesis property generates interleaved turn starts and finishes
across four identities. Every history prefix checks active identity uniqueness
and membership against an independent last-operation model, latest outcomes,
unchanged session/PR context and input immutability. Explicit cases retain
unmatched finishes, repeated starts, reopening and interleaving. The suite runs
100 generated histories of at most 30 events; this is finite evidence, not a
formal proof. Runtime source remains unchanged from `34fdfbf`; final candidate
validation and review remain tracked in
[PR #9](https://github.com/leynos/ishiban/pull/9).

### Ownership and graph-model acceptance, 11 November 2026

Assessment 10 confirmed the preceding repairs and retained two coverage gaps.
The CLI contention case now holds the actual state-directory lock while a
second collection attempt is rejected before a catalogue read, observer start
or journal initialization. Releasing ownership permits a later attempt. A
private lock-disabled probe fails the new assertion.

The graph property compares public family roots, context and exact membership
with an independent transitive-reachability model over 100 generated graphs of
one to nine nodes. Explicit controls include missing-parent chains, siblings
sharing an absent parent, self-links, cycles and paths into cycles. ADR 007 now
states the existing smallest-cycle-ID rule precisely. The reviewed
import/binding-only detector family has an exact file-pair exception; no graph
algorithm is shared with production. AGENTS now correctly distinguishes normal
xdist tests from the serial CI coverage lane. These changes do not alter
runtime source. A separate activity-clock injection refactor remains before the
affected final assessment, as tracked in
[PR #9](https://github.com/leynos/ishiban/pull/9).

### Activity observation clock, 11 November 2026

Assessment 10 retained the activity wall-clock injection criterion separately
from the PR-title constructor change. `resolve_activity` now accepts an
optional epoch-nanosecond clock in frozen internal resolution options, called
after a successful read and converted to integer milliseconds with the existing
floor operation. Omitted callbacks retain call-time system wall clock
behaviour. The monotonic TTL clock remains a separate reader dependency.

Tests supply a fixed epoch value, verify the returned observation time and its
sidecar persistence, and check default composition. Raw journal state and the
durable cursor remain unchanged. Single and batch callers share the options
record, keeping the function within its four-argument limit without a lint
waiver. This is a separate testability refactor; no new request, response or
preference fields are introduced. The spike report retains its original
measured runtime scope. Candidate-specific gates and affected reassessment
remain tracked in [PR #9](https://github.com/leynos/ishiban/pull/9).

### Stream and timestamp boundary checks, 11 November 2026

Fresh pre-merge findings identified missing source-event recovery assertions,
limited generated timestamp precision and conflicting frame-limit wording.
Tests now drive the actual live connection through valid source and observation
events, invalid identities and cursors, and reset-required recovery. The shared
EventSource fixture retains transport state and cleanup while production owns
validation and replay.

A separate generated oracle builds absolute microsecond instants and encodes
varied offsets and fractional precision. It checks latest-tab selection,
equal-instant tie-breaking and rejected calendar/offset values through public
family grouping. These are bounded tests, not formal proofs. The developer
guide distinguishes browser UTF-16 frame units from server UTF-8 frame bytes
and total response bytes. No runtime behaviour changes.

The declaration-only duplication exception now identifies all three family test
modules; no scenario or oracle algorithm is shared. The obsolete activity
resource pair exception is removed because the clock refactor no longer matches
it. Candidate-specific quality gates, negative controls and affected assessment
remain recorded in [PR #9](https://github.com/leynos/ishiban/pull/9).

### Filter and pagination checks, 11 November 2026

The saved test rows subsequently identified missing rendered filter/reset
coverage and generated static turn-page traversal. Board tests now select
activity and archive controls, then combine all filters and reset them through
the visible button, checking both control values and real session marks.

A bounded Hypothesis test seeds multiple event groups with varied turn counts,
walks every public detail cursor and compares the concatenated pages against an
independent event-ID/turn-ID ordering. It checks exact-once membership, page
size and termination, with explicit boundary examples. This property assumes a
static journal during traversal; concurrent updates remain outside the
pagination contract. No runtime behaviour changes. Candidate-specific gates and
affected confirmation remain tracked in
[PR #9](https://github.com/leynos/ishiban/pull/9).

### Installed migrations and process teardown, 11 November 2026

Formal review identified two reproducible runtime defects. An isolated wheel
install omitted the top-level migration scripts and searched `site-packages` as
though it were a checkout. Wheel packaging now includes those canonical scripts
beneath the package. Embedded initialization selects installed resources with
an in-memory Alembic configuration, preserving the checkout fallback and
synchronous migration bridge within async schema initialization. A real-wheel
regression checks isolated imports, migration head and snapshot, then exercises
the installed collector against a fake Lody stream and verifies durable
ingestion and SIGINT shutdown.

A TERM-resistant child can fill its stdout pipe while the caller has stopped
reading, leaving `Process.wait` pending even after SIGKILL. Teardown now drains
stdout without retaining payload and bounds both termination phases. The
feature-local cleanup module owns a seven-second task independent of caller
cancellation, then propagates cancellation after teardown. Native regressions
cover repeated cancellation and already-exited children as well as pipe
backpressure. A local review also identified cancellation/error precedence; a
deterministic regression checks that cleanup failure remains the cause of
cancellation rather than replacing it. Owned pipe tasks are cancelled and
reaped on exit. The native-child regression exercises early JSON completion
followed by excess output and checks actual SIGKILL, completed wait and drainer
cleanup. These are dedicated lifecycle fixtures because ordinary command mocks
cannot model pipe backpressure.

Both regressions failed against the prior implementation. Candidate-specific
quality gates, review replies and affected assessment remain tracked in
[PR #9](https://github.com/leynos/ishiban/pull/9).

### Cancellation at the context boundary, 11 November 2026

Assessment 12 identified cancellation that precedes teardown as a distinct
ordering. The child owner now forwards a cancellation received in the context
body to the bounded cleanup owner. Cleanup finishes before the original
cancellation, including its message, is re-raised; a cleanup failure remains
its cause. A native-child regression cancels a blocked stdout read before
forcing cleanup failure. It failed with a raw timeout before the fix and now
preserves the cancellation outcome. Existing during-cleanup cancellation and
uncancelled-error cases remain covered. Candidate-specific gates and post-push
disposition are tracked in [PR #9](https://github.com/leynos/ishiban/pull/9).

### Queue histories and inspector stack heading, 11 November 2026

The generated activity checks now vary bounded visibility histories, revision
placement and request-completion order through the real lazy scanner. An
independent eligibility oracle checks emitted identities, while explicit
controls check batch/concurrency limits, stale results, dropped-work
rediscovery and unchanged durable cursor semantics. Shared activity transport
and viewport fixtures replace repeated test plumbing; an obsolete import-only
duplication exception is removed and the existing cross-domain accessor guard
exception follows its moved function.

For multiple PRs the inspector now chooses a graph tip, with explicit fallback
when GitHub has retargeted branches or metadata is unavailable. Branch and
merge facts remain bounded inspector-only enrichment. The actual example is
child tab `8bc61941-06c0-4536-aae3-3e3d8e326510`, whose parent holds the
[merged prerequisite PR #740](https://github.com/leynos/axinite/pull/740) and
[open dependent PR #364](https://github.com/leynos/axinite/pull/364). The
latter's existing title includes issue reference `(#333)`; that exact title is
retained. It is not renamed to PR #333. Named regressions cover ordering, fork
isolation, fallback and late title arrival. Candidate-specific gates, browser
validation and post-push dispositions remain tracked in
[PR #9](https://github.com/leynos/ishiban/pull/9).
