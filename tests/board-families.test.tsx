/** @file Verify one stable board mark combines root workflow and latest-tab activity. */
import {afterEach, expect, it} from 'bun:test';
import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Board} from '../src/ui/board';
import {createFamilySnapshot} from './board-fixtures';
import {installFamilyBrowser} from './family-browser-fixture';

afterEach(cleanup);

it('shows one root workflow mark with the running child and stable inspector selection', async () => {
  const user = userEvent.setup();
  const snapshot = createFamilySnapshot(1);
  const {rerender} = render(<Board connection="Connected" snapshot={snapshot} />);
  const mark = screen.getByRole('button', {name: /Root planning work; Refine; running/u});
  expect(mark.getAttribute('data-family-id')).toBe('root-0');
  expect(mark.getAttribute('data-session-id')).toBe('child-0');
  expect(mark.className).toContain('activity-running');
  expect(screen.getByText(/1 sessions · workflow stages/u)).toBeTruthy();
  await user.click(mark);
  expect(screen.getByRole('heading', {name: /Implement root work/u})).toBeTruthy();
  const updated = {
    ...snapshot,
    sessions: snapshot.sessions.map((session) =>
      session.sessionId === 'child-0'
        ? {
            ...session,
            lastEventId: session.lastEventId + 1,
            latestTurn: {userTurnId: 'next', state: 'running', error: null}
          }
        : session
    )
  };
  act(() => rerender(<Board connection="Connected" snapshot={updated} />));
  expect(
    screen.getByRole('button', {name: /Root planning work; Refine; running/u}).getAttribute('data-family-id')
  ).toBe('root-0');
  expect(
    screen
      .getByRole('button', {name: /Root planning work; Refine; running/u})
      .querySelector('[data-session-update-pulse]')
  ).not.toBeNull();
});

it('searches both tab titles and identities while counting one logical entry', async () => {
  const user = userEvent.setup();
  render(<Board connection="Connected" snapshot={createFamilySnapshot(1)} />);
  await user.type(screen.getByRole('searchbox'), 'child-0');
  expect(screen.getByRole('button', {name: /Root planning work; Refine; running/u})).toBeTruthy();
  expect(document.querySelector('.board-summary')?.textContent).toContain('1 visible sessions');
});

it('keeps a live child visible when its saved root context is removed', () => {
  const snapshot = createFamilySnapshot(1);
  const removedRoot = {
    ...snapshot,
    sessions: snapshot.sessions.map((session) =>
      session.sessionId === 'root-0' ? {...session, removed: true} : session
    )
  };
  render(<Board connection="Connected" snapshot={removedRoot} />);
  expect(screen.getByRole('button', {name: /Root planning work; Refine; running/u})).toBeTruthy();
});

it('hides an archived root family until archived entries are included', async () => {
  const user = userEvent.setup();
  const snapshot = createFamilySnapshot(1);
  const archivedRoot = {
    ...snapshot,
    sessions: snapshot.sessions.map((session) =>
      session.sessionId === 'root-0' ? {...session, archived: true} : session
    )
  };
  render(<Board connection="Connected" snapshot={archivedRoot} />);
  expect(screen.queryByRole('button', {name: /Root planning work; Refine; running/u})).toBeNull();

  await user.click(screen.getByRole('checkbox', {name: 'Include archived and removed'}));
  expect(screen.getByRole('button', {name: /Root planning work; Refine; running/u})).toBeTruthy();
  expect(document.querySelector('.board-summary')?.textContent).toContain('1 visible sessions');
});

it('keeps a selected child open when its parent link arrives later', async () => {
  const user = userEvent.setup();
  const linked = createFamilySnapshot(1);
  const unlinked = {
    ...linked,
    sessions: linked.sessions.map((session) =>
      session.sessionId === 'child-0' ? {...session, parentSessionId: null} : session
    )
  };
  const {rerender} = render(<Board connection="Connected" snapshot={unlinked} />);
  await user.click(screen.getByRole('button', {name: /Child execution; Planning; running/u}));
  expect(screen.getByRole('button', {name: 'Close session inspector'})).toBeTruthy();

  act(() => rerender(<Board connection="Connected" snapshot={linked} />));
  const rootMark = screen.getByRole('button', {name: /Root planning work; Refine; running/u});
  expect(screen.getByRole('heading', {name: /Implement root work/u})).toBeTruthy();
  expect(rootMark.getAttribute('aria-pressed')).toBe('true');

  await user.click(screen.getByRole('button', {name: 'Close session inspector'}));
  expect(document.activeElement).toBe(rootMark);
});

it('settles visible family recency quietly from two validated history frames', async () => {
  const snapshot = createFamilySnapshot(1);
  const live = {
    ...snapshot,
    collector: {...snapshot.collector, state: 'running'},
    sessions: snapshot.sessions.map((session) => ({...session, source: 'persisted' as const}))
  };
  const requested: string[][] = [];
  const fetchRecency = async (_input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const body = JSON.parse(String(init?.body));
    requested.push(body.sessionIds);
    const lines = live.sessions.map((session) => ({
      workspaceId: live.workspaceId,
      sessionId: session.sessionId,
      lastActivityEventId: session.lastActivityEventId ?? 0,
      outcome: 'available',
      latestHistoryAt: session.sessionId === 'root-0' ? '2026-11-08T16:26:01.199Z' : '2026-11-03T22:05:49.972Z'
    }));
    return new Response(`${lines.map((line) => JSON.stringify(line)).join('\n')}\n`);
  };
  const browser = installFamilyBrowser(fetchRecency);
  try {
    render(<Board connection="Connected" snapshot={live} />);
    const mark = screen.getByRole('button', {name: /Root planning work; Refine; running/u});
    act(() => browser.visibility(mark, true));
    await waitFor(() => expect(mark.getAttribute('data-session-id')).toBe('root-0'));
    expect(requested).toEqual([['child-0', 'root-0']]);
    expect(mark.querySelector('[data-session-update-pulse]')).toBeNull();
  } finally {
    browser.restore();
  }
});
