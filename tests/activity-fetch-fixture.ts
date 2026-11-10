/** @file Share controlled fetch requests across visibility and fallback tests. */
import {spyOn} from 'bun:test';
import {deferred, type Deferred} from './deferred';

export interface ActivityFetchRequest {
  readonly url: string;
  readonly init: NonNullable<Parameters<typeof fetch>[1]>;
  readonly response: Deferred<Response>;
}

export interface ActivityFetchFixture {
  readonly requests: ActivityFetchRequest[];
  readonly started: readonly Deferred<void>[];
  readonly restore: () => void;
}

/**
 * Replace fetch with held responses; for example, release NDJSON only after its fallback starts.
 * @param capacity Number of request-start signals reserved for one deterministic test.
 * @returns Requests, their start signals, and a restoration function for afterEach.
 * @example
 * const fetch = installActivityFetch();
 * fetch.requests[0]?.response.resolve(new Response('{}'));
 * fetch.restore();
 */
export function installActivityFetch(capacity = 8): ActivityFetchFixture {
  const requests: ActivityFetchRequest[] = [];
  const started = Array.from({length: capacity}, () => deferred<void>());
  const fetchMock = Object.assign(
    (...args: Parameters<typeof fetch>) => {
      const [input, options] = args;
      const response = deferred<Response>();
      const request: ActivityFetchRequest = {url: String(input), init: options ?? {}, response};
      const index = requests.push(request) - 1;
      started[index]?.resolve();
      request.init.signal?.addEventListener('abort', () => response.resolve(new Response(null, {status: 499})), {
        once: true
      });
      return response.promise;
    },
    {preconnect: () => null}
  );
  const fetchSpy = spyOn(globalThis, 'fetch').mockImplementation(fetchMock);
  return {requests, started, restore: () => fetchSpy.mockRestore()};
}
