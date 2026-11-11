# Ishiban users' guide

Ishiban is a local read-only proof of concept for observing one Lody Cloud
workspace. The interface combines observed session activity with independently
classified PR workflow stages. It never sends prompts, acknowledges messages,
answers permissions, cancels sessions, or modifies GitHub PRs.

## Run the observatory

Install Python 3.14+, uv, Bun 1.4.x, and Node.js 24 or 26. Authenticate the
installed `lody` CLI against the target workspace, and authenticate `gh` for
read-only associated PR metadata. GitHub access is optional: unavailable PR
titles produce Unclassified sessions rather than guessed workflow stages.

From the repository root, install and build the interface:

```bash
uv sync --group dev
bun install --frozen-lockfile
bun run build
```

Start the collector in one terminal:

```bash
uv run ishiban collect --workspace leynos
```

After its workspace identity is saved, start Falcon in another terminal:

```bash
uv run ishiban serve
```

If the saved workspace identity or browser build is missing, the server reports
the required collector or build command before opening a listener.

Open <http://127.0.0.1:8765/>. The collector and API share the ignored
`.ishiban/` directory; keep both commands in the same repository root or pass
the same `--state-directory` to each. Only one collector may own that
directory. The API uses one worker and binds to loopback. Press Ctrl+C in each
terminal to stop its process. Falcon bounds shutdown of open event streams to
three seconds. A later collector run reconciles fresh snapshots with the
existing journal instead of erasing previous observations.

`uv run ishiban collect --no-github` disables GitHub lookups. Catalogue
associations remain visible, but active PRs without known titles cannot be
classified as Ready, Building, or Refine.

## Read the board

The live board opens on the `leynos` workspace. Search repository names,
session titles, and branches, filter activity, switch between panorama, matrix,
and list views, and change density. Task marks wrap five across with no
per-stage truncation. Archived and removed sessions are hidden by default; the
archive control includes them for historical inspection. The first table column
remains `12rem` wide in every density. Mark density offers Overview, Compact,
Balanced, Roomy, and Comfortable sizes; the board scrolls horizontally when its
content is wider than the available space. Compact hides the small evidence
glyph to keep activity legible; the task's accessible label and inspector
retain the evidence description. Table views scroll within their own pane,
including while the inspector is open.

Select a mark or a session in List view to open the right-hand inspector. The
inspector is hidden initially, docks beside the board, and leaves the board
interactive. On desktop, it fills the available board height and sits flush
beside the table pane, which retains a small right-hand padding. Horizontal
scrolling keeps every table column reachable while it is open. Close it with
its Close control or Escape. It exposes PR facts, workflow reasoning, agent
activity, and evidence freshness. List view offers larger selection targets.
The 120-repository **Demo data** mode is explicitly synthetic and stops the
live browser subscription while selected.

A solid oxide square with a tonal border marks a failed latest turn. The
oxide/amber candy cane marks blocked activity, corresponding to Lody's
`waiting` state. Labels retain the observed activity and workflow stage. A
brief halo indicates a newly received session update, independently of outcome.
List-view pulses stay within the updated task's button. Initial hydration,
duplicate replay, and view changes do not trigger a pulse; reduced-motion
preferences disable the animation. Empty placeholders are inert.

| PR association evidence                                   | Workflow stage |
| --------------------------------------------------------- | -------------- |
| Successful catalogue reports no associated PR             | Planning       |
| One active PR has a title starting with `Plan:`           | Ready          |
| One non-plan PR is a draft                                | Building       |
| One non-plan PR is ready for review                       | Refine         |
| All associated PRs are merged                             | Merged         |
| All associated PRs are closed without merge               | Closed         |
| Multiple active PRs, missing titles, or conflicting facts | Unclassified   |

Table 1: workflow labels. Terminal historical PRs do not override one active PR.

Agent activity and workflow are separate. A running session need not be
Building, and a completed turn does not prove task success or a merged PR.
Metadata-only sessions have unknown execution activity, even when their
catalogue freshness is synced. Collector following means the observer is
attached; it does not prove every session history or machine is live.

On disconnect, last-known observations remain visible. Evidence from an earlier
collector generation is carried forward until fresh persisted observations
arrive. Metadata refreshes cannot erase durable turn outcomes or make them look
newly verified. GitHub enrichment failures are shown as source-health warnings;
previous PR facts may be cached and stale.

## Inspect the read API

- `GET /api/v1/snapshot` returns session projections, collector health, and one
  transactionally consistent replay cursor. Each public session includes at
  most 100 active turns, an exact `activeTurnCount`, an `activeTurnsTruncated`
  flag, and an `activeTurnsRevision` for changes hidden beyond the preview. The
  inspector says how many active turns are shown when the list is truncated.
- `GET /api/v1/sessions/{session_id}` returns the current session, up to 100
  known turns, and bounded recent provenance. When `nextTurnCursor` is
  non-null, request
  `GET /api/v1/sessions/{session_id}?turnCursor=<nextTurnCursor>` for the next
  page. A `null` cursor ends the turn list. Invalid, foreign, or older version
  1 continuations return HTTP 400; restart at the first page after an upgrade.
  A missing session returns HTTP 404. Each request reads current state, so
  concurrent updates can change later pages. For opaque IDs containing path
  syntax, use `GET /api/v1/session-detail?sessionId=<encoded-id>` and append
  `&turnCursor=<nextTurnCursor>` for continuation. The existing path route
  remains available.
- `GET /api/v1/session-agent?sessionId=<encoded-id>` and
  `GET /api/v1/session-pull-requests?sessionId=<encoded-id>` return lazy
  inspector metadata. The browser uses these query routes to preserve opaque
  IDs; the existing `/sessions/{session_id}/agent` and
  `/sessions/{session_id}/pull-requests` routes remain available under
  `/api/v1` for compatible clients.
- `GET /api/v1/events?after=N` replays committed projections after cursor `N`
  and then follows new commits. Browser reconnect uses `Last-Event-ID` in
  preference to the original URL cursor.
- `POST /api/v1/sessions/activity` accepts up to eight session IDs and streams
  one result per ID. Each newline-delimited frame is at most 1,048,576 UTF-8
  bytes. A valid result too large for one frame yields a `response_too_large`
  marker for that member; later members still arrive. The interface fetches the
  marked session through
  `GET /api/v1/session-activity?sessionId=<encoded-id>&includeKnown=true` under
  its existing response bound. This query route preserves IDs containing path
  syntax. The existing
  `GET /api/v1/sessions/{session_id}/activity?includeKnown=true` route remains
  available for compatible IDs. The opt-in also returns current known activity
  without a new Lody read; the default route still resolves unknown activity
  only. An identity too large even for a marker returns HTTP 413 before any
  stream starts.
- `GET /health` checks API process liveness. `GET /ready` checks the local
  database. Neither endpoint claims the Lody source is connected.

A replacement database can invalidate a cursor. The stream then sends
`reset_required`, and the browser takes a new snapshot. Malformed or foreign
workspace observations stop the affected collector generation; they are not
silently dropped. Observer timestamps must be nonnegative epoch milliseconds
within the JavaScript date range (at most 8,640,000,000,000,000). Older stored
values outside the date range display **Timestamp unavailable** in the
inspector while the session evidence remains visible.

## Understand the proof of concept's limits

Lody provides current materialized evidence, not a replay of every historical
transition. Transitions missed while the collector was offline cannot be
recovered from an Ishiban-local cursor. The session catalogue is not a complete
repository or work-item inventory. GitHub enrichment is periodic, and the
application does not evaluate CI, review approval, issues, or dependencies.

During validation of the `leynos` workspace, the upstream Lody observer used
approximately 4.4 GiB of resident memory after hydration; the collector and API
used roughly 90 MiB each. These are single-run observations, rather than
capacity guarantees. Stop the collector when observation is no longer needed.

The local journal is append-only with no retention policy. It contains private
session titles, repository associations, PR metadata, and observation evidence;
keep `.ishiban/` private and out of Git. No authentication tokens or transcript
bodies are written to the browser or journal. Access beyond loopback needs an
explicit authentication and transport-security design before deployment.

## Quality Gates

Install Bun 1.4.x and Node.js 24 or 26 before running the combined quality
gates. CI pins Bun 1.4.3. JavaScript tooling dependencies are installed
automatically from `bun.lock` when a JavaScript gate runs. `make install-js`
can install them separately without creating the Python environment.

Before the first quality-gate run, initialize Git at the generated project root
with `git init`. Python source discovery and Markdown table formatting use Git
repository metadata.

Generated projects use `make all` as the standard local quality gate. It runs
these targets in order:

- `build`: create the local virtual environment and install development
  dependencies with `uv sync --group dev`.
- `check-fmt`: check Biome formatting for JavaScript, TypeScript, CSS, and JSON,
  Ruff formatting for Python sources and, when Rust is enabled, `cargo fmt` for
  the Rust extension.
- `lint`: run `lint-python`, Biome, type-aware Oxlint, and, when Rust is
  enabled, `lint-rust`.
- `typecheck`: run `ty check` and TypeScript with no emitted files.
- `test`: run pytest, Bun tests, and, when Rust is enabled, Rust tests.
- `spelling`: regenerate `typos.toml` and check repository-wide spelling.

Run `make markdownlint` separately to lint Markdown and run the same spelling
gate. Run `make audit` separately to check dependencies with `pip-audit`,
`bun audit`, and, when Rust is enabled, `cargo audit`.

`make fmt` applies both Python and JavaScript formatting plus Markdown table
formatting. For JavaScript-only work, use `make fmt-js`, `make check-fmt-js`,
`make lint-js`, `make typecheck-js`, and `make test-js`. The
[developers' guide](developers-guide.md#typescript-tooling) explains the rules
and checked source directories.

The Python baseline is `3.14` (minimum: 3.12).

Git discovers Python sources from tracked and untracked files, including hidden
action directories. `lint-python` runs Ruff 0.16.8 and Interrogate for 100%
docstring coverage, followed by the pinned base Pylint (`PYLINT_VERSION`). It
uses the interpreter selected for the baseline:

uv-managed CPython 3.14 (`PYLINT_PYTHON`)

The base sweep keeps `syntax-error` enabled, so a module that the interpreter
cannot parse fails linting rather than being skipped.

The DF12 Python Lints v0.4.0 Pylint plugin adds its configured project rules.
DF12 Pylint, Ambrleaks, Skylos, Vulture, and the duplication detector run as
isolated tools on Python 3.14. Ambrleaks checks `tests/`; Skylos checks the
repository, and Vulture checks test helpers. The duplication gate installs its
pinned Nose detector with the shared verified installer before checking
duplication families. `make lint-actions` validates GitHub Actions sources with
actionlint, action-validator, yamllint, and shellcheck.

Ruff and `ty` run as isolated tools on Python 3.14; `ty` is pinned to 0.0.56.
The Makefile pins mdtablefix to 0.6.1 for Markdown table formatting. CI
installs these CLI tools and runs `make markdownlint`.

The spelling target regenerates `typos.toml` from the live shared dictionary
and the `typos.local.toml` overlay on every run, so `typos.toml` is never drift
checked in continuous integration. Run `make spelling` directly when updating
documentation; commit the regenerated `typos.toml`. An ignored local cache
remains usable when the shared source is temporarily offline.

Pytest discovery is limited to the top-level `tests/` tree. Keep generated
project unit tests there rather than in package module directories or
`unittests/` subdirectories, because CI coverage runs through xdist-backed
SlipCover support.

When the Rust extension is enabled, `lint-rust` runs:

- `cargo doc` with warnings denied;
- `cargo clippy` with the generated Clippy configuration; and
- Whitaker with `whitaker --all`.

The generated Makefile never installs Whitaker; it fails with a clear error
when the wrapper is missing. Install it yourself with `whitaker-installer` (see
<https://github.com/leynos/whitaker>) before running local Rust linting.

## Dependency Auditing

Run `make audit` to check generated project dependencies for known
vulnerabilities. Ishiban also runs `bun audit` against its JavaScript lockfile.
All generated projects run `pip-audit` against the Python environment created by
`uv sync --group dev`. CI skips `make audit` for Dependabot pull requests; a
weekly scheduled audit on the default branch is the compensating control.
Rust-enabled projects also run `cargo audit` from the `rust_extension` crate
directory.

## Scheduled Mutation Testing

The `.github/workflows/mutation-testing.yml` workflow runs mutation testing
daily at 09:30 UTC and can also be started manually from GitHub Actions. Adjust
the generated cron schedule to stagger it against other repositories.

For projects whose minimum Python version is 3.13 or newer, the workflow runs
mutmut against `ishiban/`. The Python mutation job is omitted for older
baselines because the shared workflow helpers require Python 3.13 or newer.

## Rust Test Behaviour

Rust-enabled projects use `cargo nextest run` when `cargo-nextest` is
available. If `cargo-nextest` is not installed, the generated `test` target
falls back to `cargo test`. Rust documentation tests still run through
`cargo test --doc`.

If cargo is missing from the local environment, generated Rust test targets
fail early with a clear error instead of falling through to an unusable `cargo`
invocation.

## Local GitHub Actions Validation

The generated Makefile supports optional local workflow validation using
[`act`](https://github.com/nektos/act). When `act` is installed and Docker is
available, pass `WITH_ACT=1` to the `test` target:

```bash
make test WITH_ACT=1
```

This sets `RUN_ACT_VALIDATION=1` for the pytest invocation, enabling the
act-based integration tests that run the generated CI workflow locally. Omitting
`WITH_ACT` (or setting it to `0`) skips act validation; the rest of the test
suite runs unchanged.

## Cleaning Local State

Run `make clean` to remove local build and cache outputs, including `.venv`,
`.uv-cache`, `.uv-tools`, Python cache directories, coverage outputs, and Rust
`target` output when the Rust extension is enabled.

## Open the original session and inspect failures

The inspector's **Open in Lody** link opens the selected real session in its
configured workspace. A configured workspace slug supplies the web link; when
only the opaque workspace ID is available, the canonical `lody://` session link
opens the Lody app. Synthetic demo sessions have no external session link.

Failed latest turns include a **Last turn error** section. Supplied error text
is displayed as plain text, with long messages bounded and scrollable. If Lody
omits the diagnostic, the inspector states: “Lody did not provide error details
for this turn.” The installed CLI currently emits failed outcomes without the
underlying provider error message; its visible-history command also omits that
message. Ishiban does not infer errors from assistant prose or collector health.

## Saved interface state and unknown activity

A signed cookie saves density and presentation. New windows in the same browser
profile restore the last saved choices; the footer explains the cookie's use
and reports save failures. Search, selection and filters remain local to each
window. Clearing the cookie returns the controls to Overview and Panorama.

Real session marks with unknown activity are read lazily as they become
visible. The frame updates without a pulse when the read succeeds. Evidence
read this way is labelled “Read on demand; not journalled”. Existing event IDs
are preserved, and newer journal events take precedence over late lookup
responses. Unavailable or metadata-only reads remain unknown unless an earlier
successful observation is cached.

Collected activity, failed outcomes and supplied error details survive page
refreshes and API or collector restarts. They are stored in a local SQLite
sidecar, shared by windows viewing the same workspace. Newer execution evidence
replaces them; metadata or unknown startup snapshots retain them. The displayed
observation time describes when the runtime facts were read. To clear these
last-known observations, stop the API and collector, remove the sidecar, then
restart both processes and refresh the browser. Previously lost browser-only
results need to be collected again.

The inspector prefers a known PR name as its linked heading, with the session
title underneath. Missing PR names, including already merged PRs, are loaded on
demand. PR links also show a muted `#123`-style number. Inspector links are
underlined on hover.

The board groups sessions by `parentSessionId`, showing one entry for each
family root. The root supplies the PR, branch, title, and workflow context; the
selected tab supplies its own title, activity, error, agent details, and copied
CLI ID. The inspector keeps the root session route and adds
`?tab=session:<selected-session-id>` when a child tab is selected. Search
matches member session IDs and titles. Board counts and PR-workflow filters
count families. See [ADR 007](adr-007-session-tab-families.md) for recency and
selection details.

The board reads tab history only for visible families. When too many tabs are
visible to read as complete families within the local lookup budget, the
inspector says its selected tab is provisional. Scrolling another family out of
view releases capacity for the remaining visible work. A failed or malformed
history response pauses new requests briefly while valid sibling results stay
available.

An expired history result makes the selected tab provisional again until a
fresh read succeeds. A failed refresh can keep an older timestamp as fallback
evidence, but it does not override a running tab while selection is
provisional. Source tabs whose IDs exceed the lookup API's limit or contain a
NUL remain visible with their original inspector identity. Their recency or
unknown activity cannot be looked up; other tabs in the family continue
updating.

The inspector keeps your selection as the board discovers related tabs.

Archiving the root hides the logical task, including any child tabs Lody leaves
unarchived. **Include archived and removed** reveals those families. A removed
root catalogue record does not hide a child that is still present.

After updating Ishiban to a build with family support, restart both the API and
collector so the new routes and parent metadata are loaded. Existing stored
session data remains compatible; the added parent and creation-time fields are
optional and nullable.

**Copy session ID** copies the Lody ID accepted by commands such as
`lody session show <id>`. It does not copy the provider's ACP conversation ID.
Agent type and configuration display name are collected when the inspector
opens and cached for five minutes. Configuration secrets are never requested.
Unavailable metadata is labelled explicitly; demo IDs are not offered for CLI
copying. If a session identifier is `.` or `..` in the Lody link path, the
inspector shows an unavailable-link notice instead of opening a different
destination. Its copyable ID remains available. A selected tab carried in the
web link's query keeps its exact ID. Resolved on-demand activity survives
metadata-only collector refreshes and reconnect snapshots; newer execution
evidence still replaces it.

Visible unknown sessions are requested automatically in small batches. Each
result appears as soon as it is available, so a slow session does not hold up
its neighbours. Up to four Lody reads run concurrently across browser windows;
cached results can appear immediately. The installed Lody CLI still requires an
individual observation per uncached session, so a cold workspace can take time
to resolve.

If an activity response exceeds its transfer limit, the inspector shows a quiet
activity notice and retains known session facts and the Lody link. The notice
survives metadata-only refresh, clears on successful recovery or newer
execution, and does not pulse the task. It is not a session error.

Restarting the collector establishes a fresh pulse baseline. Replayed metadata,
unchanged runtime facts and on-demand enrichment do not pulse. Meaningful task
changes received after startup continue to pulse.
