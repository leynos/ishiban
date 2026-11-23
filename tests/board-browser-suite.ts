/** @file Share the browser suite lifecycle for the built board's Chromium checks. */
import {afterAll, beforeAll, beforeEach} from 'bun:test';
import type {Snapshot} from '../src/contracts';
import type {BoardBrowserDriver} from './board-browser-driver';
import {startBoardFixture, type BoardBrowserFixture} from './board-browser-fixture';

/** One owned fixture for a suite that has already started. */
export interface BoardBrowserSuite {
  fixture(): BoardBrowserFixture;
}

/** Timer bounds shared by every Chromium suite. */
export interface BrowserSuiteTimeouts {
  readonly setupMs: number;
  readonly caseMs: number;
  readonly cleanupMs: number;
}

export const BROWSER_SUITE_TIMEOUTS: BrowserSuiteTimeouts = {setupMs: 75_000, caseMs: 50_000, cleanupMs: 35_000};

/**
 * Register the shared open, reset and close lifecycle for one browser suite.
 * Every suite owns a private session name, so two suites can run at once.
 * Call it inside a `describe` body, never at module scope: a hook registered
 * outside a skipped suite still runs, which would launch a browser even when
 * the opt-in switch is unset.
 * @param snapshot Snapshot the fixture serves for the whole suite.
 * @param browser Browser driver already bound to this suite's session name.
 * @param timeouts Timer bounds for setup, each case and cleanup.
 * @returns Access to the fixture started by this suite's `beforeAll`.
 * @example
 * describe.skipIf(!isBrowserEnabled)('board', () => {
 *   const suite = boardBrowserSuite(createDemoSnapshot(), boardBrowser(sessionName), BROWSER_SUITE_TIMEOUTS);
 * });
 */
export function boardBrowserSuite(
  snapshot: Snapshot,
  browser: BoardBrowserDriver,
  timeouts: BrowserSuiteTimeouts
): BoardBrowserSuite {
  let started: BoardBrowserFixture | undefined;

  beforeAll(async () => {
    started = startBoardFixture(snapshot);
    await browser.run('open', started.url);
    await browser.run('set', 'viewport', '1280', '1200');
  }, timeouts.setupMs);

  beforeEach(async () => {
    await browser.run('reload');
    await browser.run('wait', '--fn', 'document.querySelectorAll(".session-mark").length > 10');
  }, timeouts.caseMs);

  afterAll(async () => {
    try {
      await browser.run('close');
    } finally {
      started?.stop();
    }
  }, timeouts.cleanupMs);

  return {
    fixture(): BoardBrowserFixture {
      if (started === undefined) throw new Error('The board fixture is unavailable before its suite starts.');
      return started;
    }
  };
}
