/** @file Check independent update cues across generated two-session histories. */
import {expect, it, jest} from 'bun:test';
import {act, cleanup, renderHook} from '@testing-library/react';
import fc from 'fast-check';
import type {Session, Snapshot} from '../src/contracts';
import {useSessionUpdates} from '../src/ui/session-updates';
import {createBoardSnapshot} from './board-fixtures';

const CUE_LIFETIME_MS = 900;
const operations = [
  'event-a',
  'event-b',
  'runtime-a',
  'runtime-b',
  'revision-a',
  'revision-b',
  'lazy-a',
  'lazy-b',
  'advance-1',
  'advance-450',
  'advance-449',
  'advance-899',
  'advance-900',
  'connecting',
  'catalogue-ready',
  'following',
  'generation',
  'workspace'
] as const;
type Operation = (typeof operations)[number];
type SessionOperation = Extract<Operation, `${'event' | 'runtime' | 'revision' | 'lazy'}-${'a' | 'b'}`>;
type BoundaryOperation = Exclude<Operation, SessionOperation | `advance-${number}`>;
const collectorStates: Record<Exclude<BoundaryOperation, 'workspace'>, string> = {
  connecting: 'connecting',
  'catalogue-ready': 'catalogue_ready',
  following: 'following',
  generation: 'following'
};

/** Recognize an operation's source without a cast at the test boundary. */
function isSessionOperation(operation: Operation): operation is SessionOperation {
  return operation.endsWith('-a') || operation.endsWith('-b');
}

/** Recognize a bounded fake-clock operation. */
function isAdvanceOperation(operation: Operation): operation is Extract<Operation, `advance-${number}`> {
  return operation.startsWith('advance-');
}

interface ExpectedCue {
  readonly revision: number;
  readonly expiresAt: number;
}

interface Scenario {
  snapshot: Snapshot;
  now: number;
  readonly cues: Map<string, ExpectedCue>;
  readonly rerender: (props: {snapshot: Snapshot}) => void;
  readonly read: () => ReadonlyMap<string, number>;
}

/** Replace one source record without using the production cue comparator. */
function replaceSession(snapshot: Snapshot, index: number, replacement: Session): Snapshot {
  const sessions = [...snapshot.sessions];
  sessions[index] = replacement;
  return {...snapshot, cursor: snapshot.cursor + 1, sessions};
}

/** Retire only cues whose independently modelled lifetime has elapsed. */
function expireCues(scenario: Scenario): void {
  for (const [id, cue] of scenario.cues) {
    if (cue.expiresAt <= scenario.now) void scenario.cues.delete(id);
  }
}

/** Advance through each expected expiry so React can schedule the next timer. */
function advanceClock(scenario: Scenario, milliseconds: number): void {
  const target = scenario.now + milliseconds;
  while (scenario.now < target) {
    const nextExpiry = Math.min(...[...scenario.cues.values()].map((cue) => cue.expiresAt), target);
    const nextTime = Math.min(target, Math.max(scenario.now + 1, nextExpiry));
    act(() => {
      void jest.advanceTimersByTime(nextTime - scenario.now);
    });
    scenario.now = nextTime;
    expireCues(scenario);
  }
}

/** Produce an immutable source record for the independent action model. */
function changedSession(previous: Session, operation: SessionOperation): Session {
  if (operation.startsWith('event-')) {
    const {activitySource: _discard, ...rest} = previous;
    return {...rest, title: `${previous.title}!`, lastEventId: previous.lastEventId + 1};
  }
  if (operation.startsWith('runtime-')) {
    const {activitySource: _discard, ...rest} = previous;
    return {...rest, state: previous.state === 'running' ? 'idle' : 'running', lastEventId: previous.lastEventId + 1};
  }
  if (operation.startsWith('revision-')) {
    return {...previous, lastEventId: previous.lastEventId + 1, lastObservedAt: (previous.lastObservedAt ?? 0) + 1};
  }
  return {...previous, state: previous.state === 'running' ? 'idle' : 'running', activitySource: 'lazy'};
}

/** Apply one domain action to one member and its expected cue. */
function updateSession(scenario: Scenario, operation: SessionOperation): void {
  const index = operation.endsWith('-a') ? 0 : 1;
  const previous = scenario.snapshot.sessions[index];
  if (!previous) throw new Error('The two-session fixture lost a member.');
  const next = changedSession(previous, operation);
  scenario.snapshot = replaceSession(scenario.snapshot, index, next);
  const isStartup = ['connecting', 'catalogue_ready'].includes(scenario.snapshot.collector.state);
  if (isStartup) {
    scenario.cues.clear();
  } else if (operation.startsWith('lazy-')) {
    void scenario.cues.delete(previous.sessionId);
  } else if (operation.startsWith('event-') || operation.startsWith('runtime-')) {
    scenario.cues.set(previous.sessionId, {revision: next.lastEventId, expiresAt: scenario.now + CUE_LIFETIME_MS});
  }
  scenario.rerender({snapshot: scenario.snapshot});
}

/** Reset workspace identity and its presentation baseline. */
function changeWorkspace(scenario: Scenario): void {
  scenario.snapshot = {
    ...scenario.snapshot,
    workspaceId: scenario.snapshot.workspaceId === 'model-a' ? 'model-b' : 'model-a'
  };
  scenario.cues.clear();
  scenario.rerender({snapshot: scenario.snapshot});
}

/** Move the collector state or generation and model its quiet boundary. */
function updateBoundary(scenario: Scenario, operation: BoundaryOperation): void {
  if (operation === 'workspace') {
    changeWorkspace(scenario);
    return;
  }
  const previousState = scenario.snapshot.collector.state;
  const state = collectorStates[operation];
  scenario.snapshot = {
    ...scenario.snapshot,
    collector: {
      ...scenario.snapshot.collector,
      state,
      generation: scenario.snapshot.collector.generation + (operation === 'generation' ? 1 : 0)
    }
  };
  const isStartupExit = ['connecting', 'catalogue_ready'].includes(previousState);
  if (operation !== 'following' || isStartupExit) scenario.cues.clear();
  scenario.rerender({snapshot: scenario.snapshot});
}

/** Read cue revisions without sharing the hook's comparison implementation. */
function checkCues(scenario: Scenario): void {
  const actual = [...scenario.read()].toSorted(([left], [right]) => left.localeCompare(right));
  const expected = [...scenario.cues]
    .map(([id, cue]): [string, number] => [id, cue.revision])
    .toSorted(([left], [right]) => left.localeCompare(right));
  expect(actual).toEqual(expected);
}

/** Drive one finite history with a real hook and an operation-level oracle. */
function verifyHistory(history: readonly Operation[]): void {
  jest.useFakeTimers();
  try {
    const fixture = createBoardSnapshot();
    const initial: Snapshot = {
      ...fixture,
      workspaceId: 'model-a',
      collector: {...fixture.collector, state: 'following'}
    };
    expect(initial.sessions).toHaveLength(2);
    const hook = renderHook(({snapshot}) => useSessionUpdates(snapshot), {initialProps: {snapshot: initial}});
    const scenario: Scenario = {
      snapshot: initial,
      now: Date.now(),
      cues: new Map(),
      rerender: hook.rerender,
      read: () => hook.result.current
    };
    checkCues(scenario);
    for (const operation of history) {
      if (isAdvanceOperation(operation)) {
        const milliseconds = Number(operation.slice('advance-'.length));
        advanceClock(scenario, milliseconds);
      } else if (isSessionOperation(operation)) {
        updateSession(scenario, operation);
      } else {
        updateBoundary(scenario, operation);
      }
      checkCues(scenario);
    }
  } finally {
    cleanup();
    jest.useRealTimers();
  }
}

it('isolates cues, honours expiry, and keeps lazy and restart updates quiet across histories', () => {
  verifyHistory([
    'event-a',
    'event-b',
    'lazy-a',
    'advance-450',
    'event-a',
    'advance-450',
    'revision-a',
    'advance-449',
    'advance-1',
    'connecting',
    'event-b',
    'following',
    'event-b',
    'generation',
    'event-a',
    'workspace',
    'event-b'
  ]);
  verifyHistory(['runtime-b', 'advance-1', 'event-a', 'advance-900', 'event-a']);
  verifyHistory(['lazy-b', 'event-b', 'event-a']);
  verifyHistory(['catalogue-ready', 'event-a', 'following', 'event-b']);
  const histories = fc.array(fc.constantFrom(...operations), {minLength: 1, maxLength: 14});
  fc.assert(fc.property(histories, verifyHistory), {
    numRuns: 50
  });
});
