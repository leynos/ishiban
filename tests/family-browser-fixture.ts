/** @file Control family-mark visibility and fetch ownership in browser tests. */
import type {Snapshot} from '../src/contracts';
import {
  ControlledIntersectionObserver,
  installControlledIntersectionObserver
} from './controlled-intersection-observer';

/**
 * Install deterministic viewport and network boundaries for one family scenario.
 * @param respond Endpoint-specific response controlled by the test.
 * @returns Visibility driver and cleanup restoring both browser globals.
 * @example
 * const browser = installFamilyBrowser(async () => new Response(''));
 * browser.restore();
 */
export function installFamilyBrowser(respond: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>) {
  const restoreObserver = installControlledIntersectionObserver();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = Object.assign(respond, {preconnect: originalFetch.preconnect});
  return {
    /** Deliver one viewport transition after React has rendered its mark. */
    visibility(mark: Element, isVisible: boolean): void {
      const observer = ControlledIntersectionObserver.instances.at(-1);
      if (!observer) throw new Error('Expected family visibility observer.');
      observer.setVisibility(mark, isVisible);
    },
    /** Restore globals even when a test fails before its request completes. */
    restore(): void {
      globalThis.fetch = originalFetch;
      restoreObserver();
    }
  };
}

/**
 * Mount bare family marks for hook tests that do not render the full board.
 * @param count Number of independent root marks.
 * @returns The mounted buttons in catalogue order.
 * @example
 * installFamilyMarks(1)[0]?.getAttribute('data-family-id') === 'root-0';
 */
export function installFamilyMarks(count: number): HTMLButtonElement[] {
  const marks = Array.from({length: count}, (_, index) => {
    const mark = document.createElement('button');
    mark.setAttribute('data-family-id', `root-${index}`);
    return mark;
  });
  document.body.replaceChildren(...marks);
  return marks;
}

/**
 * Return strict available frames for requested raw family members.
 * @param snapshot The current workspace and execution watermarks.
 * @param sessionIds Requested member identities in wire order.
 * @param latestHistoryAt A shared test history time, or null when absent.
 * @returns One NDJSON response preserving each requested identity and watermark.
 * @throws {Error} When the request names a member absent from the fixture.
 * @example
 * availableRecencyResponse(createFamilySnapshot(1), ['root-0']).status === 200;
 */
export function availableRecencyResponse(
  snapshot: Snapshot,
  sessionIds: readonly string[],
  latestHistoryAt: string | null = null
): Response {
  const revisions = new Map(snapshot.sessions.map((session) => [session.sessionId, session.lastActivityEventId ?? 0]));
  const frames = sessionIds.map((sessionId) => {
    const basis = revisions.get(sessionId);
    if (basis === undefined) throw new Error(`The recency fixture has no member ${sessionId}.`);
    return JSON.stringify({
      workspaceId: snapshot.workspaceId,
      sessionId,
      lastActivityEventId: basis,
      outcome: 'available',
      latestHistoryAt
    });
  });
  return new Response(`${frames.join('\n')}\n`);
}
