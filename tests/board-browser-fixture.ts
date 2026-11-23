/** @file Serve the built board and synthetic API boundaries to real Chromium tests. */
import type {Snapshot} from '../src/contracts';
import {firstSession} from './board-fixtures';

/** One owned loopback fixture serving the built app and its synthetic API. */
export interface BoardBrowserFixture {
  readonly url: string;
  readonly sinks: ReadonlySet<ReadableStreamDefaultController<Uint8Array>>;
  replace(snapshot: Snapshot): void;
  publishObservation(cursor: number): void;
  stop(): void;
}

const encoder = new TextEncoder();

/**
 * Start the built-asset fixture used by the opt-in Chromium suites.
 * @param initial Snapshot served until a test replaces it.
 * @returns The owned server address, live sinks and lifecycle controls.
 * @example
 * const fixture = startBoardFixture(createDemoSnapshot());
 * fixture.stop();
 */
export function startBoardFixture(initial: Snapshot): BoardBrowserFixture {
  let servedSnapshot = initial;
  const sinks = new Set<ReadableStreamDefaultController<Uint8Array>>();
  const server = Bun.serve({hostname: '127.0.0.1', port: 0, fetch: (request) => respond(request)});

  /** Keep one real SSE response open; for example, enqueue a synthetic observation. */
  function eventResponse(): Response {
    let ownedSink: ReadableStreamDefaultController<Uint8Array> | undefined;
    const stream = new ReadableStream<Uint8Array>({
      start(sink) {
        ownedSink = sink;
        sinks.add(sink);
        sink.enqueue(encoder.encode(': connected\n\n'));
      },
      cancel() {
        if (ownedSink) sinks.delete(ownedSink);
      }
    });
    return new Response(stream, {headers: {'content-type': 'text/event-stream'}});
  }

  /** Serve built assets and synthetic API boundaries. */
  function respond(request: Request): Response {
    const path = new URL(request.url).pathname;
    if (path === '/api/v1/snapshot') return Response.json(servedSnapshot);
    if (path === '/api/v1/events') return eventResponse();
    const assets = new Map([
      ['/', 'index.html'],
      ['/app.js', 'app.js'],
      ['/styles.css', 'styles.css']
    ]);
    const asset = assets.get(path);
    return asset
      ? new Response(Bun.file(new URL(`../dist/${asset}`, import.meta.url)))
      : new Response(null, {status: 404});
  }

  return {
    url: String(server.url),
    sinks,
    replace(snapshot) {
      servedSnapshot = snapshot;
    },
    publishObservation(cursor) {
      const session = firstSession(servedSnapshot);
      const data = JSON.stringify({
        cursor,
        workspaceId: servedSnapshot.workspaceId,
        sessionId: session.sessionId,
        projection: {...session, lastEventId: cursor, title: `${session.title} update ${cursor}`}
      });
      const message = encoder.encode(`id: ${cursor}\nevent: observation\ndata: ${data}\n\n`);
      for (const sink of sinks) sink.enqueue(message);
    },
    stop() {
      void server.stop(true);
      sinks.clear();
    }
  };
}
