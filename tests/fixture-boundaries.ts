/** @file Keep loopback browser fixtures' SSE streams and built assets consistent. */

/**
 * Open one retained SSE response and enqueue its connected comment.
 * @param sinks Streams owned by the fixture, so teardown can close each one.
 * @param headers Additional response headers such as cache policy.
 * @returns A streaming event response ready for the browser.
 */
export function openEventStream(
  sinks: Set<ReadableStreamDefaultController<Uint8Array>>,
  headers: Readonly<Record<string, string>> = {}
): Response {
  let ownedSink: ReadableStreamDefaultController<Uint8Array> | undefined;
  const stream = new ReadableStream<Uint8Array>({
    start(sink) {
      ownedSink = sink;
      sinks.add(sink);
      sink.enqueue(new TextEncoder().encode(': connected\n\n'));
    },
    cancel() {
      if (ownedSink) sinks.delete(ownedSink);
    }
  });
  return new Response(stream, {headers: {...headers, 'content-type': 'text/event-stream'}});
}

const BUILT_ASSETS = new Map([
  ['/', 'index.html'],
  ['/app.js', 'app.js'],
  ['/styles.css', 'styles.css']
]);

/**
 * Serve one built browser asset, or 404 for any other path.
 * @param pathname Request path that may name a built asset.
 * @returns The asset file, or an empty 404 response.
 */
export function builtAssetResponse(pathname: string): Response {
  const asset = BUILT_ASSETS.get(pathname);
  return asset
    ? new Response(Bun.file(new URL(`../dist/${asset}`, import.meta.url)))
    : new Response(null, {status: 404});
}
