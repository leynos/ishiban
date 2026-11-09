/** @file Verify scheduled transport recovery and cancellation with virtual time. */
import {expect, it, spyOn} from 'bun:test';
import {Effect, Fiber} from 'effect';
import {TestClock} from 'effect/testing';
import {createBoardStore, liveConnection, type BoardStore} from '../src/client';
import {createDemoSnapshot} from '../src/demo';

/** Controllable EventSource boundary; transport errors retain browser ready states. */
class ControlledEventSource extends EventTarget {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSED = 2;
  readonly withCredentials = false;
  readonly url: string;
  readyState = 1;
  closeCount = 0;
  onerror: EventSource['onerror'] = null;
  onmessage: EventSource['onmessage'] = null;
  onopen: EventSource['onopen'] = null;
  static instances: ControlledEventSource[] = [];

  /** Retain the requested replay URL, as the browser transport does. */
  constructor(url: string | URL) {
    super();
    this.url = String(url);
    ControlledEventSource.instances.push(this);
  }

  /** Record scoped disposal separately from a server-induced closed state. */
  close(): void {
    this.readyState = this.CLOSED;
    this.closeCount += 1;
  }
}

type RecoveryScenario = (store: BoardStore, connection: Fiber.Fiber<void, unknown>) => Effect.Effect<void>;

/** Own fetch and virtual time; for example, verifyRecovery(snapshotFetch, checkClosedStream). */
async function verifyRecovery(fetchResponse: typeof fetch, scenario: RecoveryScenario): Promise<void> {
  const fetchSpy = spyOn(globalThis, 'fetch').mockImplementation(fetchResponse);
  try {
    const store = createBoardStore();
    const recovery = Effect.gen(function* () {
      const connection = yield* Effect.forkChild(liveConnection(store));
      yield* scenario(store, connection);
    });
    const withClock = recovery.pipe(Effect.provide(TestClock.layer()));
    await Effect.runPromise(withClock);
  } finally {
    fetchSpy.mockRestore();
  }
}

it('retries beyond four failed snapshots and stops retrying when cancelled', async () => {
  let attempts = 0;
  // Bun's fetch boundary includes a preconnect method, even for HTTP failures.
  const unavailableFetch = Object.assign(
    async () => {
      attempts += 1;
      return new Response('Temporarily unavailable', {status: 503});
    },
    {
      preconnect: () => {
        // A failed HTTP fixture never opens a socket.
      }
    }
  );
  const scenario: RecoveryScenario = (store, connection) =>
    Effect.gen(function* () {
      yield* TestClock.adjust('5 seconds');
      expect(attempts).toBe(6);
      expect(store.getSnapshot().connection).toBe('Reconnecting');
      yield* Fiber.interrupt(connection);
      yield* TestClock.adjust('10 seconds');
      expect(attempts).toBe(6);
    });
  await verifyRecovery(unavailableFetch, scenario);
});

it('resnapshots a permanently closed stream while leaving browser reconnects alone', async () => {
  const previousSource = Object.getOwnPropertyDescriptor(globalThis, 'EventSource');
  Object.defineProperty(globalThis, 'EventSource', {configurable: true, value: ControlledEventSource});
  ControlledEventSource.instances = [];
  let attempts = 0;
  const snapshotFetch = Object.assign(
    async () => {
      attempts += 1;
      return Response.json(createDemoSnapshot());
    },
    {preconnect: () => null}
  );
  try {
    const scenario: RecoveryScenario = (store, connection) =>
      Effect.gen(function* () {
        yield* TestClock.adjust('0 seconds');
        const source = ControlledEventSource.instances[0];
        if (!source) throw new Error('A successful snapshot must open its stream');
        source.readyState = source.CONNECTING;
        source.dispatchEvent(new Event('error'));
        yield* TestClock.adjust('1 second');
        expect(attempts).toBe(1);
        expect(source.closeCount).toBe(0);
        expect(store.getSnapshot().connection).toBe('Reconnecting');
        source.readyState = source.CLOSED;
        source.dispatchEvent(new Event('error'));
        yield* TestClock.adjust('1 second');
        expect(attempts).toBe(2);
        expect(source.closeCount).toBe(1);
        expect(ControlledEventSource.instances).toHaveLength(2);
        yield* Fiber.interrupt(connection);
        yield* TestClock.adjust('10 seconds');
        expect(attempts).toBe(2);
        const replacement = ControlledEventSource.instances[1];
        expect(replacement?.closeCount).toBe(1);
      });
    await verifyRecovery(snapshotFetch, scenario);
  } finally {
    if (previousSource) Object.defineProperty(globalThis, 'EventSource', previousSource);
    else Reflect.deleteProperty(globalThis, 'EventSource');
  }
});
