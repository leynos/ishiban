/** @file Verify formatted task tooltip content, delivery, dismissal and isolation. */
import {afterEach, describe, expect, it} from 'bun:test';
import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type {Session, Snapshot} from '../src/contracts';
import {Board} from '../src/ui/board';
import {TASK_TOOLTIP_DELAY_MS, TASK_TOOLTIP_INSPECTOR_HINT} from '../src/ui/task-tooltip';
import {createBoardSnapshot, firstSession, markByTitle, unknownRuntime, updateFirstSession} from './board-fixtures';

afterEach(() => cleanup());

/** Render the board with the demo connection and return the interaction drivers. */
function renderTooltipBoard(snapshot: Snapshot = createBoardSnapshot(), user = userEvent.setup()) {
  const result = render(<Board connection="demo" snapshot={snapshot} />);
  return {user, rerender: result.rerender};
}

/** Deliver focus as a keyboard user would; Radix opens instantly and no timer runs. */
async function focusMark(mark: HTMLElement): Promise<void> {
  await act(async () => {
    mark.focus();
  });
}

/** Open one tooltip through the real pointer path and the shared hover delay. */
async function hoverOpen(user: ReturnType<typeof userEvent.setup>, mark: HTMLElement): Promise<void> {
  await user.hover(mark);
  await waitFor(() => expect(tooltipElement()).not.toBeNull(), {timeout: TASK_TOOLTIP_DELAY_MS + 2000});
}

/** Return the portalled tooltip element while one is mounted. */
function tooltipElement(): HTMLElement | null {
  return document.querySelector<HTMLElement>('.task-tooltip');
}

/** Return the tooltip's visible values in labelled-detail order. */
function detailValues(): readonly string[] {
  return [...(tooltipElement()?.querySelectorAll('dd') ?? [])].map((value) => value.textContent);
}

/** Render one session alone so its mark and inspector text are unambiguous. */
function renderSingleSession(session: Session) {
  const snapshot = createBoardSnapshot();
  return renderTooltipBoard({...snapshot, sessions: [session]});
}

describe('task tooltip delivery', () => {
  it('opens on pointer hover only after the shared delay', async () => {
    const {user} = renderTooltipBoard();
    const mark = markByTitle('Synthetic planning task 01');

    await user.hover(mark);
    expect(tooltipElement()).toBeNull();
    expect(mark.getAttribute('data-state')).toBe('closed');

    await hoverOpen(user, mark);
    expect(mark.getAttribute('data-state')).toBe('delayed-open');
  });

  it('opens immediately when keyboard focus arrives and portals outside the board', async () => {
    renderTooltipBoard();
    const mark = markByTitle('Synthetic planning task 01');
    const accessibleName = mark.getAttribute('aria-label');
    expect(mark.hasAttribute('title')).toBe(false);

    await focusMark(mark);

    const content = tooltipElement();
    expect(document.activeElement === mark).toBe(true);
    expect(mark.getAttribute('data-state')).toBe('instant-open');
    expect(content).not.toBeNull();
    if (content === null) throw new Error('The focused mark must render a tooltip.');
    expect(document.body.contains(content)).toBe(true);
    expect(content.closest('.board-scroll')).toBeNull();
    expect(mark.getAttribute('aria-label')).toBe(accessibleName);
    expect(mark.getAttribute('aria-describedby')).toBe(content.querySelector('[role="tooltip"]')?.id ?? null);
  });

  it('keeps aria-describedby only while the tooltip is open', async () => {
    const {user} = renderTooltipBoard();
    const mark = markByTitle('Synthetic planning task 01');
    expect(mark.hasAttribute('aria-describedby')).toBe(false);

    await focusMark(mark);
    await waitFor(() => expect(mark.hasAttribute('aria-describedby')).toBe(true));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(mark.hasAttribute('aria-describedby')).toBe(false));
    expect(tooltipElement()).toBeNull();
  });
});

describe('task tooltip dismissal', () => {
  it('dismisses on Escape while focus stays on the trigger', async () => {
    const {user} = renderTooltipBoard();
    const mark = markByTitle('Synthetic planning task 01');
    await focusMark(mark);
    expect(tooltipElement()).not.toBeNull();

    await user.keyboard('{Escape}');

    await waitFor(() => expect(tooltipElement()).toBeNull());
    expect(document.activeElement === mark).toBe(true);
    expect(screen.queryByRole('complementary', {name: 'Session inspector'})).toBeNull();
  });

  it('closes only the tooltip on the first Escape and the inspector on the second', async () => {
    const {user} = renderTooltipBoard();
    const mark = markByTitle('Synthetic planning task 01');
    const otherMark = markByTitle('Synthetic planning task 02');
    await user.click(mark);
    const closeButton = screen.getByRole('button', {name: 'Close session inspector'});
    expect(screen.getByRole('complementary', {name: 'Session inspector'})).toBeTruthy();

    // Move focus into the dock, then open another mark's tooltip with the pointer.
    await act(async () => {
      closeButton.focus();
    });
    await hoverOpen(user, otherMark);
    await user.keyboard('{Escape}');
    await waitFor(() => expect(tooltipElement()).toBeNull());
    expect(screen.getByRole('complementary', {name: 'Session inspector'})).toBeTruthy();

    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('complementary', {name: 'Session inspector'})).toBeNull());
    expect(document.activeElement === mark).toBe(true);

    // Restored focus reopens the tooltip, and a further Escape closes only that.
    await waitFor(() => expect(tooltipElement()).not.toBeNull());
    await user.keyboard('{Escape}');
    await waitFor(() => expect(tooltipElement()).toBeNull());
    expect(screen.queryByRole('complementary', {name: 'Session inspector'})).toBeNull();
  });
});

describe('task tooltip activation and pointer travel', () => {
  it('leaves no tooltip after pointer activation opens the inspector', async () => {
    const {user} = renderTooltipBoard();
    const mark = markByTitle('Synthetic planning task 01');
    await hoverOpen(user, mark);

    await user.click(mark);

    expect(screen.getByRole('complementary', {name: 'Session inspector'})).toBeTruthy();
    await waitFor(() => expect(tooltipElement()).toBeNull());
    expect(mark.getAttribute('aria-pressed')).toBe('true');
  });

  it('keeps its content readable when the pointer moves into the tooltip', async () => {
    const {user} = renderTooltipBoard();
    const mark = markByTitle('Synthetic planning task 01');
    await hoverOpen(user, mark);
    const content = tooltipElement();
    if (content === null) throw new Error('The hovered mark must render a tooltip.');

    await user.hover(content);

    expect(tooltipElement()).not.toBeNull();
    expect(mark.getAttribute('data-state')).not.toBe('closed');
  });

  it('offers no focusable control inside the tooltip', async () => {
    renderTooltipBoard();
    await focusMark(markByTitle('Synthetic planning task 01'));

    const content = tooltipElement();
    if (content === null) throw new Error('The focused mark must render a tooltip.');
    expect(content.querySelectorAll('a, button, input, select, textarea, [tabindex]')).toHaveLength(0);
  });

  it('activates the inspector from the keyboard', async () => {
    const {user} = renderTooltipBoard();
    const mark = markByTitle('Synthetic planning task 01');
    await focusMark(mark);
    expect(document.activeElement === mark).toBe(true);

    await user.keyboard('{Enter}');

    expect(screen.getByRole('complementary', {name: 'Session inspector'}).textContent).toContain(
      'Synthetic planning task 01'
    );
  });
});

describe('task tooltip content', () => {
  it('shows the title, labelled details, condition fallback and inspector hint', async () => {
    const session: Session = {...firstSession(createBoardSnapshot()), latestTurn: null};
    renderSingleSession(session);
    await focusMark(markByTitle(session.title));

    const content = tooltipElement();
    if (content === null) throw new Error('The focused mark must render a tooltip.');
    expect(content.querySelector('.task-tooltip__title')?.textContent).toBe(session.title);
    expect([...content.querySelectorAll('dt')].map((term) => term.textContent)).toEqual([
      'Repository',
      'Workflow stage',
      'Current tab activity',
      'Condition',
      'Evidence'
    ]);
    expect(detailValues()[0]).toBe('demo/repository-001');
    expect(detailValues()[1]).toBe('Planning');
    expect(detailValues()[3]).toBe('None reported');
    expect(detailValues()[4]).toBe('Synthetic demo record');
    expect(content.textContent).toContain(TASK_TOOLTIP_INSPECTOR_HINT);
    expect(content.textContent).not.toContain(session.stageReason);
  });

  it('shows independent workflow, activity, condition and evidence facts', async () => {
    const blocked: Session = {
      ...firstSession(createBoardSnapshot()),
      state: 'waiting',
      latestTurn: {userTurnId: 'turn-9', state: 'failed', error: 'Provider rejected the turn'},
      title: 'Waiting on review'
    };
    renderSingleSession(blocked);
    await focusMark(markByTitle('Waiting on review'));

    expect(detailValues()[1]).toBe('Planning');
    expect(detailValues()[2]).toBe('waiting');
    expect(detailValues()[3]).toBe('blocked; last known turn failed');
    expect(detailValues()[4]).toBe('Synthetic demo record');
    expect(tooltipElement()?.textContent).not.toContain('Provider rejected the turn');
  });

  it('reports unknown activity and missing repository without inferring either', async () => {
    const unknown: Session = {
      ...firstSession(createBoardSnapshot()),
      ...unknownRuntime('b'.repeat(64)),
      repoFullName: null
    };
    renderSingleSession(unknown);
    await focusMark(markByTitle('Synthetic planning task 01'));

    expect(detailValues()[0]).toBe('Repository not supplied');
    expect(detailValues()[2]).toBe('unknown');
    expect(detailValues()[3]).toBe('None reported');
  });

  it('renders an upstream title as literal text rather than markup', async () => {
    const hostile: Session = {
      ...firstSession(createBoardSnapshot()),
      title: '<script>window.alert(1)</script> Release note'
    };
    renderSingleSession(hostile);
    await focusMark(markByTitle('Release note'));

    const title = tooltipElement()?.querySelector('.task-tooltip__title');
    expect(title?.textContent).toBe('<script>window.alert(1)</script> Release note');
    expect(title?.querySelector('script')).toBeNull();
  });
});

describe('task tooltip and family selection', () => {
  it('describes the selected child tab while keeping the root task context', async () => {
    const snapshot = createBoardSnapshot();
    const root = {
      ...firstSession(snapshot),
      sessionId: 'root-family',
      title: 'Root planning work',
      stage: 'refine' as const
    };
    const child = {
      ...root,
      sessionId: 'child-family',
      parentSessionId: 'root-family',
      title: 'Child execution',
      state: 'running' as const
    };
    renderTooltipBoard({...snapshot, sessions: [root, child]});
    await focusMark(markByTitle('Root planning work'));

    expect(tooltipElement()?.querySelector('.task-tooltip__title')?.textContent).toBe('Root planning work');
    expect(detailValues()[1]).toBe('Refine');
    expect(detailValues()[2]).toBe('running');
  });
});

describe('task tooltip isolation', () => {
  it('leaves empty cells without tooltips, state or descriptions', () => {
    renderTooltipBoard();

    const emptyCells = [...document.querySelectorAll<HTMLElement>('.session-mark--empty')];
    expect(emptyCells.length).toBeGreaterThan(0);
    for (const cell of emptyCells) {
      expect(cell.hasAttribute('data-state')).toBe(false);
      expect(cell.hasAttribute('aria-describedby')).toBe(false);
      expect(cell.hasAttribute('title')).toBe(false);
      expect(cell.tagName).toBe('SPAN');
    }
  });

  it('renders no portal content during static markup rendering', async () => {
    const {renderToStaticMarkup} = await import('react-dom/server');
    const markup = renderToStaticMarkup(<Board connection="demo" snapshot={createBoardSnapshot()} />);

    expect(markup).toContain('class="session-mark');
    expect(markup).not.toContain('task-tooltip');
    expect(markup).not.toContain('data-radix-popper-content-wrapper');
  });

  it('reflects updated facts without a pulse, cursor or revision change', async () => {
    const initial = createBoardSnapshot();
    const {rerender} = renderTooltipBoard(initial);
    const updated = updateFirstSession(initial, {title: 'Renamed planning task'});

    rerender(<Board connection="demo" snapshot={updated} />);
    const renamed = markByTitle('Renamed planning task');
    await focusMark(renamed);

    expect(tooltipElement()?.querySelector('.task-tooltip__title')?.textContent).toBe('Renamed planning task');
    expect(renamed.getAttribute('data-update-revision')).toBeNull();
    expect(renamed.querySelector('[data-session-update-pulse]')).toBeNull();
    expect(initial.cursor).toBe(updated.cursor);
  });
});
