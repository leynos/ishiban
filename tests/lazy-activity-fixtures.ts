/** @file Share seeded activity fixtures and NDJSON frame helpers across lazy tests. */
import type {Session, Snapshot, SessionActivityFrame} from '../src/contracts';
import {createDemoSnapshot} from '../src/demo';
import type {ActivityFetchRequest} from './activity-fetch-fixture';

/** One compact demo-seeded activity fixture specification. */
export type ActivitySessionSpec = readonly [number, string, string, Session['source'], Session['state'], number];

const seedSnapshot = createDemoSnapshot();

/**
 * Reuse demo projections while giving every fixture explicit source facts.
 * @param spec Seed index, identity, title, source, state and event revision.
 * @returns A fresh session projection with the supplied identity.
 * @throws {Error} When the demo snapshot lacks the requested seed record.
 */
export function activitySession(spec: ActivitySessionSpec): Session {
  const [seedIndex, sessionId, title, source, state, lastEventId] = spec;
  const session = seedSnapshot.sessions[seedIndex];
  if (!session) throw new Error('The demo snapshot must contain activity fixture records.');
  return {...session, sessionId, title, source, state, lastEventId};
}

const activitySessions = (
  [
    [0, 'known', 'Known persisted activity', 'persisted', 'running', 80],
    [1, 'demo-unknown', 'Demo unknown activity', 'demo', 'unknown', 81],
    [2, 'persisted/session 01', 'Unknown persisted activity 01', 'persisted', 'unknown', 82],
    [3, 'persisted-session-02', 'Unknown persisted activity 02', 'persisted', 'unknown', 83],
    [4, 'persisted-session-03', 'Unknown persisted activity 03', 'persisted', 'unknown', 84],
    [5, 'persisted-session-04', 'Unknown persisted activity 04', 'persisted', 'unknown', 85]
  ] as const satisfies readonly ActivitySessionSpec[]
).map((spec) => activitySession(spec));

export const KNOWN_SESSION = requiredSession(0);
export const DEMO_UNKNOWN_SESSION = requiredSession(1);
export const UNKNOWN_REAL_ONE = requiredSession(2);
export const UNKNOWN_REAL_TWO = requiredSession(3);
export const UNKNOWN_REAL_THREE = requiredSession(4);
export const UNKNOWN_REAL_FOUR = requiredSession(5);

/** Fail clearly if the compact session fixture is missing a requested record. */
function requiredSession(index: number): Session {
  const session = activitySessions[index];
  if (!session) throw new Error('The activity fixture must contain the requested session.');
  return session;
}

/**
 * Build a connected workspace snapshot containing only the requested sessions.
 * @param sessions Sessions the case wants rendered and observed.
 * @returns A connected snapshot scoped to the lazy-activity workspace.
 */
export function activitySnapshot(sessions: readonly Session[]): Snapshot {
  return {
    ...seedSnapshot,
    workspaceId: 'workspace-lazy-activity',
    cursor: 700,
    collector: {...seedSnapshot.collector, state: 'connected'},
    sessions: [...sessions]
  };
}

/**
 * Encode one completed member while preserving its explicit request identity.
 * @param workspaceId Workspace the frame claims.
 * @param session Session projection the frame carries.
 * @returns A frame ready for {@link resolveBatch}.
 */
export function activityFrame(workspaceId: string, session: Session): SessionActivityFrame {
  return {workspaceId, sessionId: session.sessionId, session};
}

/**
 * Complete a streaming batch using independently validated NDJSON frames.
 * @param request The captured POST whose response is held.
 * @param frames Frames the batch should stream.
 */
export function resolveBatch(request: ActivityFetchRequest, frames: readonly SessionActivityFrame[]): void {
  const body = `${frames.map((frame) => JSON.stringify(frame)).join('\n')}\n`;
  request.response.resolve(new Response(body, {headers: {'content-type': 'application/x-ndjson'}}));
}

/**
 * Return a stream that exposes one frame before the batch completes.
 * @param request The captured POST whose response is held.
 * @param frame The single member to expose early.
 * @returns A response whose stream stays open until the request aborts.
 */
export function earlyActivityResponse(request: ActivityFetchRequest, frame: SessionActivityFrame): Response {
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(`${JSON.stringify(frame)}\n`));
        request.init.signal?.addEventListener('abort', () => controller.close(), {once: true});
      }
    })
  );
}

/**
 * Resolve the held first batch with the shared unknown member's running activity.
 * @param request The captured first batch request.
 * @param snapshot Workspace the frame must claim.
 * @param overrides Session fields the case wants to change.
 */
export function resolveRunningMember(
  request: ActivityFetchRequest,
  snapshot: Snapshot,
  overrides: Partial<Session> = {}
): void {
  resolveBatch(request, [
    activityFrame(snapshot.workspaceId, {...UNKNOWN_REAL_ONE, ...overrides, state: 'running', activitySource: 'lazy'})
  ]);
}

/**
 * Return the open tooltip's rendered text while one is mounted.
 * @returns The tooltip's text content, or an empty string when none is open.
 */
export function tooltipText(): string {
  return document.querySelector('.task-tooltip')?.textContent ?? '';
}
