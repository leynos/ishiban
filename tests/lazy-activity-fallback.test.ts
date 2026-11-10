/** @file Exercise oversized activity markers and their bounded same-session fallback. */
import {afterEach, expect, it} from 'bun:test';
import {waitFor} from '@testing-library/react';
import type {Session, SessionActivityFrame, Snapshot} from '../src/contracts';
import {createBoardStore} from '../src/client';
import {startLazyActivity} from '../src/lazy-activity';
import {createBoardSnapshot, firstSession} from './board-fixtures';
import {installActivityFetch, type ActivityFetchRequest} from './activity-fetch-fixture';
import {
  ControlledIntersectionObserver,
  installControlledIntersectionObserver
} from './controlled-intersection-observer';
import type {Deferred} from './deferred';
import {
  applyStaleFallbackChange,
  expectFallbackOutcome,
  fallbackCases,
  fallbackResponseFor,
  flushFallbackMicrotasks,
  storedSession,
  TRANSFER_NOTICE,
  waitForFallbackOutcome
} from './lazy-activity-fallback-fixture';
let restoreIntersectionObserver: (() => void) | undefined;
let restoreFetch: (() => void) | undefined;
let stopRequests: (() => void) | undefined;

/** Create a real-session-shaped unknown record; for example, retain a last failed turn. */
function unknownSession(sessionId: string): Session {
  return {
    ...firstSession(createBoardSnapshot()),
    sessionId,
    title: `Session ${sessionId}`,
    source: 'metadata',
    freshness: 'unavailable',
    state: 'unknown',
    lastEventId: 70,
    lastActivityEventId: 40,
    latestTurn: {userTurnId: 'prior-turn', state: 'failed', error: 'Earlier Lody error'},
    activeTurns: []
  };
}

/** Install a visible board and deterministic browser boundaries. */
function scenario(sessionIds: readonly string[]) {
  restoreIntersectionObserver = installControlledIntersectionObserver();

  const snapshot: Snapshot = {
    ...createBoardSnapshot(),
    workspaceId: 'fallback-workspace',
    sessions: sessionIds.map((sessionId) => unknownSession(sessionId))
  };
  const store = createBoardStore(() => {});
  store.replace(snapshot);
  document.body.replaceChildren(
    ...sessionIds.map((sessionId) => {
      const mark = document.createElement('button');
      mark.setAttribute('data-session-id', sessionId);
      return mark;
    })
  );

  const fetchFixture = installActivityFetch(12);
  const {requests, started} = fetchFixture;
  restoreFetch = fetchFixture.restore;

  stopRequests = startLazyActivity(store);
  const observer = ControlledIntersectionObserver.instances.at(-1);
  if (!observer) throw new Error('The visible activity scanner must install an observer.');
  for (const mark of document.querySelectorAll('button[data-session-id]')) observer.setVisibility(mark, true);
  return {snapshot, store, requests, started, observer};
}

/** Return one controlled network request; for example, POST then the GET fallback. */
function requestAt(requests: readonly ActivityFetchRequest[], index: number): ActivityFetchRequest {
  const request = requests[index];
  if (!request) throw new Error(`Expected request ${index} to start.`);
  return request;
}

/** Read one seeded session; for example, select the marked member from a batch. */
function sessionAt(snapshot: Snapshot, index = 0): Session {
  const session = snapshot.sessions[index];
  if (!session) throw new Error(`Expected test session ${index} to exist.`);
  return session;
}

/** Resolve one batch as NDJSON without coupling tests to network chunk boundaries. */
function resolveBatch(request: ActivityFetchRequest, frames: readonly unknown[]): void {
  request.response.resolve(new Response(`${frames.map((frame) => JSON.stringify(frame)).join('\n')}\n`));
}

/** Build the exact backend marker shape; no session member may fit this response. */
function oversizedMarker(workspaceId: string, sessionId: string) {
  return {workspaceId, sessionId, outcome: 'response_too_large'} satisfies SessionActivityFrame;
}

/** Build a current success frame for one member of the same batch. */
function successFrame(workspaceId: string, session: Session) {
  return {workspaceId, sessionId: session.sessionId, session: {...session, state: 'running' as const}};
}

/** Wait for one controlled fetch to begin before releasing its deferred response. */
async function waitForStart(started: readonly Deferred<void>[], index: number): Promise<void> {
  const signal = started[index];
  if (!signal) throw new Error(`Expected request ${index} to have a start signal.`);
  await signal.promise;
}

/** Start the marker and its one owned fallback; for example, inspect a large session response. */
async function beginFallback(sessionId = 'large-session') {
  const setup = scenario([sessionId]);
  await waitForStart(setup.started, 0);
  const session = sessionAt(setup.snapshot);
  resolveBatch(requestAt(setup.requests, 0), [oversizedMarker(setup.snapshot.workspaceId, session.sessionId)]);
  await waitForStart(setup.started, 1);
  return {...setup, session, fallback: requestAt(setup.requests, 1)};
}

/** Seed one unresolved session with the local transfer notice already attached. */
function scenarioWithNotice() {
  const setup = scenario(['large-session']);
  const session = sessionAt(setup.snapshot);
  setup.store.activityNotice(setup.snapshot.workspaceId, session.sessionId, session.lastEventId, TRANSFER_NOTICE);
  return {...setup, session};
}

afterEach(() => {
  stopRequests?.();
  stopRequests = undefined;
  restoreFetch?.();
  restoreFetch = undefined;
  restoreIntersectionObserver?.();
  restoreIntersectionObserver = undefined;
  document.body.replaceChildren();
});

it('keeps a later small member moving while one oversized member falls back once', async () => {
  const {snapshot, store, requests, started} = scenario(['large-session', 'small-session']);
  await waitForStart(started, 0);
  const large = sessionAt(snapshot);
  const small = sessionAt(snapshot, 1);

  resolveBatch(requestAt(requests, 0), [
    oversizedMarker(snapshot.workspaceId, large.sessionId),
    oversizedMarker(snapshot.workspaceId, large.sessionId),
    successFrame(snapshot.workspaceId, small)
  ]);
  await waitForStart(started, 1);

  expect(requestAt(requests, 1).url).toBe(
    `/api/v1/session-activity?sessionId=${encodeURIComponent(large.sessionId)}&includeKnown=true`
  );
  expect(requestAt(requests, 1).init.signal).toBe(requestAt(requests, 0).init.signal);
  expect(requestAt(requests, 1).init.signal?.aborted).toBe(false);
  expect(store.getSnapshot().snapshot?.sessions.find((item) => item.sessionId === small.sessionId)?.state).toBe(
    'running'
  );
  expect(requests).toHaveLength(2);
});

it.each(['.', '..', 'a/b', '100%?'])('uses the query fallback for exact session ID %s', async (sessionId) => {
  const {snapshot, store, session, fallback} = await beginFallback(sessionId);
  expect(fallback.url).toBe(`/api/v1/session-activity?sessionId=${encodeURIComponent(sessionId)}&includeKnown=true`);
  fallback.response.resolve(
    Response.json({workspaceId: snapshot.workspaceId, session: {...session, state: 'running'}})
  );
  await waitFor(() => expect(storedSession(store).state).toBe('running'));
  expect(storedSession(store).sessionId).toBe(sessionId);
});

it.each(fallbackCases)('$name', async (testCase) => {
  const setup = await beginFallback();
  const sideEffects = {wasCancelled: false};
  applyStaleFallbackChange(testCase, setup);
  setup.fallback.response.resolve(fallbackResponseFor(testCase, setup, sideEffects));

  await waitForFallbackOutcome(testCase, setup);
  expectFallbackOutcome(testCase, setup, sideEffects);
});

it('cancels its owned fallback without adding a notice', async () => {
  const {store, fallback} = await beginFallback();
  stopRequests?.();
  stopRequests = undefined;
  await flushFallbackMicrotasks();

  expect(fallback.init.signal?.aborted).toBe(true);
  expect(store.getSnapshot().snapshot?.sessions[0]?.activityNotice).toBeUndefined();
});

it('retains notices across metadata refreshes but clears them on newer activity', () => {
  const {snapshot, store, session} = scenarioWithNotice();

  store.session(snapshot.cursor + 1, {
    ...session,
    title: 'Refreshed metadata title',
    lastEventId: session.lastEventId + 1
  });
  expect(store.getSnapshot().snapshot?.sessions[0]?.activityNotice).toBe(TRANSFER_NOTICE);

  store.session(snapshot.cursor + 2, {
    ...session,
    lastEventId: session.lastEventId + 2,
    lastActivityEventId: (session.lastActivityEventId ?? 0) + 1
  });
  expect(store.getSnapshot().snapshot?.sessions[0]?.activityNotice).toBeUndefined();

  const refreshed = storedSession(store);
  store.activityNotice(snapshot.workspaceId, refreshed.sessionId, refreshed.lastEventId, TRANSFER_NOTICE);
  store.activity(snapshot.workspaceId, {...refreshed, state: 'running'});

  const resolved = storedSession(store);
  expect(resolved.state).toBe('running');
  expect(resolved.activityNotice).toBeUndefined();
});

it('marks all current batch members quietly when the oversized identity gets HTTP 413', async () => {
  const {store, requests, started} = scenario(['session-one', 'session-two']);
  await waitForStart(started, 0);
  requestAt(requests, 0).response.resolve(new Response('private response text', {status: 413}));
  await flushFallbackMicrotasks();

  expect(store.getSnapshot().snapshot?.sessions.map((session) => session.activityNotice)).toEqual([
    TRANSFER_NOTICE,
    TRANSFER_NOTICE
  ]);
  expect(requests).toHaveLength(1);
});
