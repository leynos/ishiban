/** @file Capture the real browser request for the Python ASGI contract test. */
import {expect, it} from 'bun:test';
import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {useSessionRecency} from '../src/session-recency';
import {createFamilySnapshot, createMultibyteFamilySnapshot} from './board-fixtures';
import {deferred} from './deferred';
import {installFamilyBrowser, installFamilyMarks} from './family-browser-fixture';

const {ISHIBAN_RECENCY_REQUEST_CAPTURE: capturePath} = Bun.env;
const {ISHIBAN_RECENCY_MULTIBYTE_CAPTURE: multibyteCapturePath} = Bun.env;

it.skipIf(!capturePath)('captures the browser request consumed by the real ASGI decoder', async () => {
  if (!capturePath) throw new Error('The Python contract test must supply its private capture path.');
  const captured = deferred<string>();
  const browser = installFamilyBrowser(async (_input, init) => {
    captured.resolve(String(init?.body));
    return new Response('');
  });
  try {
    const mark = installFamilyMarks(1)[0];
    if (!mark) throw new Error('The fixture must contain one family mark.');
    const snapshot = createFamilySnapshot(1, 'w1');
    renderHook(() => useSessionRecency(snapshot));
    act(() => browser.visibility(mark, true));
    const body = await captured.promise;
    expect(JSON.parse(body).sessionIds).toEqual(['child-0', 'root-0']);
    await Bun.write(capturePath, body);
  } finally {
    cleanup();
    browser.restore();
    document.body.replaceChildren();
  }
});

it.skipIf(!multibyteCapturePath)('captures all byte-packed multibyte requests for real ASGI', async () => {
  if (!multibyteCapturePath) throw new Error('The Python contract test must supply its multibyte capture path.');
  const bodies: string[] = [];
  const snapshot = createMultibyteFamilySnapshot();
  const browser = installFamilyBrowser(async (_input, init) => {
    const body = String(init?.body);
    bodies.push(body);
    const sessionIds: string[] = JSON.parse(body).sessionIds;
    const frames = sessionIds.map((sessionId) =>
      JSON.stringify({
        workspaceId: snapshot.workspaceId,
        sessionId,
        lastActivityEventId: 0,
        outcome: 'available',
        latestHistoryAt: null
      })
    );
    return new Response(`${frames.join('\n')}\n`);
  });
  try {
    const mark = installFamilyMarks(1)[0];
    const root = snapshot.sessions[0];
    if (!mark || !root) throw new Error('The multibyte fixture must provide one mark and a root session.');
    renderHook(() => useSessionRecency(snapshot));
    mark.setAttribute('data-family-id', root.sessionId);
    act(() => browser.visibility(mark, true));
    await waitFor(() => expect(bodies.length).toBe(2));
    await Bun.write(multibyteCapturePath, JSON.stringify(bodies));
  } finally {
    cleanup();
    browser.restore();
    document.body.replaceChildren();
  }
});
