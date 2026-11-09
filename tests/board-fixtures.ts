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
