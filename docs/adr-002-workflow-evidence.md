# Architectural decision record (ADR) 002: workflow evidence

## Status

Accepted on 9 November 2026 as part of the user-authorized proof of concept.

## Context

The HTML reference groups work into five stages, while Lody's observer protocol
reports agent execution activity. The user supplied an explicit PR convention
for deriving a session's workflow stage. The authenticated `leynos` catalogue
supplies repository names, branches, PR URLs, and PR lifecycle statuses, but
not PR titles. Execution state is insufficient to classify work.

## Decision

Use the catalogue's stable session identity and explicit PR association. Query
only the associated GitHub PRs, through read-only GitHub CLI GraphQL requests,
to obtain title, draft status, and lifecycle state. Batch no more than forty PR
selections per request, bound process duration and output size, and refresh
catalogue associations approximately every five minutes. The UI never performs
workflow classification itself.

| Evidence                                                      | Stage        |
| ------------------------------------------------------------- | ------------ |
| Successful catalogue record with no PR association            | Planning     |
| One active PR whose title starts with `Plan:`                 | Ready        |
| One non-plan draft PR                                         | Building     |
| One non-plan PR ready for review                              | Refine       |
| All associated PRs merged                                     | Merged       |
| All associated PRs closed without merge                       | Closed       |
| Multiple active PRs, unavailable titles, or conflicting facts | Unclassified |

Table 1: workflow classification from explicit PR evidence.

Ignore historical terminal PRs when exactly one associated PR is active.
Terminal lifecycle evidence takes precedence over a Plan-prefixed title. Treat
Lody's absent optional `pullRequests` field as no association only inside a
successful, validated complete catalogue response. A failed or partial
catalogue never deletes associations or classifies omitted sessions.

Maintain workflow stage independently of activity, collector connectivity, and
durable evidence freshness. Running does not mean Building; waiting for
permission does not mean a dependency is blocked; completed does not mean
Merged. Preserve raw validated observer records and immutable post-event
projections in the SQLite journal.

Cached GitHub facts can survive a lookup failure, but the collector reports
that enrichment is unavailable and the facts may be stale. With no known title,
an active PR remains Unclassified. Closed/merged catalogue facts do not require
a title lookup. This is a product convention for session-associated PRs, not a
claim that sessions are a complete work-item inventory.

## Alternatives considered

- Classifying by session title would confuse conversation names with PR titles.
- Classifying by activity would fabricate workflow state from execution state.
- Leaving all live sessions unclassified would omit the user-supplied evidence.
- A general GitHub event service would exceed the proof of concept's scope.

## Consequences

The collector needs the authenticated Lody CLI and, for active PR titles, the
authenticated GitHub CLI. Both are used read-only. No authentication token is
stored in the browser or journal. The local state directory stores only
workspace identity, database records, and a collector lock, and is ignored by
Git. The API remains bound to loopback with one worker and serves Bun-built
assets from the same origin.

Future work may replace polling with an independent GitHub feed, retain richer
metadata provenance, or associate multiple work items with a session. None of
those extensions changes the distinction between observed activity and workflow
evidence.

## PR refresh failure policy

A current catalogue status of merged or closed takes precedence over cached
open/draft metadata. A known cached title can still describe that terminal PR.
GitHub enrichment preserves successful fields and batches when other lookups
fail; a nonzero CLI exit can contain valid partial GraphQL data. Partial
results keep an explicit source-health warning, and inaccessible associations
remain unknown or visibly cached rather than acquiring invented facts.
