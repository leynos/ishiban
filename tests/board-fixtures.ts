/** @file Share small, immutable demo fixtures across board interaction tests. */
import type {Session, Snapshot} from '../src/contracts';
import {createDemoSnapshot} from '../src/demo';

/**
 * Build a two-session board without changing the demo records' public shape.
 * @returns A fresh snapshot containing two adjacent planning marks.
 * @example
 * createBoardSnapshot().sessions.length === 2;
 */
export function createBoardSnapshot(): Snapshot {
  const snapshot = createDemoSnapshot();
  return {...snapshot, sessions: snapshot.sessions.slice(0, 2)};
}

/**
 * Read the first stable session required by these interaction scenarios.
 * @param snapshot The nonempty board fixture.
 * @returns The first session, rejecting an invalid empty fixture.
 * @throws {Error} When the fixture has no first session.
 * @example
 * firstSession(createBoardSnapshot()).sessionId === 'demo-session-001-01';
 */
export function firstSession(snapshot: Snapshot): Session {
  const first = snapshot.sessions[0];
  if (first === undefined) throw new Error('The board fixture must include its first session.');
  return first;
}

/**
 * Change the first fixture session without mutating its source snapshot.
 * @param snapshot The original fixture.
 * @param changes The session fields changed by the scenario.
 * @returns A snapshot with the same session order and count.
 * @example
 * updateFirstSession(createBoardSnapshot(), {lastEventId: 100});
 */
export function updateFirstSession(snapshot: Snapshot, changes: Partial<Session>): Snapshot {
  const replacement = {...firstSession(snapshot), ...changes};
  return {...snapshot, sessions: [replacement, ...snapshot.sessions.slice(1)]};
}

/**
 * Move the first session to another repository and workflow stage on a new event.
 * @param snapshot The original two-session fixture.
 * @returns The moved session's snapshot with a newer observation revision.
 * @example
 * moveFirstSession(createBoardSnapshot()).sessions[0]?.stage === 'ready';
 */
export function moveFirstSession(snapshot: Snapshot): Snapshot {
  return updateFirstSession(snapshot, {
    lastEventId: firstSession(snapshot).lastEventId + 100,
    repoFullName: 'demo/repository-moved',
    stage: 'ready',
    stageReason: 'Demo classification: one Plan-prefixed pull request is open.'
  });
}

/**
 * Describe unresolved collector activity; for example, seed an unknown session.
 * @param revision The full active-turn semantic revision.
 * @returns The shared runtime fields for unknown activity fixtures.
 * @example
 * unknownRuntime('a'.repeat(64)).activeTurnCount === 0;
 */
export function unknownRuntime(
  revision: string
): Pick<
  Session,
  | 'state'
  | 'source'
  | 'freshness'
  | 'latestTurn'
  | 'activeTurns'
  | 'activeTurnCount'
  | 'activeTurnsTruncated'
  | 'activeTurnsRevision'
> {
  return {
    state: 'unknown',
    source: 'metadata',
    freshness: 'unavailable',
    latestTurn: null,
    activeTurns: [],
    activeTurnCount: 0,
    activeTurnsTruncated: false,
    activeTurnsRevision: revision
  };
}

/**
 * Build linked raw sessions with root workflow evidence and child activity.
 * @param count Number of independent two-tab families.
 * @param workspaceId Workspace scope for recency and board scenarios.
 * @returns A catalogue preserving every raw tab while sharing family structure.
 * @example
 * createFamilySnapshot(1).sessions.map((session) => session.sessionId); // ['root-0', 'child-0']
 */
export function createFamilySnapshot(count: number, workspaceId = 'family-workspace'): Snapshot {
  const initial = createBoardSnapshot();
  const template = firstSession(initial);
  const sessions: Session[] = [];
  for (let index = 0; index < count; index += 1) {
    const rootId = `root-${index}`;
    const root: Session = {
      ...template,
      sessionId: rootId,
      parentSessionId: null,
      createdAt: '2026-10-28T14:37:17.051Z',
      title: 'Root planning work',
      branchName: 'feature/root-work',
      stage: 'refine',
      state: 'idle',
      source: 'persisted',
      latestTurn: {userTurnId: 'old', state: 'failed', error: 'Earlier failure'},
      pullRequests: [{url: 'https://github.com/example/repo/pull/492', title: 'Implement root work', status: 'open'}]
    };
    sessions.push(root, {
      ...root,
      sessionId: `child-${index}`,
      parentSessionId: rootId,
      createdAt: '2026-11-05T14:55:35.407Z',
      title: 'Child execution',
      branchName: null,
      stage: 'planning',
      state: 'running',
      latestTurn: {userTurnId: 'current', state: 'running', error: null},
      pullRequests: []
    });
  }
  return {...initial, workspaceId, workspaceSlug: 'leynos', sessions};
}
