/** @file Exercise public stream callbacks for source evidence and invalid replay. */
import {expect, it, spyOn} from 'bun:test';
import {Effect, Fiber} from 'effect';
import {TestClock} from 'effect/testing';
import {createBoardStore, liveConnection, type BoardStore} from '../src/client';
import type {Snapshot} from '../src/contracts';
import {createBoardSnapshot, firstSession} from './board-fixtures';
import {ControlledEventSource, installControlledEventSource} from './controlled-event-source';

interface StreamScenario {
  readonly store: BoardStore;
  readonly initial: Snapshot;
  readonly refreshed: Snapshot;
  readonly source: ControlledEventSource;
  readonly fetchCount: () => number;
}

/** Run the real live connection against controlled fetch and EventSource boundaries. */
async function withLiveStream(check: (scenario: StreamScenario) => Effect.Effect<void>): Promise<void> {
  const restoreEventSource = installControlledEventSource();
  const initial = createBoardSnapshot();
  const refreshed: Snapshot = {
    ...initial,
    cursor: initial.cursor + 10,
    collector: {...initial.collector, state: 'resynced', generation: 9}
  };
  let fetchCount = 0;
  const snapshotFetch = Object.assign(
    async () => {
      fetchCount += 1;
      return Response.json(fetchCount === 1 ? initial : refreshed);
    },
    {preconnect: () => null}
  );
  const fetchSpy = spyOn(globalThis, 'fetch').mockImplementation(snapshotFetch);
  try {
    const store = createBoardStore();
    const scenario = Effect.gen(function* () {
      const connection = yield* Effect.forkChild(liveConnection(store));
      yield* TestClock.adjust('0 seconds');
      const source = ControlledEventSource.instances[0];
      if (!source) throw new Error('A valid snapshot must open the first source stream.');
      try {
        yield* check({store, initial, refreshed, source, fetchCount: () => fetchCount});
      } finally {
        yield* Fiber.interrupt(connection);
      }
    });
    const withClock = scenario.pipe(Effect.provide(TestClock.layer()));
    await Effect.runPromise(withClock);
  } finally {
    fetchSpy.mockRestore();
    restoreEventSource();
  }
}

it('applies valid source health and observation frames at their exact cursors', async () => {
  await withLiveStream(({store, initial, source, fetchCount}) =>
    Effect.sync(() => {
      expect(source.url).toBe(`/api/v1/events?after=${initial.cursor}`);
      const sourceCursor = initial.cursor + 1;
      const collector = {...initial.collector, state: 'running', generation: 2};
      source.send(
        'source',
        {cursor: sourceCursor, workspaceId: initial.workspaceId, projection: collector},
        sourceCursor
      );
      expect(store.getSnapshot().snapshot?.collector).toEqual(collector);
      expect(store.getSnapshot().snapshot?.cursor).toBe(sourceCursor);

      const observationCursor = sourceCursor + 1;
      const original = firstSession(initial);
      const session = {...original, title: 'Observed change', lastEventId: observationCursor};
      source.send(
        'observation',
        {
          cursor: observationCursor,
          workspaceId: initial.workspaceId,
          sessionId: original.sessionId,
          projection: session
        },
        observationCursor
      );
      expect(store.getSnapshot().snapshot?.sessions[0]?.title).toBe('Observed change');
      expect(store.getSnapshot().snapshot?.cursor).toBe(observationCursor);
      expect(fetchCount()).toBe(1);
    })
  );
});

const invalidFrames = [
  {
    name: 'malformed source payload',
    send: (source: ControlledEventSource, initial: Snapshot) =>
      source.send('source', {cursor: initial.cursor + 1, workspaceId: initial.workspaceId}, initial.cursor + 1)
  },
  {
    name: 'mismatched source SSE cursor',
    send: (source: ControlledEventSource, initial: Snapshot) =>
      source.send(
        'source',
        {cursor: initial.cursor + 1, workspaceId: initial.workspaceId, projection: initial.collector},
        initial.cursor + 2
      )
  },
  {
    name: 'foreign source workspace',
    send: (source: ControlledEventSource, initial: Snapshot) =>
      source.send(
        'source',
        {cursor: initial.cursor + 1, workspaceId: 'foreign', projection: initial.collector},
        initial.cursor + 1
      )
  },
  {
    name: 'mismatched observation session identity',
    send: (source: ControlledEventSource, initial: Snapshot) =>
      source.send(
        'observation',
        {
          cursor: initial.cursor + 1,
          workspaceId: initial.workspaceId,
          sessionId: 'foreign-session',
          projection: firstSession(initial)
        },
        initial.cursor + 1
      )
  },
  {
    name: 'reset required',
    send: (source: ControlledEventSource) => source.dispatchEvent(new Event('reset_required'))
  }
] as const;

it.each(invalidFrames)('rejects $name and fetches a fresh snapshot', async ({send}) => {
  await withLiveStream(({store, initial, refreshed, source, fetchCount}) =>
    Effect.gen(function* () {
      send(source, initial);
      expect(store.getSnapshot().snapshot).toEqual(initial);
      yield* TestClock.adjust('1 second');
      expect(fetchCount()).toBe(2);
      expect(source.closeCount).toBe(1);
      expect(store.getSnapshot().snapshot).toEqual(refreshed);
      expect(ControlledEventSource.instances[1]?.url).toBe(`/api/v1/events?after=${refreshed.cursor}`);
    })
  );
});
