# Persist on-demand runtime observations separately from the journal

- Status: Accepted
- Date: 10 November 2026
- Supersedes: the browser-only activity lifetime in
  [ADR 003](adr-003-interface-state-and-lazy-activity.md).

## Context

Collected failures disappeared after page refreshes because on-demand results
existed only in browser memory. Collector startup could also replace them with
persisted-source unknown projections. These results are useful last-known
runtime evidence and must survive browser, API and collector restarts.

## Decision

Store successful on-demand runtime observations in a separate SQLite sidecar
next to the journal. The filename appends `.activity.sqlite3` to the journal
filename. The API writes this cache; the collector remains the sole journal
writer. The disposable cache owns its table initialization independently of
journal migrations. Its key is workspace and session, and its bounded contents
include only state, latest/active turns, source freshness and observation time.
The existing turn projection bounds error text before caching.

Snapshots, session detail and SSE views restore cached runtime fields onto
current metadata. Raw journal readers and stored replay records remain
unchanged. Restore preserves titles, repository and PR metadata, event cursors,
session revisions and collector evidence generations. The existing lazy-source
label identifies these observations. Restoring a snapshot creates no pulse.

Retain cached last-known outcomes without a time-based expiry. Subprocess
request caching keeps its existing TTL; expiry of that optimization must not
erase evidence. Limit the sidecar to 10,000 sessions per workspace, evicting
the oldest entries when full. A missing or removed session is not restored.

New known execution evidence wins. The collector records `lastActivityEventId`
on known persisted observations and turn transitions. Metadata and unknown
observations preserve that watermark. A cache entry records its base journal
revision and cannot override a later execution watermark, including when the
browser missed the known update before another unknown projection. Late lookups
are checked against the current revision; cache upserts cannot replace entries
based on newer revisions.

## Consequences

Refreshes and process restarts retain collected failures and supplied errors.
The saved state is shared by browsers viewing the same local workspace.
Preference cookies still contain only interface controls. Removing the sidecar
discards cached observations and allows unknown sessions to be read again.
Previously lost browser-only observations require another read to recover.
Cached observations establish last-known outcomes, not machine liveness.
