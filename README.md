# Ishiban

*A read-only observatory for coding-agent sessions across a Lody workspace.*

Ishiban is an early experiment from df12 Productions. The repository currently
contains a live observer, a durable SQLite journal, a Falcon read API, and a
React board for one Lody Cloud workspace. A separate labelled demo preserves
the reference interface's 120-repository stress view.

______________________________________________________________________

## Why Ishiban?

Following agents across a fleet of repositories should not require opening
every session. Ishiban's design brings session activity into one compact view,
with enough evidence to tell what is known and how recently it was observed.

- Scan many repositories with a dense panorama and inspect individual tasks.
- Keep session activity, evidence freshness, and collector health distinct.
- Observe Lody without dispatching tasks or changing agent sessions.

______________________________________________________________________

## Quick start

### Installation

Install uv, Python 3.14+, Bun 1.4.x, and Node.js 24 or 26. Authenticate the
`lody` CLI for the target workspace and `gh` for associated PR metadata.

```bash
git clone https://github.com/leynos/ishiban.git
cd ishiban
uv sync --group dev
bun install --frozen-lockfile
bun run build
```

### Observe a workspace

In one terminal:

```bash
uv run ishiban collect --workspace leynos
```

In another terminal, from the same repository root:

```bash
uv run ishiban serve
```

Open <http://127.0.0.1:8765/>. Search repositories, select a task mark to
inspect its evidence, or switch to **Demo data**. The collector and API share
the ignored `.ishiban/` directory; press Ctrl+C in each terminal to stop them.

See the [users' guide](docs/users-guide.md) for configuration, source-health
semantics, and the proof of concept's limits.

______________________________________________________________________

## Features

- A dense repository panorama, five-wide wrapping marks, five mark sizes, and
  a docked task inspector with search, filters, and keyboard access.
- Oxide failure marks, striped waiting marks, and brief update pulses with
  reduced-motion support.
- Explicit Planning, Ready, Building, Refine, and Merged stages from PR facts,
  with separate Closed and Unclassified groups.
- Independent agent activity, evidence freshness, and collector health.
- An append-only SQLAlchemy/SQLite journal and cursor-resumable server-sent
  events, with typed Effect v4 decoding and scoped browser connections.
- Semantic Tailwind v4 and daisyUI v5 styling, built and tested with Bun 1.4.x.

The observer cannot recover transitions missed while it was offline or prove
that a completed turn produced a successful task. PR metadata is polled and may
be stale; unavailable titles remain unclassified. See the
[workflow evidence decision](docs/adr-002-workflow-evidence.md).

______________________________________________________________________

## Learn more

- [Documentation contents](docs/contents.md) — the full documentation index.
- [Users' guide](docs/users-guide.md) — running the board and interpreting
  evidence.
- [Developers' guide](docs/developers-guide.md) — contributor workflow and
  automation conventions.
- [Observation spike design](docs/ishiban-lody-observation-spike-design.md) —
  proposed architecture, scope, and acceptance criteria.
- [Implementation sequence](docs/ishiban-lody-observation-spike-design.md#10-suggested-implementation-sequence)
  — planned increments towards a working live observer.
- [Reference interface](reference/ishiban-mockup.html) — the supplied visual
  prototype; use the local preview above to interact with it.

______________________________________________________________________

## Licence

ISC — see [LICENSE](LICENSE) for details.

The imported df12 Oxlint plugin retains its
[MIT licence](tools/oxlint-plugin-df12/LICENSE).

______________________________________________________________________

## Contributing

Contributions welcome! Start with the
[design](docs/ishiban-lody-observation-spike-design.md) and
[developers' guide](docs/developers-guide.md), and follow the conventions in
[AGENTS.md](AGENTS.md). Run `make all` for the standard local quality gates and
`make markdownlint` for documentation linting and spelling.

The combined gates require Bun 1.4.x and Node.js 24 or 26 alongside Python; see
the [TypeScript tooling guide](docs/developers-guide.md#typescript-tooling).
