# Separate interface preferences and lazy activity from the journal

- Status: Accepted
- Date: 10 November 2026

## Context

Density and presentation should survive opening another browser window.
Metadata-only sessions may have unknown activity until their persisted state is
read. Neither preference changes nor these additional reads are new durable
observer events. The collector remains the sole SQLite journal writer.

## Decision

Store density and presentation in one browser cookie, signed and timestamped
with itsdangerous. Its payload is a MessagePack dictionary encoded with
msgspec, not JSON. The API validates the two enum values, restores defaults for
invalid or expired cookies, and exposes the decoded preferences in snapshots.
Preference changes use a bounded JSON request to issue the signed binary-state
cookie. The cookie is HttpOnly, uses SameSite=Lax, and lasts one year. The
local state directory retains a private signing key across server restarts.

The browser restores preferences before the board's initial controls render and
serializes subsequent full-state writes. The footer explains the cookie.
Search, selection, activity filters, and session data are not stored in it.

Unknown activity is read only when a real session mark enters the viewport. The
browser and API each limit concurrent reads to two. The API caches bounded
results and owns its read-only CLI subprocesses. The response contains the
original projection revision, workspace identity, and an explicit lazy-source
label. It does not append journal rows or invent an evidence generation.

The browser applies lazy results only while the same session revision remains
unknown in the same workspace. It preserves the journal cursor and mark
revision, suppresses any pulse for the lazily enriched mark, and labels the
information as read on demand rather than journalled. Subsequent durable events
replace this browser-local enrichment normally.

## Consequences

Different browser profiles keep separate preferences. Existing windows retain
their current controls; new windows restore the last saved values. Clearing
cookies or replacing the signing key restores defaults.

Unknown, unavailable, metadata-only, malformed, or timed-out source reads do
not become invented activity. Bounded caches and short failure caching avoid
repeated process launches. Lazy evidence is not persisted across page reloads
and does not imply machine liveness. Failed turns may still lack a provider
diagnostic because the installed Lody observer omits it.
