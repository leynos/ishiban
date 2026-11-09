/** @file Verify scheduled transport recovery and cancellation with virtual time. */
import {expect, it, spyOn} from 'bun:test';
import {Effect, Fiber} from 'effect';
import {TestClock} from 'effect/testing';
import {createBoardStore, liveConnection} from '../src/client';

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
  const fetchSpy = spyOn(globalThis, 'fetch').mockImplementation(unavailableFetch);
  try {
    const store = createBoardStore();
    const recovery = Effect.gen(function* () {
      const connection = yield* Effect.forkChild(liveConnection(store));
      yield* TestClock.adjust('5 seconds');
      expect(attempts).toBe(6);
      expect(store.getSnapshot().connection).toBe('Reconnecting');
      yield* Fiber.interrupt(connection);
      yield* TestClock.adjust('10 seconds');
      expect(attempts).toBe(6);
    });
    const withClock = recovery.pipe(Effect.provide(TestClock.layer()));
    await Effect.runPromise(withClock);
  } finally {
    fetchSpy.mockRestore();
  }
});
