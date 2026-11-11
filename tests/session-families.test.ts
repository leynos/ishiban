/** @file Specify root context and selected activity for parent-linked sessions. */
import {expect, it} from 'bun:test';
import fc from 'fast-check';
import type {Session} from '../src/contracts';
import {groupSessions, type RecencyFact} from '../src/session-families';
import {createBoardSnapshot, firstSession} from './board-fixtures';

const baseSession = firstSession(createBoardSnapshot());
const availableOutcome = {outcome: 'available'} as const;

interface GeneratedGraph {
  readonly sessions: Session[];
  readonly recency: Map<string, RecencyFact>;
}

/** Build a real-shaped session while keeping each test focused on its graph facts. */
function sessionRecord(sessionId: string, changes: Partial<Session> = {}): Session {
  return {
    ...baseSession,
    sessionId,
    parentSessionId: null,
    createdAt: null,
    source: 'metadata',
    freshness: 'synced',
    state: 'idle',
    latestTurn: null,
    activeTurns: [],
    ...changes
  };
}

/** Mark a history lookup that completed successfully, including an empty history. */
function available(latestHistoryAt: string | null): RecencyFact {
  return {...availableOutcome, latestHistoryAt} satisfies RecencyFact;
}

interface RecencySelectionCase {
  readonly name: string;
  readonly root: Session;
  readonly child: Session;
  readonly facts: ReadonlyMap<string, RecencyFact>;
  readonly expectedActivityId: string;
}

const recencySelectionCases: readonly RecencySelectionCase[] = [
  {
    name: 'uses creation time for successful empty history',
    root: sessionRecord('empty-root', {createdAt: '2026-11-03T12:00:00Z'}),
    child: sessionRecord('empty-child', {
      parentSessionId: 'empty-root',
      createdAt: '2026-11-05T12:00:00Z'
    }),
    facts: new Map([
      ['empty-root', available('2026-11-03T12:00:00Z')],
      ['empty-child', available(null)]
    ]),
    expectedActivityId: 'empty-child'
  },
  {
    name: 'keeps the latest known history when another lookup failed',
    root: sessionRecord('known-root', {createdAt: '2026-11-10T11:00:00Z'}),
    child: sessionRecord('failed-child', {
      parentSessionId: 'known-root',
      createdAt: '2026-11-10T14:00:00Z'
    }),
    facts: new Map([
      ['known-root', available('2026-11-10T15:00:00Z')],
      ['failed-child', {outcome: 'unavailable'}]
    ]),
    expectedActivityId: 'known-root'
  }
];

/** Make the graph output comparable without hiding selected raw Session identities. */
function familyIds(families: ReturnType<typeof groupSessions>) {
  return families.map(({rootId, context, activity, members}) => ({
    rootId,
    contextId: context.sessionId,
    activityId: activity.sessionId,
    memberIds: members.map(({sessionId}) => sessionId)
  }));
}

/** Produce a parent edge that may be a cycle, a missing link, or a root. */
function generatedParentId(value: number, ids: readonly string[]): string | null {
  const choice = Math.abs(value * 31 + 17) % (ids.length + 2);
  if (choice === ids.length + 1) return null;
  if (choice === ids.length) return `missing-${choice}`;
  return ids[choice] ?? `missing-${choice}`;
}

/** Build one generated graph and complete history view for permutation checks. */
function generatedGraph(values: readonly number[]): GeneratedGraph {
  const sortedValues = values.toSorted((left, right) => left - right);
  const ids = sortedValues.map((value) => `session-${value}`);
  const sessions = sortedValues.map((value, index) =>
    sessionRecord(ids[index] ?? `session-${value}`, {
      parentSessionId: generatedParentId(value, ids),
      state: index % 2 === 0 ? 'running' : 'idle',
      createdAt: `2026-11-${String(index + 1).padStart(2, '0')}T12:00:00Z`
    })
  );
  const recency = new Map<string, RecencyFact>();
  sessions.forEach((session, index) => {
    recency.set(session.sessionId, available(`2026-11-${String(index + 1).padStart(2, '0')}T12:00:00Z`));
  });
  return {sessions, recency};
}

it('keeps the PR context root while provisional activity follows a running child', () => {
  const root = sessionRecord('cf63', {
    stage: 'refine',
    state: 'waiting',
    latestTurn: {userTurnId: 'root-turn', state: 'failed', error: 'Earlier failure'},
    pullRequests: [{url: 'https://example.test/pull/42', title: 'Review work', status: 'open'}]
  });
  const child = sessionRecord('9bc', {
    parentSessionId: root.sessionId,
    state: 'running',
    stage: 'planning',
    pullRequests: []
  });

  const pending = groupSessions([child, root], new Map());
  const pendingFamily = pending[0];
  expect(pending).toHaveLength(1);
  expect(pendingFamily?.rootId).toBe(root.sessionId);
  expect(pendingFamily?.context).toBe(root);
  expect(pendingFamily?.activity).toBe(child);
  expect(pendingFamily?.members).toEqual([child, root]);

  const resolved = groupSessions(
    [root, child],
    new Map([
      [root.sessionId, available('2026-11-10T13:00:00.000Z')],
      [child.sessionId, available('2026-11-10T12:00:00.000Z')]
    ])
  );
  expect(resolved[0]?.context).toBe(root);
  expect(resolved[0]?.activity).toBe(root);
});

it('retains a removed parent as context when one of its children is still present', () => {
  const root = sessionRecord('a-root', {removed: true, title: 'Parent PR context'});
  const child = sessionRecord('b-child', {
    parentSessionId: root.sessionId,
    removed: false,
    state: 'running'
  });
  const family = groupSessions([child, root], new Map())[0];

  expect(family?.context).toBe(root);
  expect(family?.members).toEqual([root, child]);
  expect(family?.members.filter((member) => !member.removed)).toEqual([child]);
  expect(family?.activity).toBe(child);
});

it('resolves missing parents as independent roots and cycles to the smallest member', () => {
  const orphan = sessionRecord('orphan', {parentSessionId: 'missing'});
  const orphanChild = sessionRecord('orphan-child', {parentSessionId: orphan.sessionId});
  const cycleA = sessionRecord('cycle-a', {parentSessionId: 'cycle-b'});
  const cycleB = sessionRecord('cycle-b', {parentSessionId: 'cycle-a'});
  const cycleChild = sessionRecord('cycle-child', {parentSessionId: cycleB.sessionId});

  const families = groupSessions([cycleChild, orphanChild, cycleB, orphan, cycleA], new Map());

  expect(familyIds(families)).toEqual([
    {
      rootId: 'cycle-a',
      contextId: 'cycle-a',
      activityId: 'cycle-a',
      memberIds: ['cycle-a', 'cycle-b', 'cycle-child']
    },
    {
      rootId: 'orphan',
      contextId: 'orphan',
      activityId: 'orphan',
      memberIds: ['orphan', 'orphan-child']
    }
  ]);
});

it('uses creation time then lexical identity to break equal history timestamps', () => {
  const root = sessionRecord('a-root', {
    createdAt: '2026-11-10T12:00:00Z',
    parentSessionId: null
  });
  const child = sessionRecord('b-child', {
    parentSessionId: root.sessionId,
    createdAt: '2026-11-10T13:00:00Z'
  });
  const sameCreation = sessionRecord('c-child', {
    parentSessionId: root.sessionId,
    createdAt: '2026-11-10T13:00:00Z'
  });
  const facts = new Map([
    [root.sessionId, available('2026-11-10T14:00:00Z')],
    [child.sessionId, available('2026-11-10T14:00:00Z')],
    [sameCreation.sessionId, available('2026-11-10T14:00:00Z')]
  ]);

  const firstOrder = groupSessions([root, child, sameCreation], facts);
  const reverseOrder = groupSessions([sameCreation, child, root], facts);
  expect(firstOrder[0]?.activity).toBe(child);
  expect(reverseOrder[0]?.activity).toBe(child);
  expect(familyIds(reverseOrder)).toEqual(familyIds(firstOrder));
});

it('distinguishes successful empty history from an unavailable lookup', () => {
  const root = sessionRecord('root', {
    state: 'running',
    createdAt: '2026-11-10T12:00:00Z'
  });
  const child = sessionRecord('child', {
    parentSessionId: root.sessionId,
    createdAt: '2026-11-10T13:00:00Z'
  });

  const successfulEmpty = groupSessions(
    [root, child],
    new Map([
      [root.sessionId, available(null)],
      [child.sessionId, available(null)]
    ])
  );
  const unavailableRoot = groupSessions(
    [root, child],
    new Map([
      [root.sessionId, {outcome: 'unavailable'}],
      [child.sessionId, available(null)]
    ])
  );

  expect(successfulEmpty[0]?.activity).toBe(child);
  expect(unavailableRoot[0]?.activity).toBe(root);
});

it.each(recencySelectionCases)('$name', ({root, child, facts, expectedActivityId}) => {
  expect(groupSessions([root, child], facts)[0]?.activity.sessionId).toBe(expectedActivityId);
});

it('falls back deterministically when history and creation timestamps are invalid', () => {
  const root = sessionRecord('a-root', {createdAt: '2026-02-30T13:00:00Z'});
  const child = sessionRecord('b-child', {
    parentSessionId: root.sessionId,
    createdAt: '2026-11-11T13:00:00Z'
  });
  const facts = new Map([
    [root.sessionId, available('2026-02-30T14:00:00Z')],
    [child.sessionId, available('not-an-iso-timestamp')]
  ]);

  expect(groupSessions([root, child], facts)[0]?.activity).toBe(child);
});

it('keeps provisional running activity when that member lookup becomes unavailable', () => {
  const root = sessionRecord('root', {state: 'waiting'});
  const child = sessionRecord('child', {parentSessionId: root.sessionId, state: 'running'});
  const knownRootHistory = new Map([[root.sessionId, available('2026-11-03T12:00:00Z')]]);
  const historyUnavailable = new Map([
    [root.sessionId, available('2026-11-03T12:00:00Z')],
    [child.sessionId, {outcome: 'unavailable'}]
  ]);

  expect(groupSessions([root, child], knownRootHistory)[0]?.activity).toBe(child);
  expect(groupSessions([root, child], historyUnavailable)[0]?.activity).toBe(child);
});

it('keeps a running tab provisional across generated retained timestamp orderings', () => {
  const root = sessionRecord('root', {state: 'idle'});
  const child = sessionRecord('child', {parentSessionId: 'root', state: 'running'});
  fc.assert(
    fc.property(
      fc.integer({min: 0, max: 100_000}),
      fc.integer({min: 0, max: 100_000}),
      fc.constantFrom('pending', 'unavailable'),
      (rootMinute, childMinute, outcome) => {
        const rootTime = new Date(Date.UTC(2026, 10, 1) + rootMinute * 60_000).toISOString();
        const childTime = new Date(Date.UTC(2026, 10, 1) + childMinute * 60_000).toISOString();
        const facts: ReadonlyMap<string, RecencyFact> = new Map([
          ['root', {outcome, lastKnownHistoryAt: rootTime}],
          ['child', available(childTime)]
        ]);
        const family = groupSessions([root, child], facts)[0];
        expect(family?.activity.sessionId).toBe('child');
        expect(family?.recencyIncomplete).toBe(true);
      }
    )
  );
});

it('is invariant under input reversal for generated parent graphs', () => {
  const graph = fc.uniqueArray(fc.integer({min: 0, max: 10_000}), {minLength: 1, maxLength: 8});

  fc.assert(
    fc.property(graph, (values) => {
      const {sessions, recency} = generatedGraph(values);
      const forward = groupSessions(sessions, recency);
      const reversed = groupSessions(sessions.toReversed(), recency);
      expect(familyIds(reversed)).toEqual(familyIds(forward));
    })
  );
});
