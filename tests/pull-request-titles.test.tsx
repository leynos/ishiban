/** @file Fill missing terminal PR titles without replacing newer source metadata. */
import {afterEach, expect, it, spyOn} from 'bun:test';
import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import type {Session} from '../src/contracts';
import type {PrStackFacts} from '../src/ui/pr-stack-order';
import {usePullRequestTitles} from '../src/ui/pull-request-titles';
import {firstSession, createBoardSnapshot} from './board-fixtures';

afterEach(cleanup);

interface DetailOverrides {
  readonly workspaceId?: string;
  readonly sessionId?: string;
  readonly lastEventId?: number;
  readonly titles?: Readonly<Record<string, string>>;
  readonly stack?: Readonly<Record<string, PrStackFacts>>;
}

/** Keep each test's associations while sharing the live-session boundary. */
function persistedSession(pullRequests: Session['pullRequests']): Session {
  return {...firstSession(createBoardSnapshot()), source: 'persisted', pullRequests};
}

/** Build a scoped PR response while allowing one deliberately foreign fact. */
function detailResponse(session: Session, overrides: DetailOverrides): Response {
  return Response.json({
    workspaceId: 'workspace-1',
    sessionId: session.sessionId,
    lastEventId: session.lastEventId,
    titles: {},
    stack: {},
    ...overrides
  });
}

/** Install a response factory under the browser fetch contract. */
function mockDetailResponse(makeResponse: () => Response) {
  const fetchFixture = Object.assign(async () => makeResponse(), {preconnect: () => null});
  return spyOn(globalThis, 'fetch').mockImplementation(fetchFixture);
}

/** Render a selected source session under the real hook. */
function renderSelectedSession(session: Session) {
  return renderHook(({selected}) => usePullRequestTitles(selected, 'workspace-1'), {
    initialProps: {selected: session}
  });
}

/** Own fetch-mock cleanup around one hook assertion sequence. */
async function withSelectedSession(
  session: Session,
  response: Response,
  verify: (
    evidence: ReturnType<typeof renderSelectedSession> & {
      fetchSpy: ReturnType<typeof mockDetailResponse>;
      parsedBodies: readonly unknown[];
    }
  ) => Promise<void>
): Promise<void> {
  const parsedBodies: unknown[] = [];
  const fetchSpy = mockDetailResponse(() => {
    const freshResponse = response.clone();
    const readJson = freshResponse.json.bind(freshResponse);
    freshResponse.json = async () => {
      const body: unknown = await readJson();
      parsedBodies.push(body);
      return body;
    };
    return freshResponse;
  });
  try {
    await verify({...renderSelectedSession(session), fetchSpy, parsedBodies});
  } finally {
    fetchSpy.mockRestore();
  }
}

it('resolves a merged PR name lazily while retaining the session title and stage', async () => {
  const url = 'https://github.com/example/project/pull/123';
  const session: Session = {
    ...persistedSession([{url, title: null, status: 'merged'}]),
    stage: 'merged' as const
  };
  await withSelectedSession(
    session,
    detailResponse(session, {titles: {[url]: 'A merged pull request'}}),
    async ({result, rerender, fetchSpy}) => {
      await waitFor(() => expect(result.current.pullRequests[0]?.title).toBe('A merged pull request'));
      expect(result.current.title).toBe(session.title);
      expect(result.current.stage).toBe('merged');
      expect(fetchSpy.mock.calls[0]?.[0]).toBe(`/api/v1/session-pull-requests?sessionId=${session.sessionId}`);
      rerender({selected: {...session, pullRequests: [{url, title: 'Newer catalogue title', status: 'merged'}]}});
      expect(result.current.pullRequests[0]?.title).toBe('Newer catalogue title');
    }
  );
});

it.each([
  ['foreign workspace', 'another-workspace', true],
  ['foreign session', 'workspace-1', false]
])('ignores a %s PR-title response after it is processed', async (_case, responseWorkspaceId, isMatchingSession) => {
  const url = 'https://github.com/example/project/pull/123';
  const session = persistedSession([{url, title: null, status: 'merged'}]);
  const response = detailResponse(session, {
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
  const fetchSpy = mockDetailResponse(() => response);
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

it('fetches stack facts for two already titled PRs and ignores a stale revision', async () => {
  const lower = 'https://github.com/leynos/axinite/pull/740';
  const upper = 'https://github.com/leynos/axinite/pull/364';
  const session = persistedSession([
    {url: lower, title: 'Prerequisite', status: 'merged'},
    {url: upper, title: 'Dependent (#333)', status: 'open'}
  ]);
  const stack = {
    [upper]: {
      baseRefName: 'prerequisite',
      headRefName: 'dependent',
      isCrossRepository: false,
      mergedAt: null
    }
  };
  await withSelectedSession(
    session,
    detailResponse(session, {stack}),
    async ({result, rerender, fetchSpy, parsedBodies}) => {
      await waitFor(() => expect(result.current.inspectorStack?.[upper]?.baseRefName).toBe('prerequisite'));
      rerender({selected: {...session, lastEventId: session.lastEventId + 1}});
      await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
      await waitFor(() => expect(parsedBodies).toHaveLength(2));
      expect(parsedBodies[1]).toMatchObject({lastEventId: session.lastEventId});
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 0));
      });
      expect(result.current.inspectorStack).toBeUndefined();
    }
  );
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
