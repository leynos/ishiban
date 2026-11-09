# Ishiban

*A read-only observatory for coding-agent sessions across a Lody workspace.*

Ishiban is an early experiment from df12 Productions. The repository currently
contains a Python scaffold, an interactive reference interface, and a draft
design for observing one Lody Cloud workspace. The live collector, API, and
application are planned; the reference interface uses synthetic data.

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

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then
clone the repository and install its development dependencies. The package
requires Python 3.14 or newer; uv can provision the interpreter.

```bash
git clone https://github.com/leynos/ishiban.git
cd ishiban
uv sync --group dev
```

### Preview the reference interface

From the repository root, serve the standalone mockup:

```bash
uv run python -m http.server 8000 --bind 127.0.0.1 --directory reference
```

Open <http://127.0.0.1:8000/ishiban-mockup.html> in a browser. Search for a
repository, change the density, or select a task mark to inspect it. All data
is illustrative and interactions stay in the page. Press Ctrl+C to stop the
server.

### Check the Python scaffold

The package currently exposes a greeting as an installation check:

```bash
uv run python -c 'import ishiban; print(ishiban.hello())'
```

Expected output: `hello from Python`.

______________________________________________________________________

## Features

The reference interface includes:

- A 120-repository panorama with five workflow stages and wrapping task marks.
- Matrix and list views, search, filters, and adjustable density.
- A task inspector with larger selection targets.

The proposed live spike adds a durable SQLite event journal, a Falcon read API,
and a React interface with resumable Server-Sent Events (SSE). Live sessions
will remain unclassified until an explicit workflow association is available;
agent activity alone does not establish a workflow stage or task success.

______________________________________________________________________

## Learn more

- [Documentation contents](docs/contents.md) — the full documentation index.
- [Users' guide](docs/users-guide.md) — scaffold commands and quality gates.
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

______________________________________________________________________

## Contributing

Contributions welcome! Start with the
[design](docs/ishiban-lody-observation-spike-design.md) and
[developers' guide](docs/developers-guide.md), and follow the conventions in
[AGENTS.md](AGENTS.md). Run `make all` for the standard local quality gates and
`make markdownlint` for documentation linting and spelling.
