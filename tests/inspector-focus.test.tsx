/** @file Verify dialog focus trapping and return to the initiating session mark. */
import {afterEach, describe, expect, it} from 'bun:test';
import {cleanup, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Board} from '../src/ui/board';
import {createDemoSnapshot} from '../src/demo';

afterEach(() => cleanup());

/** Keep keyboard tests to two adjacent marks while retaining demo-shaped sessions. */
function createFocusSnapshot() {
  const snapshot = createDemoSnapshot();
  return {...snapshot, sessions: snapshot.sessions.slice(0, 2)};
}

describe('session inspector focus management', () => {
  it('traps keyboard focus while open and restores it to the selected mark on Escape', async () => {
    const user = userEvent.setup();
    render(<Board snapshot={createFocusSnapshot()} connection="demo" />);
    const firstMark = screen.getByRole('button', {name: /demo\/repository-001: Synthetic planning task 01/u});
    const secondMark = screen.getByRole('button', {name: /demo\/repository-001: Synthetic planning task 02/u});

    expect(firstMark.getAttribute('aria-label')).toContain('; idle;');
    expect(secondMark.getAttribute('aria-label')).toContain('; running;');
    firstMark.focus();
    expect(document.activeElement).toBe(firstMark);

    await user.keyboard('{Enter}');

    const inspector = screen.getByRole('dialog');
    await user.tab();
    const firstTabbedElement = document.activeElement;
    expect(firstTabbedElement !== null && inspector.contains(firstTabbedElement)).toBe(true);
    await user.tab();
    const secondTabbedElement = document.activeElement;
    expect(secondTabbedElement !== null && inspector.contains(secondTabbedElement)).toBe(true);
    await user.tab();
    const thirdTabbedElement = document.activeElement;
    expect(thirdTabbedElement !== null && inspector.contains(thirdTabbedElement)).toBe(true);

    await user.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement?.getAttribute('aria-label')).toBe(firstMark.getAttribute('aria-label'));
  });

  it('moves focus to the board when the initiating mark disappears before close', async () => {
    const user = userEvent.setup();
    const snapshot = createFocusSnapshot();
    const {rerender} = render(<Board snapshot={snapshot} connection="demo" />);
    const firstMark = screen.getByRole('button', {name: /demo\/repository-001: Synthetic planning task 01/u});
    await user.click(firstMark);
    expect(screen.getByRole('dialog')).toBeTruthy();

    const remainingSessions = snapshot.sessions.filter((session) => session.sessionId !== 'demo-session-001-01');
    rerender(<Board connection="demo" snapshot={{...snapshot, sessions: remainingSessions}} />);

    expect(screen.queryByRole('dialog')).toBeNull();
    await waitFor(() => expect(document.activeElement?.id).toBe('programme-board'));
  });
});
