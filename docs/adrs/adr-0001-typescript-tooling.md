# Architectural decision record (ADR) 001: TypeScript tooling

## Status

Accepted on 9 November 2026.

## Context

Ishiban's observation design calls for a TypeScript frontend alongside the
Python collector and API. The repository needs the same linting, formatting,
and typechecking policy as Simulacat Core before frontend implementation. Bun
1.4.x is required for JavaScript bundling and testing.

## Decision

Import the configuration and local df12 Oxlint plugin from Simulacat Core
revision `c2e5ddcb8092c327003f92916fe8e4a7befd5037`, retaining its MIT licence.
Preserve its rule settings, including explicitly enabled `unicorn` and
`ai-deslop` rules and the existing `unicorn/no-null` exception. Pin the
imported tool versions exactly and commit Bun's resolved dependency graph.

| Component       | Version  | Responsibility                                     |
| --------------- | -------- | -------------------------------------------------- |
| Bun             | 1.4.3    | Installation, test runner, and bundling.           |
| Biome           | 2.5.3    | Formatting and native maintainability rules.       |
| Oxlint          | 1.82.0   | Syntax-aware rules and plugin host.                |
| oxlint-tsgolint | 7.0.2004 | Type-aware Oxlint rules.                           |
| ai-deslop       | 0.4.8    | Evidence and type assertion rules.                 |
| TypeScript      | 6.0.3    | Strict static typechecking without emitting files. |

Table 1: pinned primary tooling components.

Use Bun types matching Bun 1.4.3, Node.js types 26.1.1, fast-check 4.9.0, and
Zod 4.6.6 for the imported tooling and tests. Upgrade the source's Zod 3 pin
because
[GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5)
affects versions below 4.6.6. The imported AST checks use only
`z.string().safeParse`, and the full plugin suite validates this dependency
change. CI provisions Node.js 24.11.1 for Oxlint's JavaScript plugin host.
Future tool upgrades must update the pins and lockfile together and rerun the
gates.

Connect both language toolchains to `make fmt`, `make check-fmt`, `make lint`,
`make typecheck`, and `make test`. Install JavaScript dependencies with a
frozen lockfile through a shared Make prerequisite. Preserve the Python build
target; add a Bun application bundle target once an application entrypoint
exists. Include `bun audit` in the existing `make audit` gate.

Adapt only repository-specific concerns: remove Simulacat's GraphQL generation
prerequisite and generated-file exclusions, add Ishiban's Python cache
exclusions, and exclude the supplied reference HTML from JavaScript tooling.
Support future React TSX through the compiler's JSX setting. Keep frontend
TypeScript and tests in `src/` and `tests/`.

Split the imported plugin and tests by responsibility to meet Ishiban's
400-line file limit. Preserve their behaviour with the imported examples,
property tests, and diagnostic snapshot. The internal helper modules are for
the plugin and its fixtures only. Import no legacy documentation debt baseline.

## Alternatives considered

- Biome alone would omit the df12 predicate, JSDoc, and type-aware rules.
- Copying Simulacat's entire package would import unrelated application and
  GraphQL dependencies.
- Keeping separate manual commands would leave the established Make and CI
  gates unable to enforce the TypeScript policy.

## Consequences

Contributors need Bun 1.4.x and Node.js 24 or 26 in addition to Python tooling.
The lint, typechecking, and Bun test gates pass with Node.js 24.22.2 and
26.13.0. The Oxlint JavaScript plugin interface requires deliberate
compatibility checks during upgrades. Supplied reference material remains
illustrative; application code must use the checked source tree.

The imported Biome rule exceptions remain part of the source policy rather than
an assertion that every rule suits future Ishiban UI code. Revisit those
exceptions explicitly when the live frontend is implemented.

### Duplication review

The repository-wide Nose gate also inspects imported JavaScript and HTML. Keep
its thresholds unchanged and record considered exceptions in `pyproject.toml`
for these existing patterns:

- The public and private JSDoc visitors intentionally mirror the same AST
  traversal while applying different visibility rules. Missing-tag predicates
  and diagnostics remain separate to preserve the imported contracts.
- The four statement visitors in `complex-conditional.js` explicitly name
  their ESTree hooks and delegate to one checker. The reported subgraph pairs
  split option handling from reporting and node counting from recursion.
- The synthetic AST predicate in the property tests remains independent of
  the implementation it checks; sharing it would weaken the oracle.
- `jsdoc-helpers.js` retains separate Promise object/property predicates and
  short early-return guards, rather than introducing a general AST framework.
- The supplied HTML keeps its original `.stat b` style and panorama override.

Use named members wherever Nose provides them. Its anonymous fragments require
an exact file key for the two small JSDoc modules and reference HTML. These
exceptions preserve imported behaviour; they must be reviewed again when those
modules change and must not become general exclusions for application code.
