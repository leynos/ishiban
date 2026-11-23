/** @file Verify portalled task tooltip placement and styling in real Chromium. */
import {describe, expect, it} from 'bun:test';
import {createDemoSnapshot} from '../src/demo';
import {boardBrowser} from './board-browser-driver';
import {boardBrowserSuite} from './board-browser-suite';
import {isBrowserEnabled} from './native-browser-environment';

const browser = boardBrowser(`ishiban-tooltip-${process.pid}`);
const snapshot = createDemoSnapshot();
const MARK = 'button.session-mark:not(.session-mark--empty)';
const TOOLTIP_OPEN = 'document.querySelector(".task-tooltip") !== null';
const TOOLTIP_CLOSED = 'document.querySelector(".task-tooltip") === null';
boardBrowserSuite(snapshot, browser);

interface TooltipBox {
  readonly left: number;
  readonly top: number;
  readonly right: number;
  readonly bottom: number;
  readonly width: number;
  readonly zIndex: number;
  readonly inScroll: boolean;
  readonly parentIsBody: boolean;
}

/** Return the open tooltip's box, stacking level and portal ancestry. */
async function tooltipBox(): Promise<TooltipBox> {
  return browser.json(
    `(()=>{const tip=document.querySelector('.task-tooltip');const box=tip.getBoundingClientRect();
      return {left:box.left,top:box.top,right:box.right,bottom:box.bottom,width:box.width,
        zIndex:Number.parseInt(getComputedStyle(tip).zIndex,10),
        inScroll:Boolean(tip.closest('.board-scroll')),
        parentIsBody:tip.parentElement?.parentElement === document.body};})()`
  );
}

/** Hover the first mark and wait for its delayed tooltip. */
async function hoverOpen(): Promise<void> {
  await browser.run('hover', MARK);
  await browser.run('wait', '--fn', TOOLTIP_OPEN);
}

/** Assert the open tooltip is inside the given viewport and above the board layers. */
async function expectContainedTooltip(width = 1280, height = 1200): Promise<void> {
  const box = await tooltipBox();
  expect(box.inScroll).toBe(false);
  expect(box.parentIsBody).toBe(true);
  expect(box.zIndex).toBe(40);
  expect(box.width).toBeGreaterThan(0);
  expect(box.left).toBeGreaterThanOrEqual(0);
  expect(box.top).toBeGreaterThanOrEqual(0);
  expect(box.right).toBeLessThanOrEqual(width);
  expect(box.bottom).toBeLessThanOrEqual(height);
}

/** Reset to the demo board after a viewport or mode change. */
async function reloadBoard(width: number, height: number): Promise<void> {
  await browser.run('set', 'viewport', String(width), String(height));
  await browser.run('reload');
  await browser.run('wait', '--fn', 'document.querySelectorAll(".session-mark").length > 10');
}

/** Portal the tooltip outside the scroll pane without moving table geometry. */
async function verifyPortalAndGeometry(): Promise<void> {
  const geometryExpression = `(()=>{const table=document.querySelector('.repository-table');
    const row=table.querySelector('tbody tr').getBoundingClientRect();
    const mark=document.querySelector('${MARK}');
    return {width:row.width,height:row.height,markX:mark.offsetLeft,markY:mark.offsetTop,
      columns:table.querySelectorAll('thead tr:first-child th').length};})()`;
  const before = await browser.json<{width: number; height: number; markX: number; markY: number; columns: number}>(
    geometryExpression
  );
  await hoverOpen();
  const opened = await browser.json<{
    described: boolean;
    nativeTitle: boolean;
    width: number;
    height: number;
    markX: number;
    markY: number;
    columns: number;
  }>(`(()=>{const mark=document.querySelector('${MARK}');
    return {...${geometryExpression},described:mark.hasAttribute('aria-describedby'),
      nativeTitle:mark.hasAttribute('title')};})()`);
  expect(opened.described).toBe(true);
  expect(opened.nativeTitle).toBe(false);
  expect(opened.columns).toBe(6);
  expect(Math.abs(opened.width - before.width)).toBeLessThan(0.5);
  expect(Math.abs(opened.height - before.height)).toBeLessThan(0.5);
  expect(opened.markX).toBe(before.markX);
  expect(opened.markY).toBe(before.markY);
  await expectContainedTooltip();
}

/** Keep the tooltip over the sticky column and inspector, closing on ancestor scroll. */
async function verifyLayeringAndScroll(): Promise<void> {
  await browser.run('find', 'role', 'button', 'click', '--name', 'Synthetic planning task 01');
  await hoverOpen();
  const layering = await browser.json<{
    topmostAtCenter: boolean;
    zIndex: number;
    stickyZIndex: number;
    inspectorZIndex: number;
  }>(
    `(()=>{const tip=document.querySelector('.task-tooltip');const box=tip.getBoundingClientRect();
      const parse=(node)=>{const value=Number.parseInt(getComputedStyle(node).zIndex,10);
        return Number.isNaN(value)?0:value;};
      return {topmostAtCenter:tip.contains(document.elementFromPoint(box.x+box.width/2,box.y+box.height/2)),
        zIndex:parse(tip),
        stickyZIndex:parse(document.querySelector('.repository-name')),
        inspectorZIndex:parse(document.querySelector('.session-inspector'))};})()`
  );
  expect(layering.topmostAtCenter).toBe(true);
  expect(layering.zIndex).toBeGreaterThan(layering.stickyZIndex);
  expect(layering.zIndex).toBeGreaterThan(layering.inspectorZIndex);
  await expectContainedTooltip();

  await browser.run('eval', 'document.querySelector(".board-scroll").scrollLeft=120');
  await browser.run('wait', '--fn', TOOLTIP_CLOSED);

  await browser.run('eval', 'document.querySelector(".board-scroll").scrollLeft=0');
  await hoverOpen();
  await expectContainedTooltip();
}

/** Close only the tooltip on the first Escape, then the inspector on the second. */
async function verifyEscapeLayering(): Promise<void> {
  await browser.run('find', 'role', 'button', 'click', '--name', 'Synthetic planning task 01');
  await hoverOpen();
  await browser.run('press', 'Escape');
  await browser.run('wait', '--fn', TOOLTIP_CLOSED);
  expect(await browser.run('eval', 'document.querySelector(".session-inspector") !== null')).toBe('true');

  await browser.run('press', 'Escape');
  await browser.run(
    'wait',
    '--fn',
    'document.querySelector(".session-inspector") === null && document.activeElement?.classList.contains("session-mark")'
  );
}

/** Check semantic tokens, wrapping bounds and placement at every density. */
async function verifyDensities(): Promise<void> {
  for (const density of ['overview', 'compact', 'balanced', 'roomy', 'comfortable']) {
    await browser.run('select', 'select[aria-label="Mark density"]', density);
    await hoverOpen();
    const styles = await browser.json<{
      background: string;
      color: string;
      width: number;
      maxWidth: number;
      density: string;
    }>(
      `(()=>{const tip=document.querySelector('.task-tooltip');const s=getComputedStyle(tip);
        return {background:s.backgroundColor,color:s.color,width:tip.getBoundingClientRect().width,
          maxWidth:Number.parseFloat(s.maxWidth),
          density:document.querySelector('.ishiban-board').getAttribute('data-density')};})()`
    );
    expect(styles.density).toBe(density);
    expect(styles.background).toBe('rgb(250, 249, 244)');
    expect(styles.color).toBe('rgb(23, 32, 28)');
    expect(styles.width).toBeLessThanOrEqual(styles.maxWidth + 0.5);
    await expectContainedTooltip();
    await browser.run('press', 'Escape');
    await browser.run('wait', '--fn', TOOLTIP_CLOSED);
    // Move the pointer off the mark so the next density generates a real pointermove.
    await browser.run('hover', '.board-heading h1');
  }
}

/** Keep the tooltip on screen at both supported narrow viewports, docked or not. */
async function verifyNarrowViewports(): Promise<void> {
  for (const width of [640, 900]) {
    await reloadBoard(width, 900);
    await hoverOpen();
    await expectContainedTooltip(width, 900);

    await browser.run('find', 'role', 'button', 'click', '--name', 'Synthetic planning task 01');
    await hoverOpen();
    await expectContainedTooltip(width, 900);

    await browser.run('press', 'Escape');
    await browser.run('wait', '--fn', TOOLTIP_CLOSED);
    await browser.run('press', 'Escape');
    await browser.run('wait', '--fn', 'document.querySelector(".session-inspector") === null');
  }
  await reloadBoard(1280, 1200);
}

describe.skipIf(!isBrowserEnabled)('task tooltip in Chromium', () => {
  it('portals content outside the scroll pane without moving table geometry', verifyPortalAndGeometry, 240_000);

  it('stays readable over the inspector and closes on ancestor scroll', verifyLayeringAndScroll, 240_000);

  it('dismisses the tooltip before the inspector on Escape', verifyEscapeLayering, 240_000);

  it('keeps semantic tokens, wrapping bounds and geometry in every density', verifyDensities, 240_000);

  it('stays inside narrow viewports with the inspector open and closed', verifyNarrowViewports, 300_000);
});
