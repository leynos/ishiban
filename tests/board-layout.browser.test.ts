/** @file Exercise computed board geometry and real SSE pulses in Chromium. */
import {describe, expect, it} from 'bun:test';
import {createDemoSnapshot} from '../src/demo';
import {firstSession} from './board-fixtures';
import {boardBrowserSuite} from './board-browser-suite';
import {boardBrowser} from './board-browser-driver';
import {isBrowserEnabled} from './native-browser-environment';

const sessionName = `ishiban-layout-${process.pid}`;
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
const browser = boardBrowser(sessionName);
const suite = boardBrowserSuite(snapshot, browser);

/** Observe one task revision only; for example, watchPulse(snapshot.cursor + 1). */
async function watchPulse(cursor: number): Promise<void> {
  const selector = JSON.stringify(
    `[data-session-id="${firstSession(snapshot).sessionId}"] [data-session-update-pulse="${cursor}"]`
  );
  await browser.run(
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
  const geometry = await browser.json<{
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
  return browser.json<{left: number; width: number; content: number; page: number; viewport: number}>(
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
    if (suite.fixture().sinks.size === expected) return;
    await Bun.sleep(20);
  }
  throw new Error(`Expected ${expected} owned SSE streams; found ${suite.fixture().sinks.size}.`);
}

/** Count only observers that actually scan session marks. */
async function installObserverProbe(): Promise<void> {
  await browser.run(
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
  suite.fixture().replace(snapshot);
  await browser.run(
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
  suite.fixture().replace(liveSnapshot);
  try {
    await browser.run('reload');
    await browser.run('wait', '--fn', LIVE_CONNECTED_PREDICATE);
    await waitForSinkCount(1);
    const live = await browser.json<ModeView>(MODE_VIEW_EXPRESSION);
    expect(live.workspace).toContain('live-source-fixture');
    expect(live.connection).toContain('Connected');
    expect(live.mark).toContain('Live source task');

    await browser.run('find', 'role', 'button', 'click', '--name', 'Demo data · 120 repositories', '--exact');
    await browser.run(
      'wait',
      '--fn',
      'document.querySelector(".source-health")?.textContent?.includes("Demo data — no live connections")'
    );
    await waitForSinkCount(0);
    const demo = await browser.json<ModeView>(MODE_VIEW_EXPRESSION);
    expect(demo.workspace).toContain('leynos');
    expect(demo.connection).toContain('Demo data — no live connections');
    expect(demo.mark).toContain('Synthetic');
    expect(demo.mark).not.toContain('Live source task');
    await installObserverProbe();

    await browser.run('find', 'role', 'button', 'click', '--name', 'Live · leynos', '--exact');
    await browser.run('wait', '--fn', LIVE_CONNECTED_PREDICATE);
    await browser.run('wait', '--fn', 'window.modeObserver?.markObservers.size >= 2');
    await waitForSinkCount(1);
    const resumed = await browser.json<ModeView>(MODE_VIEW_EXPRESSION);
    expect(resumed.connection).toContain('Connected');
    expect(resumed.mark).toContain('Live source task');
    await browser.run('eval', 'window.modeObserver.captured=new Set(window.modeObserver.markObservers);true');
    await browser.run('find', 'role', 'button', 'click', '--name', 'Demo data · 120 repositories', '--exact');
    await browser.run(
      'wait',
      '--fn',
      'Array.from(window.modeObserver?.captured ?? []).every((observer)=>window.modeObserver.closedObservers.has(observer))'
    );
    await waitForSinkCount(0);
  } finally {
    await restoreModeFixture();
  }
}

describe.skipIf(!isBrowserEnabled)('real board layout', () => {
  it('hides compact evidence without hiding the activity glyph or accessible evidence', async () => {
    await browser.run('select', 'select[aria-label="Mark density"]', 'compact');
    const result = await browser.run(
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
    await browser.run('eval', "document.querySelector('button.session-mark').click()");
    const docked = await measureScrollPane();
    expect(docked.page).toBe(docked.viewport);
    expect(docked.width).toBeLessThan(closed.width);
    expect(docked.left).toBeGreaterThan(0);
    await assertDockedGeometry();
  }, 240_000);

  it('hides a selected planning mark beneath the sticky repository column', async () => {
    await browser.run('eval', "document.querySelector('button.session-mark').click()");
    const result = await browser.run(
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
    await browser.run('find', 'role', 'button', 'click', '--name', 'List', '--exact');
    await watchPulse(snapshot.cursor + 1);
    expect(suite.fixture().sinks.size).toBeGreaterThan(0);
    suite.fixture().publishObservation(snapshot.cursor + 1);
    await browser.run('wait', '--fn', `window.layoutPulse?.cursor === ${snapshot.cursor + 1}`);
    const bounds = JSON.parse(await browser.run('eval', 'window.layoutPulse'));
    expect(bounds.cursor).toBe(snapshot.cursor + 1);
    expect(bounds.parentPosition).toBe('relative');
    expect(bounds.parentOverflow).toBe('clip');
    expect(bounds.pulseWidth).toBeLessThanOrEqual(bounds.taskWidth * 1.5 + 8);
    expect(bounds.pulseHeight).toBeLessThanOrEqual(bounds.taskHeight * 1.5 + 8);
    await browser.run('set', 'media', 'light', 'reduced-motion');
    await browser.run('wait', '--fn', 'matchMedia("(prefers-reduced-motion: reduce)").matches');
    await watchPulse(snapshot.cursor + 2);
    suite.fixture().publishObservation(snapshot.cursor + 2);
    await browser.run('wait', '--fn', `window.layoutPulse?.cursor === ${snapshot.cursor + 2}`);
    const reduced = JSON.parse(await browser.run('eval', 'window.layoutPulse'));
    expect(reduced.cursor).toBe(snapshot.cursor + 2);
    expect(reduced.animation).toBe('none');
    expect(reduced.display).toBe('none');
  }, 240_000);

  it('closes live observation in demo mode and resumes it on return', verifyLiveDemoLiveSwitch, 240_000);
});
