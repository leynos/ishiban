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
 * Require one captured activity request at a known index.
 * @param requests Held requests from the activity fetch fixture.
 * @param index Zero-based request position.
 * @returns The captured request, or a clear fixture failure.
 * @throws {Error} When the requested batch has not started.
 * @example
 * const first = activityRequestAt(fetchFixture.requests, 0);
 */
export function activityRequestAt(requests: readonly ActivityFetchRequest[], index: number): ActivityFetchRequest {
  const request = requests[index];
  if (!request) throw new Error(`Expected activity request ${index} to start.`);
  return request;
}

/**
 * Complete one activity batch as newline-delimited JSON frames.
 * @param request The captured POST whose response is held.
 * @param frames Valid or deliberately invalid frames chosen by the caller.
 * @example
 * resolveActivityBatch(first, [{workspaceId: 'w1', sessionId: 's1', session: null}]);
 */
export function resolveActivityBatch(request: ActivityFetchRequest, frames: readonly unknown[]): void {
  request.response.resolve(new Response(`${frames.map((frame) => JSON.stringify(frame)).join('\n')}\n`));
}

/**
 * Render raw activity marks before starting the visibility observer.
 * @param sessions Distinct sessions whose raw identities reach the activity scanner.
 * @returns The rendered marks for explicit viewport transitions.
 * @example
 * activityMarks([{sessionId: 's1'}])[0]?.getAttribute('data-session-id'); // 's1'
 */
export function activityMarks(sessions: readonly {readonly sessionId: string}[]): HTMLButtonElement[] {
  const marks = sessions.map((session) => {
    const mark = document.createElement('button');
    mark.setAttribute('data-session-id', session.sessionId);
    return mark;
  });
  document.body.replaceChildren(...marks);
  return marks;
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
