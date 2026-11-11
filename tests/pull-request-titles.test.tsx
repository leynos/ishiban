/** @file Fill missing terminal PR titles without replacing newer source metadata. */
import {afterEach, expect, it, spyOn} from 'bun:test';
import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import type {Session} from '../src/contracts';
import {usePullRequestTitles} from '../src/ui/pull-request-titles';
import {firstSession, createBoardSnapshot} from './board-fixtures';

afterEach(cleanup);

it('resolves a merged PR name lazily while retaining the session title and stage', async () => {
  const url = 'https://github.com/example/project/pull/123';
  const session: Session = {
    ...firstSession(createBoardSnapshot()),
    source: 'persisted' as const,
    stage: 'merged' as const,
    pullRequests: [{url, title: null, status: 'merged'}]
  };
  const fetchFixture = Object.assign(
    async () =>
      Response.json({
        workspaceId: 'workspace-1',
        sessionId: session.sessionId,
        titles: {[url]: 'A merged pull request'}
      }),
    {preconnect: () => null}
  );
  const fetchSpy = spyOn(globalThis, 'fetch').mockImplementation(fetchFixture);
  try {
    const {result, rerender} = renderHook(({selected}) => usePullRequestTitles(selected, 'workspace-1'), {
      initialProps: {selected: session}
    });
    await waitFor(() => expect(result.current.pullRequests[0]?.title).toBe('A merged pull request'));
    expect(result.current.title).toBe(session.title);
    expect(result.current.stage).toBe('merged');
    expect(fetchSpy.mock.calls[0]?.[0]).toBe(`/api/v1/session-pull-requests?sessionId=${session.sessionId}`);
    rerender({selected: {...session, pullRequests: [{url, title: 'Newer catalogue title', status: 'merged'}]}});
    expect(result.current.pullRequests[0]?.title).toBe('Newer catalogue title');
  } finally {
    fetchSpy.mockRestore();
  }
});

it.each([
  ['foreign workspace', 'another-workspace', true],
  ['foreign session', 'workspace-1', false]
])('ignores a %s PR-title response after it is processed', async (_case, responseWorkspaceId, isMatchingSession) => {
  const url = 'https://github.com/example/project/pull/123';
  const session: Session = {
    ...firstSession(createBoardSnapshot()),
    source: 'persisted',
    pullRequests: [{url, title: null, status: 'merged'}]
  };
  const response = Response.json({
    workspaceId: responseWorkspaceId,
    sessionId: isMatchingSession ? session.sessionId : 'another-session',
    titles: {[url]: 'Foreign pull request title'}
  });
  const originalJson = response.json.bind(response);
  const jsonFinished = Promise.withResolvers<void>();
  response.json = async () => {
    const body: unknown = await originalJson();
    jsonFinished.resolve();
    return body;
  };
  const fetchFixture = Object.assign(async () => response, {preconnect: () => null});
  const fetchSpy = spyOn(globalThis, 'fetch').mockImplementation(fetchFixture);
  try {
    const {result} = renderHook(() => usePullRequestTitles(session, 'workspace-1'));
    await act(async () => {
      await jsonFinished.promise;
      // Let the lookup settle and React apply any queued title update.
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(result.current.pullRequests[0]?.title).toBeNull();
    expect(result.current.title).toBe(session.title);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  } finally {
    fetchSpy.mockRestore();
  }
});

it('does not fetch PR titles for synthetic demo data', () => {
  const session = {
    ...firstSession(createBoardSnapshot()),
    pullRequests: [{url: 'https://github.com/example/project/pull/123', title: null, status: 'merged'}]
  };
  const fetchSpy = spyOn(globalThis, 'fetch');
  try {
    const {result} = renderHook(() => usePullRequestTitles(session, 'demo'));
    expect(result.current).toBe(session);
    expect(fetchSpy).not.toHaveBeenCalled();
  } finally {
    fetchSpy.mockRestore();
  }
});
