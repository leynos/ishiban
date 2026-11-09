# Repository layout

This page locates the proof of concept's runtime components and verification.

- `ishiban/domain.py` defines typed observer and catalogue records.
- `ishiban/protocol.py` validates the read-only CLI boundary.
- `ishiban/workflow.py` classifies explicit PR facts.
- `ishiban/lody.py` owns bounded Lody and GitHub subprocess lifetimes.
- `ishiban/catalogue_framing.py` locates complete catalogue objects
  incrementally, leaving validation to the protocol decoder.
- `ishiban/collector.py` supervises observation and catalogue reconciliation.
- `ishiban/storage/` contains SQLAlchemy models, transactional journal writing,
  snapshot reads, and projection reconciliation.
- `ishiban/api.py` exposes Falcon snapshots, session detail, health, and SSE.
- `ishiban/cli.py` supplies the `ishiban collect` and `ishiban serve` commands.
- `migrations/` and `alembic.ini` define the local database schema history.
- `src/contracts.ts` and `src/client.ts` validate and apply browser projections.
- `src/ui/` renders the board and accessible inspector; `src/styles.css` owns
  semantic Tailwind and daisyUI styling.
- `src/ui/session-updates.ts` owns transient board update cues.
- `src/demo.ts` supplies isolated synthetic presentation data.
- `tests/` contains pytest, pytest-bdd, Hypothesis, and Bun verification.
- `reference/ishiban-mockup.html` is the original visual reference.
- `docs/execplans/initial-spike.md` records delivery and acceptance evidence.
- `.ishiban/` is ignored private local state, including the SQLite journal.
- `dist/` is ignored output built by Bun and Tailwind for Falcon to serve.

Run commands and operational limits are documented in the
[Users' guide](users-guide.md). Internal conventions are in the
[Developers' guide](developers-guide.md).
