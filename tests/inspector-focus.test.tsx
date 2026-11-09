/** @file Verify docked inspector access and return to the initiating session mark. */
import {afterEach, expect, it} from 'bun:test';
import {cleanup, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type {Snapshot} from '../src/contracts';
import {Board} from '../src/ui/board';
import {createBoardSnapshot, moveFirstSession} from './board-fixtures';

afterEach(() => cleanup());

/** Render two adjacent marks for dock selection and keyboard interaction. */
function renderFocusBoard(snapshot: Snapshot = createBoardSnapshot()) {
  const user = userEvent.setup();
  render(<Board snapshot={snapshot} connection="demo" />);
  const firstMark = screen.getByRole('button', {name: /demo\/repository-001: Synthetic planning task 01/u});
  const secondMark = screen.getByRole('button', {name: /demo\/repository-001: Synthetic planning task 02/u});
  return {user, firstMark, secondMark};
}

it('keeps the board nonmodal and restores the selected mark on Escape', async () => {
  const {user, firstMark, secondMark} = renderFocusBoard();

  expect(firstMark.getAttribute('aria-label')).toContain('; idle;');
  expect(secondMark.getAttribute('aria-label')).toContain('; running;');
  firstMark.focus();
  expect(document.activeElement).toBe(firstMark);

  await user.keyboard('{Enter}');

  const inspector = screen.getByRole('complementary', {name: 'Session inspector'});
  expect(inspector.id).toBe('session-inspector');
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(document.activeElement).toBe(firstMark);
  expect(firstMark.getAttribute('aria-expanded')).toBe('true');
  await user.tab();
  expect(document.activeElement).toBe(secondMark);
  await user.tab();
  expect(document.activeElement).toBe(screen.getByRole('button', {name: 'Close session inspector'}));

  await user.keyboard('{Escape}');

  expect(screen.queryByRole('complementary', {name: 'Session inspector'})).toBeNull();
  expect(document.activeElement?.getAttribute('aria-label')).toBe(firstMark.getAttribute('aria-label'));
});

it('keeps the inspector open when another mark is selected and returns focus on close', async () => {
  const {user, firstMark, secondMark} = renderFocusBoard();

  await user.click(firstMark);
  await user.click(secondMark);

  expect(screen.getByRole('complementary', {name: 'Session inspector'}).textContent).toContain(
    'Synthetic planning task 02'
  );
  expect(document.activeElement).toBe(secondMark);

  await user.click(screen.getByRole('button', {name: 'Close session inspector'}));

  expect(screen.queryByRole('complementary', {name: 'Session inspector'})).toBeNull();
  expect(document.activeElement).toBe(secondMark);
});

it('keeps search usable while the selected mark is filtered out', async () => {
  const user = userEvent.setup();
  render(<Board snapshot={createBoardSnapshot()} connection="demo" />);
  const firstMark = screen.getByRole('button', {name: /demo\/repository-001: Synthetic planning task 01/u});
  await user.click(firstMark);

  const search = screen.getByRole('searchbox', {name: 'Find repository, session or branch'});
  await user.type(search, 'not in this workspace');

  expect(screen.getByRole('complementary', {name: 'Session inspector'})).toBeTruthy();
  expect(document.activeElement).toBe(search);
  expect(screen.queryByRole('button', {name: /Synthetic planning task 01/u})).toBeNull();
});

it('restores focus to the same session when a collector update moves its mark', async () => {
  const snapshot = createBoardSnapshot();
  const {rerender} = render(<Board snapshot={snapshot} connection="demo" />);
  const firstMark = screen.getByRole('button', {name: /demo\/repository-001: Synthetic planning task 01/u});
  firstMark.focus();
  expect(document.activeElement).toBe(firstMark);

  rerender(<Board connection="demo" snapshot={moveFirstSession(snapshot)} />);

  const movedMark = screen.getByRole('button', {name: /repository-moved: Synthetic planning task 01/u});
  await waitFor(() => expect(document.activeElement).toBe(movedMark));
});

it('moves focus to the board when the selected mark disappears from the snapshot', async () => {
  const user = userEvent.setup();
  const snapshot = createBoardSnapshot();
  const {rerender} = render(<Board snapshot={snapshot} connection="demo" />);
  const firstMark = screen.getByRole('button', {name: /demo\/repository-001: Synthetic planning task 01/u});
  await user.click(firstMark);
  expect(screen.getByRole('complementary', {name: 'Session inspector'})).toBeTruthy();

  const remainingSessions = snapshot.sessions.filter((session) => session.sessionId !== 'demo-session-001-01');
  rerender(<Board connection="demo" snapshot={{...snapshot, sessions: remainingSessions}} />);

  expect(screen.queryByRole('complementary', {name: 'Session inspector'})).toBeNull();
  await waitFor(() => expect(document.activeElement?.id).toBe('programme-board'));
});
