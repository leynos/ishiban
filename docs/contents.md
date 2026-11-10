# Documentation contents

[Documentation contents](contents.md) indexes Ishiban's guides, design, and
reference material.

## Design and reference

- [Batched activity and update cues](adr-005-batched-activity-and-update-cues.md)
  bounds concurrent lazy reads and suppresses unchanged startup pulses.

- [Persistent on-demand activity decision](adr-004-persist-on-demand-activity.md)
  preserves collected runtime outcomes across browser and process restarts.
- [Interface state and lazy activity decision](adr-003-interface-state-and-lazy-activity.md)
  separates signed MessagePack preferences and ephemeral activity reads from
  the durable observation journal.

- [Observation proof-of-concept plan](execplans/initial-spike.md) records the
  implementation milestones, validation evidence, and remaining limits.
- [Workflow evidence decision](adr-002-workflow-evidence.md) defines the
  PR-based stages and independent activity/freshness semantics.

- [TypeScript tooling decision](adr-001-typescript-tooling.md) records the
  imported linting, formatting, compiler policy, and Bun runtime pins.
- [Lody observation spike design](ishiban-lody-observation-spike-design.md)
  defines the proposed read-only workspace observer, persistence model, live
  interface, verification plan, and implementation sequence.
- [Reference interface](../reference/ishiban-mockup.html) provides an
  interactive panorama of 120 repositories using synthetic data, with density
  controls, filters, and a task inspector.

## Project guides

- [Repository layout](repository-layout.md) locates runtime, frontend, schema,
  test, and local state files.

- [User guide](users-guide.md) explains read-only Lody observation, board
  controls, session evidence, and proof-of-concept limitations.
- [Developer guide](developers-guide.md) explains the contributor workflow and
  points maintainers to script automation standards.
- [Documentation style guide](documentation-style-guide.md) defines the
  spelling, structure, Markdown, Architecture Decision Record (ADR), Request
  for Comments (RFC), and roadmap conventions used by this documentation set.

## Engineering practice

- [Complexity antipatterns and refactoring strategies](complexity-antipatterns-and-refactoring-strategies.md)
  explains cognitive complexity, the bumpy-road antipattern, and refactoring
  approaches for maintainable code.
- [Local validation of GitHub Actions with act and pytest](local-validation-of-github-actions-with-act-and-pytest.md)
  explains how to validate workflow behaviour locally before relying on remote
  Continuous Integration (CI) runs.
- [Scripting standards](scripting-standards.md) explains the preferred Python
  scripting stack, command execution patterns, and test expectations for helper
  scripts.

## Frontend architecture and testing

These shared reference guides inform implementation. Ishiban's design and
decision records define the project's selected scope and tooling.

- [v2a front-end stack](v2a-front-end-stack.md) describes the shared mockup and
  full application tiers, their dependencies, and integration boundaries.
- [React and Tailwind with Bun](react-tailwind-with-bun.md) walks through
  building, serving, and bundling a React interface with Bun.
- [Effect 4.0 in TypeScript](effect-4-0-in-typescript.md) explains typed effects
  and their use in TypeScript applications.
- [Data model-driven card architecture](data-model-driven-card-architecture.md)
  explains entity-backed rendering, localization, and measurement boundaries.
- [Pure, accessible, and localizable React components](pure-accessible-and-localizable-react-components.md)
  covers component boundaries, accessibility, and localization with Radix,
  TanStack, and daisyUI.
- [Accessibility-first component testing](high-velocity-accessibility-first-component-testing.md)
  describes a layered testing strategy for fast feedback and accessible
  components.

## Frontend styling

- [Tailwind v4 guide](tailwind-v4-guide.md) explains Tailwind CSS v4 conventions
  and implementation patterns.
- [daisyUI v5 guide](daisyui-v5-guide.md) provides component classes, themes,
  and usage guidance for daisyUI 5 with Tailwind CSS 4.
- [Semantic Tailwind with daisyUI](semantic-tailwind-with-daisyui-best-practice.md)
  describes semantic markup and styling with Tailwind, daisyUI, and Radix.
- [Enforcing semantic Tailwind](enforcing-semantic-tailwind-best-practice.md)
  explains automated rules for semantic, accessible markup and token-based
  styling.
