/** @file Verify visible-family recency ownership across scope and viewport changes. */
import {afterEach, expect, it, setSystemTime} from 'bun:test';
import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import type {Snapshot} from '../src/contracts';
import {useSessionRecency} from '../src/session-recency';
import {groupSessions, type RecencyFact, type SessionFamily} from '../src/session-families';
import {createFamilySnapshot} from './board-fixtures';
import {installFamilyBrowser, installFamilyMarks} from './family-browser-fixture';
import {deferred, type Deferred} from './deferred';

let browser: ReturnType<typeof installFamilyBrowser> | undefined;

/** Hold real fetch promises so request ownership can be inspected before completion. */
function installPendingFetch() {
  const requests: string[][] = [];
  const gates: Deferred<Response>[] = [];
  const controlled = async (_input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const body = JSON.parse(String(init?.body));
    requests.push(body.sessionIds);
    const gate = deferred<Response>();
    gates.push(gate);
    return gate.promise;
  };
  browser = installFamilyBrowser(controlled);
  return {requests, gates};
}

/** Deliver one successful member with a timestamp chosen by the test. */
function availableFrame(snapshot: Snapshot, sessionId: string, time: string): Response {
  const session = snapshot.sessions.find((member) => member.sessionId === sessionId);
  if (!session) throw new Error(`Expected ${sessionId} in the fixture catalogue.`);
  return new Response(
    `${JSON.stringify({
      workspaceId: snapshot.workspaceId,
      sessionId,
      lastActivityEventId: session.lastActivityEventId ?? 0,
      outcome: 'available',
      latestHistoryAt: time
    })}\n`
  );
}

/** Require a family after projecting current recency into the fixture catalogue. */
function currentFamily(snapshot: Snapshot, facts: ReadonlyMap<string, RecencyFact>): SessionFamily {
  const family = groupSessions(snapshot.sessions, facts)[0];
  if (!family) throw new Error('The refresh fixture must keep its linked family.');
  return family;
}

/** Require one held recency request before advancing its response. */
function requestGate(network: ReturnType<typeof installPendingFetch>, index: number): Deferred<Response> {
  const gate = network.gates[index];
  if (!gate) throw new Error(`The refresh fixture must start request ${index}.`);
  return gate;
}

afterEach(() => {
  cleanup();
  browser?.restore();
  browser = undefined;
  document.body.replaceChildren();
});

it('does not publish a previous workspace response for matching raw session IDs', async () => {
  const marks = installFamilyMarks(1);
  const network = installPendingFetch();
  const initial = createFamilySnapshot(1, 'first-workspace');
  const {result, rerender} = renderHook(({snapshot}) => useSessionRecency(snapshot), {
    initialProps: {snapshot: initial}
  });
  act(() => browser?.visibility(marks[0]!, true));
  await waitFor(() => expect(network.requests.length).toBe(1));
  const later = createFamilySnapshot(1, 'second-workspace');
  rerender({snapshot: later});
  await act(async () => {
    network.gates[0]?.resolve(availableFrame(initial, 'root-0', '2026-11-10T18:41:02.707Z'));
  });
  expect(result.current.facts.size).toBe(0);
});

it('ignores foreign members while retaining a later valid sibling', async () => {
  const marks = installFamilyMarks(1);
  const network = installPendingFetch();
  const snapshot = createFamilySnapshot(1);
  const {result} = renderHook(() => useSessionRecency(snapshot));
  act(() => browser?.visibility(marks[0]!, true));
  await waitFor(() => expect(network.requests.length).toBe(1));
  const valid = await availableFrame(snapshot, 'child-0', '2026-11-10T18:41:02.707Z').text();
  const foreign = valid.replace(snapshot.workspaceId, 'other-workspace').replace('child-0', 'root-0');
  await act(async () => {
    network.gates[0]?.resolve(new Response(`${foreign}${valid}`));
  });
  await waitFor(() => expect(result.current.facts.get('child-0')?.outcome).toBe('available'));
  expect(result.current.facts.get('root-0')?.outcome).toBe('unavailable');
});

it('rejects a late member after its execution watermark advances', async () => {
  let now = Date.now();
  setSystemTime(now);
  try {
    const marks = installFamilyMarks(1);
    const network = installPendingFetch();
    const initial = createFamilySnapshot(1);
    const {result, rerender} = renderHook(({snapshot}) => useSessionRecency(snapshot), {
      initialProps: {snapshot: initial}
    });
    act(() => browser?.visibility(marks[0]!, true));
    await waitFor(() => expect(network.requests.length).toBe(1));
    const next = {
      ...initial,
      sessions: initial.sessions.map((session) =>
        session.sessionId === 'child-0' ? {...session, lastActivityEventId: 17} : session
      )
    };
    rerender({snapshot: next});
    await act(async () => {
      network.gates[0]?.resolve(availableFrame(initial, 'child-0', '2026-11-10T18:41:02.707Z'));
    });
    expect(result.current.facts.get('child-0')?.outcome).not.toBe('available');
    expect(network.requests.length).toBe(1);
    now += 30_001;
    setSystemTime(now);
    rerender({snapshot: {...next}});
    await waitFor(() => expect(network.requests.length).toBe(2));
  } finally {
    setSystemTime();
  }
});

it('drops a queued family after its mark leaves the viewport', async () => {
  const marks = installFamilyMarks(4);
  const network = installPendingFetch();
  const snapshot = createFamilySnapshot(4);
  renderHook(() => useSessionRecency(snapshot));
  for (const mark of marks) act(() => browser?.visibility(mark, true));
  await waitFor(() => expect(network.requests.length).toBe(2));
  act(() => browser?.visibility(marks[2]!, false));
  await act(async () => {
    const child = await availableFrame(snapshot, 'child-0', '2026-11-10T18:41:02.707Z').text();
    const root = await availableFrame(snapshot, 'root-0', '2026-11-03T22:05:49.972Z').text();
    network.gates[0]?.resolve(new Response(child + root));
  });
  await waitFor(() => expect(network.requests.length).toBe(3));
  expect(network.requests[2]).toEqual(['child-3', 'root-3']);
});

it('makes an expired winner provisional through failed refresh and conclusive recovery', async () => {
  let now = Date.now();
  setSystemTime(now);
  try {
    const marks = installFamilyMarks(1);
    const mark = marks[0];
    if (!mark) throw new Error('The refresh fixture needs one visible family mark.');
    const network = installPendingFetch();
    const snapshot = createFamilySnapshot(1);
    const {result, rerender} = renderHook(({current}) => useSessionRecency(current), {
      initialProps: {current: snapshot}
    });
    act(() => browser?.visibility(mark, true));
    await waitFor(() => expect(network.gates.length).toBe(1));
    const oldRoot = '2026-11-10T18:41:02.707Z';
    const oldChild = '2026-11-03T22:05:49.972Z';
    const root = await availableFrame(snapshot, 'root-0', oldRoot).text();
    const child = await availableFrame(snapshot, 'child-0', oldChild).text();
    const successfulBody = root + child;
    await act(async () => requestGate(network, 0).resolve(new Response(successfulBody)));
    await waitFor(() => expect(result.current.facts.get('root-0')?.outcome).toBe('available'));
    expect(currentFamily(snapshot, result.current.facts).activity.sessionId).toBe('root-0');

    now += 300_001;
    setSystemTime(now);
    rerender({current: {...snapshot}});
    await waitFor(() => expect(network.gates.length).toBe(2));
    expect(result.current.facts.get('root-0')).toEqual({outcome: 'pending', lastKnownHistoryAt: oldRoot});
    const pending = currentFamily(snapshot, result.current.facts);
    expect(pending.activity.sessionId).toBe('child-0');
    expect(pending.recencyIncomplete).toBe(true);

    await act(async () => requestGate(network, 1).resolve(new Response('', {status: 429})));
    expect(result.current.facts.get('root-0')).toEqual({outcome: 'unavailable', lastKnownHistoryAt: oldRoot});
    expect(currentFamily(snapshot, result.current.facts).activity.sessionId).toBe('child-0');
    now += 30_001;
    setSystemTime(now);
    rerender({current: {...snapshot}});
    await waitFor(() => expect(network.gates.length).toBe(3));
    await act(async () => requestGate(network, 2).resolve(new Response(successfulBody)));
    await waitFor(() => expect(result.current.facts.get('root-0')?.outcome).toBe('available'));
    const settled = currentFamily(snapshot, result.current.facts);
    expect(settled.activity.sessionId).toBe('root-0');
    expect(settled.recencyIncomplete).toBe(false);
  } finally {
    setSystemTime();
  }
});
