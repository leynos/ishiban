# Observation spike report

This report records bounded measurements of the Ishiban observation proof of
concept. The measured runtime candidate was
`10114716f303e9add6aeb9fc3ca10c33cdf88732` on 11 November 2026. The
measurements do not establish a service-level objective, long-term leak rate,
or upstream Lody latency.

Later refactors inject the PR-title clock and lookup dependencies and the
activity observation's epoch clock. Compatibility tests cover their unchanged
defaults; these measurements have not been repeated on those refactors and
remain scoped to the runtime above.

## Method and scope

Runs used `ibara` on WSL2 kernel `6.6.87.2-microsoft-standard-WSL2`, with
Python 3.14.2, SQLite 3.50.4, uv 0.13.7, Bun 1.4.3, Lody CLI 0.110.1, and
agent-browser 0.33.2. Live collection observed the `leynos` workspace using
read-only Lody commands. Synthetic runs used a private Lody shim and an
isolated database. No user process was signalled, no Lody session was mutated,
and no transcript was read.

The recorded run windows are UTC filesystem creation-to-result-write bounds,
rounded to whole seconds; they are not exact instrument timestamps.

| Run            | Bounded UTC window | Workload                                    |
| -------------- | ------------------ | ------------------------------------------- |
| Corrected live | 03:21:14–03:22:51  | 90-second observation and resource sampling |
| Synthetic      | 03:23:28–03:24:15  | 1,000 journal writes and 1/4/8 SSE readers  |
| Browser-only   | 03:26:00–03:26:05  | Three local commit-to-render samples        |

*Table 1. Valid measurement windows and workloads.*

An earlier live sample has valid health and snapshot counts but invalid
resource and child-discovery data: its sampler inspected only the process-group
leader's child list and missed children created by other threads. Its resource
figures are excluded below. The first browser timing attempt also yielded no
samples because the harness counted inert placeholder spans. Its selector was
corrected to target real session buttons; only the browser timing was repeated.
The invalid first resource sample is retained separately at
`/tmp/ishiban-spike-pr9-BkZEwf/live-result.json`.

## Live observation and resources

Across 90 one-second health checks, the collector was `connecting` 52 times and
`following` 38 times. All 90 local API readiness checks returned HTTP 200; no
sampled health observation contained a source error. This does not rule out
errors between samples. The final snapshot contained 2,788 sessions, 2,725 with
unknown activity, 3 without a repository, and 727 without a branch. There were
1,272 sessions with at least one associated pull request lacking an enriched
title; this is a post-GitHub-enrichment count, not evidence about which titles
Lody supplied. The durable cursor was 5,647, and journal, WAL, and sidecar
files occupied 16,912,280 bytes at the final sample.

| Owned role                     | Observed CPU core-seconds | RSS start / sampled peak / end KiB | FDs start / peak / end |
| ------------------------------ | ------------------------: | ---------------------------------: | ---------------------: |
| Collector tree, including Lody | 96.84                     | 152,896 / 2,189,636 / 2,123,276    | 35 / 62 / 58           |
| Lody child subset              | 56.15                     | sampled peak 2,076,932             | sampled peak 34        |
| API                            | 0.47                      | 104,640 / 104,640 / 104,640        | 25 / 25 / 25           |

*Table 2. Live process-tree resource observations over the corrected run.*

CPU is a sampled lower bound: one-second sampling can miss short-lived
children. Summed RSS counts shared pages more than once and is not unique
physical memory; sampled peaks are not exact process-tree high-water marks. The
window includes startup and metadata reconciliation, and only 38 sampled
seconds were `following`. It cannot establish a long-term leak rate. API
readiness demonstrates local API/database availability, not Lody connectivity.
Unknown activity and missing metadata are incomplete observations, not proof
that source state is failed or that private fields were absent.

## SQLite writes and event fan-out

The synthetic run committed 1,000 serial `Store.ingest` events in 7.598
seconds, or 131.62 events per second. Commit-call median was 7.56 ms, reported
p95 was 8.75 ms, and maximum was 11.42 ms. The reported p95 selects zero-based
sorted sample index `floor(0.95 × n)`; it is descriptive, with no threshold
implied. Database, WAL, and sidecar size changed from 263,312 to 7,057,232
bytes after the fan-out phases as well. This is combined growth through 1,000
writes and 300 fan-out events, not the size attributable to the 1,000 writes
alone.

| SSE readers | Events received per reader | Commit-to-HTTP arrival median / p95 / maximum ms | API CPU core-seconds | Sampled FD peak |
| ----------: | -------------------------- | -----------------------------------------------: | -------------------: | --------------: |
| 1           | 100/100                    | 133.38 / 249.73 / 253.70                         | 0.09                 | 26              |
| 4           | 100/100 each               | 127.58 / 244.02 / 259.06                         | 0.34                 | 35              |
| 8           | 100/100 each               | 129.84 / 249.04 / 266.77                         | 0.89                 | 44              |

*Table 3. Synthetic HTTP event fan-out measurements.*

All 1,300 expected HTTP receipts matched committed cursors, with no phase
errors. A sequence-gap protocol event was rejected without advancing protocol
position or the journal cursor. A paused reader later received 16 committed
events; after disconnect, a new connection received exactly one next event
after its cursor. This finite case does not demonstrate behaviour under an
arbitrarily slow consumer or establish socket backpressure limits.

## Browser timing and cleanup

On the same synthetic database, a browser filtered to one visible task produced
three commit-return-to-two-animation-frame samples: 148.09, 175.24, and 188.51
ms. Their respective estimated clock uncertainties were ±30.27, ±29.11, and
±28.59 ms. These local SQLite-to-DOM timings exclude upstream Lody and GitHub
latency.

Seven owned process groups or sessions were checked after cleanup. One Lody
child remained at the immediate post-stop check, then disappeared; a later
identity check confirmed it was gone. The final read-only process scan found
zero owned group or session survivors. No unknown process was signalled.

## Evidence and interpretation

Private run artefacts are retained under `/tmp/ishiban-spike-pr9-retry-KBzwJG/`:
`live-result.json`, `synthetic-result.json`, `browser-only-result.json`, and
`cleanup-after-grace.json`. These local artefacts are evidence for this report,
not a reusable benchmark harness. The measurements describe one bounded
workload on one host. They do not establish production capacity, upstream
observation latency, or an absence of intermittent source errors.

The known source-contract gaps remain that Lody's catalogue exposes pull
request URLs and status but omits pull request titles, and observed turn errors
may lack provider detail. The missing-title snapshot count above is measured
after GitHub enrichment and does not quantify title availability from Lody.
