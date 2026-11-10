/** @file Verify visibility-gated activity reads and revision-safe local merges. */
import {afterEach, expect, it} from 'bun:test';
import fc from 'fast-check';
import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import {useSyncExternalStore} from 'react';
import type {ReactElement} from 'react';
import type {Session, Snapshot, SessionActivityFrame} from '../src/contracts';
import {createBoardStore, type BoardStore} from '../src/client';
import {createDemoSnapshot} from '../src/demo';
import {startLazyActivity} from '../src/lazy-activity';
import {Board} from '../src/ui/board';
import {installActivityFetch, type ActivityFetchRequest} from './activity-fetch-fixture';
import type {Deferred} from './deferred';
import {
  ControlledIntersectionObserver,
  installControlledIntersectionObserver
} from './controlled-intersection-observer';
type ActivitySessionSpec = readonly [number, string, string, Session['source'], Session['state'], number];
interface ActivityMergeScenario {
  readonly cursor: number;
  readonly responseRevision: number;
  readonly isForeignWorkspace: boolean;
  readonly isMatchingSession: boolean;
  readonly hasNewerRevision: boolean;
  readonly isCurrentlyUnknown: boolean;
  readonly nextActivity: 'idle' | 'pending' | 'running' | 'waiting';
}

const seedSnapshot = createDemoSnapshot();

/** Reuse demo projections while giving every fixture explicit source facts. */
function activitySession(spec: ActivitySessionSpec): Session {
  const [seedIndex, sessionId, title, source, state, lastEventId] = spec;
  const session = seedSnapshot.sessions[seedIndex];
  if (!session) throw new Error('The demo snapshot must contain activity fixture records.');
  return {
    ...session,
    sessionId,
    title,
    source,
    state,
    lastEventId
  };
}
const activitySpecs: readonly ActivitySessionSpec[] = [
  [0, 'known', 'Known persisted activity', 'persisted', 'running', 80],
  [1, 'demo-unknown', 'Demo unknown activity', 'demo', 'unknown', 81],
  [2, 'persisted/session 01', 'Unknown persisted activity 01', 'persisted', 'unknown', 82],
  [3, 'persisted-session-02', 'Unknown persisted activity 02', 'persisted', 'unknown', 83],
  [4, 'persisted-session-03', 'Unknown persisted activity 03', 'persisted', 'unknown', 84],
  [5, 'persisted-session-04', 'Unknown persisted activity 04', 'persisted', 'unknown', 85]
];
const activitySessions = activitySpecs.map((spec) => activitySession(spec));
/** Fail clearly if the compact session fixture is missing a requested record. */
function fixtureSession(index: number): Session {
  const session = activitySessions[index];
  if (!session) throw new Error('The activity fixture must contain the requested session.');
  return session;
}
const KNOWN_SESSION = fixtureSession(0);
const DEMO_UNKNOWN_SESSION = fixtureSession(1);
const UNKNOWN_REAL_ONE = fixtureSession(2);
const UNKNOWN_REAL_TWO = fixtureSession(3);
const UNKNOWN_REAL_THREE = fixtureSession(4);
const UNKNOWN_REAL_FOUR = fixtureSession(5);

/** Build a connected workspace snapshot containing only the requested sessions. */
function activitySnapshot(sessions: readonly Session[]): Snapshot {
  return {
    ...seedSnapshot,
    workspaceId: 'workspace-lazy-activity',
    cursor: 700,
    collector: {...seedSnapshot.collector, state: 'connected'},
    sessions: [...sessions]
  };
}
/** Render real marks before starting their visibility observer. */
function mountBoard(sessions: readonly Session[]) {
  const snapshot = activitySnapshot(sessions);
  const store = createBoardStore();
  store.replace(snapshot);
  render(<StoreBackedBoard store={store} />);
  stopLazyActivity = startLazyActivity(store);
  return {snapshot, store, observer: currentObserver()};
}
/** Install controlled boundaries around the board's real visible marks. */
function activityBoard(sessions: readonly Session[]) {
  installIntersectionObserver();
  const transport = installFetch();
  return {...transport, ...mountBoard(sessions)};
}
/** Dispose observer subscriptions and abort owned activity reads between cases. */
function stopActivity(): void {
  stopLazyActivity?.();
  stopLazyActivity = null;
}
/** Reflect external-store merges through the real board renderer. */
function StoreBackedBoard({store}: {readonly store: BoardStore}): ReactElement | null {
  const current = useSyncExternalStore(store.subscribe, store.getSnapshot);
  if (!current.snapshot) return null;
  return <Board connection={current.connection} snapshot={current.snapshot} />;
}

let restoreObserver: (() => void) | null = null;
let restoreFetch: (() => void) | null = null;
let stopLazyActivity: (() => void) | null = null;
/** Replace viewport observation with explicitly controlled entry delivery. */
function installIntersectionObserver(): void {
  restoreObserver = installControlledIntersectionObserver();
}
/** Return the observer installed by the live activity scanner. */
function currentObserver(): ControlledIntersectionObserver {
  const observer = ControlledIntersectionObserver.instances.at(-1);
  if (!observer) throw new Error('Lazy activity must install an intersection observer.');
  return observer;
}
/** Record batch requests and hold their responses for deterministic ordering. */
function installFetch() {
  const fixture = installActivityFetch();
  restoreFetch = fixture.restore;
  return fixture;
}
/** Find the actual rendered session mark by its accessible title. */
function markFor(title: string): HTMLElement {
  return screen.getByRole('button', {name: new RegExp(title, 'u')});
}
/** Send visible entries for selected real DOM marks. */
function revealSessions(observer: ControlledIntersectionObserver, sessions: readonly Session[]): void {
  for (const session of sessions) observer.setVisibility(markFor(session.title), true);
}
/** Guard an expected pending request before controlling its response. */
function requestAt(requests: readonly ActivityFetchRequest[], index: number): ActivityFetchRequest {
  const request = requests[index];
  if (!request) throw new Error('The expected visible activity request did not start.');
  return request;
}
/** Check the shared POST contract; for example, browser batches contain four IDs or fewer. */
function expectBatchPost(request: ActivityFetchRequest, sessionIds: readonly string[]): void {
  expect(request.url).toBe('/api/v1/sessions/activity');
  expect(request.init.method).toBe('POST');
  expect(JSON.parse(String(request.init.body))).toEqual({sessionIds});
  expect(request.init.cache).toBe('no-store');
  expect(request.init.signal?.aborted).toBe(false);
}
/** Wait for one ephemeral state without changing its journal cursor. */
async function waitForActivity(store: BoardStore, sessionId: string, expectedState: Session['state']): Promise<void> {
  await waitFor(() => {
    const current = store.getSnapshot().snapshot?.sessions.find((item) => item.sessionId === sessionId);
    expect(current?.state).toBe(expectedState);
  });
}
/** Assert the batch limits and that queued identities are distinct. */
function expectBoundedPipeline(requests: readonly ActivityFetchRequest[], count: number): void {
  expect(requests).toHaveLength(2);
  const requestedIds = requests.flatMap((request) => JSON.parse(String(request.init.body)).sessionIds);
  expect(requestedIds).toHaveLength(count);
  expect(new Set(requestedIds).size).toBe(count);
  for (const request of requests) {
    const ids: string[] = JSON.parse(String(request.init.body)).sessionIds;
    expect(ids.length).toBeLessThanOrEqual(4);
    expectBatchPost(request, ids);
  }
}
/** Return a stream that exposes one frame before the batch completes. */
function earlyActivityResponse(request: ActivityFetchRequest, frame: SessionActivityFrame): Response {
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(`${JSON.stringify(frame)}\n`));
        request.init.signal?.addEventListener('abort', () => controller.close(), {once: true});
      }
    })
  );
}
/** Encode a completed member while preserving its explicit request identity. */
function activityFrame(workspaceId: string, session: Session): SessionActivityFrame {
  return {workspaceId, sessionId: session.sessionId, session};
}
/** Complete a streaming batch using independently validated NDJSON frames. */
function resolveBatch(request: ActivityFetchRequest, frames: readonly SessionActivityFrame[]): void {
  const body = `${frames.map((frame) => JSON.stringify(frame)).join('\n')}\n`;
  request.response.resolve(new Response(body, {headers: {'content-type': 'application/x-ndjson'}}));
}
/** Accept only same-workspace, same-session, current unknown revisions. */
function activityReplyMatches(scenario: ActivityMergeScenario): boolean {
  return (
    !scenario.isForeignWorkspace &&
    scenario.isMatchingSession &&
    !scenario.hasNewerRevision &&
    scenario.isCurrentlyUnknown
  );
}
/** Generate the stored state against which a lazy reply must be checked. */
function currentSessionFor(scenario: ActivityMergeScenario): Session {
  return {
    ...UNKNOWN_REAL_ONE,
    state: scenario.isCurrentlyUnknown ? 'unknown' : 'running',
    lastEventId: scenario.responseRevision + (scenario.hasNewerRevision ? 1 : 0)
  };
}
/** Wait for a queued request to enter the controlled fetch boundary. */
async function waitForRequest(started: readonly Deferred<void>[], index: number): Promise<void> {
  const signal = started[index];
  if (!signal) throw new Error('The expected queued activity request did not start.');
  await signal.promise;
}

afterEach(() => {
  stopActivity();
  cleanup();
  restoreFetch?.();
  restoreFetch = null;
  restoreObserver?.();
  restoreObserver = null;
});

it('looks up the new tab when a visible family mark changes its raw session ID', async () => {
  const {requests, started, observer} = activityBoard([UNKNOWN_REAL_ONE, UNKNOWN_REAL_TWO]);
  const mark = markFor(UNKNOWN_REAL_ONE.title);
  act(() => observer.setVisibility(mark, true));
  await waitForRequest(started, 0);
  expectBatchPost(requestAt(requests, 0), [UNKNOWN_REAL_ONE.sessionId]);

  // React may preserve this exact button while recency selects another tab.
  act(() => mark.setAttribute('data-session-id', UNKNOWN_REAL_TWO.sessionId));
  await waitFor(() => expect(requests.length).toBe(2));
  expectBatchPost(requestAt(requests, 1), [UNKNOWN_REAL_TWO.sessionId]);
});

it('batches visible unknown activity and allows immediate rediscovery after dropping offscreen work', async () => {
  const {requests, started, snapshot, store, observer} = activityBoard([
    KNOWN_SESSION,
    DEMO_UNKNOWN_SESSION,
    UNKNOWN_REAL_ONE,
    UNKNOWN_REAL_TWO,
    UNKNOWN_REAL_THREE,
    UNKNOWN_REAL_FOUR
  ]);
  revealSessions(observer, [DEMO_UNKNOWN_SESSION, KNOWN_SESSION, UNKNOWN_REAL_ONE, UNKNOWN_REAL_TWO]);
  observer.setVisibility(markFor(UNKNOWN_REAL_ONE.title), true);
  const queuedMark = markFor(UNKNOWN_REAL_THREE.title);
  observer.setVisibility(queuedMark, true);
  observer.setVisibility(queuedMark, false);
  await waitForRequest(started, 0);
  expect(requests).toHaveLength(1);
  const firstRequest = requestAt(requests, 0);
  expectBatchPost(firstRequest, [UNKNOWN_REAL_ONE.sessionId, UNKNOWN_REAL_TWO.sessionId]);
  resolveBatch(firstRequest, [
    activityFrame(snapshot.workspaceId, {...UNKNOWN_REAL_ONE, state: 'running', activitySource: 'lazy'}),
    {workspaceId: snapshot.workspaceId, sessionId: UNKNOWN_REAL_TWO.sessionId, session: null}
  ]);
  await waitForActivity(store, UNKNOWN_REAL_ONE.sessionId, 'running');
  observer.setVisibility(queuedMark, true);
  await waitForRequest(started, 1);
  expect(requests).toHaveLength(2);
  const secondRequest = requestAt(requests, 1);
  expectBatchPost(secondRequest, [UNKNOWN_REAL_THREE.sessionId]);
  const current = store.getSnapshot().snapshot;
  expect(current?.cursor).toBe(snapshot.cursor);
  expect(current?.sessions[2]?.lastEventId).toBe(UNKNOWN_REAL_ONE.lastEventId);
  expect(current?.sessions[2]?.activitySource).toBe('lazy');
  const updatedMark = markFor(UNKNOWN_REAL_ONE.title);
  expect(updatedMark.getAttribute('data-update-revision')).toBeNull();
  expect(updatedMark.querySelector('[data-session-update-pulse]')).toBeNull();
  stopActivity();
  expect(observer.disconnected).toBe(true);
  expect(secondRequest.init.signal?.aborted).toBe(true);
});

it('rejects stale, foreign and mismatched members without discarding a valid batch member', async () => {
  const {requests, started, snapshot, store, observer} = activityBoard([
    UNKNOWN_REAL_ONE,
    UNKNOWN_REAL_TWO,
    UNKNOWN_REAL_THREE,
    UNKNOWN_REAL_FOUR
  ]);
  revealSessions(observer, [UNKNOWN_REAL_ONE, UNKNOWN_REAL_TWO, UNKNOWN_REAL_THREE, UNKNOWN_REAL_FOUR]);
  await waitForRequest(started, 0);
  expect(requests).toHaveLength(1);
  const newerSession: Session = {...UNKNOWN_REAL_ONE, state: 'pending', lastEventId: UNKNOWN_REAL_ONE.lastEventId + 1};
  await act(async () => {
    store.session(snapshot.cursor + 1, newerSession);
    await Promise.resolve();
  });
  resolveBatch(requestAt(requests, 0), [
    activityFrame(snapshot.workspaceId, {...UNKNOWN_REAL_ONE, state: 'running', activitySource: 'lazy'}),
    activityFrame('another-workspace', {...UNKNOWN_REAL_TWO, state: 'waiting', activitySource: 'lazy'}),
    {
      workspaceId: snapshot.workspaceId,
      sessionId: UNKNOWN_REAL_THREE.sessionId,
      session: {...UNKNOWN_REAL_THREE, sessionId: 'wrong-session', state: 'idle'}
    },
    activityFrame(snapshot.workspaceId, {...UNKNOWN_REAL_FOUR, state: 'waiting', activitySource: 'lazy'})
  ]);
  await waitFor(() => expect(store.getSnapshot().snapshot?.sessions[3]?.state).toBe('waiting'));
  const current = store.getSnapshot().snapshot;
  if (!current) throw new Error('The validated batch must retain its workspace.');
  expect(current.cursor).toBe(snapshot.cursor + 1);
  expect(current.sessions[0]?.state).toBe('pending');
  expect(current.sessions[0]?.lastEventId).toBe(newerSession.lastEventId);
  expect(current.sessions[1]?.state).toBe('unknown');
  expect(current.sessions[2]?.state).toBe('unknown');
});

it('shares a pending lookup through metadata replay and accepts its current rebased result', async () => {
  const {requests, started, snapshot, store, observer} = activityBoard([UNKNOWN_REAL_ONE]);
  revealSessions(observer, [UNKNOWN_REAL_ONE]);
  await waitForRequest(started, 0);
  const current: Session = {
    ...UNKNOWN_REAL_ONE,
    title: 'Updated metadata',
    lastEventId: UNKNOWN_REAL_ONE.lastEventId + 1
  };
  await act(async () => {
    store.session(snapshot.cursor + 1, current);
    await Promise.resolve();
  });
  expect(requests).toHaveLength(1);
  resolveBatch(requestAt(requests, 0), [
    activityFrame(snapshot.workspaceId, {...current, state: 'running', activitySource: 'lazy'})
  ]);
  await waitFor(() => expect(store.getSnapshot().snapshot?.sessions[0]?.state).toBe('running'));
  expect(store.getSnapshot().snapshot?.sessions[0]?.title).toBe('Updated metadata');
  expect(store.getSnapshot().snapshot?.cursor).toBe(snapshot.cursor + 1);
  expect(requests).toHaveLength(1);
});

it('pipelines two bounded batches and applies an early member before its stream ends', async () => {
  const sessions = Array.from({length: 9}, (_, index) =>
    activitySession([2, `pipeline-${index}`, `Pipeline ${index}`, 'persisted', 'unknown', 100 + index])
  );
  const {requests, started, snapshot, store, observer} = activityBoard(sessions);
  revealSessions(observer, sessions);
  await waitForRequest(started, 1);
  expectBoundedPipeline(requests, 8);
  const first = sessions[0];
  if (!first) throw new Error('The pipeline fixture needs its first session.');
  const request = requestAt(requests, 0);
  const frame = activityFrame(snapshot.workspaceId, {...first, state: 'running', activitySource: 'lazy'});
  request.response.resolve(earlyActivityResponse(request, frame));
  await waitForActivity(store, first.sessionId, 'running');
  expect(store.getSnapshot().snapshot?.sessions[1]?.state).toBe('unknown');
  expect(requests).toHaveLength(2);
  stopActivity();
  expect(requests.every((item) => item.init.signal?.aborted)).toBe(true);
});

it('merges only matching unknown activity replies without changing the journal boundary', () => {
  const base = activitySnapshot([UNKNOWN_REAL_ONE]);
  const scenarios: fc.Arbitrary<ActivityMergeScenario> = fc.record({
    cursor: fc.integer({min: 0, max: 1_000_000}),
    responseRevision: fc.integer({min: 1, max: 1_000_000}),
    isForeignWorkspace: fc.boolean(),
    isMatchingSession: fc.boolean(),
    hasNewerRevision: fc.boolean(),
    isCurrentlyUnknown: fc.boolean(),
    nextActivity: fc.constantFrom('idle', 'pending', 'running', 'waiting')
  });

  fc.assert(
    fc.property(scenarios, (scenario) => {
      const currentSession = currentSessionFor(scenario);
      const snapshot: Snapshot = {...base, cursor: scenario.cursor, sessions: [currentSession]};
      const store = createBoardStore(() => {});
      store.replace(snapshot);
      const before = store.getSnapshot();
      const reply: Session = {
        ...currentSession,
        sessionId: scenario.isMatchingSession ? currentSession.sessionId : 'other-session',
        state: scenario.nextActivity,
        lastEventId: scenario.responseRevision,
        activitySource: 'lazy'
      };

      const lookupWorkspace = scenario.isForeignWorkspace ? 'another-workspace' : snapshot.workspaceId;
      store.activity(lookupWorkspace, reply);

      const shouldMerge = activityReplyMatches(scenario);
      const after = store.getSnapshot();
      expect(after === before).toBe(!shouldMerge);
      expect(after.snapshot?.cursor).toBe(scenario.cursor);
      expect(after.snapshot?.sessions[0]?.lastEventId).toBe(currentSession.lastEventId);
      expect(after.snapshot?.sessions[0]).toEqual(shouldMerge ? reply : currentSession);
    }),
    {numRuns: 40, seed: 20_261_110}
  );
});
