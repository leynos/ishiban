/** @file Keep visible history reads bounded when catalogue families grow. */
import {afterEach, expect, it} from 'bun:test';
import {act, cleanup, render, renderHook, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type {Session, Snapshot} from '../src/contracts';
import {useSessionRecency, type RecencyState} from '../src/session-recency';
import {groupSessions, type SessionFamily} from '../src/session-families';
import {Board} from '../src/ui/board';
import {createFamilySnapshot} from './board-fixtures';
import {installFamilyBrowser, installFamilyMarks} from './family-browser-fixture';
import {deferred, type Deferred} from './deferred';

let browser: ReturnType<typeof installFamilyBrowser> | undefined;

/** Build raw tab chains of the requested sizes without changing their root context. */
function largeFamilies(memberCounts: readonly number[]): Snapshot {
  const baseline = createFamilySnapshot(memberCounts.length);
  const sessions: Session[] = [];
  for (const [familyIndex, count] of memberCounts.entries()) {
    const root = baseline.sessions.find((session) => session.sessionId === `root-${familyIndex}`);
    const child = baseline.sessions.find((session) => session.sessionId === `child-${familyIndex}`);
    if (!root || !child) throw new Error('Each large family needs root and child templates.');
    sessions.push(root, child);
    for (let memberIndex = 2; memberIndex < count; memberIndex += 1) {
      sessions.push({...child, sessionId: `child-${familyIndex}-${memberIndex}`});
    }
  }
  return {...baseline, sessions};
}

/** Keep one B child running while making all other B members idle. */
function warmFamilySnapshot(): Snapshot {
  const baseline = largeFamilies([300, 300]);
  return {
    ...baseline,
    sessions: baseline.sessions.map((session) => {
      if (session.parentSessionId !== 'root-1') return session;
      if (session.sessionId === 'child-1') return session;
      return {...session, state: 'idle' as const};
    })
  };
}

/** Return one schema-valid frame per requested raw member. */
function available(
  snapshot: Snapshot,
  sessionIds: readonly string[],
  historyTimes: ReadonlyMap<string, string> = new Map()
): Response {
  const frames = sessionIds.map((sessionId) => {
    const session = snapshot.sessions.find((member) => member.sessionId === sessionId);
    if (!session) throw new Error(`Unknown request member ${sessionId}.`);
    return JSON.stringify({
      workspaceId: snapshot.workspaceId,
      sessionId,
      lastActivityEventId: session.lastActivityEventId ?? 0,
      outcome: 'available',
      latestHistoryAt: historyTimes.get(sessionId) ?? session.createdAt
    });
  });
  return new Response(`${frames.join('\n')}\n`);
}

/** Derive generated family membership from raw parent links, independent of ID spelling. */
function familyMemberIds(snapshot: Snapshot, rootId: string): ReadonlySet<string> {
  return new Set(
    snapshot.sessions
      .filter((member) => member.sessionId === rootId || member.parentSessionId === rootId)
      .map((member) => member.sessionId)
  );
}

/** Require a generated mark before changing its viewport state. */
function familyMarkAt(marks: readonly HTMLButtonElement[], index = 0): HTMLButtonElement {
  const mark = marks[index];
  if (!mark) throw new Error(`The family fixture must provide mark ${index}.`);
  return mark;
}

/** Require one named family in the current recency projection. */
function familyAt(snapshot: Snapshot, state: RecencyState, rootId: string): SessionFamily {
  const family = groupSessions(snapshot.sessions, state.facts, state.limitedRoots).find(
    (item) => item.rootId === rootId
  );
  if (!family) throw new Error(`The recency fixture must contain family ${rootId}.`);
  return family;
}

afterEach(() => {
  cleanup();
  browser?.restore();
  browser = undefined;
  document.body.replaceChildren();
});

it('reports a 513-tab family as incomplete without starting an unfinishable sweep', async () => {
  const snapshot = largeFamilies([513]);
  const marks = installFamilyMarks(1);
  const mark = familyMarkAt(marks);
  const requests: string[][] = [];
  browser = installFamilyBrowser(async (_input, init) => {
    requests.push(JSON.parse(String(init?.body)).sessionIds);
    return new Promise<Response>(() => {});
  });
  const {result} = renderHook(() => useSessionRecency(snapshot));
  act(() => browser?.visibility(mark, true));
  expect(requests).toEqual([]);
  await waitFor(() => expect(result.current.limitedRoots.has('root-0')).toBe(true));
  expect(result.current.facts.size).toBe(0);
});

it('explains the provisional tab when its family cannot fit the lookup budget', async () => {
  const snapshot = largeFamilies([513]);
  browser = installFamilyBrowser(async () => {
    throw new Error('A non-admitted family must not submit a metadata request.');
  });
  const user = userEvent.setup();
  render(<Board connection="Connected" snapshot={snapshot} />);
  const mark = screen.getByRole('button', {name: /Root planning work; Refine; running/u});
  act(() => browser?.visibility(mark, true));
  await user.click(mark);
  expect(
    screen.getByText(/cannot fit within the visible tab lookup budget.*selected tab is provisional/iu)
  ).toBeTruthy();
});

it('admits complete families within the shared budget and releases it on hide', async () => {
  const snapshot = largeFamilies([300, 300]);
  const firstFamilyIds = familyMemberIds(snapshot, 'root-0');
  const secondFamilyIds = familyMemberIds(snapshot, 'root-1');
  const marks = installFamilyMarks(2);
  const firstMark = familyMarkAt(marks);
  const requests: string[][] = [];
  browser = installFamilyBrowser(async (_input, init) => {
    const ids: string[] = JSON.parse(String(init?.body)).sessionIds;
    requests.push(ids);
    return available(snapshot, ids);
  });
  const {result} = renderHook(() => useSessionRecency(snapshot));
  for (const mark of marks) act(() => browser?.visibility(mark, true));
  await waitFor(() => expect(result.current.facts.size).toBe(300), {timeout: 10_000});
  expect(result.current.limitedRoots.has('root-1')).toBe(true);
  expect(requests.flat().every((id) => firstFamilyIds.has(id))).toBe(true);
  const completed = requests.length;
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(requests.length).toBe(completed);

  act(() => browser?.visibility(firstMark, false));
  await waitFor(() => expect(requests.flat().some((id) => secondFamilyIds.has(id))).toBe(true), {
    timeout: 10_000
  });
  expect(result.current.limitedRoots.has('root-1')).toBe(false);
  await waitFor(
    () =>
      expect([...result.current.facts.keys()].filter((id) => secondFamilyIds.has(id)).length).toBe(
        secondFamilyIds.size
      ),
    {timeout: 10_000}
  );
  expect(result.current.facts.size).toBe(512);
  const families = groupSessions(snapshot.sessions, result.current.facts, result.current.limitedRoots);
  expect(families.find((family) => family.rootId === 'root-0')?.recencyIncomplete).toBe(true);
  expect(families.find((family) => family.rootId === 'root-1')?.recencyIncomplete).toBe(false);
});

it('ignores an in-flight family after its slot transfers to another visible family', async () => {
  const snapshot = largeFamilies([300, 300]);
  const secondFamilyIds = familyMemberIds(snapshot, 'root-1');
  const marks = installFamilyMarks(2);
  const firstMark = familyMarkAt(marks);
  const requests: string[][] = [];
  const gates: Deferred<Response>[] = [];
  browser = installFamilyBrowser(async (_input, init) => {
    requests.push(JSON.parse(String(init?.body)).sessionIds);
    const gate = deferred<Response>();
    gates.push(gate);
    return gate.promise;
  });
  const {result} = renderHook(() => useSessionRecency(snapshot));
  for (const mark of marks) act(() => browser?.visibility(mark, true));
  await waitFor(() => expect(gates.length).toBe(2));
  expect(result.current.limitedRoots.has('root-1')).toBe(true);

  act(() => browser?.visibility(firstMark, false));
  expect(result.current.limitedRoots.has('root-1')).toBe(false);
  await act(async () => gates[0]?.resolve(available(snapshot, requests[0] ?? [])));
  expect(result.current.facts.size).toBe(0);
  await waitFor(() => expect(gates.length).toBe(3));
  expect(requests[2]?.every((id) => secondFamilyIds.has(id))).toBe(true);
});

it('prefers a warm limited family running tab until lookup capacity returns', async () => {
  const snapshot = warmFamilySnapshot();
  const warmFamilyIds = familyMemberIds(snapshot, 'root-1');
  const historyTimes = new Map([
    ['root-1', '2026-11-10T18:41:02.707Z'],
    ['child-1', '2026-11-03T22:05:49.972Z']
  ]);
  const marks = installFamilyMarks(2);
  const firstMark = familyMarkAt(marks);
  const secondMark = familyMarkAt(marks, 1);
  const heldFirstFamily: Deferred<Response>[] = [];
  const requests: string[][] = [];
  browser = installFamilyBrowser(async (_input, init) => {
    const ids: string[] = JSON.parse(String(init?.body)).sessionIds;
    requests.push(ids);
    if (ids.every((id) => warmFamilyIds.has(id))) return available(snapshot, ids, historyTimes);
    const gate = deferred<Response>();
    heldFirstFamily.push(gate);
    return gate.promise;
  });
  const {result} = renderHook(() => useSessionRecency(snapshot));
  act(() => browser?.visibility(secondMark, true));
  await waitFor(() => expect([...result.current.facts.keys()].filter((id) => warmFamilyIds.has(id)).length).toBe(300), {
    timeout: 10_000
  });
  expect(familyAt(snapshot, result.current, 'root-1').activity.sessionId).toBe('root-1');
  const warmRequestCount = requests.length;

  act(() => browser?.visibility(firstMark, true));
  await waitFor(() => expect(result.current.limitedRoots.has('root-1')).toBe(true));
  await waitFor(() => expect(heldFirstFamily.length).toBe(2));
  expect([...result.current.facts.keys()].filter((id) => warmFamilyIds.has(id))).toHaveLength(300);
  const limited = familyAt(snapshot, result.current, 'root-1');
  expect(limited.recencyIncomplete).toBe(true);
  expect(limited.activity.sessionId).toBe('child-1');

  act(() => browser?.visibility(firstMark, false));
  await waitFor(() => expect(result.current.limitedRoots.has('root-1')).toBe(false));
  const recovered = familyAt(snapshot, result.current, 'root-1');
  expect(recovered.recencyIncomplete).toBe(false);
  expect(recovered.activity.sessionId).toBe('root-1');
  expect(requests.filter((ids) => ids.every((id) => warmFamilyIds.has(id))).length).toBe(warmRequestCount);
});
