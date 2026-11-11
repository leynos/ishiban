/** @file Capture real inspector fetch URLs before Falcon validates raw IDs. */
import {expect, it, spyOn} from 'bun:test';
import {cleanup, render, renderHook, screen, waitFor} from '@testing-library/react';
import type {Session} from '../src/contracts';
import {AgentDetails} from '../src/ui/agent-details';
import {usePullRequestTitles} from '../src/ui/pull-request-titles';
import {createBoardSnapshot, firstSession} from './board-fixtures';
import {writeCapturedText} from './capture-writer';

const {ISHIBAN_INSPECTOR_REQUEST_CAPTURE: capturePath} = Bun.env;
const prUrl = 'https://github.com/example/project/pull/123';

it.skipIf(!capturePath)('captures inspector URLs for exact source session identities', async () => {
  if (!capturePath) throw new Error('The Falcon contract must supply its private capture path.');
  const requests: {sessionId: string; agent: string; titles: string}[] = [];
  for (const sessionId of ['.', '..', 'a/b', '100%?']) {
    const session: Session = {
      ...firstSession(createBoardSnapshot()),
      sessionId,
      source: 'persisted',
      pullRequests: [{url: prUrl, title: null, status: 'merged'}]
    };
    const paths: string[] = [];
    const fetchFixture = Object.assign(
      async (input: RequestInfo | URL) => {
        const url = new URL(String(input), 'http://127.0.0.1:8765');
        paths.push(`${url.pathname}${url.search}`);
        return Response.json(
          url.pathname === '/api/v1/session-agent'
            ? {
                workspaceId: 'w1',
                sessionId,
                agent: {agentType: 'codex', configurationId: null, configurationName: null}
              }
            : {
                workspaceId: 'w1',
                sessionId,
                lastEventId: session.lastEventId,
                titles: {[prUrl]: 'Resolved title'},
                stack: {}
              }
        );
      },
      {preconnect: () => null}
    );
    const fetchSpy = spyOn(globalThis, 'fetch').mockImplementation(fetchFixture);
    try {
      render(<AgentDetails workspaceId="w1" sessionId={sessionId} isDemo={false} />);
      const {result} = renderHook(() => usePullRequestTitles(session, 'w1'));
      await screen.findByText('codex');
      await waitFor(() => expect(result.current.pullRequests[0]?.title).toBe('Resolved title'));
      expect(paths).toHaveLength(2);
      const [agent, titles] = paths;
      if (!agent || !titles) throw new Error('Both inspector routes must be captured.');
      requests.push({sessionId, agent, titles});
    } finally {
      cleanup();
      fetchSpy.mockRestore();
    }
  }
  writeCapturedText(capturePath, JSON.stringify(requests));
});
