/** @file Scoped Effect transport and an external immutable board store. */
import {Effect, Schedule, Schema} from 'effect';
import {CollectorSchema, CursorSchema, type Session, SessionSchema, type Snapshot, SnapshotSchema} from './contracts';

const SessionEvent = Schema.Struct({
  cursor: CursorSchema,
  workspaceId: Schema.String,
  sessionId: Schema.String,
  projection: SessionSchema
});
const CollectorEvent = Schema.Struct({cursor: CursorSchema, workspaceId: Schema.String, projection: CollectorSchema});
const SessionJSON = Schema.fromJsonString(SessionEvent);
const CollectorJSON = Schema.fromJsonString(CollectorEvent);
const SnapshotJSON = Schema.fromJsonString(SnapshotSchema);

export interface BoardState {
  readonly snapshot: Snapshot | undefined;
  readonly connection: string;
}
export interface BoardStore {
  readonly subscribe: (listener: () => void) => () => void;
  readonly getSnapshot: () => BoardState;
  readonly replace: (snapshot: Snapshot) => void;
  readonly status: (connection: string) => void;
  readonly session: (cursor: number, projection: Session) => void;
  readonly collector: (cursor: number, projection: typeof CollectorSchema.Type) => void;
  readonly activity: (workspaceId: string, session: Session) => void;
}

/**
 * Create the React external store; for example, replace it with one snapshot.
 * @param schedule Notification scheduler; browsers can coalesce on animation frames.
 * @returns An immutable projection store with stable subscription functions.
 */
export function createBoardStore(schedule: (notify: () => void) => void = queueMicrotask): BoardStore {
  let current: BoardState = {snapshot: undefined, connection: 'Connecting'};
  const listeners = new Set<() => void>();
  let isPending = false;
  const publish = (value: BoardState) => {
    current = value;
    if (isPending) return;
    isPending = true;
    schedule(() => {
      isPending = false;
      for (const listener of listeners) listener();
    });
  };
  const update = (cursor: number, change: (snapshot: Snapshot) => Snapshot) => {
    if (!current.snapshot || cursor <= current.snapshot.cursor) return;
    publish({...current, snapshot: {...change(current.snapshot), cursor}});
  };
  return {
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    getSnapshot: () => current,
    replace: (snapshot) => publish({snapshot: retainActivity(current.snapshot, snapshot), connection: 'Connected'}),
    status: (connection) => publish({...current, connection}),
    session: (cursor, projection) =>
      update(cursor, (snapshot) => ({
        ...snapshot,
        sessions: replaceSession(snapshot.sessions, projection)
      })),
    collector: (cursor, projection) => update(cursor, (snapshot) => ({...snapshot, collector: projection})),
    activity: (workspaceId, session) => {
      const snapshot = withActivity(current.snapshot, workspaceId, session);
      if (snapshot) publish({...current, snapshot});
    }
  };
}

/** Apply ephemeral activity only to a matching unknown revision; for example, reject a late response. */
function withActivity(snapshot: Snapshot | undefined, workspaceId: string, session: Session): Snapshot | undefined {
  if (!snapshot) return undefined;
  if (snapshot.workspaceId !== workspaceId) return undefined;
  const previous = snapshot.sessions.find((item) => item.sessionId === session.sessionId);
  if (!previous) return undefined;
  if (previous.state !== 'unknown') return undefined;
  if (previous.lastEventId !== session.lastEventId) return undefined;
  if (session.state === 'unknown') return undefined;
  return {...snapshot, sessions: replaceSession(snapshot.sessions, {...session, activitySource: 'lazy'})};
}

/** Decide whether an unknown real refresh may inherit local activity; e.g., reject a newer execution watermark. */
function shouldCarryActivity(previous: Session | undefined, next: Session): previous is Session {
  if (!previous) return false;
  if (previous.activitySource !== 'lazy') return false;
  if (next.state !== 'unknown') return false;
  if (next.removed) return false;
  if (next.source === 'demo') return false;
  return (next.lastActivityEventId ?? 0) <= (previous.lastActivityEventId ?? 0);
}

/** Preserve last-read activity through real unknowns; for example, keep a failed mark on reconnect. */
function carryActivity(previous: Session | undefined, next: Session): Session {
  if (!shouldCarryActivity(previous, next)) return next;
  return {
    ...next,
    state: previous.state,
    latestTurn: previous.latestTurn,
    activeTurns: previous.activeTurns,
    activeTurnCount: previous.activeTurnCount,
    activeTurnsTruncated: previous.activeTurnsTruncated,
    activeTurnsRevision: previous.activeTurnsRevision,
    lastObservedAt: previous.lastObservedAt,
    source: previous.source,
    freshness: previous.freshness,
    lastActivityEventId: next.lastActivityEventId ?? previous.lastActivityEventId,
    activitySource: 'lazy'
  };
}

/** Retain browser-local reads in the same workspace; for example, a collector refresh is not new execution evidence. */
function retainActivity(previous: Snapshot | undefined, next: Snapshot): Snapshot {
  if (previous?.workspaceId !== next.workspaceId) return next;
  const sessions = new Map(previous.sessions.map((session) => [session.sessionId, session]));
  return {...next, sessions: next.sessions.map((session) => carryActivity(sessions.get(session.sessionId), session))};
}

/** Replace a projection by identity; for example, append a newly seen session. */
function replaceSession(sessions: readonly Session[], next: Session): readonly Session[] {
  const existing = sessions.some((session) => session.sessionId === next.sessionId);
  if (!existing) return [...sessions, next];
  return sessions.map((session) => (session.sessionId === next.sessionId ? carryActivity(session, next) : session));
}

/** Fetch a validated snapshot; for example, reject an HTML proxy error page. */
const fetchSnapshot = Effect.fn('ishiban.snapshot')(function* () {
  const body = yield* Effect.tryPromise({
    try: async (signal) => {
      const response = await fetch('/api/v1/snapshot', {signal, cache: 'no-store'});
      if (!response.ok) throw new Error('Snapshot unavailable');
      return response.text();
    },
    catch: () => new Error('Snapshot unavailable')
  });
  return yield* Schema.decodeUnknownEffect(SnapshotJSON)(body);
});

/**
 * Follow the board until disposed; for example, return this from a React effect.
 * @param store Destination for validated snapshots, projections, and health.
 * @returns A cancellation function that closes the EventSource and fetch.
 */
export function startLive(store: BoardStore): () => void {
  return Effect.runCallback(liveConnection(store));
}

/**
 * Describe the scoped browser connection as an Effect owned by its caller.
 * @param store Projection state and visible transport health.
 * @returns A cancellable snapshot-and-event connection with scheduled recovery.
 * @example
 * Effect.runCallback(liveConnection(createBoardStore()));
 */
export function liveConnection(store: BoardStore) {
  return Effect.gen(function* () {
    const snapshot = yield* fetchSnapshot();
    store.replace(snapshot);
    const source = yield* Effect.acquireRelease(
      Effect.sync(() => new EventSource(`/api/v1/events?after=${snapshot.cursor}`)),
      (connection) => Effect.sync(() => connection.close())
    );
    yield* listen(source, store);
  }).pipe(
    Effect.scoped,
    Effect.tapError(() => Effect.sync(() => store.status('Reconnecting'))),
    Effect.retry({schedule: Schedule.spaced('1 second')})
  );
}

/** Register scoped listeners; for example, malformed data forces a fresh snapshot. */
function listen(source: EventSource, store: BoardStore) {
  return Effect.callback<void, Error>((resume) => {
    const malformed = () => resume(Effect.fail(new Error('Invalid event or reset required')));
    const observation = (event: MessageEvent<string>) => {
      const decode = Schema.decodeUnknownEffect(SessionJSON)(event.data).pipe(
        Effect.match({
          onFailure: malformed,
          onSuccess: (value) => applySession(event.lastEventId, value, store, malformed)
        })
      );
      Effect.runSync(decode);
    };
    const health = (event: MessageEvent<string>) => {
      Effect.runSync(
        Schema.decodeUnknownEffect(CollectorJSON)(event.data).pipe(
          Effect.match({
            onFailure: malformed,
            onSuccess: (value) => {
              if (isCurrentEvent(event.lastEventId, value, store)) store.collector(value.cursor, value.projection);
              else malformed();
            }
          })
        )
      );
    };
    const opened = () => store.status('Connected');
    const failed = () => {
      if (source.readyState === EventSource.CLOSED) {
        resume(Effect.fail(new Error('Event stream closed')));
        return;
      }
      store.status('Reconnecting');
    };
    source.addEventListener('observation', observation);
    source.addEventListener('source', health);
    source.addEventListener('reset_required', malformed);
    source.addEventListener('open', opened);
    source.addEventListener('error', failed);
    return Effect.sync(() => {
      source.removeEventListener('observation', observation);
      source.removeEventListener('source', health);
      source.removeEventListener('reset_required', malformed);
      source.removeEventListener('open', opened);
      source.removeEventListener('error', failed);
    });
  });
}

/** Reject mismatched event cursors rather than silently losing replay position. */
function applySession(id: string, event: typeof SessionEvent.Type, store: BoardStore, malformed: () => void) {
  if (!isCurrentEvent(id, event, store) || event.sessionId !== event.projection.sessionId) {
    malformed();
    return;
  }
  store.session(event.cursor, event.projection);
}

/** Verify workspace and replay identity against the current snapshot. */
function isCurrentEvent(id: string, event: {cursor: number; workspaceId: string}, store: BoardStore): boolean {
  if (id !== String(event.cursor)) return false;
  return event.workspaceId === store.getSnapshot().snapshot?.workspaceId;
}
