/** @file Exercise computed board geometry and real SSE pulses in Chromium. */
import {afterAll, beforeAll, beforeEach, describe, expect, it} from 'bun:test';
import {createDemoSnapshot} from '../src/demo';
import {firstSession} from './board-fixtures';
import {runCapturedCommand} from './browser-command';
import {isBrowserEnabled} from './native-browser-environment';

const sessionName = `ishiban-layout-${process.pid}`;
const snapshot = createDemoSnapshot();
const sinks = new Set<ReadableStreamDefaultController<Uint8Array>>();
const encoder = new TextEncoder();
let server: ReturnType<typeof Bun.serve> | undefined;

/** Run the actual browser CLI; for example, browser('eval', 'innerWidth'). */
async function browser(...args: string[]): Promise<string> {
  const {
    stdout: output,
    stderr: error,
    status
  } = await runCapturedCommand(['agent-browser', '--session', sessionName, ...args], 20_000);
  if (status !== 0) {
    throw new Error(`Browser command ${JSON.stringify(args)} failed (${status}): ${error || output}`);
  }
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
    projection: {...session, lastEventId: cursor, title: `${session.title} update ${cursor}`}
  });
  const message = encoder.encode(`id: ${cursor}\nevent: observation\ndata: ${data}\n\n`);
  for (const sink of sinks) sink.enqueue(message);
}

/** Observe one task revision only; for example, watchPulse(snapshot.cursor + 1). */
async function watchPulse(cursor: number): Promise<void> {
  const selector = JSON.stringify(
    `[data-session-id="${firstSession(snapshot).sessionId}"] [data-session-update-pulse="${cursor}"]`
  );
  await browser(
    'eval',
    `(()=>{
    window.layoutObserver?.disconnect();window.layoutPulse=null;
    window.layoutObserver=new MutationObserver(()=>{
      const pulse=document.querySelector(${selector});if(!pulse)return;
      const task=pulse.parentElement,p=pulse.getBoundingClientRect(),b=task.getBoundingClientRect();
      const style=getComputedStyle(pulse),owner=getComputedStyle(task);
      window.layoutPulse={cursor:${cursor},pulseWidth:p.width,pulseHeight:p.height,
        taskWidth:b.width,taskHeight:b.height,parentPosition:owner.position,parentOverflow:owner.overflow,
        display:style.display,animation:style.animationName};
    });
    window.layoutObserver.observe(document.querySelector('.board-scroll'),{subtree:true,childList:true});
    return true;
  })()`
  );
}

/** Measure rendered board geometry; for example, await assertDockedGeometry(). */
async function assertDockedGeometry(): Promise<void> {
  const geometry = JSON.parse(
    await browser(
      'eval',
      `(()=>{
      const main=document.querySelector('.board-main').getBoundingClientRect();
      const inspector=document.querySelector('.session-inspector').getBoundingClientRect();
      const scroll=document.querySelector('.board-scroll');
      return {mainHeight:main.height,inspectorHeight:inspector.height,
        mainRight:main.right,inspectorLeft:inspector.left,
        paddingRight:Number.parseFloat(getComputedStyle(scroll).paddingRight),
        rootFontSize:Number.parseFloat(getComputedStyle(document.documentElement).fontSize)};
    })()`
    )
  );
  expect(Math.abs(geometry.inspectorHeight - geometry.mainHeight)).toBeLessThan(1);
  expect(Math.abs(geometry.inspectorLeft - geometry.mainRight)).toBeLessThan(1);
  expect(Math.abs(geometry.paddingRight - geometry.rootFontSize * 0.6)).toBeLessThan(0.1);
}

/** Measure the table pane; for example, await measureScrollPane(). */
async function measureScrollPane() {
  return JSON.parse(
    await browser(
      'eval',
      `(()=>{const s=document.querySelector('.board-scroll');
        s.scrollLeft=s.scrollWidth;
        return {left:s.scrollLeft,width:s.clientWidth,content:s.scrollWidth,
          page:document.documentElement.scrollWidth,viewport:innerWidth};})()`
    )
  );
}

describe.skipIf(!isBrowserEnabled)('real board layout', () => {
  beforeAll(async () => {
    server = Bun.serve({hostname: '127.0.0.1', port: 0, fetch: fixtureResponse});
    await browser('open', String(server.url));
    await browser('set', 'viewport', '1280', '1200');
  }, 75_000);

  beforeEach(async () => {
    await browser('reload');
    await browser('wait', '--fn', 'document.querySelectorAll(".session-mark").length > 10');
  }, 50_000);

  afterAll(async () => {
    try {
      await browser('close');
    } finally {
      await server?.stop(true);
      sinks.clear();
    }
  }, 35_000);

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
  }, 240_000);

  it('scrolls the table pane horizontally with and without a docked inspector', async () => {
    const closed = await measureScrollPane();
    expect(closed.page).toBe(closed.viewport);
    expect(closed.content).toBeGreaterThan(closed.width);
    expect(closed.left).toBeGreaterThan(0);
    await browser('eval', "document.querySelector('button.session-mark').click()");
    const docked = await measureScrollPane();
    expect(docked.page).toBe(docked.viewport);
    expect(docked.width).toBeLessThan(closed.width);
    expect(docked.left).toBeGreaterThan(0);
    await assertDockedGeometry();
  }, 240_000);

  it('hides a selected planning mark beneath the sticky repository column', async () => {
    await browser('eval', "document.querySelector('button.session-mark').click()");
    const result = await browser(
      'eval',
      `(()=>{
      const mark=document.querySelector('button.session-mark');
      const pane=document.querySelector('.board-scroll');
      const heading=document.querySelector('.repository-name');const before=heading.getBoundingClientRect().left;
      pane.scrollLeft=80;
      const rect=mark.getBoundingClientRect();
      const top=document.elementFromPoint(rect.x+rect.width/2,rect.y+rect.height/2);
      return {covered:Boolean(top?.closest('.repository-name')),
        headingShift:heading.getBoundingClientRect().left-before,
        padding:getComputedStyle(document.querySelector('.board-banks')).paddingInlineStart};
    })()`
    );
    const state = JSON.parse(result);
    expect(state.covered).toBe(true);
    expect(Math.abs(state.headingShift)).toBeLessThan(0.5);
    expect(state.padding).toBe('0px');
  }, 240_000);

  it('bounds a live list pulse to its task button', async () => {
    await browser('find', 'role', 'button', 'click', '--name', 'List', '--exact');
    await watchPulse(snapshot.cursor + 1);
    expect(sinks.size).toBeGreaterThan(0);
    publishObservation(snapshot.cursor + 1);
    await browser('wait', '--fn', `window.layoutPulse?.cursor === ${snapshot.cursor + 1}`);
    const bounds = JSON.parse(await browser('eval', 'window.layoutPulse'));
    expect(bounds.cursor).toBe(snapshot.cursor + 1);
    expect(bounds.parentPosition).toBe('relative');
    expect(bounds.parentOverflow).toBe('clip');
    expect(bounds.pulseWidth).toBeLessThanOrEqual(bounds.taskWidth * 1.5 + 8);
    expect(bounds.pulseHeight).toBeLessThanOrEqual(bounds.taskHeight * 1.5 + 8);
    await browser('set', 'media', 'light', 'reduced-motion');
    await browser('wait', '--fn', 'matchMedia("(prefers-reduced-motion: reduce)").matches');
    await watchPulse(snapshot.cursor + 2);
    publishObservation(snapshot.cursor + 2);
    await browser('wait', '--fn', `window.layoutPulse?.cursor === ${snapshot.cursor + 2}`);
    const reduced = JSON.parse(await browser('eval', 'window.layoutPulse'));
    expect(reduced.cursor).toBe(snapshot.cursor + 2);
    expect(reduced.animation).toBe('none');
    expect(reduced.display).toBe('none');
  }, 240_000);
});
