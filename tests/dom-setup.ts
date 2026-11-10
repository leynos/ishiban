/** @file Register Happy DOM globals for focused React interaction tests. */
import {GlobalRegistrator} from '@happy-dom/global-registrator';

GlobalRegistrator.register({url: 'http://localhost:3000'});

// Component tests own HTTP boundaries; explicit transport tests replace this fixture.
const componentFetch = Object.assign(
  async (input: RequestInfo | URL) => {
    const url = input instanceof Request ? input.url : String(input);
    const path = new URL(url, 'http://localhost:3000').pathname;
    if (path === '/api/v1/interface-state') return new Response(null, {status: 204});
    if (path.endsWith('/agent')) {
      return Response.json({workspaceId: 'workspace-1', sessionId: path.split('/')[4], agent: null});
    }
    throw new Error(`No HTTP fixture for ${path}`);
  },
  {
    preconnect: () => {
      // Component fixtures never open network connections.
    }
  }
);
globalThis.fetch = componentFetch;
