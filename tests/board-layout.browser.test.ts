/** @file Exercise computed board geometry and real SSE pulses in Chromium. */
import {afterAll, beforeAll, beforeEach, describe, expect, it} from 'bun:test';
import {GlobalRegistrator} from '@happy-dom/global-registrator';
import {createDemoSnapshot} from '../src/demo';
import {firstSession} from './board-fixtures';

const {ISHIBAN_BROWSER_TESTS: browserTestSwitch} = Bun.env;
const isBrowserEnabled = browserTestSwitch === '1';
// This opt-in suite uses Chromium and Bun's native HTTP types, rather than Happy DOM.
if (isBrowserEnabled) await GlobalRegistrator.unregister();

const sessionName = `ishiban-layout-${process.pid}`;
const snapshot = createDemoSnapshot();
const sinks = new Set<ReadableStreamDefaultController<Uint8Array>>();
const encoder = new TextEncoder();
let server: ReturnType<typeof Bun.serve> | undefined;

/** Run the actual browser CLI; for example, browser('eval', 'innerWidth'). */
async function browser(...args: string[]): Promise<string> {
  const child = Bun.spawn(['agent-browser', '--session', sessionName, ...args], {stdout: 'pipe', stderr: 'pipe'});
  const [output, error, status] = await Promise.all([
    new Response(child.stdout).text(),
    new Response(child.stderr).text(),
    child.exited
  ]);
  if (status !== 0) throw new Error(`Browser command failed: ${error}`);
  return output.trim();
}

/** Keep a real SSE response open; for example, enqueue one observation in a test. */
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

/** Serve built assets and synthetic API boundaries; for example, GET /api/v1/snapshot. */
function fixtureResponse(request: Request): Response {
  const path = new URL(request.url).pathname;
  if (path === '/api/v1/snapshot') return Response.json(snapshot);
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

/** Send a synthetic revision; for example, publishObservation(snapshot.cursor + 1). */
function publishObservation(cursor: number): void {
  const session = firstSession(snapshot);
  const data = JSON.stringify({
    cursor,
    workspaceId: snapshot.workspaceId,
    sessionId: session.sessionId,
    projection: {...session, lastEventId: cursor}
  });
  const message = encoder.encode(`id: ${cursor}\nevent: observation\ndata: ${data}\n\n`);
  for (const sink of sinks) sink.enqueue(message);
}

describe.skipIf(!isBrowserEnabled)('real board layout', () => {
  beforeAll(async () => {
    server = Bun.serve({hostname: '127.0.0.1', port: 0, fetch: fixtureResponse});
    await browser('open', String(server.url));
    await browser('set', 'viewport', '1280', '900');
  });

  beforeEach(async () => {
    await browser('reload');
    await browser('wait', '--fn', 'document.querySelectorAll(".session-mark").length > 10');
  });

  afterAll(async () => {
    await browser('close');
    await server?.stop(true);
    sinks.clear();
  });

  it('hides compact evidence without hiding the activity glyph or accessible evidence', async () => {
    await browser('select', 'select[aria-label="Mark density"]', 'compact');
    const result = await browser(
      'eval',
      `(()=>{
      const mark=document.querySelector('button.session-mark');
      return {evidence:getComputedStyle(mark.querySelector('small')).display,
        activity:getComputedStyle(mark.querySelector('span')).display,
        label:mark.getAttribute('aria-label')};
    })()`
    );
    const styles = JSON.parse(result);
    expect(styles.evidence).toBe('none');
    expect(styles.activity).not.toBe('none');
    expect(styles.label).toContain('Synthetic demo record');
  });

  it('scrolls the table pane horizontally with and without a docked inspector', async () => {
    const measure = `(()=>{const s=document.querySelector('.board-scroll');
      s.scrollLeft=s.scrollWidth;
      return {left:s.scrollLeft,width:s.clientWidth,content:s.scrollWidth,
        page:document.documentElement.scrollWidth,viewport:innerWidth};})()`;
    const closed = JSON.parse(await browser('eval', measure));
    expect(closed.page).toBe(closed.viewport);
    expect(closed.content).toBeGreaterThan(closed.width);
    expect(closed.left).toBeGreaterThan(0);
    await browser('eval', "document.querySelector('button.session-mark').click()");
    const docked = JSON.parse(await browser('eval', measure));
    expect(docked.page).toBe(docked.viewport);
    expect(docked.width).toBeLessThan(closed.width);
    expect(docked.left).toBeGreaterThan(0);
  });

  it('bounds a live list pulse to its task button', async () => {
    await browser('find', 'role', 'button', 'click', '--name', 'List', '--exact');
    await browser(
      'eval',
      `(()=>{window.layoutPulse=null;
      new MutationObserver(()=>{const pulse=document.querySelector('.session-update-pulse');
        if(!pulse)return;const p=pulse.getBoundingClientRect(),b=pulse.parentElement.getBoundingClientRect();
        const style=getComputedStyle(pulse);
        window.layoutPulse={pulseWidth:p.width,pulseHeight:p.height,taskWidth:b.width,taskHeight:b.height,
          display:style.display,animation:style.animationName};
      }).observe(document.querySelector('.board-scroll'),{subtree:true,childList:true});return true;})()`
    );
    expect(sinks.size).toBeGreaterThan(0);
    publishObservation(snapshot.cursor + 1);
    await browser('wait', '--fn', 'window.layoutPulse !== null');
    const bounds = JSON.parse(await browser('eval', 'window.layoutPulse'));
    expect(bounds.pulseWidth).toBeLessThanOrEqual(bounds.taskWidth * 1.5 + 8);
    expect(bounds.pulseHeight).toBeLessThanOrEqual(bounds.taskHeight * 1.5 + 8);
    await browser('set', 'media', 'light', 'reduced-motion');
    await browser('eval', 'window.layoutPulse=null');
    publishObservation(snapshot.cursor + 2);
    await browser('wait', '--fn', 'window.layoutPulse !== null');
    const reduced = JSON.parse(await browser('eval', 'window.layoutPulse'));
    expect(reduced.animation).toBe('none');
    expect(reduced.display).toBe('none');
  });
});
