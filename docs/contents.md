# Documentation contents

[Documentation contents](contents.md) indexes Ishiban's guides, design, and
reference material.

## Design and reference

- [TypeScript tooling decision](adr-001-typescript-tooling.md) records the
  imported linting, formatting, compiler policy, and Bun runtime pins.
- [Lody observation spike design](ishiban-lody-observation-spike-design.md)
  defines the proposed read-only workspace observer, persistence model, live
  interface, verification plan, and implementation sequence.
- [Reference interface](../reference/ishiban-mockup.html) provides an
  interactive panorama of 120 repositories using synthetic data, with density
  controls, filters, and a task inspector.

## Project guides

- [User guide](users-guide.md) explains how to use the generated project and
  its public build and test commands.
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
