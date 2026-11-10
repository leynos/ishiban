/** @file Verify density controls and session-update pulse lifetimes. */
import {afterEach, expect, it, jest} from 'bun:test';
import {act, cleanup, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Board} from '../src/ui/board';
import {
  createBoardSnapshot,
  firstSession,
  moveFirstSession,
  unknownRuntime,
  updateFirstSession
} from './board-fixtures';

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

it('pulses a new session added after the initial snapshot', () => {
  const initial = createBoardSnapshot();
  const first = firstSession(initial);
  const {rerender} = render(<Board connection="Connected" snapshot={initial} />);
  const addedSession = {
    ...first,
    sessionId: 'new-session-after-startup',
    title: 'Newly observed session',
    lastEventId: first.lastEventId + 200
  };
  const next = {
    ...initial,
    cursor: initial.cursor + 1,
    sessions: [...initial.sessions, addedSession]
  };

  rerender(<Board connection="Connected" snapshot={next} />);

  const mark = screen.getByRole('button', {name: /Newly observed session/u});
  expect(mark.getAttribute('data-update-revision')).toBe(String(addedSession.lastEventId));
  expect(getPulse(mark)).not.toBeNull();
});

it('pulses a new event revision and restarts only when that revision changes', async () => {
  const user = userEvent.setup();
  const initial = createBoardSnapshot();
  const {rerender} = render(<Board connection="demo" snapshot={initial} />);
  const originalMark = getFirstMark();
  const first = firstSession(initial);
  const updated = updateFirstSession(initial, {
    lastEventId: first.lastEventId + 100,
    title: 'Synthetic planning task 01 revised'
  });

  rerender(<Board connection="demo" snapshot={updated} />);
  const updatedMark = getFirstMark();
  const firstPulse = getPulse(updatedMark);
  expect(updatedMark).toBe(originalMark);
  expect(updatedMark.getAttribute('data-update-revision')).toBe(String(first.lastEventId + 100));
  expect(firstPulse).not.toBeNull();

  const repeated = updateFirstSession(updated, {
    lastEventId: first.lastEventId + 101,
    lastObservedAt: 4567,
    lastMetadataGeneration: 4
  });
  rerender(<Board connection="demo" snapshot={repeated} />);
  expect(getPulse(getFirstMark())).toBe(firstPulse);
  expect(getFirstMark().getAttribute('data-update-revision')).toBe(String(first.lastEventId + 100));

  await user.selectOptions(screen.getByRole('combobox', {name: 'Mark density'}), 'balanced');
  await user.type(screen.getByRole('searchbox', {name: 'Find repository, session or branch'}), 'Synthetic planning');
  expect(getPulse(getFirstMark())).toBe(firstPulse);

  const meaningfulAgain = updateFirstSession(repeated, {
    lastEventId: first.lastEventId + 102,
    title: 'Synthetic planning task 01 revised again'
  });
  rerender(<Board connection="demo" snapshot={meaningfulAgain} />);
  expect(getFirstMark().getAttribute('data-update-revision')).toBe(String(first.lastEventId + 102));
  expect(getPulse(getFirstMark())).not.toBe(firstPulse);
});

it('ignores revision-only startup replay across metadata changes and generations', () => {
  const base = createBoardSnapshot();
  const initial = updateFirstSession(
    {...base, collector: {...base.collector, state: 'connected', generation: 1}},
    {source: 'persisted', freshness: 'synced'}
  );
  const first = firstSession(initial);
  const {rerender} = render(<Board connection="Connected" snapshot={initial} />);
  const expectNoPulse = () => {
    expect(getFirstMark().getAttribute('data-update-revision')).toBeNull();
    expect(getPulse(getFirstMark())).toBeNull();
  };

  const metadata = updateFirstSession(initial, {
    lastEventId: first.lastEventId + 1,
    lastObservedAt: 100,
    lastMetadataGeneration: 2,
    source: 'metadata',
    freshness: 'unavailable'
  });
  rerender(<Board connection="Connected" snapshot={metadata} />);
  expectNoPulse();

  const persisted = updateFirstSession(metadata, {
    lastEventId: first.lastEventId + 2,
    lastObservedAt: 200,
    lastMetadataGeneration: 3,
    source: 'persisted',
    freshness: 'synced'
  });
  rerender(<Board connection="Connected" snapshot={persisted} />);
  expectNoPulse();

  const connecting = updateFirstSession(
    {
      ...persisted,
      collector: {...persisted.collector, state: 'connecting', generation: 2}
    },
    {lastEventId: first.lastEventId + 3, lastObservedAt: 300}
  );
  rerender(<Board connection="Reconnecting" snapshot={connecting} />);
  expectNoPulse();

  const connectingReplay = updateFirstSession(connecting, {
    lastEventId: first.lastEventId + 4,
    lastObservedAt: 400,
    lastMetadataGeneration: 5
  });
  rerender(<Board connection="Reconnecting" snapshot={connectingReplay} />);
  expectNoPulse();

  const firstFollowingFrame = updateFirstSession(
    {
      ...connectingReplay,
      collector: {...connectingReplay.collector, state: 'connected'}
    },
    {lastEventId: first.lastEventId + 5, lastObservedAt: 500}
  );
  rerender(<Board connection="Connected" snapshot={firstFollowingFrame} />);
  expectNoPulse();

  const identicalLaterObservation = updateFirstSession(firstFollowingFrame, {
    lastEventId: first.lastEventId + 6,
    lastObservedAt: 600,
    source: 'metadata',
    freshness: 'unavailable'
  });
  rerender(<Board connection="Connected" snapshot={identicalLaterObservation} />);
  expectNoPulse();

  const actualChange = updateFirstSession(identicalLaterObservation, {
    lastEventId: first.lastEventId + 7,
    title: 'Synthetic planning task 01 after restart'
  });
  rerender(<Board connection="Connected" snapshot={actualChange} />);
  expect(getFirstMark().getAttribute('data-update-revision')).toBe(String(first.lastEventId + 7));
  expect(getPulse(getFirstMark())).not.toBeNull();
});

it('normalizes turn and pull-request order while pulsing their semantic changes', () => {
  const initial = createBoardSnapshot();
  const first = firstSession(initial);
  const {rerender} = render(<Board connection="Connected" snapshot={initial} />);
  const withFacts = updateFirstSession(initial, {
    lastEventId: first.lastEventId + 10,
    pullRequests: [
      {url: 'https://github.com/acme/repo/pull/1', title: 'One', status: 'open'},
      {url: 'https://github.com/acme/repo/pull/2', title: 'Two', status: 'draft'}
    ],
    latestTurn: {userTurnId: 'turn-1', state: 'failed', error: 'retry me'},
    activeTurns: [
      {userTurnId: 'turn-2', state: 'running'},
      {userTurnId: 'turn-3', state: 'waiting'}
    ]
  });
  rerender(<Board connection="Connected" snapshot={withFacts} />);
  const firstPulse = getPulse(getFirstMark());
  const withFactsSession = firstSession(withFacts);
  expect(firstPulse).not.toBeNull();

  const reordered = updateFirstSession(withFacts, {
    lastEventId: first.lastEventId + 11,
    pullRequests: withFactsSession.pullRequests.toReversed(),
    activeTurns: withFactsSession.activeTurns.toReversed(),
    lastObservedAt: 9876
  });
  rerender(<Board connection="Connected" snapshot={reordered} />);
  expect(getPulse(getFirstMark())).toBe(firstPulse);
  expect(getFirstMark().getAttribute('data-update-revision')).toBe(String(first.lastEventId + 10));

  const changedTurn = updateFirstSession(reordered, {
    lastEventId: first.lastEventId + 12,
    latestTurn: {userTurnId: 'turn-1', state: 'failed', error: 'still failing'}
  });
  rerender(<Board connection="Connected" snapshot={changedTurn} />);
  expect(getFirstMark().getAttribute('data-update-revision')).toBe(String(first.lastEventId + 12));
  expect(getPulse(getFirstMark())).not.toBe(firstPulse);
});

it('uses summary revisions for hidden turns and the visible set for partial frames', () => {
  const initial = updateFirstSession(createBoardSnapshot(), {
    activeTurns: [
      {userTurnId: 'visible-turn', state: 'running'},
      {userTurnId: 'second-turn', state: 'waiting'}
    ],
    activeTurnCount: 101,
    activeTurnsTruncated: true,
    activeTurnsRevision: 'a'.repeat(64)
  });
  const first = firstSession(initial);
  const {rerender} = render(<Board connection="Connected" snapshot={initial} />);
  const updateRevision = () => getFirstMark().getAttribute('data-update-revision');

  const hiddenChange = updateFirstSession(initial, {
    lastEventId: first.lastEventId + 1,
    activeTurnsRevision: 'b'.repeat(64)
  });
  rerender(<Board connection="Connected" snapshot={hiddenChange} />);
  expect(updateRevision()).toBe(String(first.lastEventId + 1));

  const reordered = updateFirstSession(hiddenChange, {
    lastEventId: first.lastEventId + 2,
    activeTurns: firstSession(hiddenChange).activeTurns.toReversed()
  });
  rerender(<Board connection="Connected" snapshot={reordered} />);
  expect(updateRevision()).toBe(String(first.lastEventId + 1));

  const partial = updateFirstSession(reordered, {
    lastEventId: first.lastEventId + 3,
    activeTurnsTruncated: undefined,
    activeTurns: [
      {userTurnId: 'second-turn', state: 'failed'},
      {userTurnId: 'visible-turn', state: 'running'}
    ]
  });
  rerender(<Board connection="Connected" snapshot={partial} />);
  expect(updateRevision()).toBe(String(first.lastEventId + 3));
});

it('keeps lazy runtime resolution quiet while pulsing metadata changes on lazy sessions', () => {
  const initial = updateFirstSession(createBoardSnapshot(), {
    ...unknownRuntime('a'.repeat(64))
  });
  const first = firstSession(initial);
  const {rerender} = render(<Board connection="Connected" snapshot={initial} />);
  const lazyResolution = updateFirstSession(initial, {
    lastEventId: first.lastEventId + 1,
    state: 'idle',
    source: 'persisted',
    freshness: 'synced',
    activitySource: 'lazy',
    latestTurn: {userTurnId: 'resolved-turn', state: 'failed', error: 'last turn failed'},
    activeTurnCount: 1,
    activeTurnsRevision: 'b'.repeat(64),
    lastObservedAt: 1234
  });
  rerender(<Board connection="Connected" snapshot={lazyResolution} />);
  expect(getFirstMark().getAttribute('data-update-revision')).toBeNull();
  expect(getPulse(getFirstMark())).toBeNull();

  const metadataChange = updateFirstSession(lazyResolution, {
    lastEventId: first.lastEventId + 2,
    title: 'Synthetic planning task 01 refreshed',
    stage: 'ready'
  });
  rerender(<Board connection="Connected" snapshot={metadataChange} />);
  expect(getFirstMark().getAttribute('data-update-revision')).toBe(String(first.lastEventId + 2));
  expect(getPulse(getFirstMark())).not.toBeNull();
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
  const updated = updateFirstSession(initial, {
    lastEventId: first.lastEventId + 100,
    title: 'Synthetic planning task 01 expires later'
  });
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
