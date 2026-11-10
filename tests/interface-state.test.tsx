/** @file Verify restored preferences and ordered cookie persistence. */
import {afterEach, expect, it, spyOn} from 'bun:test';
import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import type {InterfaceState} from '../src/contracts';
import {useInterfaceState} from '../src/ui/interface-state';
import type {InterfaceStateControls} from '../src/ui/interface-state';
import {deferred} from './deferred';

afterEach(cleanup);

/** Add Bun's required fetch extension to a deterministic test implementation. */
function spyOnFetch(implementation: (...args: Parameters<typeof fetch>) => Promise<Response>) {
  return spyOn(globalThis, 'fetch').mockImplementation(Object.assign(implementation, {preconnect: () => null}));
}

interface HookResult {
  readonly current: InterfaceStateControls;
}

/** Run a preference scenario with one mocked fetch and a shared cleanup path. */
async function withPreferenceHook(
  implementation: (...args: Parameters<typeof fetch>) => Promise<Response>,
  exercise: (result: HookResult) => Promise<void>
): Promise<void> {
  const fetchMock = spyOnFetch(implementation);
  const {result, unmount} = renderHook(() => useInterfaceState());
  try {
    await exercise(result);
  } finally {
    unmount();
    fetchMock.mockRestore();
  }
}

it('restores cookie preferences and defaults without saving on mount', () => {
  const fetchMock = spyOn(globalThis, 'fetch');
  const restored: InterfaceState = {density: 'roomy', presentation: 'matrix'};
  const restoredHook = renderHook(() => useInterfaceState(restored));
  expect(restoredHook.result.current.density).toBe('roomy');
  expect(restoredHook.result.current.presentation).toBe('matrix');
  expect(restoredHook.result.current.saveStatus).toBe('');
  restoredHook.unmount();

  const defaultHook = renderHook(() => useInterfaceState());
  expect(defaultHook.result.current.density).toBe('overview');
  expect(defaultHook.result.current.presentation).toBe('panorama');
  expect(fetchMock).not.toHaveBeenCalled();
  defaultHook.unmount();
  fetchMock.mockRestore();
});

it('serializes rapid changes and writes the latest complete preference state', async () => {
  const firstStarted = deferred<void>();
  const secondStarted = deferred<void>();
  const firstResponse = deferred<Response>();
  const secondResponse = deferred<Response>();
  const requests: RequestInit[] = [];
  let requestNumber = 0;
  await withPreferenceHook(
    (_input, init) => {
      requests.push(init ?? {});
      requestNumber += 1;
      if (requestNumber === 1) {
        firstStarted.resolve();
        return firstResponse.promise;
      }
      if (requestNumber === 2) {
        secondStarted.resolve();
        return secondResponse.promise;
      }
      return Promise.reject(new Error('Unexpected extra preference save.'));
    },
    async (result) => {
      act(() => {
        result.current.onDensityChange('balanced');
        result.current.onPresentationChange('matrix');
      });
      await firstStarted.promise;

      expect(requests).toHaveLength(1);
      expect(requests[0]?.method).toBe('POST');
      expect(requests[0]?.keepalive).toBe(true);
      expect(requests[0]?.headers).toEqual({'content-type': 'application/json'});
      expect(JSON.parse(String(requests[0]?.body))).toEqual({
        density: 'balanced',
        presentation: 'panorama'
      });

      firstResponse.resolve(new Response(null, {status: 204}));
      await secondStarted.promise;

      expect(requests).toHaveLength(2);
      expect(JSON.parse(String(requests[1]?.body))).toEqual({
        density: 'balanced',
        presentation: 'matrix'
      });
      secondResponse.resolve(new Response(null, {status: 204}));
      await waitFor(() => expect(result.current.saveStatus).toBe(''));
    }
  );
});

it('shows a failed save and clears the message after a later successful save', async () => {
  const firstStarted = deferred<void>();
  const failedResponse = deferred<Response>();
  let requestNumber = 0;
  await withPreferenceHook(
    () => {
      requestNumber += 1;
      if (requestNumber === 1) {
        firstStarted.resolve();
        return failedResponse.promise;
      }
      return Promise.resolve(new Response(null, {status: 204}));
    },
    async (result) => {
      act(() => result.current.onDensityChange('compact'));
      await firstStarted.promise;
      failedResponse.resolve(new Response('unavailable', {status: 503}));
      await waitFor(() => expect(result.current.saveStatus).toBe('Could not save interface state.'));

      act(() => result.current.onPresentationChange('list'));
      expect(result.current.saveStatus).toBe('Saving interface state…');
      await waitFor(() => expect(result.current.saveStatus).toBe(''));
      expect(requestNumber).toBe(2);
    }
  );
});

it('lets a queued save finish after unmount without another UI update', async () => {
  const requestStarted = deferred<void>();
  const response = deferred<Response>();
  const fetchMock = spyOnFetch(() => {
    requestStarted.resolve();
    return response.promise;
  });
  let renderCount = 0;
  const hook = renderHook(() => {
    renderCount += 1;
    return useInterfaceState();
  });

  act(() => hook.result.current.onDensityChange('comfortable'));
  await requestStarted.promise;
  const rendersAtUnmount = renderCount;
  hook.unmount();

  response.resolve(new Response(null, {status: 204}));
  await response.promise;
  await Promise.resolve();

  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(renderCount).toBe(rendersAtUnmount);
  expect(hook.result.current.saveStatus).toBe('Saving interface state…');
  fetchMock.mockRestore();
});
