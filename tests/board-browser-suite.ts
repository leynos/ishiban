/** @file Share the browser suite lifecycle for the built board's Chromium checks. */
import {afterAll, beforeAll, beforeEach} from 'bun:test';
import type {Snapshot} from '../src/contracts';
import type {BoardBrowserDriver} from './board-browser-driver';
import {startBoardFixture, type BoardBrowserFixture} from './board-browser-fixture';

/** One owned fixture for a suite that has already started. */
export interface BoardBrowserSuite {
  fixture(): BoardBrowserFixture;
}

const SETUP_TIMEOUT_MS = 75_000;
const CASE_TIMEOUT_MS = 50_000;
const CLEANUP_TIMEOUT_MS = 35_000;

/**
 * Register the shared open, reset and close lifecycle for one browser suite.
 * Every suite owns a private session name, so two suites can run at once.
 * Call it while the suite body executes, then use `fixture()` inside cases.
 * @param snapshot Snapshot the fixture serves for the whole suite.
 * @param browser Browser driver already bound to this suite's session name.
 * @returns Access to the fixture started by this suite's `beforeAll`.
 * @example
 * const suite = boardBrowserSuite(createDemoSnapshot(), boardBrowser(sessionName));
 * // inside a case: suite.fixture().url
 */
export function boardBrowserSuite(snapshot: Snapshot, browser: BoardBrowserDriver): BoardBrowserSuite {
  let started: BoardBrowserFixture | undefined;

  beforeAll(async () => {
    started = startBoardFixture(snapshot);
    await browser.run('open', started.url);
    await browser.run('set', 'viewport', '1280', '1200');
  }, SETUP_TIMEOUT_MS);

  beforeEach(async () => {
    await browser.run('reload');
    await browser.run('wait', '--fn', 'document.querySelectorAll(".session-mark").length > 10');
  }, CASE_TIMEOUT_MS);

  afterAll(async () => {
    try {
      await browser.run('close');
    } finally {
      started?.stop();
    }
  }, CLEANUP_TIMEOUT_MS);

  return {
    fixture(): BoardBrowserFixture {
      if (started === undefined) throw new Error('The board fixture is unavailable before its suite starts.');
      return started;
    }
  };
}
