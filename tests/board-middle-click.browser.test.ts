/** @file Exercise genuine Chromium middle-button thread navigation on a grouped family. */
import {afterAll, beforeAll, beforeEach, describe, expect, it} from 'bun:test';
import {Schema} from 'effect';
import {createBrowserSession} from './browser-session';
import {startEgressProxy, type EgressProxy} from './egress-proxy';
import {FAMILY_SNAPSHOT, startFamilyBoardServer, type FamilyBoardServer} from './family-board-server';
import {isBrowserEnabled} from './native-browser-environment';

const {browser, browserJson, tabs, countTabs} = createBrowserSession(`ishiban-middle-click-${process.pid}`);
const FAMILY_URL = 'https://lody.ai/leynos/sessions/root-0?tab=session%3Achild-0';
const MINIMUM_BROWSER_VERSION = '0.34.0';
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
  window.__ishibanProbe={opens:[],mousedowns:[],nativeOpen:window.open,passthrough:false};
  window.open=(url,target,features)=>{
    window.__ishibanProbe.opens.push({url:String(url),target:String(target),features:String(features)});
    if(!window.__ishibanProbe.passthrough)return null;
    return window.__ishibanProbe.nativeOpen.call(window,url,target,features);
  };
  window.__ishibanProbe.mousedownHandler=(event)=>{
    if(event.button!==1)return;
    const button=event.target instanceof Element?event.target.closest('button'):null;
    window.__ishibanProbe.mousedowns.push({
      family:button?.getAttribute('data-family-id')??null,
      defaultPrevented:event.defaultPrevented
    });
  };
  document.addEventListener('mousedown',window.__ishibanProbe.mousedownHandler);
  return true;
})()`;
const RESTORE_PROBE_EXPRESSION = `(()=>{
  const probe=window.__ishibanProbe;
  if(!probe)return false;
  window.open=probe.nativeOpen;
  document.removeEventListener('mousedown',probe.mousedownHandler);
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
const RestoredSchema = Schema.Struct({restored: Schema.Boolean});

let fixture: FamilyBoardServer | undefined;
let proxy: EgressProxy | undefined;
let baselineTabIds = new Set<string>();
let tabCount = 0;

/** Parse the version from `agent-browser --version`; for example, 0.34.0. */
function parseBrowserVersion(output: string): string {
  const match = /^agent-browser (\d+\.\d+\.\d+)$/u.exec(output);
  if (match?.[1] === undefined) throw new Error(`Unrecognized agent-browser version output: ${output}`);
  return match[1];
}

/** Reject a browser CLI older than the documented gesture contract. */
async function assertSupportedBrowser(): Promise<void> {
  const version = parseBrowserVersion(await browser('--version'));
  expect(Bun.semver.order(version, MINIMUM_BROWSER_VERSION)).toBeGreaterThanOrEqual(0);
}

/** Wait until the egress proxy records one refused tunnel to the target. */
async function waitForConnectTarget(egress: EgressProxy, target: string): Promise<void> {
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    if (egress.connectTargets().includes(target)) return;
    await Bun.sleep(50);
  }
  throw new Error(`Expected the egress proxy to record a tunnel to ${target}.`);
}

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
  const openTabs = await tabs();
  tabCount = openTabs.length;
  baselineTabIds = new Set(openTabs.map((tab) => tab.tabId));
  await browser('eval', PROBE_EXPRESSION);
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

/** Wait for one recorded opener call and assert its canonical destination. */
async function readSingleOpenerRequest() {
  await browser('wait', '--fn', 'window.__ishibanProbe?.opens.length >= 1');
  const probe = await browserJson(PROBE_STATE, ProbeStateSchema);
  expect(probe.opens).toEqual([{url: FAMILY_URL, target: '_blank', features: 'noopener,noreferrer'}]);
  return probe;
}

/** Assert the middle click left the task unselected and the inspector closed. */
async function assertInspectorClosed(): Promise<void> {
  expect(await readInspector()).toMatchObject({open: 'false', pressed: 'false', href: null});
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
  const probe = await readSingleOpenerRequest();
  expect(probe.mousedowns).toHaveLength(1);
  expect(probe.mousedowns[0]?.family).toBe('root-0');
  expect(probe.mousedowns[0]?.defaultPrevented).toBe(true);
  expect(await countTabs()).toBe(tabCount);
  await assertInspectorClosed();

  await middleClick('.session-mark--empty');
  const afterEmpty = await browserJson(PROBE_STATE, ProbeStateSchema);
  expect(afterEmpty.opens).toHaveLength(1);
  expect(afterEmpty.mousedowns).toHaveLength(2);
  expect(afterEmpty.mousedowns[1]).toEqual({family: null, defaultPrevented: false});
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

/** Identities of the application tab and the one popup it opened. */
interface RealTabPair {
  readonly applicationTabId: string;
  readonly popupTabId: string;
}

/** Wait for one settled popup and identify both real tabs; for example, one Lody tab. */
async function waitForPopupTabs(): Promise<RealTabPair> {
  await waitForTabs(tabCount + 1);
  await Bun.sleep(1000);
  expect(await countTabs()).toBe(tabCount + 1);
  const openTabs = await tabs();
  const lodyTabs = openTabs.filter((tab) => tab.url === FAMILY_URL);
  expect(lodyTabs).toHaveLength(1);
  const applicationTab = openTabs.find((tab) => tab.url !== FAMILY_URL);
  const popupTab = lodyTabs[0];
  if (applicationTab === undefined || popupTab === undefined) {
    throw new Error('Expected one application tab and one Lody tab.');
  }
  return {applicationTabId: applicationTab.tabId, popupTabId: popupTab.tabId};
}

/** Restore the probe and the baseline tab count in the application tab. */
async function restoreRealTabs(): Promise<void> {
  // Read the live tab list rather than the identities a successful assertion
  // returned, so a failure before popup identification cannot leak an extra
  // tab. Swallow cleanup errors so the original assertion stays the reported
  // failure.
  const openTabs = await tabs().catch(() => []);
  const applicationTab = openTabs.find((tab) => baselineTabIds.has(tab.tabId));
  if (applicationTab !== undefined) await browser('tab', applicationTab.tabId).catch(() => null);
  await browser('eval', RESTORE_PROBE_EXPRESSION).catch(() => null);
  for (const tab of openTabs.filter((open) => !baselineTabIds.has(open.tabId))) {
    await browser('tab', 'close', tab.tabId).catch(() => null);
  }
}

/** Verify one pass-through-probed middle click creates a genuine browser tab. */
async function verifyRealBrowsingContext(): Promise<void> {
  await browser('eval', 'window.__ishibanProbe.passthrough=true; true');
  expect(await countTabs()).toBe(tabCount);
  try {
    await middleClick(MARK_SELECTOR);
    if (proxy === undefined) throw new Error('The egress proxy must be running.');
    await waitForConnectTarget(proxy, 'lody.ai:443');
    const realTabs = await waitForPopupTabs();
    await browser('tab', realTabs.applicationTabId);
    await readSingleOpenerRequest();
    await assertInspectorClosed();
  } finally {
    await restoreRealTabs();
  }
}

/** Verify failed identification still restores the opener and closes duplicate tabs. */
async function verifyFailureSafeCleanup(): Promise<void> {
  await browser('eval', 'window.__ishibanProbe.passthrough=true; true');
  await browser(
    'eval',
    `(()=>{
      window.open(${JSON.stringify(FAMILY_URL)},'_blank','noopener,noreferrer');
      window.open(${JSON.stringify(FAMILY_URL)},'_blank','noopener,noreferrer');
      return true;
    })()`
  );
  await waitForTabs(tabCount + 2);
  let identificationFailed = false;
  try {
    expect(await countTabs()).toBe(tabCount + 3);
  } catch {
    identificationFailed = true;
  } finally {
    await restoreRealTabs();
  }
  expect(identificationFailed).toBe(true);
  expect(await countTabs()).toBe(tabCount);
  const restored = await browserJson('({restored: window.open === window.__ishibanProbe?.nativeOpen})', RestoredSchema);
  expect(restored.restored).toBe(true);
  const before = await browserJson(PROBE_STATE, ProbeStateSchema);
  await middleClick('.session-mark--empty');
  const after = await browserJson(PROBE_STATE, ProbeStateSchema);
  expect(after.mousedowns).toHaveLength(before.mousedowns.length);
}

describe.skipIf(!isBrowserEnabled)('real middle-click thread navigation', () => {
  beforeAll(async () => {
    await assertSupportedBrowser();
    proxy = startEgressProxy();
    fixture = startFamilyBoardServer();
    // The proxy contains popups as well as the active tab; route controls do not.
    await browser('--proxy', proxy.url, '--proxy-bypass', '127.0.0.1,localhost', 'open', fixture.url);
    await browser('set', 'viewport', '1280', '1200');
  }, 75_000);

  beforeEach(installFreshPage, 50_000);

  afterAll(async () => {
    try {
      await browser('close');
    } finally {
      proxy?.stop();
      await fixture?.stop();
    }
  }, 35_000);

  it('opens the displayed child thread once and preserves the inspector route', verifyProbeNavigation, 240_000);

  it('opens the displayed child thread in a real browsing context', verifyRealBrowsingContext, 240_000);

  it('restores the opener and closes duplicate tabs after failed identification', verifyFailureSafeCleanup, 240_000);
});
