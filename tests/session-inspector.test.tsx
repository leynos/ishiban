/** @file Verify inspector navigation and honest failed-turn diagnostics. */
import {afterEach, expect, it, spyOn} from 'bun:test';
import {cleanup, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Schema} from 'effect';
import {SessionSchema, type Session} from '../src/contracts';
import {SessionInspector} from '../src/ui/session-inspector';
import {createBoardSnapshot, firstSession} from './board-fixtures';

afterEach(cleanup);

/** Render a live failed turn; for example, omit error text to exercise old journals. */
function inspectFailure(error?: string) {
  const session = {
    ...firstSession(createBoardSnapshot()),
    source: 'persisted' as const,
    latestTurn: {userTurnId: 'turn-1', state: 'failed', error: error ?? null}
  };
  return render(
    <SessionInspector
      session={session}
      currentGeneration={1}
      onClose={() => {}}
      workspaceId="workspace-1"
      workspaceSlug="leynos"
    />
  );
}

it('links directly to the selected session in its configured workspace', () => {
  inspectFailure();
  expect(screen.getByRole('link', {name: 'Open in Lody'}).getAttribute('href')).toBe(
    'https://lody.ai/leynos/sessions/demo-session-001-01'
  );
});

it('shows the supplied turn error as plain text', () => {
  inspectFailure('Provider rejected the request.\n<script>alert("unsafe")</script>');
  const error = screen.getByRole('region', {name: 'Last turn error'});
  expect(error.textContent).toContain('Provider rejected the request.');
  expect(error.textContent).toContain('<script>');
  expect(error.querySelector('script')).toBeNull();
});

it('explains when Lody omitted the underlying error instead of inventing one', () => {
  inspectFailure();
  expect(screen.getByRole('region', {name: 'Last turn error'}).textContent).toContain(
    'Lody did not provide error details for this turn.'
  );
});

it('keeps session evidence visible when a retained observation timestamp is invalid', () => {
  const session = {
    ...firstSession(createBoardSnapshot()),
    lastObservedAt: 8_640_000_000_000_001
  };
  render(
    <SessionInspector
      session={session}
      currentGeneration={1}
      onClose={() => {}}
      workspaceId="workspace-1"
      workspaceSlug="leynos"
    />
  );

  expect(screen.getByRole('heading', {name: 'Synthetic planning task 01 for demo/repository-001'})).toBeTruthy();
  expect(screen.getByText('Timestamp unavailable')).toBeTruthy();
});

it('uses the canonical native link when no workspace slug is configured', () => {
  const session = {...firstSession(createBoardSnapshot()), source: 'persisted' as const};
  render(<SessionInspector session={session} currentGeneration={1} onClose={() => {}} workspaceId="workspace-1" />);
  expect(screen.getByRole('link', {name: 'Open in Lody'}).getAttribute('href')).toBe(
    'lody://session/demo-session-001-01?workspace=workspace-1'
  );
});

// A failed boolean check avoids serializing a large happy-dom link object.
it.each([
  {route: 'web', sessionId: '.'},
  {route: 'web', sessionId: '..'},
  {route: 'native', sessionId: '.'},
  {route: 'native', sessionId: '..'}
])('explains unavailable $route links for dot-segment ID $sessionId', ({route, sessionId}) => {
  const baseline = firstSession(createBoardSnapshot());
  const context = {
    ...baseline,
    sessionId: route === 'web' ? sessionId : 'root-session',
    source: 'persisted' as const
  };
  render(
    <SessionInspector
      session={context}
      activitySession={{...context, sessionId}}
      currentGeneration={1}
      onClose={() => {}}
      workspaceId="workspace-1"
      {...(route === 'web' ? {workspaceSlug: 'leynos'} : {})}
    />
  );

  expect(screen.queryByRole('link', {name: 'Open in Lody'}) === null).toBe(true);
  expect(screen.getByText('Lody link unavailable for this session identifier.')).toBeTruthy();
  expect(screen.getByRole('button', {name: 'Copy session ID'})).toBeTruthy();
});

it('keeps a dot-segment selected tab in the query of a valid web root link', () => {
  const baseline = firstSession(createBoardSnapshot());
  const context = {...baseline, sessionId: 'root-session', source: 'persisted' as const};
  const activity = {...context, sessionId: '..'};
  render(
    <SessionInspector
      session={context}
      activitySession={activity}
      currentGeneration={1}
      onClose={() => {}}
      workspaceId="workspace-1"
      workspaceSlug="leynos"
    />
  );

  const href = screen.getByRole('link', {name: 'Open in Lody'}).getAttribute('href');
  expect(href).toBe('https://lody.ai/leynos/sessions/root-session?tab=session%3A..');
  expect(new URL(String(href)).searchParams.get('tab')).toBe('session:..');
});

it('keeps slash and percent session identities encoded in Lody links', () => {
  const baseline = firstSession(createBoardSnapshot());
  const routes = [
    {sessionId: 'a/b', workspaceSlug: 'leynos', href: 'https://lody.ai/leynos/sessions/a%2Fb'},
    {sessionId: '100%?', workspaceSlug: 'leynos', href: 'https://lody.ai/leynos/sessions/100%25%3F'},
    {sessionId: 'a/b', workspaceSlug: undefined, href: 'lody://session/a%2Fb?workspace=workspace-1'},
    {sessionId: '100%?', workspaceSlug: undefined, href: 'lody://session/100%25%3F?workspace=workspace-1'}
  ];
  for (const {sessionId, workspaceSlug, href} of routes) {
    render(
      <SessionInspector
        session={{...baseline, sessionId, source: 'persisted'}}
        currentGeneration={1}
        onClose={() => {}}
        workspaceId="workspace-1"
        {...(workspaceSlug === undefined ? {} : {workspaceSlug})}
      />
    );

    expect(screen.getByRole('link', {name: 'Open in Lody'}).getAttribute('href')).toBe(href);
    cleanup();
  }
});

it('does not present a synthetic demo session as an actual Lody session', () => {
  render(
    <SessionInspector
      session={firstSession(createBoardSnapshot())}
      currentGeneration={1}
      onClose={() => {}}
      workspaceId="workspace-1"
      workspaceSlug="leynos"
    />
  );
  expect(screen.queryByRole('link', {name: 'Open in Lody'})).toBeNull();
  expect(screen.getByText('Synthetic demo session')).toBeTruthy();
});

it('accepts legacy sessions and validates summary marker types when present', () => {
  const legacy = firstSession(createBoardSnapshot());
  const decodeSession = Schema.decodeUnknownSync(SessionSchema);

  expect(decodeSession(legacy).sessionId).toBe(legacy.sessionId);
  expect(() => decodeSession({...legacy, activeTurnCount: '143'})).toThrow();
  expect(() => decodeSession({...legacy, activeTurnCount: -1})).toThrow();
  expect(() => decodeSession({...legacy, activeTurnCount: 1.5})).toThrow();
  expect(() => decodeSession({...legacy, activeTurnsTruncated: 'yes'})).toThrow();
  expect(() => decodeSession({...legacy, activeTurnsRevision: 143})).toThrow();
});

it('explains a truncated active-turn preview and keeps the Lody session link', () => {
  const session = {
    ...firstSession(createBoardSnapshot()),
    source: 'persisted' as const,
    activeTurns: Array.from({length: 100}, (_, index) => ({
      userTurnId: `turn-${index}`,
      state: 'running'
    })),
    activeTurnCount: 143,
    activeTurnsTruncated: true,
    activeTurnsRevision: 'a'.repeat(64)
  };
  render(
    <SessionInspector
      session={session}
      currentGeneration={1}
      onClose={() => {}}
      workspaceId="workspace-1"
      workspaceSlug="leynos"
    />
  );

  expect(screen.getByText('Showing 100 of 143 active turns.')).toBeTruthy();
  expect(screen.getByRole('link', {name: 'Open in Lody'}).getAttribute('href')).toBe(
    'https://lody.ai/leynos/sessions/demo-session-001-01'
  );
});

it('shows a quiet transport notice beside activity without replacing turn errors', () => {
  const session = {
    ...firstSession(createBoardSnapshot()),
    activityNotice: 'Activity details exceed the transfer limit. Open the session in Lody.',
    latestTurn: {userTurnId: 'turn-1', state: 'failed', error: 'Earlier Lody error'}
  };
  render(
    <SessionInspector
      session={session}
      currentGeneration={1}
      onClose={() => {}}
      workspaceId="workspace-1"
      workspaceSlug="leynos"
    />
  );

  const notice = screen.getByText(session.activityNotice);
  expect(notice.getAttribute('role')).toBe('status');
  expect(screen.getByRole('region', {name: 'Last turn error'}).textContent).toContain('Earlier Lody error');
  expect(notice.compareDocumentPosition(screen.getByText('Active turns')) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
    Node.DOCUMENT_POSITION_FOLLOWING
  );
});

it('does not display failure text on a successful turn', () => {
  const session = {
    ...firstSession(createBoardSnapshot()),
    latestTurn: {userTurnId: 'turn-1', state: 'completed', error: 'An old error'}
  };
  render(<SessionInspector session={session} currentGeneration={1} onClose={() => {}} workspaceId="workspace-1" />);
  expect(screen.queryByRole('region', {name: 'Last turn error'})).toBeNull();
});

it('uses the linked PR name as the heading and the session name as its subtitle', () => {
  const original = firstSession(createBoardSnapshot());
  const session = {
    ...original,
    pullRequests: [
      {url: 'https://github.com/example/project/pull/1', title: 'Plan: improve the inspector', status: 'open'}
    ]
  };
  render(<SessionInspector session={session} workspaceId="workspace-1" currentGeneration={1} onClose={() => {}} />);
  const heading = screen.getByRole('heading', {name: 'Plan: improve the inspector', level: 3});
  expect(heading.querySelector('a')?.href).toBe('https://github.com/example/project/pull/1');
  expect(screen.getByText(original.title).className).toBe('session-inspector__subtitle');
});

it('places a readable PR number after its link', () => {
  const session = {
    ...firstSession(createBoardSnapshot()),
    pullRequests: [{url: 'https://github.com/example/project/pull/123', title: 'Improve inspector', status: 'open'}]
  };
  render(<SessionInspector session={session} workspaceId="workspace-1" currentGeneration={1} onClose={() => {}} />);
  const number = screen.getByText('#123');
  expect(number.className).toBe('session-pr-number');
  expect(number.previousElementSibling?.tagName).toBe('A');
});

it.each(['', '   '])('gives a blank PR title an accessible fallback: %j', (title) => {
  const session = {
    ...firstSession(createBoardSnapshot()),
    pullRequests: [{url: 'https://github.com/example/project/pull/123', title, status: 'open'}]
  };
  render(<SessionInspector session={session} workspaceId="workspace-1" currentGeneration={1} onClose={() => {}} />);
  expect(screen.getByRole('link', {name: 'Open pull request'}).getAttribute('href')).toBe(
    'https://github.com/example/project/pull/123'
  );
});

/** Keep root workflow facts distinct from the running tab in inspector regressions. */
function inspectorFamily() {
  const context: Session = {
    ...firstSession(createBoardSnapshot()),
    sessionId: 'parent-session',
    title: 'Import verification support',
    source: 'persisted',
    branchName: 'verification-support',
    stage: 'refine',
    stageReason: 'The parent PR is ready for review.',
    latestTurn: {userTurnId: 'old-root-turn', state: 'failed', error: 'Old parent failure'},
    pullRequests: [{url: 'https://github.com/example/project/pull/492', title: 'Verification support', status: 'open'}]
  };
  const activity: Session = {
    ...context,
    sessionId: 'latest-tab',
    title: 'Review queue wait',
    parentSessionId: context.sessionId,
    branchName: null,
    pullRequests: [],
    state: 'running',
    latestTurn: {userTurnId: 'child-turn', state: 'running'}
  };
  return {context, activity};
}

it('keeps parent workflow context while linking and describing the selected tab', () => {
  const {context, activity} = inspectorFamily();
  render(
    <SessionInspector
      session={context}
      activitySession={activity}
      workspaceId="workspace-1"
      workspaceSlug="leynos"
      currentGeneration={1}
      onClose={() => {}}
    />
  );

  expect(screen.getByRole('heading', {name: 'Verification support', level: 3})).toBeTruthy();
  expect(screen.getByText(context.title).className).toBe('session-inspector__subtitle');
  expect(screen.getByText('verification-support')).toBeTruthy();
  expect(screen.getByText('Refine')).toBeTruthy();
  expect(screen.getByText(activity.title)).toBeTruthy();
  expect(screen.getByText('running')).toBeTruthy();
  expect(screen.queryByRole('region', {name: 'Last turn error'})).toBeNull();
  expect(screen.getByRole('link', {name: 'Open in Lody'}).getAttribute('href')).toBe(
    'https://lody.ai/leynos/sessions/parent-session?tab=session%3Alatest-tab'
  );
});

it('updates selected-tab error evidence without replacing the parent heading', () => {
  const {context, activity} = inspectorFamily();
  const props = {session: context, workspaceId: 'workspace-1', currentGeneration: 1, onClose: () => {}};
  const view = render(<SessionInspector {...props} activitySession={activity} />);
  const next = {
    ...activity,
    sessionId: 'next-tab',
    latestTurn: {userTurnId: 'next-turn', state: 'failed', error: 'New tab failure'}
  };
  view.rerender(<SessionInspector {...props} activitySession={next} />);

  expect(screen.getByRole('heading', {name: 'Verification support', level: 3})).toBeTruthy();
  expect(screen.getByRole('region', {name: 'Last turn error'}).textContent).toContain('New tab failure');
  expect(screen.queryByText('latest-tab')).toBeNull();
  expect(screen.getByText('next-tab')).toBeTruthy();
  expect(screen.getByRole('link', {name: 'Open in Lody'}).getAttribute('href')).toBe(
    'lody://session/next-tab?workspace=workspace-1'
  );
});

it('reads and copies the selected tab identity rather than the parent identity', async () => {
  const {context, activity} = inspectorFamily();
  const user = userEvent.setup();
  const write = spyOn(navigator.clipboard, 'writeText').mockResolvedValue();
  const fetchSpy = spyOn(globalThis, 'fetch').mockResolvedValue(
    Response.json({
      workspaceId: 'workspace-1',
      sessionId: activity.sessionId,
      agent: {agentType: 'claude', configurationId: 'child-config', configurationName: 'Review configuration'}
    })
  );
  try {
    render(
      <SessionInspector
        session={context}
        activitySession={activity}
        workspaceId="workspace-1"
        currentGeneration={1}
        onClose={() => {}}
      />
    );
    expect(await screen.findByText('Review configuration')).toBeTruthy();
    expect(screen.getByText('claude')).toBeTruthy();
    expect(screen.getByText(activity.sessionId).tagName).toBe('CODE');
    expect(fetchSpy.mock.calls[0]?.[0]).toBe('/api/v1/session-agent?sessionId=latest-tab');
    await user.click(screen.getByRole('button', {name: 'Copy session ID'}));
    expect(write).toHaveBeenCalledWith(activity.sessionId);
  } finally {
    fetchSpy.mockRestore();
    write.mockRestore();
  }
});
