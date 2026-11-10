/** @file Verify density controls and session-update pulse lifetimes. */
import {afterEach, expect, it, jest} from 'bun:test';
import {act, cleanup, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Board} from '../src/ui/board';
import {createBoardSnapshot, firstSession, moveFirstSession, updateFirstSession} from './board-fixtures';

afterEach(() => {
  cleanup();
  jest.useRealTimers();
});

/** Query the first session through its accessible name. */
function getFirstMark() {
  return screen.getByRole('button', {name: /demo\/repository-001: Synthetic planning task 01/u});
}

/** Inspect the CSS-only cue because the pulse is deliberately hidden from AT. */
function getPulse(mark: HTMLElement): Element | null {
  return mark.querySelector('[data-session-update-pulse]');
}

it('offers five named density levels and applies every selected value', async () => {
  const user = userEvent.setup();
  render(<Board connection="demo" snapshot={createBoardSnapshot()} />);
  const density = screen.getByRole('combobox', {name: 'Mark density'});
  if (!(density instanceof HTMLSelectElement)) {
    throw new Error('Mark density must use a native select control.');
  }
  const labels = Array.from(density.options, (option) => option.textContent);

  expect(labels).toEqual(['Overview', 'Compact', 'Balanced', 'Roomy', 'Comfortable']);
  for (const value of ['overview', 'compact', 'balanced', 'roomy', 'comfortable']) {
    await user.selectOptions(density, value);
    expect(density.value).toBe(value);
  }
});

it('does not pulse the initial demo snapshot', () => {
  render(<Board connection="demo" snapshot={createBoardSnapshot()} />);

  expect(getFirstMark().getAttribute('data-update-revision')).toBeNull();
  expect(getPulse(getFirstMark())).toBeNull();
});

it('pulses a new event revision and restarts only when that revision changes', async () => {
  const user = userEvent.setup();
  const initial = createBoardSnapshot();
  const {rerender} = render(<Board connection="demo" snapshot={initial} />);
  const originalMark = getFirstMark();
  const first = firstSession(initial);

  rerender(<Board connection="demo" snapshot={updateFirstSession(initial, {lastEventId: first.lastEventId + 100})} />);
  const updatedMark = getFirstMark();
  const firstPulse = getPulse(updatedMark);
  expect(updatedMark).toBe(originalMark);
  expect(updatedMark.getAttribute('data-update-revision')).toBe(String(first.lastEventId + 100));
  expect(firstPulse).not.toBeNull();

  const updated = updateFirstSession(initial, {lastEventId: first.lastEventId + 100});
  rerender(<Board connection="demo" snapshot={{...updated, cursor: updated.cursor + 1}} />);
  expect(getPulse(getFirstMark())).toBe(firstPulse);

  await user.selectOptions(screen.getByRole('combobox', {name: 'Mark density'}), 'balanced');
  await user.type(screen.getByRole('searchbox', {name: 'Find repository, session or branch'}), 'Synthetic planning');
  expect(getPulse(getFirstMark())).toBe(firstPulse);

  rerender(<Board connection="demo" snapshot={updateFirstSession(initial, {lastEventId: first.lastEventId + 101})} />);
  expect(getFirstMark().getAttribute('data-update-revision')).toBe(String(first.lastEventId + 101));
  expect(getPulse(getFirstMark())).not.toBe(firstPulse);
});

it('does not pulse metadata-only changes that keep the event identifier', () => {
  const initial = createBoardSnapshot();
  const {rerender} = render(<Board connection="demo" snapshot={initial} />);
  const first = firstSession(initial);

  rerender(
    <Board
      connection="demo"
      snapshot={updateFirstSession(initial, {
        lastMetadataGeneration: 2,
        lastEventId: first.lastEventId,
        source: 'metadata',
        freshness: 'unavailable',
        title: 'Synthetic planning task 01 metadata refresh'
      })}
    />
  );

  const metadataRefreshMark = screen.getByRole('button', {name: /metadata refresh/u});
  expect(metadataRefreshMark.getAttribute('data-update-revision')).toBeNull();
  expect(metadataRefreshMark.getAttribute('data-last-turn-failed')).toBe('true');
  expect(metadataRefreshMark.getAttribute('aria-label')).toContain('last known turn failed');
});

it('pulses a session that moves repository and stage on a new event', () => {
  const initial = createBoardSnapshot();
  const {rerender} = render(<Board connection="demo" snapshot={initial} />);
  const first = firstSession(initial);
  const moved = moveFirstSession(initial);

  rerender(<Board connection="demo" snapshot={moved} />);

  const movedMark = screen.getByRole('button', {name: /repository-moved: Synthetic planning task 01/u});
  expect(movedMark.getAttribute('data-stage')).toBe('ready');
  expect(movedMark.getAttribute('data-update-revision')).toBe(String(first.lastEventId + 100));
});

it('expires pulse cues before unchanged snapshots return through filters or density changes', async () => {
  jest.useFakeTimers();
  const user = userEvent.setup({advanceTimers: jest.advanceTimersByTime});
  const initial = createBoardSnapshot();
  const first = firstSession(initial);
  const updated = updateFirstSession(initial, {lastEventId: first.lastEventId + 100});
  const {rerender} = render(<Board connection="demo" snapshot={initial} />);
  rerender(<Board connection="demo" snapshot={updated} />);

  expect(getFirstMark().getAttribute('data-update-revision')).toBe(String(first.lastEventId + 100));
  await act(async () => {
    jest.advanceTimersByTime(901);
  });
  await user.selectOptions(screen.getByRole('combobox', {name: 'Mark density'}), 'balanced');
  await user.clear(screen.getByRole('searchbox', {name: 'Find repository, session or branch'}));

  expect(getFirstMark().getAttribute('data-update-revision')).toBeNull();
  expect(getPulse(getFirstMark())).toBeNull();
});

it('resets the event baseline when switching workspace', () => {
  const initial = createBoardSnapshot();
  const {rerender} = render(<Board connection="demo" snapshot={initial} />);
  const nextWorkspace = {...initial, workspaceId: 'another-workspace'};

  rerender(<Board connection="live" snapshot={nextWorkspace} />);

  expect(getFirstMark().getAttribute('data-update-revision')).toBeNull();
  expect(screen.getByText(/another-workspace/u)).toBeTruthy();
});

it('does not pulse the initial live snapshot after demo mode in the same workspace', () => {
  const initial = createBoardSnapshot();
  const {rerender} = render(<Board connection="demo" snapshot={initial} />);
  const liveSnapshot = {
    ...initial,
    collector: {...initial.collector, state: 'ready'}
  };

  rerender(<Board connection="connected" snapshot={liveSnapshot} />);

  expect(getFirstMark().getAttribute('data-update-revision')).toBeNull();
});

it('removes an existing cue when unknown activity resolves lazily', () => {
  const initial = createBoardSnapshot();
  const first = firstSession(initial);
  const updated = updateFirstSession(initial, {lastEventId: first.lastEventId + 100, state: 'unknown'});
  const {rerender} = render(<Board connection="live" snapshot={initial} />);
  rerender(<Board connection="live" snapshot={updated} />);
  expect(getPulse(getFirstMark())).not.toBeNull();
  const resolved = updateFirstSession(updated, {state: 'idle', activitySource: 'lazy'});
  rerender(<Board connection="live" snapshot={resolved} />);
  expect(getPulse(getFirstMark())).toBeNull();
  expect(getFirstMark().getAttribute('data-update-revision')).toBeNull();
});
