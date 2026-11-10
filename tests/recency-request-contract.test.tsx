/** @file Capture the real browser request for the Python ASGI contract test. */
import {expect, it} from 'bun:test';
import {act, cleanup, renderHook} from '@testing-library/react';
import {useSessionRecency} from '../src/session-recency';
import {createFamilySnapshot} from './board-fixtures';
import {deferred} from './deferred';
import {installFamilyBrowser, installFamilyMarks} from './family-browser-fixture';

const {ISHIBAN_RECENCY_REQUEST_CAPTURE: capturePath} = Bun.env;

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
