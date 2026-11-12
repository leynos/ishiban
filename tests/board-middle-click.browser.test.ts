/** @file Exercise genuine Chromium middle-button thread navigation on a grouped family. */
import {afterAll, beforeAll, beforeEach, describe, expect, it} from 'bun:test';
import {Schema} from 'effect';
import {createBrowserSession} from './browser-session';
import {FAMILY_SNAPSHOT, startFamilyBoardServer, type FamilyBoardServer} from './family-board-server';
import {isBrowserEnabled} from './native-browser-environment';

const {browser, browserJson, tabs, countTabs} = createBrowserSession(`ishiban-middle-click-${process.pid}`);
const FAMILY_URL = 'https://lody.ai/leynos/sessions/root-0?tab=session%3Achild-0';
const PROBE_STATE = 'window.__ishibanProbe';
const MARK_SELECTOR = 'button[data-family-id="root-0"]';
const READY_PREDICATE = `document.querySelector(${JSON.stringify(MARK_SELECTOR)})?.getAttribute('data-session-id') === 'child-0'`;
const RECENCY_SETTLED_PREDICATE = `(()=>{
  const inspector=document.querySelector('.session-inspector');
  return inspector?.textContent?.includes('Selected tab') === true &&
    inspector.textContent.includes('Child execution') &&
    !inspector.textContent.includes('provisional');
})()`;
const PROBE_EXPRESSION = `(()=>{
  window.__ishibanProbe={opens:[],mousedowns:[],nativeOpen:window.open};
  window.open=(url,target,features)=>{
    window.__ishibanProbe.opens.push({url:String(url),target:String(target),features:String(features)});
    return null;
  };
  document.addEventListener('mousedown',(event)=>{
    if(event.button!==1)return;
    const button=event.target instanceof Element?event.target.closest('button'):null;
    window.__ishibanProbe.mousedowns.push({
      family:button?.getAttribute('data-family-id')??null,
      defaultPrevented:event.defaultPrevented
    });
  });
  return true;
})()`;
const PointSchema = Schema.Struct({x: Schema.Number, y: Schema.Number});
const OpenRequestSchema = Schema.Struct({url: Schema.String, target: Schema.String, features: Schema.String});
const MouseDownSchema = Schema.Struct({
  family: Schema.NullOr(Schema.String),
  defaultPrevented: Schema.Boolean
});
const ProbeStateSchema = Schema.Struct({
  opens: Schema.Array(OpenRequestSchema),
  mousedowns: Schema.Array(MouseDownSchema)
});
const InspectorStateSchema = Schema.Struct({
  open: Schema.NullOr(Schema.String),
  pressed: Schema.NullOr(Schema.String),
  href: Schema.NullOr(Schema.String),
  rel: Schema.NullOr(Schema.String),
  target: Schema.NullOr(Schema.String),
  sessionId: Schema.NullOr(Schema.String),
  selectedTab: Schema.Boolean
});

let fixture: FamilyBoardServer | undefined;
let tabCount = 0;

/** Centre the pointer over one rendered control before a low-level gesture. */
async function pointAt(selector: string): Promise<{x: number; y: number}> {
  const point = await browserJson(
    `(()=>{
    const rect=document.querySelector(${JSON.stringify(selector)})?.getBoundingClientRect();
    if(!rect)throw new Error('Missing gesture target');
    return {x:rect.x+rect.width/2,y:rect.y+rect.height/2};
  })()`,
    PointSchema
  );
  await browser('mouse', 'move', String(Math.round(point.x)), String(Math.round(point.y)));
  return point;
}

/** Deliver one real middle-button press and release at the current pointer. */
async function middleClick(selector: string): Promise<void> {
  await pointAt(selector);
  await browser('mouse', 'down', 'middle');
  await browser('mouse', 'up', 'middle');
}

/** Wait until the browser reports the expected number of real tabs. */
async function waitForTabs(expected: number): Promise<void> {
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    if ((await countTabs()) === expected) return;
    await Bun.sleep(50);
  }
  throw new Error(`Expected ${expected} browser tabs; found ${await countTabs()}.`);
}

/** Wait until this page load has completed one available child-recency lookup. */
async function waitForRecency(): Promise<void> {
  if (!fixture) throw new Error('The family fixture must be running.');
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    if (fixture.recencyRequests.some((sessionIds) => sessionIds.includes('child-0'))) return;
    await Bun.sleep(25);
  }
  throw new Error('The browser did not request grouped-family recency.');
}

/** Load a fresh grouped family and replace `window.open` with an owned probe. */
async function installFreshPage(): Promise<void> {
  if (!fixture) throw new Error('The family fixture must be running.');
  fixture.recencyRequests.length = 0;
  await browser('reload');
  await browser('wait', '--fn', READY_PREDICATE);
  await waitForRecency();
  await browser('eval', PROBE_EXPRESSION);
  tabCount = await countTabs();
}

/** Read the inspector's canonical destination and selected identity. */
async function readInspector() {
  return browserJson(
    `(()=>{
    const aside=document.querySelector('.session-inspector');
    const link=[...(aside?.querySelectorAll('a')??[])].find((anchor)=>anchor.textContent?.trim()==='Open in Lody');
    return {
      open:document.querySelector('.ishiban-board')?.getAttribute('data-inspector-open')??null,
      pressed:document.querySelector(${JSON.stringify(MARK_SELECTOR)})?.getAttribute('aria-pressed')??null,
      href:link?.href??null,
      rel:link?.getAttribute('rel')??null,
      target:link?.getAttribute('target')??null,
      sessionId:aside?.querySelector('code')?.textContent??null,
      selectedTab:aside?.textContent?.includes('Selected tab')??false
    };
  })()`,
    InspectorStateSchema
  );
}

/** Verify one probe-recorded middle click without opening a real tab. */
async function verifyProbeNavigation(): Promise<void> {
  expect(FAMILY_SNAPSHOT.sessions.map((session) => session.sessionId)).toEqual(['root-0', 'child-0']);

  await browser('click', MARK_SELECTOR);
  await browser('wait', '--fn', RECENCY_SETTLED_PREDICATE);
  const selected = await readInspector();
  expect(selected.open).toBe('true');
  expect(selected.pressed).toBe('true');
  expect(selected.selectedTab).toBe(true);
  expect(selected.sessionId).toBe('child-0');
  expect(selected.href).toBe(FAMILY_URL);
  expect(selected.rel).toBe('noreferrer');
  expect(selected.target).toBe('_blank');
  const beforeMiddle = await browserJson(PROBE_STATE, ProbeStateSchema);
  expect(beforeMiddle.opens).toHaveLength(0);

  await browser('find', 'role', 'button', 'click', '--name', 'Close session inspector', '--exact');
  await browser(
    'wait',
    '--fn',
    'document.querySelector(".ishiban-board")?.getAttribute("data-inspector-open") === "false"'
  );

  await middleClick(MARK_SELECTOR);
  await browser('wait', '--fn', 'window.__ishibanProbe?.opens.length >= 1');
  const probe = await browserJson(PROBE_STATE, ProbeStateSchema);
  expect(probe.opens).toEqual([{url: FAMILY_URL, target: '_blank', features: 'noopener,noreferrer'}]);
  expect(probe.mousedowns).toHaveLength(1);
  expect(probe.mousedowns[0]?.family).toBe('root-0');
  expect(probe.mousedowns[0]?.defaultPrevented).toBe(true);
  expect(await countTabs()).toBe(tabCount);
  expect(await readInspector()).toMatchObject({open: 'false', pressed: 'false', href: null});

  await middleClick('.session-mark--empty');
  const afterEmpty = await browserJson(PROBE_STATE, ProbeStateSchema);
  expect(afterEmpty.opens).toHaveLength(1);
  expect(await readInspector()).toMatchObject({open: 'false', pressed: 'false'});

  await browser('click', MARK_SELECTOR);
  await browser(
    'wait',
    '--fn',
    'document.querySelector(".ishiban-board")?.getAttribute("data-inspector-open") === "true"'
  );
  const reopened = await readInspector();
  expect(reopened.sessionId).toBe('child-0');
  expect(reopened.href).toBe(FAMILY_URL);
  const afterReopen = await browserJson(PROBE_STATE, ProbeStateSchema);
  expect(afterReopen.opens).toHaveLength(1);
  expect(await countTabs()).toBe(tabCount);
}

/** Verify one unmocked middle click creates a genuine browser tab. */
async function verifyRealBrowsingContext(): Promise<void> {
  await browser('eval', 'window.open=window.__ishibanProbe.nativeOpen; true');
  expect(await countTabs()).toBe(tabCount);

  await middleClick(MARK_SELECTOR);
  await waitForTabs(tabCount + 1);
  const openTabs = await tabs();
  const lodyTabs = openTabs.filter((tab) => tab.url === FAMILY_URL);
  expect(lodyTabs).toHaveLength(1);

  const applicationTab = openTabs.find((tab) => tab.url !== FAMILY_URL);
  const popupTab = lodyTabs[0];
  if (applicationTab === undefined || popupTab === undefined) {
    throw new Error('Expected one application tab and one Lody tab.');
  }
  await browser('tab', applicationTab.tabId);
  expect(await readInspector()).toMatchObject({open: 'false', pressed: 'false', href: null});
  await browser('tab', 'close', popupTab.tabId);
  await waitForTabs(tabCount);
}

describe.skipIf(!isBrowserEnabled)('real middle-click thread navigation', () => {
  beforeAll(async () => {
    fixture = startFamilyBoardServer();
    await browser('open', fixture.url);
    // agent-browser cannot attach network controls to a popup under its domain
    // allowlist, so abort the canonical Lody requests instead of allowing egress.
    await browser('network', 'route', 'https://lody.ai/**', '--abort');
    await browser('set', 'viewport', '1280', '1200');
  }, 75_000);

  beforeEach(installFreshPage, 50_000);

  afterAll(async () => {
    try {
      await browser('close');
    } finally {
      await fixture?.stop();
    }
  }, 35_000);

  it('opens the displayed child thread once and preserves the inspector route', verifyProbeNavigation, 240_000);

  it('opens the displayed child thread in a real browsing context', verifyRealBrowsingContext, 240_000);
});
