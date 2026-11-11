/** @file Keep unsupported source IDs out of bounded activity batches. */
import {expect, it} from 'bun:test';
import {waitFor} from '@testing-library/react';
import type {Session} from '../src/contracts';
import {createBoardStore, type BoardStore} from '../src/client';
import {startLazyActivity} from '../src/lazy-activity';
import {createBoardSnapshot, firstSession} from './board-fixtures';
import {installActivityFetch} from './activity-fetch-fixture';
import {
  ControlledIntersectionObserver,
  installControlledIntersectionObserver
} from './controlled-intersection-observer';

/** Read one raw member's current activity without assuming a snapshot exists. */
function activityStateAt(store: BoardStore, index: number): Session['state'] | undefined {
  return store.getSnapshot().snapshot?.sessions[index]?.state;
}

it('resolves a valid unknown sibling without submitting long or NUL source IDs', async () => {
  const baseline = createBoardSnapshot();
  const template = firstSession(baseline);
  const unknown = (sessionId: string): Session => ({
    ...template,
    sessionId,
    source: 'persisted',
    state: 'unknown',
    title: sessionId
  });
  const sessions = [unknown('x'.repeat(257)), unknown('valid-session'), unknown('bad\0id')];
  const store = createBoardStore();
  store.replace({...baseline, sessions});
  const restoreObserver = installControlledIntersectionObserver();
  const fetchFixture = installActivityFetch();
  const marks = sessions.map((session) => {
    const mark = document.createElement('button');
    mark.setAttribute('data-session-id', session.sessionId);
    return mark;
  });
  document.body.replaceChildren(...marks);
  const stop = startLazyActivity(store);
  try {
    const observer = ControlledIntersectionObserver.instances.at(-1);
    if (!observer) throw new Error('The activity identity test needs a visibility observer.');
    for (const mark of marks) observer.setVisibility(mark, true);
    await waitFor(() => expect(fetchFixture.requests).toHaveLength(1));
    const request = fetchFixture.requests[0];
    if (!request) throw new Error('The valid session must start one activity batch.');
    expect(JSON.parse(String(request.init.body))).toEqual({sessionIds: ['valid-session']});
    const resolved = {...sessions[1], state: 'running', activitySource: 'lazy'};
    request.response.resolve(
      new Response(
        `${JSON.stringify({
          workspaceId: baseline.workspaceId,
          sessionId: 'valid-session',
          session: resolved
        })}\n`
      )
    );
    await waitFor(() => expect(activityStateAt(store, 1)).toBe('running'));
    expect(activityStateAt(store, 0)).toBe('unknown');
    expect(activityStateAt(store, 2)).toBe('unknown');
    expect(fetchFixture.requests).toHaveLength(1);
  } finally {
    stop();
    fetchFixture.restore();
    restoreObserver();
    document.body.replaceChildren();
  }
});
