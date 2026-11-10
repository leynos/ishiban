# Developer guide

This guide explains the contributor workflow for the Ishiban proof of concept.

## Observation runtime

The [repository layout](repository-layout.md) locates the Python runtime,
frontend, and tests. Run the collector and Falcon API as separate processes
sharing one ignored state directory. The collector is the only writer, with a
local process lock and serialized SQLAlchemy transactions. Falcon serves the
Bun-built `dist/` directory and reads short SQLite transactions.

Use `msgspec` at the CLI boundary, Effect Schema at the browser boundary, and
keep workflow classification in `ishiban/workflow.py`. The browser applies
immutable post-event projections by cursor; it does not repeat the Python
classifier. The client scopes fetch and EventSource lifetime with Effect,
closes subscriptions on mode changes, and coalesces React notifications through
animation frames. PR-stage evidence and its limitations are recorded in
[ADR 002](adr-002-workflow-evidence.md).

Observer and catalogue subprocesses use fixed argument vectors without a shell.
Their protocol lifecycle requires asyncio pipe streaming; the collector owns
bounded stdout, a draining stderr task, cancellation, termination, and reap.
Raw stderr is never persisted. GitHub lookups admit only validated GitHub PR
URLs and issue bounded read-only GraphQL queries. No generic command-execution
helper or public adapter is introduced by these private runtime modules.

SQLite WAL, foreign keys, busy timeout, and explicit transaction isolation are
configured by `ishiban/storage/`. Alembic applies the initial schema on
startup. Do not delete a journal to resolve a transient source error. Source
stream/sequence identity deduplicates replay; the independent local journal ID
is the public SSE cursor. The workspace-filtered `read_cursor` query is shared
by snapshot reads and `Store.current_cursor`; use the latter when a caller only
needs the replay boundary, such as SSE reset validation. Metadata and durable-
evidence generations remain separate during reconciliation.

The storage serialization module owns decoded JSON string-field access and UTC
journal timestamps. These helpers are private to persistence; reuse them for
storage readers and writers, rather than introducing a general application
utility layer. Session lookup uses the same transaction-bound projection loader
in detail reads and writes. Snapshot and incremental-turn projections share one
private turn-field encoder, including optional-key omission. Frontend table,
list, and exception marks share `SessionSelectionProps` so keyboard trigger
identity travels through the same callback contract.

Run `bun run build` after frontend changes; the resulting bundle is what Falcon
serves and what browser validation must inspect. `make test` includes Python
unit/integration tests, pytest-bdd provenance scenarios, Hypothesis journal
properties, Bun renderer tests, and generated browser projection replay. Use
agent-browser for keyboard/inspector/filter/reconnect checks and accessibility
audits; use css-view to verify computed semantic tokens and five-column mark
grids rather than assuming CSS source declarations took effect.

The opt-in Chromium geometry suite requires `agent-browser` and a built bundle:

```sh
make build-web
ISHIBAN_BROWSER_TESTS=1 bun test tests/board-layout.browser.test.ts
```

Scope that environment flag to this file. The suite restores Bun's native HTTP
globals after the Happy DOM preload, serves built assets with synthetic
snapshots and real SSE, and closes its own server and browser. Its fixture
helpers belong only to these browser layout scenarios. Default unit-test runs
skip the browser cases. Geometry checks cover the pane's horizontal overflow
with and without the inspector, compact evidence visibility, and task-bounded
list pulses with reduced-motion support.

## Local workflow

The public entrypoint for formatting, linting, typechecking, tests, and
spelling is `make all`. Narrower Make targets may be invoked when investigating
a specific failure, and changes should be reconciled with the aggregate gate
before being considered complete.

`make lint` checks tracked and untracked Python sources discovered by Git,
including sources under hidden action directories. It runs Ruff 0.16.8,
Interrogate for 100% docstring coverage, Pylint, the DF12 Python lint plugin,
Ambrleaks on `tests/`, the strict Skylos gate and Vulture on test helpers, the
shared Nose duplication gate, and workflow/action validation. Pylint's base
sweep runs on PyPy 3.12 when the selected Python baseline is exactly 3.12; for
a newer baseline it runs on CPython at that baseline. The baseline is the
selected `python_version`, with 3.12 as the minimum supported version. The DF12
Python Lints v0.4.0, Ambrleaks, Skylos, Vulture, and duplication tools run as
isolated tools on Python 3.14.

With default Git source discovery, `fmt`, `check-fmt`, `lint-python`, and
`typecheck` stop with a diagnostic before running tools if Git or repository
metadata is unavailable. GNU Make 4.2 or newer captures one Git result and
checks its `.SHELLSTATUS` immediately; the tools share that captured source
list. `help` and `build` do not depend on source discovery; initialize the
generated project with `git init` before its first quality-gate run.

Rust-enabled projects declare only the PyO3 module initializer as a runtime
entrypoint. The native import tests exercise that boundary, and unused sibling
functions remain blocking.

`make typecheck` runs `ty`, pinned at `0.0.56`: unpinned installations broke
repositories when ty 0.0.56 landed. Bump the pin deliberately — update the
version and fix any new diagnostics in the same pull request.

Ruff and `ty` run from isolated tools on Python 3.14; their versions are pinned
to Ruff 0.16.8 and `ty` 0.0.56. `make check-fmt` and `make fmt` also check or
apply Markdown table formatting with mdtablefix 0.6.1.

`make lint-actions` validates YAML under `.github/` with yamllint 1.38.0,
workflow syntax with actionlint, composite actions with action-validator, and
shell scripts with shellcheck. `make markdownlint` runs markdownlint-cli2 and
the spelling gate. Spelling uses `typos-config-builder` with scope `all`.

Run `make audit` as the dependency vulnerability gate. It runs `pip-audit` for
Python dependencies and `bun audit` for the JavaScript lockfile. Rust-enabled
projects also run `cargo audit` from the `rust_extension` crate directory.

## TypeScript tooling

Install Bun 1.4.x before running the JavaScript gates. CI and `package.json`
pin Bun 1.4.3; `make install-js` rejects other release lines and installs the
committed `bun.lock` with `--frozen-lockfile`. Oxlint's JavaScript plugin host
uses Node.js 24 or 26; CI pins Node.js 24.11.1. With nvm, `nvm use 24` selects
the matching release line. Both installed release lines pass the tooling suite.

The shared Make targets include both language toolchains. The narrower targets
are useful while developing the frontend or maintaining the lint plugin:

| Target              | Purpose                                                  |
| ------------------- | -------------------------------------------------------- |
| `make install-js`   | Install locked JavaScript development dependencies.      |
| `make fmt-js`       | Apply Biome formatting.                                  |
| `make check-fmt-js` | Check formatting without linting or writing files.       |
| `make lint-js`      | Run Biome and type-aware Oxlint.                         |
| `make typecheck-js` | Run TypeScript with no emitted output.                   |
| `make test-js`      | Run Bun tests, property checks, and bundle verification. |
| `make audit-js`     | Check the JavaScript lockfile for known vulnerabilities. |

Table 1: JavaScript and TypeScript quality gates.

Biome uses Simulacat's formatting and rule configuration: two spaces,
120-column code, single quotes, semicolons, and no trailing commas. It enforces
70-line functions, at most four parameters, and cognitive complexity eight.
Oxlint adds McCabe complexity eight, nesting depth three, and the local df12
predicate and documentation rules, alongside `unicorn` and `ai-deslop` rules.
Type-aware checks use the pinned `oxlint-tsgolint` backend. Temporary
suppressions must explain the invariant and link to the planned removal.

`tsconfig.json` covers TypeScript and TSX in `src/` and `tests/`, with strict
checking, exact optional properties, checked indexed access, explicit
overrides, and bundler module resolution. The imported plugin and its fixtures
remain JavaScript, checked by both linters and the Bun behavioural tests. No
legacy JSDoc baseline is imported.

The standalone HTML in `reference/` is supplied design material and stays
outside the JavaScript tool scopes. The live frontend belongs in `src/`; its
code must pass the same gates as the tooling tests.

`tools/oxlint-plugin-df12/` is an imported implementation of the established
df12 rules, split into predicate complexity, JSDoc validation, and internal
JSDoc helpers to meet the repository's 400-line file limit. Those helpers are
private to this plugin, and `tests/fixtures/oxlint.js` is private to its tests;
neither is an application utility or public API. Preserve the plugin's bundled
MIT licence when copying it elsewhere. The
[tooling decision](adr-001-typescript-tooling.md) records its provenance,
dependency pins, and scope.

Bun 1.4.x owns JavaScript testing and bundling. The tooling suite verifies the
bundle API using a disposable TypeScript entrypoint. Add an application bundle
target when a real frontend entrypoint exists; no application bundle is
produced by the current Python `make build` target.

## Automation scripts

The [Scripting standards](scripting-standards.md) document provides guidance
for adding or updating helper scripts. New and updated scripts are expected to
use `Cyclopts` for command-line interfaces, `cuprum` for typed and
catalogue-bound external command execution, `pathlib` for filesystem paths, and
`cmd-mox` for tests that mock external executables.

Script changes should update the scripting guide when they introduce a new
convention, command catalogue, testing pattern, or operational expectation that
future contributors need to follow.

## GitHub Actions

The generated repository includes GitHub Actions workflows and local composite
actions under `.github/`.

- `.github/workflows/ci.yml` runs on pushes to `main` and on pull requests. It
  sets up the selected `python_version` baseline (at least 3.12), installs
  `uv`, validates the generated `Makefile` with `mbake`, installs CLI tools,
  then runs `make build`, `make check-fmt`, `make lint`, `make typecheck`,
  `make markdownlint`, and `make audit` except for Dependabot pull requests via
  `if: github.actor != 'dependabot[bot]'`. The Markdown target includes
  repository-wide spelling. CI provisions Go and Rust/Cargo toolchains for
  installing CLI tools, then delegates coverage generation to the shared
  coverage action. Rust lint and test tools are installed and
  `rust_extension/Cargo.toml` is passed to coverage only when the Rust
  extension is enabled.
- `.github/workflows/audit.yml` runs `make audit` against the default branch
  weekly as the compensating control for the Dependabot CI bypass.
- `.github/workflows/act-validation.yml` runs rendered workflow validation in a
  separate workflow. It installs `act`, checks Docker availability, and runs
  `make test WITH_ACT=1` outside the coverage path.
- `.github/workflows/release.yml` publishes wheels when a `v*.*.*` tag is
  pushed. It builds a pure Python wheel, creates a GitHub release with
  generated release notes, downloads wheel artefacts, and uploads them to the
  tag release.
- `.github/workflows/build-wheels.yml` is a reusable workflow for extension
  builds. It accepts a Python version and builds wheels across Linux, Windows,
  and macOS architectures via `.github/actions/build-wheels`.
- `.github/workflows/get-codescene-sha.yml` is manually dispatched. It fetches
  the CodeScene coverage CLI installer, computes its SHA-256 digest, and writes
  the result to the `CODESCENE_CLI_SHA256` repository variable.

- `.github/workflows/mutation-testing.yml` runs daily at 09:30 UTC and supports
  manual dispatch. It delegates to reusable workflows from
  `leynos/shared-actions`; stagger the generated cron schedule before adopting
  it alongside other repositories.

  The mutmut job is generated only when the minimum Python version is 3.13 or
  newer because the shared workflow helpers require Python 3.13 or newer.

- `.github/actions/build-wheels` wraps `cibuildwheel` with `uvx` and uploads
  architecture-specific wheel artefacts.
- `.github/actions/pure-python-wheel` builds a pure Python wheel with
  `uv build --wheel` and uploads the resulting artefact.
- `.github/dependabot.yml` enables dependency update pull requests for GitHub
  Actions and Python packages. Rust-enabled projects also receive Cargo updates.

CI provisions Go 1.27 before installing Actionlint 1.7.12, whose minimum is Go
1.25; module caching is disabled because the project has no Go module. It also
provisions stable Rust/Cargo for the `mdtablefix` `cargo-binstall` installer in
both pure-Python and Rust-enabled projects. These prerequisites do not change
the selected `python_version` application baseline. In Rust-enabled projects,
the Rust lint and test cache uses the `rust_extension -> target` workspace
while retaining the tool-cache directories; Rust-specific cache configuration
and tools remain conditional on the extension.

The `CS_ACCESS_TOKEN` secret must be configured when CodeScene coverage upload
is required. The `CODESCENE_CLI_SHA256` variable should be populated using the
refresh workflow, so CI can verify the downloaded CodeScene installer before
upload.

## Shared spelling configuration

Run `make spelling` to enforce en-GB-oxendict spelling. The shared
`typos-config-builder` gate regenerates `typos.toml` from the live estate
dictionary in `leynos/agent-helper-scripts` and the `typos.local.toml` overlay
on every run, then checks all repository content. A word added to the shared
dictionary therefore needs no change here, and `typos.toml` must never be drift
checked in continuous integration. `typos.toml` is generated output, but it is
tracked: commit the regenerated file after a `make spelling` run changes it.
The local cache that keeps the gate usable when the authority is temporarily
unreachable is ignored by Git. Add only narrow project-specific terms and
exclusions to `typos.local.toml`; never edit generated `typos.toml` by hand.

## Proof-of-concept boundary conventions

The API marks responses `Cache-Control: no-store`. Browser assets currently
have stable filenames, so a local rebuild must not leave old interaction
handlers in a browser's heuristic cache. Fingerprinted production assets are
outside this spike.

The collector applies migrations to its selected state directory through an
injected SQLAlchemy connection. Standalone Alembic commands use the synchronous
SQLite driver and target `.ishiban/observatory.sqlite3` relative to the
checkout's `alembic.ini`, independently of the caller's working directory.
Create that state directory first. A custom collector `--state-directory`
continues to use its injected connection rather than the standalone URL.

Storage assertion shapes live in `tests/storage_contracts.pyi`. These static
contracts describe camel-case public JSON fields without constructing unused
runtime classes. The test helpers import them only for type checking.
`pytest-bdd` step decorators and Falcon lifecycle callbacks are documented
runtime entry points in the quality configuration; their implementations remain
subject to linting and behavioural tests.

## Duplication review

The spike consolidates decoded string access, UTC timestamps, session lookup,
turn-field encoding, and board selection contracts. The remaining reviewed Nose
families are immutable migration declarations, explicit module imports,
independent test boundary reads, typed contract casts, Falcon injection
constructors, and short presentation or transport-state branches. The snapshot
and cursor-only store accessors retain their own initialization and transaction
wrappers; their shared cursor SQL is extracted. The transport tests share only
fetch-spy and virtual-clock ownership, keeping each failure scenario's
assertions independent.

On-demand activity and inspector metadata retain distinct response schemas and
failure results, while sharing bounded subprocess ownership. Projection-only
and transcript-bearing reads use distinct existing queries under explicit
transactions. Their short transaction wrappers, injected resource constructors,
and independently arranged API/clipboard assertions are reviewed duplication
exceptions rather than reasons to couple unrelated contracts. Title-cache TTL
scenarios share one parametrized test for positive and negative expiry. Reader
tests share process creation and call-log polling while preserving different
observer/session-show envelopes. Brief setup and partial-result assertions
remain independent where the tests distinguish cache expiry, identity
validation, waiter cancellation, and service shutdown.

Each exception in `pyproject.toml` records its participating units or exact
files and its reason. Nose reports anonymous fragments without enclosing unit
names; those exceptions require file paths rather than function names. Review
these records whenever their files change, since native file matching can also
cover later fragments in those files. Do not add new copies or extend these
exceptions to unrelated files without another review. Frozen migrations must
remain independent of evolving model metadata, and source protocol records must
remain independent of journal-write records.

The detail-page tests share one seeded API fixture, collector lifecycle tests
share one cached-PR setup, and coverage workflow tests share a local action
loader. `storage.reader._read_turn_page` owns the bounded keyset query,
lookahead and continuation; `read_detail` composes it with current session and
provenance reads. Workflow classification handles association eligibility and
active PRs, while `_classify_terminal` handles terminal evidence. The only new
Nose exception is the anonymous two-line nullable guard shared by
`detail_pagination.parse_turn_cursor` and
`storage.projections._turn_projection`. Nose cannot name these fragments by
function or range, so the exception names the exact file pair it supports. One
guard selects the API's first page; the other handles an absent stored turn. A
shared helper would couple unrelated contracts for trivial indirection. Revisit
the exception if cross-file duplication grows beyond that guard. The former
`Store.detail`/ `Store.session_projection` exception is removed because the
current scan no longer reports that family.

The client exposes its connection lifetime as `liveConnection`, an Effect
consumed by the cancellable `startLive` browser adapter. Scheduled retries
continue until the owner cancels the connection; transient failures update
visible transport health. Browser-managed EventSource reconnection retains its
stream, while a permanently closed source fails the scoped connection and
causes a fresh snapshot and stream after the retry delay. Tests supply Effect's
virtual clock to verify retry and cancellation behaviour without changing
production delays. The controllable EventSource fixture is confined to this
transport test and preserves the browser's connecting/open/closed states.

Protocol validators remain private to the Lody boundary. Compatibility,
process-local sequencing, session evidence vocabulary, and turn payloads have
separate checks; no generic application-wide validation framework is implied.
Journal ingestion validates identity and generation before routing to the
existing event-specific projection writers.

GitHub enrichment returns a private `_PullRequestLookup` with `records` and
`is_partial`. Its only production consumer is collector reconciliation. Each
bounded batch retains usable typed GraphQL fields, including after a nonzero
CLI exit, and a failed batch leaves other batches intact. Error objects retain
only failure markers; their messages are ignored. Partial enrichment keeps a
visible source warning. Fresh terminal catalogue statuses override older cached
active statuses while preserving a known PR title.

`CatalogueFramer` is private to the catalogue subprocess adapter. It scans
incoming bytes once to locate an object boundary; the protocol decoder then
validates the entire buffered document exactly once. This preserves completion
before transport EOF without repeatedly copying and parsing partial buffers.
Framing alone never establishes JSON validity. Generated chunk-boundary tests
cover quoted delimiters, escapes, UTF-8, and root completion.

Transient update cues belong to the board's private session-update hook. They
compare accepted projection revisions, expire through an owned cleanup timer,
and reset when the workspace changes. Density, filters, and panel selection do
not become observation events. Pulse overlays leave task-button identity and
keyboard focus intact; a repository or stage move may replace a button, so
focus restoration follows the session identity instead of an obsolete node.

The inspector is a native complementary region with explicit close and focus
restoration behaviour. Its desktop grid reserves a right-hand column; narrow
viewports stack the panel. The board owns its scroll viewport, including while
the inspector is open. The former modal-only Radix Dialog dependency is removed.

## Inspector navigation and turn diagnostics

`serve` passes the marker's configured workspace selector to the snapshot API
as optional `workspaceSlug` navigation metadata. The inspector accepts a
slug-shaped selector distinct from the opaque workspace ID for HTTPS links;
otherwise it uses Lody's canonical workspace-qualified native session URI. Both
URL formats were checked against the installed CLI and public Lody app router.
IDs are encoded, the origin is fixed, and demo sessions omit the link. Restart
the API after updating this routing metadata.

Ishiban accepts an optional `error` string on a turn projection or turn-finish
envelope. This is a forward-compatible extension, not a claim that the
installed Lody observer emits the field. Failed-turn errors are capped at 4,096
characters in the existing projection JSON and replay payloads. No relational
schema migration is needed. The shared turn encoder takes a typed `Turn` so
snapshot and incremental paths use the same optional-field policy. A restarted
or successful turn does not inherit an earlier error. React renders diagnostics
as text; source/transport errors remain independent collector health evidence.
Older journals and missing error fields remain readable. The current CLI's
observer and visible-history output omit the underlying provider diagnostic;
there is no transcript scraping or additional history polling in the runtime.

## Preference cookies and cached activity

[ADR 003](adr-003-interface-state-and-lazy-activity.md) defines the separation
between the journal, browser preferences, and direct activity reads. The
`interface-state` endpoint accepts only bounded, validated density/presentation
updates. itsdangerous signs a msgspec MessagePack dictionary with a versioned
salt; the private key in the state directory survives API restarts. Snapshot
responses restore preferences from that cookie. The React preference hook owns
ordered writes and save status; no initial-render write or localStorage cache
is needed.

The lazy activity service owns bounded read-only CLI observations, a four-child
limit, execution-watermark-keyed caching and shared in-flight requests. The
API's `session_projection` read reuses the existing projection query without
loading transcripts. Lazy response projections are marked separately and do not
create journal rows. The client activity merge is scoped to the live store and
rejects foreign, stale, or already-resolved revisions. Intersection and
mutation observers own visible-mark discovery and cleanup; requests that have
not started are skipped when their mark leaves the viewport. Update-cue
tracking suppresses lazy enrichment even if an earlier journal cue is still
active. Discarded queued work releases only its own retry marker, so a task
revealed again can be read immediately without clearing a newer attempt's
backoff.

Inspector agent metadata uses a separate bounded reader and 128-entry TTL
cache. The only exported fields are agent type, configuration ID and
configuration name; configuration commands never use `--show-secrets`. The copy
control uses the Lody projection's session ID directly, not `acpSessionId`.
Clipboard failures are reported accessibly. Missing PR names are fetched only
for the selected session and cached separately; this includes terminal PRs and
cannot change workflow classification. The primary known PR name becomes a
linked heading, with the original session title retained below it. PR numbers
are parsed from the supplied URLs and rendered in the neutral text colour.

The shared bounded JSON-object reader belongs only to read-only CLI adapters.
Catalogue, activity and metadata readers supply their own limits and perform
their own typed decoding. It closes stdin, detects a complete root object once,
and reaps the child without waiting indefinitely for transport EOF.

Lazy activity is retained through metadata and persisted-source unknown
updates, reconnect snapshots and full reloads. Incoming metadata and event
cursors still advance. [ADR 004](adr-004-persist-on-demand-activity.md) defines
the persistent cache and execution-watermark precedence. Direct lazy results
still suppress their own pulses.

`storage.activity_cache.ActivityCache` owns only derived runtime observations
in the journal's `.activity.sqlite3` sidecar. `Store.snapshot`, `Store.detail`
and `Store.events` remain raw readers. `Store.activity_snapshot` and
`Store.restore_activity` prepare API views; `Store.remember_activity` checks an
execution watermark before rebasing and caching and returns a freshly checked
view. API replay decorates its own copies, preserving the stored event and its
cursor. The sidecar uses SQLAlchemy and bounded upserts without a journal
migration. Sidecar creation uses SQL-level `IF NOT EXISTS` and bounded
asynchronous retries for SQLite busy/locked errors during initial WAL setup,
allowing the API and collector to start concurrently. Other startup failures
propagate immediately. Generated cache-ordering tests vary execution watermarks
and Unicode metadata to check invalidation, metadata preservation and
projection immutability.

The cache and journal retain separate initialization guards because they own
different engines. Their short guards, explicit envelope fixtures and
independent cache-ordering/eligibility assertions are reviewed duplication
exceptions. Browser reconnect tests share a parametrized metadata/persisted
case while keeping newer-execution and workspace-reset assertions separate.

Configuration reads may opt into the installed CLI's known Remote Streams
transport chatter. The shared reader discards only that recognized prelude and
uses the exact root-object boundary; other readers retain strict whole-buffer
JSON decoding. Unknown prelude text is rejected. Raw transport text and
configuration environment values are not retained in the metadata cache.

Skylos does not propagate reachability from the interface-state Falcon handlers
through the injected signer or their body/mapping helpers. Four exact qualified
symbols are recorded as runtime entry points, with their actual callers in the
configuration reasons; no name-wide whitelist is used. API tests exercise these
paths through real Falcon requests. Shared reader fixture option types in
`tests/lody_reader_fixtures.py` belong only to the activity and agent reader
tests; they are not application data contracts.

`tests/lody_process_support.py` shares executable-script creation and call-log
reading between those two reader suites. Each suite retains its own protocol
fixtures and assertions. `tests/deferred.ts` supplies controlled asynchronous
completion for browser-hook tests without production timing delays.

[ADR 005](adr-005-batched-activity-and-update-cues.md) defines streaming batch
activity and semantic pulse comparisons. `batch_activity_api` owns only bounded
HTTP decoding and response-waiter cleanup; `activity_api.resolve_activity`
shares projection restoration and lookup precedence with the single-session
route. `src/activity-batch.ts` owns incremental UTF-8 NDJSON decoding and
Effect frame validation, with a 1,048,576-character frame limit and an
eight-MiB response limit. These helpers are specific to activity reads and are
not generic transport APIs. The browser pipelines two four-member batches; the
shared reader permits four children and 64 pending observations with a
45-second total lifetime. Metadata replay preserves in-flight identity
ownership and execution-watermark reuse.

The server pre-encodes each public batch frame, including its newline, against
the browser's 1,048,576-byte UTF-8 limit. An oversized member becomes a typed
`response_too_large` marker; a marker whose identity cannot fit causes a
pre-stream HTTP 413. The browser keeps reading smaller siblings while one owned
single-session GET recovers the marked member under the same batch deadline.
That GET uses `includeKnown=true` so a session that became known between batch
preparation and fallback returns its current projection without another Lody
read. The GET's eight-MiB body bound, abort signal, and revision guard remain
local to activity transport. The fixed activity diagnostic is quiet, survives
metadata-only refresh while the execution watermark is unchanged, and never
changes a turn's error or the journal. This boundary does not cap private
projection decoding or cache memory; see
[ADR 006](adr-006-public-turn-previews-and-cursors.md).

The dead-code configuration records the batch handler's exact bounded decoders
and msgspec request type as runtime entry points; Falcon dispatch is not
propagated by Skylos.

The batch decoder and preference endpoint share
`request_body.read_bounded_body`, which accumulates HTTP bodies only. Each
caller supplies its own byte limit and diagnostic and owns JSON decoding. This
helper is restricted to bounded JSON API requests; CLI transport ownership
remains separate. Semantic cue comparison stays separate from animation
mutation, with a single unchanged-object fast path before comparison.
Queue-bound tests share their fake-service setup; browser batch tests share
controlled board setup. Batch API tests reuse session seeding and cache setup
from `tests/batch_activity_support.py` and retain independent assertions.
`tests/activity-fetch-fixture.ts` shares only deterministic fetch request
recording between browser activity suites.
`tests/lazy-activity-fallback-fixture.ts` keeps response variants and their
semantic expectations beside the fallback suite; neither helper is a production
transport abstraction.

Command-response fixtures use the dev-only `cmd-mox` 0.2.0 dependency and the
plugin registered in `tests/conftest.py`. The exact `pytest_plugins` runtime
entry-point name joins `pytestmark` in the Vulture configuration. Prefer its
`cmd_mox` fixture for ordinary CLI outcomes and assert the recorded arguments
and invocation count. The fixture owns replay, verification and cleanup; do not
duplicate those lifecycle calls. Dynamic responses use a command spy with an
`Invocation` to `Response` handler. The batch ASGI test still launches real
shim subprocesses, without writing a private executable or parsing call logs.
Keep dedicated real process fixtures for tests of transport chunking, delayed
EOF, timeout and cancellation behaviour that command-response mocks do not
model.

Code-health cleanup separates the CLI reader into bounded raw chunks, the
optional recognized transport prelude, and `CatalogueFramer` completion.
`_OwnedChild` owns subprocess termination and stderr-drainer cleanup. These
seams belong to the read-only CLI adapter; other process callers retain their
existing lifetimes. Protocol validation uses ordered feature-local rules so
first-error selection stays stable across decoding and evidence checks.

`storage.activity_projection` owns pure cached-runtime validation and overlay;
`storage.activity_cache` retains SQLite lifecycle and transaction ownership.
The pure helpers are confined to this derived-runtime feature.

The batch API partitions current projections once before cache restoration and
pending observations. Browser `ActivityVisibility` owns mark discovery and DOM
observer cleanup, while the PR-title lookup owns its timeout and cancellation.
Inspector PR rows and session facts remain presentational. These helpers are
scoped to their existing features and preserve journal and browser contracts.

### Coverage instrumentation

PR and main coverage use `.github/coverage-constraints.txt` for the action's
separate dependency installation. The verified pytest 9.1.0/SlipCover 1.1.0
combination avoids the unsupported pytest assertion-cache hook. Coverage runs
serially because the current xdist instrumentation misses dynamically loaded
Alembic migration hits; normal unit tests retain their parallel execution. The
known instrumentation-activation warning is an error in coverage lanes. Revisit
the pytest pin when upstream compatibility and serial/xdist migration checks
both pass; the investigation is recorded in
[the PR discussion](https://github.com/leynos/ishiban/pull/9#issuecomment-6771868675).

The user authorizes a one-time reset of the historical cached Python baseline
to zero during this delivery. This preserves measurement scope and the
one-percentage-point ratchet tolerance. The next successful main publisher
establishes a new measured baseline; future scope or tool changes still need
comparable measurements or an explicit baseline policy decision.

The main coverage job runs only when `github.ref` is `refs/heads/main`,
including manual dispatch after a token-authored automerge. It forces the
shared action to publish the measured baseline on that manual path; the
pull-request lane never publishes a baseline. A manual dispatch from another
ref is skipped by the job guard. The next authorized main update must verify
that the publisher actually saves the measured baseline instead of
bootstrapping zero again. An unexpected cache miss still uses the authorized
zero bootstrap, so it is not evidence that measured publication succeeded.

`cache_entries.fresh_cache_entry` shares only monotonic expiry and LRU touch
behaviour between activity and PR-title lookups. Each adapter retains its own
keys, entry payloads, clocks, positive/negative TTLs, capacity and async work.
A cached unavailable payload remains distinct from a missing or expired entry;
this helper is not a shared service lifecycle or persistence abstraction.

Python Syrupy snapshots use `.ambr`; Bun snapshots use `.snap`. Pytest ignores
the Bun extension during unused-snapshot discovery, while both runners retain
their own snapshot assertions and unused Python snapshot checks.

`detail_pagination` owns only the versioned, bounded continuation encoding and
identity validation for session-turn pages. Version 2 hashes a structured
workspace/session pair and carries an event ID plus rank within that event's
turn group, so token size ignores identifier length. `storage.reader` counts
that rank under the same SQLite transaction and collation used by the ordered
100-turn page. Continuing scans from the event ID and skips the rank, which can
shift under concurrent writes; version 1 tokens require a first-page restart.
`Store.detail` owns its read transaction, and the Falcon route maps malformed
cursors to HTTP 400. The cursor is a position in current materialized state,
not a replay cursor or frozen snapshot.

`public_projection.public_session` is the sole transport copy boundary for
active-turn previews. It runs after activity sidecar overlays in snapshot,
detail, SSE, and single and batch activity responses. It selects a stable
100-turn preview and derives exact count, truncation, and a full-set digest
from user turn identity, state, and error. Stored projections and sidecar cache
entries stay complete. This response bound does not limit private JSON, SQL
decode work, process memory, or individual field byte length. See
[ADR 006](adr-006-public-turn-previews-and-cursors.md) for the trade-off and
reuse scope.

`tests/board-fixtures.unknownRuntime` supplies only the shared unknown activity
fields for board pulse and client retention tests. Each test keeps its own
collector metadata, revision transitions, and assertions. It is not a general
session or catalogue fixture.
