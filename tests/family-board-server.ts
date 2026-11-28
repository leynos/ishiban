/** @file Serve one grouped family and its lazy inspector boundaries to Chromium. */
import {Option, Schema} from 'effect';
import type {Snapshot} from '../src/contracts';
import {createFamilySnapshot} from './board-fixtures';
import {builtAssetResponse, openEventStream} from './fixture-boundaries';

const RecencyBodySchema = Schema.Struct({sessionIds: Schema.Array(Schema.String)});

/** Grouped catalogue with a running child tab newer than its idle parent. */
const GROUPED = createFamilySnapshot(1);

/** Build a following snapshot whose child tab is the displayed activity. */
function liveFamilySnapshot(): Snapshot {
  const [root, child] = GROUPED.sessions;
  if (!root || !child) throw new Error('The family server requires a root and child tab.');
  return {
    ...GROUPED,
    cursor: Math.max(GROUPED.cursor, root.lastEventId, child.lastEventId),
    collector: {
      ...GROUPED.collector,
      state: 'following',
      lastError: null,
      lastReceivedAt: '2026-11-12T09:30:00.000Z'
    },
    sessions: [
      {...root, freshness: 'synced', lastActivityEventId: 1, lastObservedAt: 1_762_900_200_000},
      {...child, freshness: 'synced', lastActivityEventId: 2, lastObservedAt: 1_762_900_260_000}
    ]
  };
}

/** The exact snapshot served to the browser test. */
export const FAMILY_SNAPSHOT = liveFamilySnapshot();

/** Owned loopback fixture serving built assets and grouped-family API boundaries. */
export interface FamilyBoardServer {
  readonly url: string;
  readonly recencyRequests: string[][];
  stop(): Promise<void>;
}

/** Return strict NDJSON recency frames with the child as the newest history. */
function recencyResponse(sessionIds: readonly string[]): Response {
  const frames = sessionIds.map((sessionId) => {
    const session = FAMILY_SNAPSHOT.sessions.find((entry) => entry.sessionId === sessionId);
    return JSON.stringify({
      workspaceId: FAMILY_SNAPSHOT.workspaceId,
      sessionId,
      lastActivityEventId: session?.lastActivityEventId ?? 0,
      outcome: 'available',
      latestHistoryAt: sessionId === 'child-0' ? '2026-11-05T16:00:00.000Z' : '2026-10-28T15:00:00.000Z'
    });
  });
  return new Response(`${frames.join('\n')}\n`, {headers: {'content-type': 'application/x-ndjson'}});
}

/** Record a parsed lookup before replying; for example, retain the child's request. */
async function recencyRoute(request: Request, recorded: string[][]): Promise<Response> {
  const parsed = Schema.decodeUnknownOption(RecencyBodySchema)(await request.json().catch(() => null));
  if (Option.isNone(parsed)) return new Response('Invalid recency request', {status: 400});
  recorded.push([...parsed.value.sessionIds]);
  return recencyResponse(parsed.value.sessionIds);
}

/** Answer only identities owned by this fixture; for example, reject root-0 agent reads. */
function agentResponse(sessionId: string | null): Response {
  if (sessionId !== 'child-0') return new Response(null, {status: 404});
  return Response.json({
    workspaceId: FAMILY_SNAPSHOT.workspaceId,
    sessionId,
    agent: {agentType: 'claude', configurationId: 'fixture-config', configurationName: 'Fixture agent'}
  });
}

/** Dispatch synthetic API boundaries; for example, POST sessions/recency. */
function apiResponse(
  request: Request,
  url: URL,
  sinks: Set<ReadableStreamDefaultController<Uint8Array>>,
  recorded: string[][]
): Response | Promise<Response> | undefined {
  switch (url.pathname) {
    case '/api/v1/snapshot': {
      return Response.json(FAMILY_SNAPSHOT);
    }
    case '/api/v1/events': {
      return openEventStream(sinks, {'cache-control': 'no-cache'});
    }
    case '/api/v1/sessions/recency': {
      return recencyRoute(request, recorded);
    }
    case '/api/v1/session-agent': {
      return agentResponse(url.searchParams.get('sessionId'));
    }
    default: {
      return undefined;
    }
  }
}

/**
 * Start an ephemeral loopback server for the grouped-family middle-click scenario.
 * @returns The URL, recorded recency request bodies, and an idempotent cleanup.
 * @example
 * const fixture = startFamilyBoardServer();
 * fixture.recencyRequests.length === 0;
 */
export function startFamilyBoardServer(): FamilyBoardServer {
  const sinks = new Set<ReadableStreamDefaultController<Uint8Array>>();
  const recencyRequests: string[][] = [];
  const server = Bun.serve({
    hostname: '127.0.0.1',
    port: 0,
    async fetch(request) {
      const url = new URL(request.url);
      return (await apiResponse(request, url, sinks, recencyRequests)) ?? builtAssetResponse(url.pathname);
    }
  });
  return {
    url: String(server.url),
    recencyRequests,
    async stop() {
      for (const sink of sinks) {
        try {
          sink.close();
        } catch {
          // The browser may already have cancelled its own SSE stream.
        }
      }
      sinks.clear();
      await server.stop(true);
    }
  };
}
