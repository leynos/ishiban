/** @file Exercise computed board geometry and real SSE pulses in Chromium. */
import {afterAll, beforeAll, beforeEach, describe, expect, it} from 'bun:test';
import {createDemoSnapshot} from '../src/demo';
import {firstSession} from './board-fixtures';
import {createBrowserSession} from './browser-session';
import {builtAssetResponse, openEventStream} from './fixture-boundaries';
import {isBrowserEnabled} from './native-browser-environment';

const {browser, browserJson} = createBrowserSession(`ishiban-layout-${process.pid}`);
const snapshot = createDemoSnapshot();
const liveSnapshot = {
  ...snapshot,
  workspaceId: 'live-source-fixture',
  collector: {...snapshot.collector, state: 'following' as const},
  sessions: [
    {
      ...firstSession(snapshot),
      title: 'Live source task',
      source: 'metadata' as const,
      freshness: 'synced' as const,
      state: 'idle' as const
    }
  ]
};
interface ModeView {
  readonly workspace: string;
  readonly connection: string;
  readonly mark: string;
}
const MODE_VIEW_EXPRESSION = `(()=>({workspace:document.querySelector('.board-workspace')?.textContent,
  connection:document.querySelector('.source-health span')?.textContent,
  mark:document.querySelector('button.session-mark')?.getAttribute('aria-label')}))()`;
const LIVE_CONNECTED_PREDICATE = `(()=>
  document.querySelector('.board-workspace')?.textContent?.includes('live-source-fixture')&&
  document.querySelector('.source-health span')?.textContent?.includes('Connected'))()`;
let servedSnapshot = snapshot;
const sinks = new Set<ReadableStreamDefaultController<Uint8Array>>();
const encoder = new TextEncoder();
let server: ReturnType<typeof Bun.serve> | undefined;

/** Serve built assets and synthetic API boundaries; for example, GET /api/v1/snapshot. */
function fixtureResponse(request: Request): Response {
  const path = new URL(request.url).pathname;
  if (path === '/api/v1/snapshot') return Response.json(servedSnapshot);
  if (path === '/api/v1/events') return openEventStream(sinks);
  return builtAssetResponse(path);
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
  const geometry = await browserJson<{
    mainHeight: number;
    inspectorHeight: number;
    mainRight: number;
    inspectorLeft: number;
    paddingRight: number;
    rootFontSize: number;
  }>(
    `(()=>{
      const main=document.querySelector('.board-main').getBoundingClientRect();
      const inspector=document.querySelector('.session-inspector').getBoundingClientRect();
      const scroll=document.querySelector('.board-scroll');
      return {mainHeight:main.height,inspectorHeight:inspector.height,
        mainRight:main.right,inspectorLeft:inspector.left,
        paddingRight:Number.parseFloat(getComputedStyle(scroll).paddingRight),
        rootFontSize:Number.parseFloat(getComputedStyle(document.documentElement).fontSize)};
    })()`
  );
  expect(Math.abs(geometry.inspectorHeight - geometry.mainHeight)).toBeLessThan(1);
  expect(Math.abs(geometry.inspectorLeft - geometry.mainRight)).toBeLessThan(1);
  expect(Math.abs(geometry.paddingRight - geometry.rootFontSize * 0.6)).toBeLessThan(0.1);
}

/** Measure the table pane; for example, await measureScrollPane(). */
async function measureScrollPane() {
  return browserJson<{left: number; width: number; content: number; page: number; viewport: number}>(
    `(()=>{const s=document.querySelector('.board-scroll');
        s.scrollLeft=s.scrollWidth;
        return {left:s.scrollLeft,width:s.clientWidth,content:s.scrollWidth,
          page:document.documentElement.scrollWidth,viewport:innerWidth};})()`
  );
}

/** Wait for a browser SSE teardown or restart without guessing its timing. */
async function waitForSinkCount(expected: number): Promise<void> {
  const deadline = Date.now() + 2000;
  while (Date.now() < deadline) {
    if (sinks.size === expected) return;
    await Bun.sleep(20);
  }
  throw new Error(`Expected ${expected} owned SSE streams; found ${sinks.size}.`);
}

/** Count only observers that actually scan session marks. */
async function installObserverProbe(): Promise<void> {
  await browser(
    'eval',
    `(()=>{const original=window.IntersectionObserver;
      window.modeObserver={markObservers:new Set(),closedObservers:new Set(),original};
      window.IntersectionObserver=function(callback,options){
        const observer=new original(callback,options);
        const observe=observer.observe.bind(observer);
        const disconnect=observer.disconnect.bind(observer);
        observer.observe=(target)=>{if(target.matches?.('button[data-session-id]')){
          window.modeObserver.markObservers.add(observer);}return observe(target)};
        observer.disconnect=()=>{window.modeObserver.closedObservers.add(observer);return disconnect()};
        return observer};
      window.IntersectionObserver.prototype=original.prototype;
      return true;})()`
  );
}

/** Release the probe and return to an inert demo view after this case. */
async function restoreModeFixture(): Promise<void> {
  servedSnapshot = snapshot;
  await browser(
    'eval',
    `(()=>{const metrics=window.modeObserver;
      if(metrics)window.IntersectionObserver=metrics.original;
      const demo=[...document.querySelectorAll('.data-mode button')]
        .find((button)=>button.textContent?.includes('Demo data'));
      if(demo?.getAttribute('aria-pressed')==='false')demo.click();})()`
  );
  await waitForSinkCount(0);
}

/** Exercise the real app's source switch through visible browser controls. */
async function verifyLiveDemoLiveSwitch(): Promise<void> {
  servedSnapshot = liveSnapshot;
  try {
    await browser('reload');
    await browser('wait', '--fn', LIVE_CONNECTED_PREDICATE);
    await waitForSinkCount(1);
    const live = await browserJson<ModeView>(MODE_VIEW_EXPRESSION);
    expect(live.workspace).toContain('live-source-fixture');
    expect(live.connection).toContain('Connected');
    expect(live.mark).toContain('Live source task');

    await browser('find', 'role', 'button', 'click', '--name', 'Demo data · 120 repositories', '--exact');
    await browser(
      'wait',
      '--fn',
      'document.querySelector(".source-health")?.textContent?.includes("Demo data — no live connections")'
    );
    await waitForSinkCount(0);
    const demo = await browserJson<ModeView>(MODE_VIEW_EXPRESSION);
    expect(demo.workspace).toContain('leynos');
    expect(demo.connection).toContain('Demo data — no live connections');
    expect(demo.mark).toContain('Synthetic');
    expect(demo.mark).not.toContain('Live source task');
    await installObserverProbe();

    await browser('find', 'role', 'button', 'click', '--name', 'Live · leynos', '--exact');
    await browser('wait', '--fn', LIVE_CONNECTED_PREDICATE);
    await browser('wait', '--fn', 'window.modeObserver?.markObservers.size >= 2');
    await waitForSinkCount(1);
    const resumed = await browserJson<ModeView>(MODE_VIEW_EXPRESSION);
    expect(resumed.connection).toContain('Connected');
    expect(resumed.mark).toContain('Live source task');
    await browser('eval', 'window.modeObserver.captured=new Set(window.modeObserver.markObservers);true');
    await browser('find', 'role', 'button', 'click', '--name', 'Demo data · 120 repositories', '--exact');
    await browser(
      'wait',
      '--fn',
      'Array.from(window.modeObserver?.captured ?? []).every((observer)=>window.modeObserver.closedObservers.has(observer))'
    );
    await waitForSinkCount(0);
  } finally {
    await restoreModeFixture();
  }
}

/** Start the owned loopback fixture and its uniquely named Chromium session. */
async function startBrowserFixture(): Promise<void> {
  server = Bun.serve({hostname: '127.0.0.1', port: 0, fetch: fixtureResponse});
  await browser('open', String(server.url));
  await browser('set', 'viewport', '1280', '1200');
}

describe.skipIf(!isBrowserEnabled)('real board layout', () => {
  beforeAll(startBrowserFixture, 75_000);

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

  it('closes live observation in demo mode and resumes it on return', verifyLiveDemoLiveSwitch, 240_000);
});
