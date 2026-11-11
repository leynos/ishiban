/** @file Check visible activity request lifecycles against generated operations. */
import {expect, it} from 'bun:test';
import {Schema} from 'effect';
import fc from 'fast-check';
import {waitFor} from '@testing-library/react';
import type {Session, Snapshot} from '../src/contracts';
import {createBoardStore, type BoardStore} from '../src/client';
import {createBoardSnapshot, firstSession} from './board-fixtures';
import {
  activityMarks,
  activityRequestAt as requestAt,
  installActivityFetch,
  resolveActivityBatch,
  type ActivityFetchFixture,
  type ActivityFetchRequest
} from './activity-fetch-fixture';
import {
  type ControlledIntersectionObserver,
  installControlledIntersectionObserver,
  startControlledActivity
} from './controlled-intersection-observer';

interface HistoryScenario {
  readonly count: number;
  readonly idWidth: number;
  readonly revisedIndex: number;
  readonly firstCompletion: 0 | 1;
  readonly visibilityHistory: 0 | 1 | 2;
  readonly revisionSlot: number;
}

interface LifecycleFixture {
  readonly sessions: Session[];
  readonly byId: ReadonlyMap<string, Session>;
  readonly snapshot: Snapshot;
  readonly store: BoardStore;
  readonly observer: ControlledIntersectionObserver;
  readonly fixture: ActivityFetchFixture;
  readonly marks: HTMLButtonElement[];
  readonly stop: () => void;
  readonly restoreObserver: () => void;
}

const RequestSchema = Schema.Struct({sessionIds: Schema.Array(Schema.String)});

/** Build valid raw IDs: sessionId(2, 3) includes three multibyte code points. */
function sessionId(index: number, width: number): string {
  return `${'😀'.repeat(width)}-activity-${index}`;
}

/** Seed unknown real sessions: sessionsFor(10, 1) yields ten distinct lookups. */
function sessionsFor(count: number, idWidth: number): Session[] {
  const template = firstSession(createBoardSnapshot());
  return Array.from({length: count}, (_, index) => ({
    ...template,
    sessionId: sessionId(index, idWidth),
    title: `Activity mark ${index}`,
    source: 'metadata',
    freshness: 'unavailable',
    state: 'unknown',
    lastEventId: 100 + index
  }));
}

/** Decode actual POST identities: requestIds(request) returns validated IDs. */
function requestIds(request: ActivityFetchRequest): readonly string[] {
  return Schema.decodeUnknownSync(RequestSchema)(JSON.parse(String(request.init.body))).sessionIds;
}

/** Resolve a whole batch: every requested baseline session has one running frame. */
function completeBatch(
  request: ActivityFetchRequest,
  sessions: ReadonlyMap<string, Session>,
  workspaceId: string
): void {
  const frames = requestIds(request).map((id) => {
    const session = sessions.get(id);
    if (!session) throw new Error(`A requested session ${id} needs a fixture.`);
    return {
      workspaceId,
      sessionId: id,
      session: {...session, state: 'running' as const, activitySource: 'lazy' as const}
    };
  });
  resolveActivityBatch(request, frames);
}

/** Assert transport bounds: each posted batch has at most four distinct valid IDs. */
function expectBoundedRequests(requests: readonly ActivityFetchRequest[]): void {
  for (const request of requests) {
    const ids = requestIds(request);
    expect(request.url).toBe('/api/v1/sessions/activity');
    expect(request.init.method).toBe('POST');
    expect(ids.length).toBeGreaterThan(0);
    expect(ids.length).toBeLessThanOrEqual(4);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new TextEncoder().encode(String(request.init.body)).length).toBeLessThanOrEqual(8192);
  }
}

/** Read one public store state: activityOf(store, id) is unknown before enrichment. */
function activityOf(store: BoardStore, id: string): Session['state'] | undefined {
  return store.getSnapshot().snapshot?.sessions.find((session) => session.sessionId === id)?.state;
}

/** Mount real marks: prepareLifecycle(10, 1) owns ten unknown visible candidates. */
function prepareLifecycle(count: number, idWidth: number): LifecycleFixture {
  const sessions = sessionsFor(count, idWidth);
  const byId = new Map(sessions.map((session) => [session.sessionId, session]));
  const baseline = createBoardSnapshot();
  const snapshot: Snapshot = {...baseline, workspaceId: 'lifecycle-workspace', sessions};
  const store = createBoardStore();
  store.replace(snapshot);
  const restoreObserver = installControlledIntersectionObserver();
  const fixture = installActivityFetch(6);
  const marks = activityMarks(sessions);
  const {observer, stop} = startControlledActivity(store);
  return {sessions, byId, snapshot, store, observer, fixture, marks, stop, restoreObserver};
}

/** Release one held batch and await a valid sibling's visible activity result. */
async function settleBatch(setup: LifecycleFixture, index: number, revisedId: string): Promise<void> {
  const request = requestAt(setup.fixture.requests, index);
  completeBatch(request, setup.byId, setup.snapshot.workspaceId);
  const settledId = requestIds(request).find((id) => id !== revisedId);
  if (!settledId) throw new Error('A batch needs a nonrevised sibling.');
  await waitFor(() => expect(activityOf(setup.store, settledId)).toBe('running'));
}

/** Require one started request without waiting on an unissued response. */
async function waitForBatch(fixture: ActivityFetchFixture, index: number): Promise<void> {
  const start = fixture.started[index];
  if (!start) throw new Error(`Activity batch ${index} needs a start gate.`);
  await start.promise;
}

/** Apply one generated prefix while both initial requests are held. */
function applyHistory(setup: LifecycleFixture, scenario: HistoryScenario) {
  const histories = [['hide'], ['hide', 'show', 'hide'], ['hide', 'show']] as const;
  const steps = histories[scenario.visibilityHistory];
  const last = setup.marks.at(-1);
  const revised = setup.sessions[scenario.revisedIndex];
  if (!last || !revised) throw new Error('The history needs one queued and one active session.');
  const revisionSlot = scenario.revisionSlot % (steps.length + 1);
  let isLastVisible = true;
  for (let position = 0; position <= steps.length; position += 1) {
    if (position === revisionSlot) {
      setup.store.session(setup.snapshot.cursor + 1, {...revised, lastEventId: revised.lastEventId + 1});
    }
    const step = steps[position];
    if (step) {
      isLastVisible = step === 'show';
      setup.observer.setVisibility(last, isLastVisible);
    }
  }
  return {revised, isLastVisible};
}

/** Derive expected eligibility from the visible queued marks and the revised active member. */
function eligibleRequests(setup: LifecycleFixture, revisedId: string, isLastVisible: boolean, firstCompletion: 0 | 1) {
  const queued = setup.sessions.slice(8);
  const last = queued.at(-1);
  if (!last) throw new Error('The history needs at least one queued mark.');
  const third = queued.filter((session) => isLastVisible || session !== last).map((session) => session.sessionId);
  const fourth: string[] = [];
  if (firstCompletion === 0) third.push(revisedId);
  else fourth.push(revisedId);
  if (!isLastVisible) fourth.push(last.sessionId);
  return {third, fourth};
}

/** Release the other initial request after the hidden mark has been rediscovered. */
async function finishHistory(
  setup: LifecycleFixture,
  result: ReturnType<typeof applyHistory>,
  firstCompletion: 0 | 1,
  fourthExpected: readonly string[]
): Promise<void> {
  if (!result.isLastVisible) {
    const last = setup.marks.at(-1);
    if (!last) throw new Error('The hidden mark must remain mounted.');
    setup.observer.setVisibility(last, true);
  }
  await settleBatch(setup, firstCompletion === 0 ? 1 : 0, result.revised.sessionId);
  await waitForBatch(setup.fixture, 3);
  expect(requestIds(requestAt(setup.fixture.requests, 3)).toSorted()).toEqual(fourthExpected.toSorted());
  expect(activityOf(setup.store, result.revised.sessionId)).toBe('unknown');
  expect(setup.store.getSnapshot().snapshot?.cursor).toBe(setup.snapshot.cursor + 1);
  expectBoundedRequests(setup.fixture.requests);
}

/** Compare real requests with the visible, still-unknown identities at each release. */
async function checkOperationHistory(scenario: HistoryScenario): Promise<void> {
  const setup = prepareLifecycle(scenario.count, scenario.idWidth);
  try {
    for (const mark of setup.marks) setup.observer.setVisibility(mark, true);
    await waitForBatch(setup.fixture, 1);
    expect(setup.fixture.requests).toHaveLength(2);
    const firstIds = setup.fixture.requests.flatMap((request) => requestIds(request));
    expect(firstIds).toEqual(setup.sessions.slice(0, 8).map((session) => session.sessionId));

    const result = applyHistory(setup, scenario);
    const firstCompletion = scenario.visibilityHistory === 2 ? 1 : scenario.firstCompletion;
    await settleBatch(setup, firstCompletion, result.revised.sessionId);
    await waitForBatch(setup.fixture, 2);
    const expected = eligibleRequests(setup, result.revised.sessionId, result.isLastVisible, firstCompletion);
    expect(requestIds(requestAt(setup.fixture.requests, 2))).toEqual(expected.third);
    await finishHistory(setup, result, firstCompletion, expected.fourth);
  } finally {
    setup.stop();
    setup.fixture.restore();
    setup.restoreObserver();
    document.body.replaceChildren();
  }
}

it.each([
  {count: 10, idWidth: 1, revisedIndex: 0, firstCompletion: 0, visibilityHistory: 0, revisionSlot: 0},
  {count: 12, idWidth: 240, revisedIndex: 3, firstCompletion: 1, visibilityHistory: 1, revisionSlot: 2},
  {count: 10, idWidth: 40, revisedIndex: 1, firstCompletion: 1, visibilityHistory: 2, revisionSlot: 1}
] as const)('settles a controlled activity history with $count marks', checkOperationHistory);

it('models visibility, revision and completion order across generated histories', async () => {
  const history = fc.record({
    count: fc.integer({min: 10, max: 12}),
    idWidth: fc.integer({min: 1, max: 240}),
    revisedIndex: fc.integer({min: 0, max: 3}),
    firstCompletion: fc.constantFrom(0 as const, 1 as const),
    visibilityHistory: fc.constantFrom(0 as const, 1 as const, 2 as const),
    revisionSlot: fc.integer({min: 0, max: 3})
  });
  await fc.assert(fc.asyncProperty(history, checkOperationHistory), {numRuns: 30});
});
