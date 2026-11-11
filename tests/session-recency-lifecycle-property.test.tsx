/** @file Exercise recency ownership across generated viewport and response histories. */
import {expect, it} from 'bun:test';
import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import fc from 'fast-check';
import type {Snapshot} from '../src/contracts';
import {useSessionRecency} from '../src/session-recency';
import type {RecencyFact} from '../src/session-families';
import {createFamilySnapshot} from './board-fixtures';
import {deferred, type Deferred} from './deferred';
import {availableRecencyResponse, installFamilyBrowser, installFamilyMarks} from './family-browser-fixture';

type Operation =
  | 'hide-0'
  | 'show-0'
  | 'hide-1'
  | 'show-1'
  | 'revise-0'
  | 'revise-1'
  | 'switch-workspace'
  | 'resolve-first'
  | 'resolve-second'
  | 'resolve-newest';

interface HeldRequest {
  readonly workspaceId: string;
  readonly ids: readonly string[];
  readonly revisions: ReadonlyMap<string, number>;
  readonly latestHistoryAt: string;
  readonly gate: Deferred<Response>;
  isResolved: boolean;
}

interface ScenarioState {
  snapshot: Snapshot;
  readonly visible: boolean[];
  readonly expected: Map<string, string>;
  readonly requests: HeldRequest[];
  readonly requestEligibility: ReadonlySet<string>[];
}

interface ScenarioDriver extends ScenarioState {
  readonly marks: readonly HTMLButtonElement[];
  readonly browser: ReturnType<typeof installFamilyBrowser>;
  readonly rerender: (props: {current: Snapshot}) => void;
  readonly readFacts: () => ReturnType<typeof useSessionRecency>['facts'];
}

const familyIds = [
  ['root-0', 'child-0'],
  ['root-1', 'child-1']
] as const;

/** Model the public admission rule from fixture parent links, not the hook's queue. */
function admittedIds(isVisible: readonly boolean[]): ReadonlySet<string> {
  return new Set(familyIds.flatMap((ids, index) => (isVisible[index] ? ids : [])));
}

/** Read current execution bases from the raw snapshot supplied to the hook. */
function revisionsOf(snapshot: Snapshot): ReadonlyMap<string, number> {
  return new Map(snapshot.sessions.map((session) => [session.sessionId, session.lastActivityEventId ?? 0]));
}

/** Check both the published facts and each submitted request against the model. */
function checkCurrent(
  facts: ReadonlyMap<string, RecencyFact>,
  expected: ReadonlyMap<string, string>,
  requests: readonly HeldRequest[],
  requestEligibility: readonly ReadonlySet<string>[]
): void {
  expect(new Set(facts.keys())).toEqual(new Set(expected.keys()));
  for (const [id, latestHistoryAt] of expected) {
    const fact = facts.get(id);
    expect(fact?.outcome).toBe('available');
    if (fact?.outcome === 'available') expect(fact.latestHistoryAt).toBe(latestHistoryAt);
  }
  for (const [index, request] of requests.entries()) {
    const eligible = requestEligibility[index];
    expect(eligible).toBeDefined();
    expect(request.ids.length).toBeGreaterThan(0);
    expect(request.ids.every((id) => eligible?.has(id))).toBe(true);
  }
}

/** Read a generated root suffix without conflating response and viewport actions. */
function familyIndex(operation: Operation): number {
  const index = Number(operation.at(-1));
  if (index !== 0 && index !== 1) throw new Error(`Operation ${operation} does not name a family.`);
  return index;
}

/** Report the viewport transition to the real observer and independent model. */
function setVisibility(driver: ScenarioDriver, operation: Operation, isVisible: boolean): void {
  const index = familyIndex(operation);
  const mark = driver.marks[index];
  if (!mark) throw new Error('The generated family must have a mark.');
  driver.visible[index] = isVisible;
  act(() => driver.browser.visibility(mark, isVisible));
}

/** Change one child execution basis without rebuilding its family identity. */
function reviseExecution(driver: ScenarioDriver, operation: Operation): void {
  const childId = `child-${familyIndex(operation)}`;
  driver.snapshot = {
    ...driver.snapshot,
    sessions: driver.snapshot.sessions.map((session) =>
      session.sessionId === childId
        ? {...session, lastActivityEventId: (session.lastActivityEventId ?? 0) + 1}
        : session
    )
  };
  driver.expected.delete(childId);
  driver.rerender({current: driver.snapshot});
}

/** A workspace change creates a new recency owner with no admitted marks. */
function switchWorkspace(driver: ScenarioDriver): void {
  if (driver.snapshot.workspaceId === 'second-workspace') return;
  driver.snapshot = {...driver.snapshot, workspaceId: 'second-workspace'};
  driver.visible.fill(false);
  driver.expected.clear();
  driver.rerender({current: driver.snapshot});
}

/** Select a held network result without assuming requests complete in order. */
function requestFor(driver: ScenarioDriver, operation: Operation): HeldRequest | undefined {
  const fixedIndex: Partial<Record<Operation, number>> = {'resolve-first': 0, 'resolve-second': 1};
  const index = fixedIndex[operation];
  return index === undefined ? driver.requests.findLast((request) => !request.isResolved) : driver.requests[index];
}

/** Admit a completed member only when its original identity still has authority. */
function accepts(driver: ScenarioDriver, request: HeldRequest, id: string): boolean {
  if (request.workspaceId !== driver.snapshot.workspaceId) return false;
  if (!admittedIds(driver.visible).has(id)) return false;
  return request.revisions.get(id) === revisionsOf(driver.snapshot).get(id);
}

/** Build a response whose second pull witnesses consumption of all newline frames. */
async function consumedResponse(
  driver: ScenarioDriver,
  request: HeldRequest
): Promise<{
  response: Response;
  hasConsumed: () => boolean;
}> {
  const responseSnapshot = {
    ...driver.snapshot,
    workspaceId: request.workspaceId,
    sessions: driver.snapshot.sessions.map((session) => ({
      ...session,
      lastActivityEventId: request.revisions.get(session.sessionId) ?? 0
    }))
  };
  const payload = await availableRecencyResponse(responseSnapshot, request.ids, request.latestHistoryAt).text();
  const bytes = new TextEncoder().encode(payload);
  let isConsumed = false;
  let isSent = false;
  const body = new ReadableStream<Uint8Array>(
    {
      pull(controller) {
        if (isSent) {
          // The next read follows frame application, including discarded facts.
          isConsumed = true;
          controller.close();
          return;
        }
        isSent = true;
        controller.enqueue(bytes);
      }
    },
    {highWaterMark: 0}
  );
  return {response: new Response(body), hasConsumed: () => isConsumed};
}

/** Resolve one network request and wait until the real hook consumes its frames. */
async function resolveRequest(driver: ScenarioDriver, operation: Operation): Promise<void> {
  const request = requestFor(driver, operation);
  if (!request || request.isResolved) return;
  request.isResolved = true;
  for (const id of request.ids) {
    if (accepts(driver, request, id)) driver.expected.set(id, request.latestHistoryAt);
  }
  const {response, hasConsumed} = await consumedResponse(driver, request);
  await act(async () => request.gate.resolve(response));
  await waitFor(() => expect(hasConsumed()).toBe(true));
}

/** Apply one generated external event to the model and actual browser hook. */
async function applyOperation(driver: ScenarioDriver, operation: Operation): Promise<void> {
  if (operation.startsWith('show-')) return setVisibility(driver, operation, true);
  if (operation.startsWith('hide-')) return setVisibility(driver, operation, false);
  if (operation.startsWith('revise-')) return reviseExecution(driver, operation);
  if (operation === 'switch-workspace') return switchWorkspace(driver);
  await resolveRequest(driver, operation);
}

/** Run the real hook while the model changes only on external operations. */
async function verifyHistory(
  operations: readonly Operation[],
  expectedFinalFacts?: number,
  shouldResumeInSecondWorkspace = false
): Promise<void> {
  const state: ScenarioState = {
    snapshot: createFamilySnapshot(2, 'first-workspace'),
    visible: [false, false],
    expected: new Map(),
    requests: [],
    requestEligibility: []
  };
  const marks = installFamilyMarks(2);
  const browser = installFamilyBrowser(async (_input, init) => {
    const ids: string[] = JSON.parse(String(init?.body)).sessionIds;
    state.requestEligibility.push(admittedIds(state.visible));
    const gate = deferred<Response>();
    const latestHistoryAt = new Date(Date.UTC(2026, 10, 10, 0, 0, state.requests.length)).toISOString();
    state.requests.push({
      workspaceId: state.snapshot.workspaceId,
      ids,
      revisions: revisionsOf(state.snapshot),
      latestHistoryAt,
      gate,
      isResolved: false
    });
    return gate.promise;
  });
  try {
    const {result, rerender} = renderHook(({current}) => useSessionRecency(current), {
      initialProps: {current: state.snapshot}
    });
    const driver: ScenarioDriver = Object.assign(state, {
      marks,
      browser,
      rerender,
      readFacts: () => result.current.facts
    });
    for (const [index, mark] of marks.entries()) {
      driver.visible[index] = true;
      act(() => browser.visibility(mark, true));
    }
    await waitFor(() => expect(driver.requests.length).toBe(2));

    for (const operation of operations) {
      await applyOperation(driver, operation);
      await waitFor(() =>
        checkCurrent(driver.readFacts(), driver.expected, driver.requests, driver.requestEligibility)
      );
    }
    if (expectedFinalFacts !== undefined) expect(driver.readFacts().size).toBe(expectedFinalFacts);
    if (shouldResumeInSecondWorkspace) {
      expect(driver.requests.some((request) => request.workspaceId === 'second-workspace')).toBe(true);
    }
  } finally {
    cleanup();
    for (const request of state.requests) {
      if (!request.isResolved) request.gate.resolve(new Response('', {status: 503}));
    }
    browser.restore();
    document.body.replaceChildren();
  }
}

const operation = fc.constantFrom<Operation>(
  'hide-0',
  'show-0',
  'hide-1',
  'show-1',
  'revise-0',
  'revise-1',
  'switch-workspace',
  'resolve-first',
  'resolve-second',
  'resolve-newest'
);

const lifecycleHistory = fc
  .tuple(
    fc.shuffledSubarray<Operation>(
      [
        'hide-0',
        'show-0',
        'revise-0',
        'switch-workspace',
        'show-1',
        'resolve-first',
        'resolve-second',
        'resolve-newest'
      ],
      {minLength: 8, maxLength: 8}
    ),
    fc.array(operation, {maxLength: 3})
  )
  .map(([required, extra]) => [...required, ...extra]);

it('keeps current recency facts scoped through generated viewport, revision and response orderings', async () => {
  await verifyHistory(['resolve-second', 'resolve-first'], 4);
  await verifyHistory(['hide-0', 'resolve-second', 'resolve-first', 'show-0', 'revise-1'], 1);
  await verifyHistory(['switch-workspace', 'show-1', 'resolve-second', 'resolve-first', 'resolve-newest'], 2, true);
  await verifyHistory(['switch-workspace', 'show-0', 'resolve-newest', 'resolve-first'], 2, true);
  await fc.assert(
    fc.asyncProperty(lifecycleHistory, async (history) => {
      await verifyHistory(history);
    }),
    {
      numRuns: 35
    }
  );
}, 60_000);
