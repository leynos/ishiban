/** @file Verify strict recency request shape and transport retry ownership. */
import {afterEach, expect, it, setSystemTime} from 'bun:test';
import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {useSessionRecency} from '../src/session-recency';
import {groupSessions} from '../src/session-families';
import {createFamilySnapshot, createMultibyteFamilySnapshot, firstSession} from './board-fixtures';
import {deferred, type Deferred} from './deferred';
import {availableRecencyResponse, installFamilyBrowser, installFamilyMarks} from './family-browser-fixture';

let browser: ReturnType<typeof installFamilyBrowser> | undefined;
interface RequestBody {
  readonly sessionIds?: readonly string[];
}

/** Encode current member facts as the strict endpoint would after decoding. */
function availableResponse() {
  const snapshot = createFamilySnapshot(1);
  return availableRecencyResponse(
    snapshot,
    snapshot.sessions.map((session) => session.sessionId),
    '2026-11-10T18:41:02.707Z'
  );
}

afterEach(() => {
  cleanup();
  browser?.restore();
  browser = undefined;
  document.body.replaceChildren();
});

it('sends only the server schema field and accepts its strict response', async () => {
  const marks = installFamilyMarks(1);
  const snapshot = createFamilySnapshot(1);
  const bodies: RequestBody[] = [];
  browser = installFamilyBrowser(async (_input, init) => {
    const body: RequestBody = JSON.parse(String(init?.body));
    bodies.push(body);
    if (Object.keys(body).length !== 1 || !Array.isArray(body.sessionIds)) {
      return new Response('', {status: 400});
    }
    return availableResponse();
  });
  const {result} = renderHook(() => useSessionRecency(snapshot));
  act(() => browser?.visibility(marks[0]!, true));
  await waitFor(() => expect(result.current.facts.get('child-0')?.outcome).toBe('available'));
  expect(Object.keys(bodies[0] ?? {})).toEqual(['sessionIds']);
  expect(bodies[0]?.sessionIds).toEqual(['child-0', 'root-0']);
});

it('holds an HTTP 429 cooldown while more families remain visible', async () => {
  const marks = installFamilyMarks(4);
  const gates: Deferred<Response>[] = [];
  browser = installFamilyBrowser(async () => {
    const gate = deferred<Response>();
    gates.push(gate);
    return gate.promise;
  });
  renderHook(() => useSessionRecency(createFamilySnapshot(4)));
  for (const mark of marks) act(() => browser?.visibility(mark, true));
  await waitFor(() => expect(gates.length).toBe(2));
  await act(async () => {
    gates[0]?.resolve(new Response('', {status: 429}));
    gates[1]?.resolve(new Response('', {status: 429}));
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(gates.length).toBe(2);
});

it('settles a stale execution without delaying other visible families', async () => {
  const snapshot = createFamilySnapshot(4);
  const marks = installFamilyMarks(4);
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
  const frames = ['child-0', 'root-0'].map((sessionId) => ({
    workspaceId: snapshot.workspaceId,
    sessionId,
    lastActivityEventId: sessionId === 'child-0' ? 1 : 0,
    outcome: 'available',
    latestHistoryAt: '2026-11-10T18:41:02.707Z'
  }));
  await act(async () =>
    gates[0]?.resolve(new Response(`${frames.map((frame) => JSON.stringify(frame)).join('\n')}\n`))
  );
  expect(result.current.facts.get('child-0')?.outcome).toBe('unavailable');
  expect(result.current.facts.get('root-0')?.outcome).toBe('available');
  await waitFor(() => expect(gates.length).toBe(3));
  expect(requests[2]).toEqual(expect.arrayContaining(['child-2', 'root-2']));
  expect(requests[2]).not.toContain('child-0');
});

it('packs accepted multibyte member IDs by encoded byte size', async () => {
  const snapshot = createMultibyteFamilySnapshot();
  const mark = installFamilyMarks(1)[0];
  if (!mark) throw new Error('The multibyte fixture must provide a family mark.');
  const bodies: string[] = [];
  browser = installFamilyBrowser(async (_input, init) => {
    const body = String(init?.body);
    bodies.push(body);
    const sessionIds: string[] = JSON.parse(body).sessionIds;
    return availableRecencyResponse(snapshot, sessionIds);
  });
  const {result} = renderHook(() => useSessionRecency(snapshot));
  mark.setAttribute('data-family-id', firstSession(snapshot).sessionId);
  act(() => browser?.visibility(mark, true));
  await waitFor(() => expect(bodies.length).toBe(2));
  await waitFor(() => expect(result.current.facts.size).toBe(8));
  expect(bodies.flatMap((body) => JSON.parse(body).sessionIds).length).toBe(8);
  expect(bodies.every((body) => new TextEncoder().encode(body).byteLength <= 8192)).toBe(true);
});

it('keeps a valid family sibling out of a batch with a 257-code-point source ID', async () => {
  const base = createFamilySnapshot(1);
  const snapshot = {
    ...base,
    sessions: base.sessions.map((session) =>
      session.sessionId === 'child-0' ? {...session, sessionId: 'x'.repeat(257)} : session
    )
  };
  const mark = installFamilyMarks(1)[0];
  if (!mark) throw new Error('The unsupported-ID family needs a root mark.');
  const requests: string[][] = [];
  browser = installFamilyBrowser(async (_input, init) => {
    const ids: string[] = JSON.parse(String(init?.body)).sessionIds;
    requests.push(ids);
    return availableResponse();
  });
  const {result, rerender} = renderHook(({current}) => useSessionRecency(current), {
    initialProps: {current: snapshot}
  });
  act(() => browser?.visibility(mark, true));
  await waitFor(() => expect(result.current.facts.get('root-0')?.outcome).toBe('available'));
  expect(requests).toEqual([['root-0']]);
  const family = groupSessions(snapshot.sessions, result.current.facts)[0];
  expect(family?.recencyIncomplete).toBe(true);
  rerender({current: {...snapshot}});
  expect(requests).toEqual([['root-0']]);
});

for (const variant of [
  {name: 'a malformed member', suffix: '{malformed}\n', includeRoot: false},
  {name: 'a missing member', suffix: '', includeRoot: false},
  {name: 'a malformed frame after all results', suffix: '{malformed}\n', includeRoot: true}
]) {
  it(`cools down for ${variant.name} in an HTTP 200 stream while retaining valid siblings`, async () => {
    const initial = createFamilySnapshot(4);
    const marks = installFamilyMarks(4);
    const gates: Deferred<Response>[] = [];
    let now = Date.now();
    setSystemTime(now);
    try {
      browser = installFamilyBrowser(async () => {
        const gate = deferred<Response>();
        gates.push(gate);
        return gate.promise;
      });
      const {result, rerender} = renderHook(({snapshot}) => useSessionRecency(snapshot), {
        initialProps: {snapshot: initial}
      });
      for (const mark of marks) act(() => browser?.visibility(mark, true));
      await waitFor(() => expect(gates.length).toBe(2));
      const valid = JSON.stringify({
        workspaceId: initial.workspaceId,
        sessionId: 'child-0',
        lastActivityEventId: 0,
        outcome: 'available',
        latestHistoryAt: '2026-11-10T18:41:02.707Z'
      });
      const root = JSON.stringify({
        workspaceId: initial.workspaceId,
        sessionId: 'root-0',
        lastActivityEventId: 0,
        outcome: 'available',
        latestHistoryAt: '2026-11-03T22:05:49.972Z'
      });
      const optionalRoot = variant.includeRoot ? `${root}\n` : '';
      await act(async () => gates[0]?.resolve(new Response(`${valid}\n${optionalRoot}${variant.suffix}`)));
      expect(gates.length).toBe(2);
      expect(result.current.facts.get('child-0')?.outcome).toBe('available');
      expect(result.current.facts.get('root-0')?.outcome).toBe(variant.includeRoot ? 'available' : 'unavailable');

      now += 30_001;
      setSystemTime(now);
      rerender({snapshot: {...initial}});
      await waitFor(() => expect(gates.length).toBeGreaterThan(2));
    } finally {
      setSystemTime();
    }
  });
}
