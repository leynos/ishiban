/** @file Verify lazy activity survives metadata refreshes but not new evidence or workspaces. */
import {expect, it} from 'bun:test';
import type {Session, Snapshot} from '../src/contracts';
import {createBoardStore, type BoardStore} from '../src/client';
import {createBoardSnapshot, firstSession} from './board-fixtures';

interface LazyScenario {
  readonly store: BoardStore;
  readonly snapshot: Snapshot;
  readonly session: Session;
}

/** Install one unresolved metadata record and enrich it through the real store path. */
function createLazyScenario(): LazyScenario {
  const base = createBoardSnapshot();
  const template = firstSession(base);
  const metadataSession: Session = {
    ...template,
    sessionId: 'retention-session',
    title: 'Before activity lookup',
    state: 'unknown',
    source: 'metadata',
    freshness: 'unavailable',
    lastEventId: 40,
    latestTurn: null,
    activeTurns: [],
    lastObservedAt: null
  };
  const snapshot: Snapshot = {
    ...base,
    workspaceId: 'retention-workspace',
    cursor: 700,
    collector: {...base.collector, state: 'connected'},
    sessions: [metadataSession, ...base.sessions.slice(1)]
  };
  const store = createBoardStore(() => {});
  store.replace(snapshot);
  store.activity(snapshot.workspaceId, {
    ...metadataSession,
    state: 'running',
    source: 'persisted',
    freshness: 'synced',
    latestTurn: {userTurnId: 'lazy-turn', state: 'completed', error: 'retained failure'},
    activeTurns: [{userTurnId: 'active-turn', state: 'running'}],
    lastObservedAt: 1234
  });
  const enriched = store.getSnapshot().snapshot;
  const session = enriched?.sessions.find((item) => item.sessionId === metadataSession.sessionId);
  if (!enriched || !session) throw new Error('The activity lookup must enrich its matching session.');
  return {store, snapshot: enriched, session};
}

/** Build a newer collector projection with deliberately unknown activity. */
function metadataRefresh(session: Session, lastEventId: number): Session {
  return {
    ...session,
    title: 'Refreshed metadata title',
    state: 'unknown',
    source: 'metadata',
    freshness: 'unavailable',
    latestTurn: null,
    activeTurns: [],
    lastObservedAt: null,
    archived: true,
    stage: 'building',
    stageReason: 'Metadata refresh classified an open draft pull request.',
    pullRequests: [{url: 'https://github.com/acme/repo/pull/42', title: 'Implement work', status: 'open'}],
    lastMetadataGeneration: 9,
    lastEventId
  };
}

/** Check retained runtime evidence and fields owned by the newer metadata record. */
function expectMetadataCarry(actual: Session | undefined, incoming: Session, retained: Session): void {
  expect(actual).toMatchObject({
    state: retained.state,
    latestTurn: retained.latestTurn,
    activeTurns: retained.activeTurns,
    source: retained.source,
    freshness: retained.freshness,
    lastObservedAt: retained.lastObservedAt,
    activitySource: 'lazy',
    title: incoming.title,
    pullRequests: incoming.pullRequests,
    stage: incoming.stage,
    stageReason: incoming.stageReason,
    archived: incoming.archived,
    lastMetadataGeneration: incoming.lastMetadataGeneration,
    lastEventId: incoming.lastEventId
  });
}

it('carries lazy runtime fields across a newer metadata event and accepts its revision', () => {
  const scenario = createLazyScenario();
  const incoming = metadataRefresh(scenario.session, scenario.session.lastEventId + 1);
  const nextCursor = scenario.snapshot.cursor + 1;

  scenario.store.session(nextCursor, incoming);

  const current = scenario.store.getSnapshot().snapshot;
  expect(current?.cursor).toBe(nextCursor);
  expectMetadataCarry(
    current?.sessions.find((session) => session.sessionId === incoming.sessionId),
    incoming,
    scenario.session
  );
});

it('retains lazy activity across a same-workspace reconnect snapshot', () => {
  const scenario = createLazyScenario();
  const incoming = metadataRefresh(scenario.session, scenario.session.lastEventId + 5);
  const reconnect: Snapshot = {
    ...scenario.snapshot,
    cursor: scenario.snapshot.cursor + 20,
    sessions: [incoming, ...scenario.snapshot.sessions.slice(1)]
  };

  scenario.store.replace(reconnect);

  const current = scenario.store.getSnapshot().snapshot;
  expect(current?.cursor).toBe(reconnect.cursor);
  expectMetadataCarry(
    current?.sessions.find((session) => session.sessionId === incoming.sessionId),
    incoming,
    scenario.session
  );
});

it('lets a newer durable execution projection replace lazy activity', () => {
  const scenario = createLazyScenario();
  const {activitySource: _lazySource, ...durableBase} = scenario.session;
  const durable: Session = {
    ...durableBase,
    state: 'waiting',
    source: 'persisted',
    freshness: 'synced',
    latestTurn: {userTurnId: 'durable-turn', state: 'waiting'},
    activeTurns: [{userTurnId: 'durable-active', state: 'waiting'}],
    lastObservedAt: 5678,
    lastEventId: scenario.session.lastEventId + 1
  };
  const nextCursor = scenario.snapshot.cursor + 1;

  scenario.store.session(nextCursor, durable);

  const current = scenario.store.getSnapshot().snapshot;
  const session = current?.sessions.find((item) => item.sessionId === durable.sessionId);
  expect(current?.cursor).toBe(nextCursor);
  expect(session).toMatchObject(durable);
  expect(session?.activitySource).toBeUndefined();
});

it('does not carry local activity into a replacement workspace', () => {
  const scenario = createLazyScenario();
  const {activitySource, ...metadataSession} = scenario.session;
  expect(activitySource).toBe('lazy');
  const replacementSession = metadataRefresh(metadataSession, 5);
  const replacement: Snapshot = {
    ...scenario.snapshot,
    workspaceId: 'another-workspace',
    cursor: 5,
    sessions: [replacementSession]
  };

  scenario.store.replace(replacement);

  const current = scenario.store.getSnapshot().snapshot;
  expect(current).toBe(replacement);
  expect(current?.cursor).toBe(5);
  expect(current?.sessions[0]?.state).toBe('unknown');
  expect(current?.sessions[0]?.source).toBe('metadata');
  expect(current?.sessions[0]?.activitySource).toBeUndefined();
});
