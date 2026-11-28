/** @file Refuse and record browser egress during native Chromium fixtures. */

/** A loopback proxy that records each tunnelled authority and refuses it. */
export interface EgressProxy {
  readonly url: string;
  readonly connectTargets: () => readonly string[];
  readonly stop: () => void;
}

/**
 * Start a proxy that refuses every request while recording HTTPS tunnels.
 *
 * Chromium sends an HTTP `CONNECT` request for each HTTPS destination. Keeping
 * those requests on a loopback proxy contains popups as well as the active
 * application tab, unlike `network route`, which agent-browser 0.34 installs
 * only on the active page session.
 *
 * @returns The proxy URL, recorded `host:port` tunnel targets, and its stop hook.
 * @example
 * const proxy = startEgressProxy();
 * proxy.url; // 'http://127.0.0.1:43123'
 * proxy.stop();
 */
export function startEgressProxy(): EgressProxy {
  const targets: string[] = [];
  const server = Bun.serve({
    hostname: '127.0.0.1',
    port: 0,
    fetch(request) {
      if (request.method === 'CONNECT') targets.push(request.url);
      return new Response('Blocked by the Ishiban browser-test egress proxy.', {status: 502});
    }
  });
  return {
    url: `http://127.0.0.1:${server.port}`,
    connectTargets: () => [...targets],
    stop: () => server.stop(true)
  };
}
