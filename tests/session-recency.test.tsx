/** @file Verify visible-family recency ownership across scope and viewport changes. */
import {afterEach, expect, it} from 'bun:test';
import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import type {Snapshot} from '../src/contracts';
import {useSessionRecency} from '../src/session-recency';
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
  expect(result.current.size).toBe(0);
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
  await waitFor(() => expect(result.current.get('child-0')?.outcome).toBe('available'));
  expect(result.current.get('root-0')?.outcome).toBe('unavailable');
});

it('rejects a late member after its execution watermark advances', async () => {
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
  expect(result.current.get('child-0')?.outcome).not.toBe('available');
  await waitFor(() => expect(network.requests.length).toBe(2));
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
    network.gates[0]?.resolve(availableFrame(snapshot, 'child-0', '2026-11-10T18:41:02.707Z'));
  });
  await waitFor(() => expect(network.requests.length).toBe(3));
  expect(network.requests[2]).toEqual(['child-3', 'root-3']);
});
