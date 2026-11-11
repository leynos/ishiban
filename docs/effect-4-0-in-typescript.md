# Effect 4.0 in TypeScript

This note records the parts of Effect 4.0 that the Vibe Coder mockup relies on,
verified against `effect@4.0.5` in this repository. It exists so that
contributors (human or agent) need not rediscover the 4.0 surface, which
differs materially from the 3.x line most training material describes.

## Where the authoritative documentation lives

Effect 4 ships its own agent-oriented documentation inside the package:

- `node_modules/effect/AGENTS.md` (identical to `CLAUDE.md`) is the index.
- `node_modules/effect/ai-docs/src/**` holds small, compiling example
  programmes grouped by topic (services, schema, errors, streams, testing,
  integration, schedules).
- `node_modules/effect/dist/*.d.ts` carries JSDoc with examples for every
  export; `grep -n "^export declare const name" dist/Module.d.ts` is the
  quickest way to confirm a function exists.

The package documentation explicitly warns against relying on unrelated or
older copies of Effect documentation. Prefer those sources over memory.

## Version policy

- 4.0.0 was released on 2026-10-01, and patch releases have followed every
  few days. The project depends on `effect@^4.0.5`.
- Everything is imported from the single `effect` package. Sub-areas use
  sub-path exports, for example `effect/testing` for `TestClock`.

## Changes from 3.x that matter here

| Concern                | Effect 3.x habit                    | Effect 4.0                                                  |
| ---------------------- | ----------------------------------- | ----------------------------------------------------------- |
| Defining a service     | `Context.Tag` / `Effect.Service`    | `class X extends Context.Service<X, Shape>()("id") {}`      |
| Building an instance   | object literal                      | `X.of({ ... })`                                             |
| Using a service inline | `Effect.flatMap(X, f)`              | `X.use((x) => ...)` or `yield* X` inside `Effect.gen`       |
| Default-valued service | `Context.Reference` class           | `Context.Reference<T>("id", { defaultValue: () => value })` |
| Tagged errors          | `Data.TaggedError`                  | `Schema.TaggedError<E>()("Tag", { field: Schema.String })`  |
| Catch everything       | `Effect.catchAll`                   | `Effect.catch`                                              |
| Fork to global scope   | `Effect.forkDaemon`                 | `Effect.forkDetach`                                         |
| Fork to parent scope   | `Effect.fork`                       | `Effect.forkChild`                                          |
| Test clock             | `TestClock` from `effect/TestClock` | `import { TestClock } from "effect/testing"`                |
| Reusable effect fn     | `Effect.fn` (late 3.x)              | `Effect.fn("name")(function* ...)` or `Effect.fnUntraced`   |

`Data.TaggedError` still exists, but the library guidance prefers
`Schema.TaggedError` so errors are serializable and self-describing.

## Writing effects

Prefer `Effect.gen` for inline code. For reusable functions, use
`Effect.fn("name")` when a tracing span is useful and `Effect.fnUntraced` in
hot paths. Do not write functions whose only job is to return `Effect.gen(...)`.

```ts
import { Effect, Schema } from "effect";

export class PolicyRejected extends Schema.TaggedError<PolicyRejected>()(
  "PolicyRejected",
  { reason: Schema.String },
) {}

export const commitPolicy = Effect.fn("commitPolicy")(function* (
  total: number,
): Effect.fn.Return<number, PolicyRejected> {
  if (total !== 100) {
    // Always `return yield*` an error so TypeScript knows control stops here.
    return yield* new PolicyRejected({ reason: "allocations must sum to 100" });
  }
  return total;
});
```

Extra behaviour is attached by passing further arguments to `Effect.fn` (for
example `Effect.catch(...)`), not by calling `.pipe` on the result.

## Services and layers (ports and adapters)

A service class carries its interface as the second type parameter and a string
key that should include the module path. Implementations are layers,
conventionally attached as static members.

```ts
import { Context, Effect, Layer } from "effect";

export class GameClock extends Context.Service<
  GameClock,
  { readonly nowIso: Effect.Effect<string> }
>()("vibe-coder/domain/ports/GameClock") {
  static readonly browser = Layer.succeed(
    GameClock,
    GameClock.of({ nowIso: Effect.sync(() => new Date().toISOString()) }),
  );
}

const program = Effect.gen(function* () {
  const clock = yield* GameClock;
  return yield* clock.nowIso;
});

// Or, without a generator:
const same = GameClock.use((clock) => clock.nowIso);
```

- `Layer.succeed(Tag, value)` provides a ready-made instance.
- `Layer.effect(Tag, effect)` builds an instance effectfully (for example
  allocating a `Ref`).
- `Layer.provide(dependencies)` hides dependencies; `Layer.provideMerge`
  exposes them as well, which is handy in tests.
- `Layer.mergeAll(a, b, c)` combines independent layers.
- `X["Service"]` names the service's interface type when it is needed.

In this project, ports are services declared beside the domain and adapters are
layers under `src/app/adapters/`. Domain rules stay plain, synchronous
TypeScript; Effect orchestrates them.

## Bridging to React with `ManagedRuntime`

`ManagedRuntime.make(layer)` builds the layer once and exposes `runPromise`,
`runSync`, `runFork`, `runCallback`, and `dispose`. Create one runtime per
application (or per test) and share it.

```ts
import { ManagedRuntime } from "effect";

const runtime = ManagedRuntime.make(AppLayer);
const value = await runtime.runPromise(program);
await runtime.dispose(); // releases scoped resources and interrupts fibres
```

`runSync` throws if the effect is asynchronous, so use it only for effects
known to be synchronous, such as reading a `SubscriptionRef`.

## Observable state with `SubscriptionRef`

`SubscriptionRef` is a `Ref` whose changes can be streamed. It is the project's
bridge from Effect-owned state to `useSyncExternalStore`.

```ts
import { Effect, Stream, SubscriptionRef } from "effect";

const demo = Effect.gen(function* () {
  const ref = yield* SubscriptionRef.make(0);
  yield* SubscriptionRef.update(ref, (n) => n + 1);
  const current = yield* SubscriptionRef.get(ref);
  // `changes` emits the current value first, then every subsequent update.
  yield* Stream.runForEach(SubscriptionRef.changes(ref), (n) =>
    Effect.sync(() => console.log(n)),
  ).pipe(Effect.forkChild);
  return current;
});
```

Verified behaviour: a listener started before any update receives the initial
value immediately, followed by each update in order.

## Fibres, schedules, and long-running loops

- `Effect.repeat(effect, Schedule.spaced("400 millis"))` runs the effect,
  then repeats it with the given gap. The first run is immediate.
- `Schedule.fixed(interval)` keeps a fixed cadence instead of a fixed gap.
- `runtime.runFork(effect)` returns a `Fiber`; stop it with
  `runtime.runPromise(Fiber.interrupt(fiber))`.
- `Effect.forkChild` ties a fibre to its parent's scope; `Effect.forkDetach`
  attaches it to the global scope so it outlives the parent.
- `Effect.sleep("1 hour")` accepts duration strings as well as
  `Duration` values.

## Testing

`bun test` runs Effect programmes directly with `Effect.runPromise` or a
test-specific `ManagedRuntime`. Swap adapters by providing test layers.

Virtual time comes from `TestClock` in `effect/testing`:

```ts
import { Effect, Fiber } from "effect";
import { TestClock } from "effect/testing";

const program = Effect.gen(function* () {
  const fiber = yield* Effect.sleep("1 hour").pipe(Effect.as("woke"), Effect.forkChild);
  yield* TestClock.adjust("1 hour");
  return yield* Fiber.join(fiber);
});

await Effect.runPromise(program.pipe(Effect.provide(TestClock.layer())));
// => "woke"
```

`@effect/vitest` exists for `it.effect`, but this repository uses `bun test`,
so tests call `Effect.runPromise` instead.

## Validation boundaries

Ishiban uses Effect 4 `Schema` to parse untrusted browser-boundary data, as
specified in `AGENTS.md` and the developers' guide. Use the same schemas for
runtime validation and inferred types at those boundaries. Do not introduce a
second general-purpose schema library for the same boundary.

## Gotchas observed

- Imports that look like 3.x (`Context.Tag`, `Effect.Service`, `Effect.fork`,
  `Effect.catchAll`, `Effect.forkDaemon`) fail to type-check because those
  exports no longer exist; consult the `.d.ts` files rather than guessing.
- `SubscriptionRef.changes` replays the current value, so a React bridge
  must tolerate an immediate notification on subscription.
- Disposing a `ManagedRuntime` interrupts fibres started with
  `runtime.runFork`; tests must dispose runtimes to avoid leaking timers.
