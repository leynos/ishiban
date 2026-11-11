/** @file Check family roots and membership against a bounded graph oracle. */
import {expect, it} from 'bun:test';
import fc from 'fast-check';
import type {Session} from '../src/contracts';
import {groupSessions} from '../src/session-families';
import {createBoardSnapshot, firstSession} from './board-fixtures';

const template = firstSession(createBoardSnapshot());

/** Map parent indices: parentIdFor(-1, ['node-00']) gives 'absent-parent'. */
function parentIdFor(parent: number, ids: readonly string[]): string | null {
  if (parent === -2) return null;
  if (parent === -1) return 'absent-parent';
  return ids[parent] ?? 'absent-parent';
}

/** Build records: graphSessions([-1, 0]) gives a missing-parent root and child. */
function graphSessions(parents: readonly number[]): Session[] {
  const ids = parents.map((_, index) => `node-${String(index).padStart(2, '0')}`);
  return parents.map((parent, index) => ({
    ...template,
    sessionId: ids[index] ?? `node-${index}`,
    parentSessionId: parentIdFor(parent, ids),
    source: 'metadata',
    state: 'idle',
    createdAt: null
  }));
}

/** Expand a row: expandThrough([new Set([0, 1]), new Set([1, 2])], 0, 1) adds 2 to row 0. */
function expandThrough(reachable: readonly Set<number>[], from: number, via: number): void {
  const row = reachable[from];
  if (!row?.has(via)) return;
  for (const target of reachable[via] ?? []) row.add(target);
}

/** Close edges: reachability([-2, 0])[1] contains both node indices. */
function reachability(parents: readonly number[]): Set<number>[] {
  const nodes = [...parents.keys()];
  const reachable = nodes.map((from) => {
    const parent = parents[from];
    const row = new Set([from]);
    if (parent !== undefined && parent >= 0) row.add(parent);
    return row;
  });
  for (const via of nodes) {
    for (const from of nodes) expandThrough(reachable, from, via);
  }
  return reachable;
}

/** Find terminal nodes: isTerminalCandidate(-1, 0, []) is true. */
function isTerminalCandidate(
  parent: number | undefined,
  candidate: number,
  reachable: readonly Set<number>[]
): boolean {
  if (parent === undefined || parent < 0) return true;
  return reachable[parent]?.has(candidate) ?? false;
}

/** Find roots: expectedRootIndices([1, 0, 1]) gives [0, 0, 0]. */
function expectedRootIndices(parents: readonly number[]): number[] {
  const nodes = [...parents.keys()];
  const reachable = reachability(parents);
  return nodes.map((from) => {
    const terminal = nodes.filter((candidate) => {
      return reachable[from]?.has(candidate) && isTerminalCandidate(parents[candidate], candidate, reachable);
    });
    const root = terminal.toSorted((left, right) => left - right)[0];
    if (root === undefined) throw new Error('Every finite parent graph needs a terminal component.');
    return root;
  });
}

/** Check families: expectFamiliesToMatchGraph([-1, 0]) verifies the orphan chain. */
function expectFamiliesToMatchGraph(parents: readonly number[]): void {
  const sessions = graphSessions(parents);
  const rootIndices = expectedRootIndices(parents);
  const expected = new Map<string, string[]>();
  sessions.forEach((session, index) => {
    const rootId = sessions[rootIndices[index] ?? -1]?.sessionId;
    if (rootId === undefined) throw new Error('The graph oracle returned an absent root.');
    expected.set(rootId, [...(expected.get(rootId) ?? []), session.sessionId]);
  });

  const families = groupSessions(sessions, new Map());
  expect(families.map(({rootId}) => rootId)).toEqual([...expected.keys()].toSorted());
  expect(families.flatMap(({members}) => members.map(({sessionId}) => sessionId)).toSorted()).toEqual(
    sessions.map(({sessionId}) => sessionId).toSorted()
  );
  for (const family of families) {
    const expectedContext = sessions.find(({sessionId}) => sessionId === family.rootId);
    const expectedMembers = expected.get(family.rootId);
    if (expectedContext === undefined || expectedMembers === undefined) {
      throw new Error('A family root must identify its expected present component.');
    }
    expect(family.context).toBe(expectedContext);
    expect(family.members.map(({sessionId}) => sessionId)).toEqual(expectedMembers);
  }
}

it.each([
  ['unlinked roots', [-2, -2]],
  ['siblings sharing an absent parent', [-1, -1]],
  ['a chain ending at an absent parent', [-1, 0, 1]],
  ['a self-parent and its child', [0, 0]],
  ['a two-node cycle and its child', [1, 0, 1]],
  ['a path entering a cycle', [1, 2, 1, 0]]
] as const)('matches the graph oracle for %s', (_name, parents) => {
  expectFamiliesToMatchGraph(parents);
});

it('matches terminal roots and membership across generated parent graphs', () => {
  fc.assert(
    fc.property(
      fc
        .integer({min: 1, max: 9})
        .chain((size) => fc.array(fc.integer({min: -2, max: size - 1}), {minLength: size, maxLength: size})),
      expectFamiliesToMatchGraph
    ),
    {numRuns: 100}
  );
});
