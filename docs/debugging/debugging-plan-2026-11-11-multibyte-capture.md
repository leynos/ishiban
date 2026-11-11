# Debugging plan: intermittent multibyte FIFO capture corruption

- **Generated**: 11 November 2026
- **Issue ID**: PR #9, plateau A validation
- **Severity**: blocking test-infrastructure failure
- **Falsification sub-agent**: `alchemist`, one hypothesis per agent

**Planning agent boundary**: The parent prepared this plan. Separate alchemist
agents execute falsification; the planning agent does not run these probes.

## Problem statement

The full parallel Python suite returned malformed JSON from the Bun multibyte
request capture. The same contract passed earlier focused runs. Captured bytes
must preserve the exact writer payload, regardless of UTF-8 encoding or FIFO
backpressure. This blocks validation; no production Lody failure is established.

## Context summary

| Aspect              | Details                                                             |
| ------------------- | ------------------------------------------------------------------- |
| First observed      | Validation after committed `8eea770`, with uncommitted FIFO fixture |
| Reproduction rate   | One failure in 297 Python cases; focused runs passed                |
| Affected components | Bun 1.4.3, `_CapturePipe`, multibyte request capture                |
| Recent changes      | Regular capture files replaced by a bounded private FIFO            |

### Error artefacts

```plaintext
JSONDecodeError: Expecting ',' delimiter: line 1 column 2114 (char 2113)
test_multibyte_browser_batches_pass_real_asgi_decoder
cmd_mox.ipc.server: IPC received malformed JSON
```

The full private log is `/tmp/test-ishiban-initial-spike-plateau-a-10.out`. The
parse failed immediately after capture, before the test's Lody requests. The
CmdMox message is correlated output, not an established cause.

### Information gaps

The failing FIFO was removed correctly, so its complete bytes are unavailable.
The child write count, return value and pipe capacity were not recorded.

## Hypotheses

### H1: Bun string writes lose UTF-8 bytes under FIFO backpressure

**Claim**: A single `Bun.write(path, string)` can produce a shorter or altered
UTF-8 payload when a non-seekable pipe requires partial writes.

**Plausibility**: High. The failing payload contains astral characters near a
small pipe boundary; ASCII and focused captures passed.

**Prediction**: Known UTF-8 strings fail byte equality at a pipe boundary while
an equivalent explicitly encoded byte buffer survives the same conditions.

| Step | Action                                                                                                                                              | Expected Negative Result                                                |
| ---- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| 1    | Write deterministic multibyte JSON around 4, 8 and 16 KiB using both Bun string and byte-buffer writes; compare lengths, hashes and first mismatch. | Both forms preserve all bytes under forced small-pipe backpressure.     |
| 2    | Repeat the captured eight-ID request shape with isolated bounded children.                                                                          | Identical bytes and valid JSON for every controlled partition and exit. |

**Tooling**: Private Bun tests, the actual helper, bounded child diagnostics
and optional `F_SETPIPE_SZ` within the private process.

**Confidence on falsification**: Strong for the specified partial-write
mechanism; finite runs do not rule out every Bun scheduling defect.

### H2: parent completion races the final FIFO drain

**Claim**: `_CapturePipe.finish` can return before consuming bytes already
written when the child exits before a reader callback.

**Plausibility**: Medium. Process completion and reader readiness are separate
callbacks, although the helper explicitly drains before returning.

**Prediction**: A Python producer with an explicit write-all loop also loses
bytes when reader callbacks are delayed until after child completion.

| Step | Action                                                                                                                          | Expected Negative Result                                          |
| ---- | ------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| 1    | Replace only the private child launcher with a Python write-all producer; delay reader delivery for a payload fitting the pipe. | `finish` returns every byte after exit despite no prior callback. |
| 2    | Allow an initial read, then delay the final reader callback until exit.                                                         | The final buffered tail is complete and ordered.                  |

**Tooling**: Private helper instrumentation and Python children, without Bun's
string writer or tracked source edits.

**Confidence on falsification**: Strong for the specific exit-before-drain
ordering; retain exact forced ordering and payload sizes in the result.

### H3: multiple capture writers interleave on one FIFO

**Claim**: inherited capture variables or multiple writes enable more than one
producer for the target FIFO in the contract's Bun process.

**Plausibility**: Low. Three opt-in capture tests share the Bun file, but each
normally receives one environment variable.

**Prediction**: instrumentation records more than one target write, or clearing
unrelated capture variables changes the result under otherwise identical input.

| Step | Action                                                                                                                  | Expected Negative Result                                                 |
| ---- | ----------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| 1    | Record only capture-variable names and target-write counts in a private preload; never expose other environment values. | Exactly one enabled target and one write, including failing repetitions. |
| 2    | Repeat with only the intended capture variable enabled.                                                                 | The result is unchanged, excluding competing writers as the cause.       |

**Tooling**: Isolated Bun preload instrumentation and the real contract file;
no credential output or global environment changes.

**Confidence on falsification**: Decisive if a corrupted capture has one
instrumented producer; otherwise report finite-run coverage honestly.

## Recommended execution order

1. H1 is the cheapest direct comparison of string and byte writes.
2. H2 independently tests parent ownership and final draining.
3. H3 checks competing producers if the direct comparisons are inconclusive.

Independent probes may run concurrently in separate private directories.

## Results and revised test

H1's string-specific prediction was falsified: both strings and explicitly
encoded byte buffers corrupted identically. With a private FIFO limited to
4,096 bytes, Bun 1.4.3 reported writing 8,004 bytes but the reader received
12,100 bytes, with the first mismatch at offset 4,096. Both 4,004-byte controls
were exact. This isolates the common `Bun.write(path, FIFO)` boundary rather
than UTF-8 string conversion. Replacing strings with byte buffers is therefore
insufficient.

H2 was falsified for both forced callback orderings. A Python write-all
producer preserved all 64,004 bytes when the final drain consumed the entire
unread payload, and when it consumed an unread tail after an earlier prefix
read. Every private child was reaped and its FIFO removed. These finite
experiments do not rule out unrelated ordering defects.

The direct counterexample makes H3 unnecessary for this failure. The next
bounded experiment, delegated to the H1 alchemist, tests H4: an explicit
`node:fs` write-all loop over byte-buffer offsets preserves the same payload
under the same backpressure. Its prediction is exact length and hash, with no
zero-progress write. A mismatch falsifies that proposed transport remedy. Use
the same five-second child deadline and private-resource cleanup, with no
tracked edits or full-suite retries during the experiment.

H4 survived the bounded experiment: the explicit write-all loop preserved 8,004
bytes and an 8,251-byte eight-ID request under the same 4,096-byte FIFO limit.
Both hashes matched, no write made zero progress, and both children exited
successfully. The repair therefore uses this writer only for private
cross-runtime test captures, retaining the parent's byte and lifetime bounds. A
real-child regression forces the small pipe and checks patterned multibyte
content; zero-filled boundary tests alone can hide repeated byte ranges.

## Termination criteria

- Stop after a reproducible counterexample identifies the failing boundary and
  the other probes delimit it; report evidence before proposing source edits.
- If all hypotheses are falsified or probes do not reproduce the symptom,
  report the exact coverage and revise this plan rather than adding hypotheses
  during execution or rerunning the full gate blindly.

## Notes for executing agent

Run private probes only, at most three minutes per hypothesis and five seconds
per child. Keep all output bounded. Do not modify tracked files, run full
gates, read credentials or transcripts, mutate Lody, or signal user services.
Reap only children created by the current probe and remove owned FIFO
resources. Return commands, payload byte counts, hashes, first mismatch and
owned-child cleanup evidence. Root owns any eventual repair and publication.
