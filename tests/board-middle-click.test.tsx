/** @file Verify middle-button thread navigation matches the inspector's canonical link. */
import {afterEach, expect, it, mock, spyOn} from 'bun:test';
import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Board} from '../src/ui/board';
import {createBoardSnapshot, createFamilySnapshot, firstSession} from './board-fixtures';

afterEach(() => {
  cleanup();
  mock.restore();
});

const GROUPED_URL = 'https://lody.ai/leynos/sessions/root-0?tab=session%3Achild-0';

/** Dispatch one native mouse event and return whether it remained uncancelled. */
function mouseEvent(target: Element, type: 'mousedown' | 'auxclick', button: number): boolean {
  return fireEvent(target, new MouseEvent(type, {button, bubbles: true, cancelable: true}));
}

/** Resolve the single grouped mark, proving its displayed tab is the child. */
function groupedMark(): HTMLElement {
  const mark = screen.getByRole('button', {name: /Root planning work; Refine; running/u});
  expect(mark.getAttribute('data-family-id')).toBe('root-0');
  expect(mark.getAttribute('data-session-id')).toBe('child-0');
  return mark;
}

/** Assert that the inspector stayed closed after a non-select gesture. */
function expectInspectorClosed(): void {
  expect(screen.queryByRole('button', {name: 'Close session inspector'})).toBeNull();
  expect(document.querySelector('.ishiban-board')?.getAttribute('data-inspector-open')).toBe('false');
}

/** Replace the window opener for one test; the shared cleanup restores it. */
function spyOnOpen() {
  return spyOn(globalThis, 'open').mockReturnValue(null);
}

/** Render one grouped family and own the opener spy for a gesture case. */
function renderGroupedMark() {
  render(<Board connection="Connected" snapshot={createFamilySnapshot(1)} />);
  return {mark: groupedMark(), open: spyOnOpen()};
}

it('opens the displayed child tab once on middle click without selecting the task', () => {
  const {mark, open} = renderGroupedMark();

  expect(mouseEvent(mark, 'mousedown', 1)).toBe(false);
  expect(open).not.toHaveBeenCalled();
  expect(mouseEvent(mark, 'auxclick', 1)).toBe(false);
  expect(open).toHaveBeenCalledTimes(1);
  expect(open).toHaveBeenCalledWith(GROUPED_URL, '_blank', 'noopener,noreferrer');
  expect(mark.getAttribute('aria-pressed')).toBe('false');
  expectInspectorClosed();
});

it('opens a root-only family without a tab query', () => {
  const snapshot = createFamilySnapshot(1);
  const rootOnly = {...snapshot, sessions: snapshot.sessions.slice(0, 1)};
  render(<Board connection="Connected" snapshot={rootOnly} />);
  const mark = screen.getByRole('button', {name: /Root planning work; Refine; idle/u});
  const open = spyOnOpen();

  expect(mouseEvent(mark, 'auxclick', 1)).toBe(false);
  expect(open).toHaveBeenCalledWith('https://lody.ai/leynos/sessions/root-0', '_blank', 'noopener,noreferrer');
  expectInspectorClosed();
});

it('navigates from list and workflow-exception controls with the same thread destination', async () => {
  const user = userEvent.setup();
  const snapshot = createFamilySnapshot(1);
  const closed = {
    ...snapshot,
    sessions: snapshot.sessions.map((session) => ({...session, stage: 'closed' as const}))
  };
  render(<Board connection="Connected" snapshot={closed} />);
  const exceptions = screen.getByRole('region', {name: 'Other workflow groups'});
  const exceptionMark = within(exceptions).getByRole('button', {name: /Root planning work; Closed; running/u});
  const open = spyOnOpen();

  mouseEvent(exceptionMark, 'auxclick', 1);
  expect(open).toHaveBeenCalledWith(GROUPED_URL, '_blank', 'noopener,noreferrer');
  open.mockClear();

  await user.click(screen.getByRole('button', {name: 'List'}));
  const listMark = screen.getByRole('button', {name: /Root planning work; Closed; running/u});
  expect(listMark.className).toContain('session-list-item');
  mouseEvent(listMark, 'auxclick', 1);
  expect(open).toHaveBeenCalledWith(GROUPED_URL, '_blank', 'noopener,noreferrer');
  expectInspectorClosed();
});

it('leaves demo and dot-segment destinations without a navigable middle click', () => {
  const demo = createBoardSnapshot();
  const {unmount} = render(<Board connection="Demo data" snapshot={demo} />);
  const open = spyOnOpen();

  const demoMark = screen.getAllByRole('button', {name: /Synthetic/u})[0];
  if (!demoMark) throw new Error('The demo fixture must render a session mark.');
  expect(mouseEvent(demoMark, 'mousedown', 1)).toBe(true);
  expect(mouseEvent(demoMark, 'auxclick', 1)).toBe(false);
  expect(open).not.toHaveBeenCalled();
  unmount();

  const baseline = createFamilySnapshot(1);
  const root = firstSession(baseline);
  const dotRoot = {...baseline, sessions: [{...root, sessionId: '.'}]};
  render(<Board connection="Connected" snapshot={dotRoot} />);
  const dotMark = screen.getByRole('button', {name: /Root planning work; Refine; idle/u});
  expect(mouseEvent(dotMark, 'mousedown', 1)).toBe(true);
  expect(mouseEvent(dotMark, 'auxclick', 1)).toBe(false);
  expect(open).not.toHaveBeenCalled();
});

it('ignores non-middle buttons and leaves placeholders inert', () => {
  const {mark, open} = renderGroupedMark();

  expect(mouseEvent(mark, 'mousedown', 0)).toBe(true);
  expect(mouseEvent(mark, 'mousedown', 2)).toBe(true);
  expect(mouseEvent(mark, 'auxclick', 0)).toBe(true);
  expect(mouseEvent(mark, 'auxclick', 2)).toBe(true);
  expect(open).not.toHaveBeenCalled();

  const placeholder = document.querySelector('.session-mark--empty');
  if (!(placeholder instanceof HTMLElement)) throw new Error('The fixture must render an empty mark slot.');
  expect(mouseEvent(placeholder, 'mousedown', 1)).toBe(true);
  expect(mouseEvent(placeholder, 'auxclick', 1)).toBe(true);
  expect(open).not.toHaveBeenCalled();
  expectInspectorClosed();
});

it('keeps ordinary left-click selection and exposes the same URL in the inspector', async () => {
  const user = userEvent.setup();
  const {mark, open} = renderGroupedMark();

  await user.click(mark);
  expect(open).not.toHaveBeenCalled();
  expect(mark.getAttribute('aria-pressed')).toBe('true');
  expect(mark.getAttribute('aria-expanded')).toBe('true');
  expect(document.querySelector('.ishiban-board')?.getAttribute('data-inspector-open')).toBe('true');
  const link = screen.getByRole('link', {name: 'Open in Lody'});
  expect(link.getAttribute('href')).toBe(GROUPED_URL);
  expect(link.getAttribute('target')).toBe('_blank');
  expect(link.getAttribute('rel')).toBe('noreferrer');
  expect(within(screen.getByRole('complementary')).getByText('child-0').tagName).toBe('CODE');
});
