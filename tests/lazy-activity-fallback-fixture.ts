/** @file Describe bounded fallback outcomes shared by lazy-activity contract tests. */
import {expect} from 'bun:test';
import {waitFor} from '@testing-library/react';
import type {Session, Snapshot} from '../src/contracts';
import type {BoardStore} from '../src/client';
import type {ActivityFetchRequest} from './activity-fetch-fixture';

export const TRANSFER_NOTICE = 'Activity details exceed the transfer limit. Open the session in Lody.';

export interface FallbackContext {
  readonly snapshot: Snapshot;
  readonly store: BoardStore;
  readonly session: Session;
  readonly fallback: ActivityFetchRequest;
}

export interface FallbackSideEffects {
  wasCancelled: boolean;
}

export type FallbackCase =
  | {
      readonly name: string;
      readonly kind: 'success';
      readonly expectedState: 'running';
      readonly expectedNotice: undefined;
    }
  | {
      readonly name: string;
      readonly kind: 'oversized';
      readonly expectedState: 'unknown';
      readonly expectedNotice: string;
    }
  | {
      readonly name: string;
      readonly kind: 'invalid';
      readonly workspaceId: string;
      readonly sessionId: string;
      readonly revisionDelta: number;
      readonly expectedState: 'unknown';
      readonly expectedNotice: undefined;
    }
  | {
      readonly name: string;
      readonly kind: 'stale';
      readonly change: 'revision' | 'workspace';
      readonly expectedState: 'unknown';
      readonly expectedNotice: undefined;
    };

export const fallbackCases: readonly FallbackCase[] = [
  {
    name: 'accepts a 1.1 MiB single-session fallback response',
    kind: 'success',
    expectedState: 'running',
    expectedNotice: undefined
  },
  {
    name: 'shows a quiet bounded-transfer notice when the fallback exceeds 8 MiB',
    kind: 'oversized',
    expectedState: 'unknown',
    expectedNotice: TRANSFER_NOTICE
  },
  {
    name: 'ignores a foreign fallback workspace without a transfer notice',
    kind: 'invalid',
    workspaceId: 'foreign-workspace',
    sessionId: 'large-session',
    revisionDelta: 0,
    expectedState: 'unknown',
    expectedNotice: undefined
  },
  {
    name: 'ignores a foreign fallback session without a transfer notice',
    kind: 'invalid',
    workspaceId: 'fallback-workspace',
    sessionId: 'foreign-session',
    revisionDelta: 0,
    expectedState: 'unknown',
    expectedNotice: undefined
  },
  {
    name: 'ignores a future fallback revision without a transfer notice',
    kind: 'invalid',
    workspaceId: 'fallback-workspace',
    sessionId: 'large-session',
    revisionDelta: 1,
    expectedState: 'unknown',
    expectedNotice: undefined
  },
  {
    name: 'does not attach a late failure after a revision change',
    kind: 'stale',
    change: 'revision',
    expectedState: 'unknown',
    expectedNotice: undefined
  },
  {
    name: 'does not attach a late failure after a workspace change',
    kind: 'stale',
    change: 'workspace',
    expectedState: 'unknown',
    expectedNotice: undefined
  }
];

/**
 * Apply the stale request's competing update; for example, advance only session revision.
 * @param testCase Named fallback scenario whose response is now stale.
 * @param setup Current board and held fallback request.
 * @returns Nothing; the store is advanced before the request is released.
 * @example
 * applyStaleFallbackChange(revisionChangeCase, setup);
 */
export function applyStaleFallbackChange(testCase: FallbackCase, setup: FallbackContext): void {
  if (testCase.kind !== 'stale') return;
  if (testCase.change === 'revision') {
    setup.store.session(setup.snapshot.cursor + 1, {
      ...setup.session,
      lastEventId: setup.session.lastEventId + 1
    });
  } else {
    setup.store.replace({...setup.snapshot, workspaceId: 'new-workspace'});
  }
}

/**
 * Build each fallback wire result; for example, return a different-session projection.
 * @param testCase The named valid, oversized, invalid, or stale response case.
 * @param setup Current board and request identities.
 * @param sideEffects Mutable facts observed by the transport test.
 * @returns The HTTP response that the held fallback request receives.
 * @example
 * const response = fallbackResponseFor(fallbackCases[0]!, setup, sideEffects);
 */
export function fallbackResponseFor(
  testCase: FallbackCase,
  setup: FallbackContext,
  sideEffects: FallbackSideEffects
): Response {
  if (testCase.kind === 'success') {
    return singleResponse(setup.snapshot.workspaceId, {
      ...setup.session,
      title: 'x'.repeat(1_100_000),
      state: 'running'
    });
  }
  if (testCase.kind === 'oversized') return oversizedFallbackResponse(sideEffects);
  if (testCase.kind === 'invalid') {
    return singleResponse(testCase.workspaceId, {
      ...setup.session,
      sessionId: testCase.sessionId,
      state: 'running',
      lastEventId: setup.session.lastEventId + testCase.revisionDelta
    });
  }
  return new Response('unavailable', {status: 503});
}

/** Drain short-lived failure handlers before checking cases without a success-state transition. */
function shouldDrainMicrotasksBeforeAssertion(testCase: FallbackCase): boolean {
  return testCase.kind === 'stale' || testCase.kind === 'invalid';
}

/**
 * Wait for the expected observable fallback result; stale replies only need to settle.
 * @param testCase Expected store outcome for this fallback response.
 * @param setup Current board and fallback request.
 * @returns Completion when the state is visible or stale handling has settled.
 * @example
 * await waitForFallbackOutcome(fallbackCases[0]!, setup);
 */
export async function waitForFallbackOutcome(testCase: FallbackCase, setup: FallbackContext): Promise<void> {
  return shouldDrainMicrotasksBeforeAssertion(testCase)
    ? flushFallbackMicrotasks()
    : waitFor(() => expectFallbackState(testCase, setup));
}

/** Assert session state and notice for one fallback case. */
function expectFallbackState(testCase: FallbackCase, setup: FallbackContext): void {
  const actual = storedSession(setup.store);
  expect(actual.state).toBe(testCase.expectedState);
  expect(actual.activityNotice).toBe(testCase.expectedNotice);
}

/**
 * Keep returned evidence intact while checking the special bound under test.
 * @param testCase Expected visible outcome.
 * @param setup Original session projection and current board.
 * @param sideEffects Transport effects recorded while reading the response.
 * @returns Nothing if all session and transport assertions pass.
 * @example
 * expectFallbackOutcome(fallbackCases[1]!, setup, sideEffects);
 */
export function expectFallbackOutcome(
  testCase: FallbackCase,
  setup: FallbackContext,
  sideEffects: FallbackSideEffects
): void {
  const actual = storedSession(setup.store);
  expectFallbackState(testCase, setup);
  expect(actual.latestTurn).toEqual(setup.session.latestTurn);
  if (testCase.kind === 'invalid') expect(actual.lastEventId).toBe(setup.session.lastEventId);
  if (testCase.kind === 'success') expect(actual.title.length).toBeGreaterThan(1_000_000);
  if (testCase.kind === 'oversized') {
    expect(actual.lastEventId).toBe(setup.session.lastEventId);
    expect(storedSnapshot(setup.store).cursor).toBe(setup.snapshot.cursor);
    expect(sideEffects.wasCancelled).toBe(true);
  }
}

/**
 * Read the current test snapshot; for example, confirm the journal cursor stayed fixed.
 * @param store The test board store.
 * @returns Its current snapshot.
 * @throws {Error} When no snapshot has been installed.
 * @example
 * const cursor = storedSnapshot(store).cursor;
 */
export function storedSnapshot(store: BoardStore): Snapshot {
  const snapshot = store.getSnapshot().snapshot;
  if (!snapshot) throw new Error('The activity store must contain its test snapshot.');
  return snapshot;
}

/**
 * Read the first current test session without optional assertions.
 * @param store The test board store.
 * @returns Its first current session.
 * @throws {Error} When the snapshot or first session is absent.
 * @example
 * const state = storedSession(store).state;
 */
export function storedSession(store: BoardStore): Session {
  const session = storedSnapshot(store).sessions[0];
  if (!session) throw new Error('The activity store must contain a test session.');
  return session;
}

/**
 * Drain deterministic continuations without introducing a timer race.
 * @returns Completion after the scheduled promise continuations have run.
 * @example
 * await flushFallbackMicrotasks();
 */
export async function flushFallbackMicrotasks(): Promise<void> {
  for (let index = 0; index < 12; index += 1) await Promise.resolve();
}

/** Encode one full single-session activity response. */
function singleResponse(workspaceId: string, session: Session): Response {
  return Response.json({workspaceId, session});
}

/** Make the over-budget body cancellation observable to the regression case. */
function oversizedFallbackResponse(sideEffects: FallbackSideEffects): Response {
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new Uint8Array(8_388_609));
      },
      cancel() {
        sideEffects.wasCancelled = true;
      }
    })
  );
}
