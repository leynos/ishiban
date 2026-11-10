/** @file Verify strict recency request shape and transport retry ownership. */
import {afterEach, expect, it} from 'bun:test';
import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {useSessionRecency} from '../src/session-recency';
import {createFamilySnapshot} from './board-fixtures';
import {deferred, type Deferred} from './deferred';
import {installFamilyBrowser, installFamilyMarks} from './family-browser-fixture';

let browser: ReturnType<typeof installFamilyBrowser> | undefined;
interface RequestBody {
  readonly sessionIds?: readonly string[];
}

/** Encode current member facts as the strict endpoint would after decoding. */
function availableResponse() {
  const snapshot = createFamilySnapshot(1);
  const frames = snapshot.sessions.map((session) => ({
    workspaceId: snapshot.workspaceId,
    sessionId: session.sessionId,
    lastActivityEventId: session.lastActivityEventId ?? 0,
    outcome: 'available',
    latestHistoryAt: '2026-11-10T18:41:02.707Z'
  }));
  return new Response(`${frames.map((frame) => JSON.stringify(frame)).join('\n')}\n`);
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
  await waitFor(() => expect(result.current.get('child-0')?.outcome).toBe('available'));
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
