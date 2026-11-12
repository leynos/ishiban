/** @file Share bounded agent-browser commands between native Chromium suites. */
import {Option, Schema} from 'effect';
import {runCapturedCommand} from './browser-command';

const TabListSchema = Schema.Struct({data: Schema.Struct({tabs: Schema.Array(Schema.Unknown)})});

/** One owned Chromium session whose commands fail loudly when the CLI refuses them. */
export interface BrowserSession {
  readonly browser: (...args: string[]) => Promise<string>;
  readonly browserJson: <Value>(expression: string) => Promise<Value>;
  readonly countTabs: () => Promise<number>;
}

/**
 * Create the browser command boundary for one uniquely named CLI session.
 * @param sessionName Unique agent-browser session owned by the calling suite.
 * @returns Commands, JSON evaluation and a real-tab count for that session.
 * @example
 * const {browser, browserJson} = createBrowserSession('layout-1');
 * await browser('reload');
 * const width = await browserJson<number>('innerWidth');
 */
export function createBrowserSession(sessionName: string): BrowserSession {
  /** Run the owned browser CLI; for example, browser('reload'). */
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

  /** Decode one bounded browser measurement returned by the owned CLI. */
  async function browserJson<Value>(expression: string): Promise<Value> {
    return JSON.parse(await browser('eval', expression));
  }

  /** Count real browser tabs without deriving it from app state. */
  async function countTabs(): Promise<number> {
    const parsed = Schema.decodeUnknownOption(TabListSchema)(JSON.parse(await browser('tab', 'list', '--json')));
    if (Option.isNone(parsed)) {
      throw new Error('Expected agent-browser tab list output shaped {"data":{"tabs":[]}}.');
    }
    return parsed.value.data.tabs.length;
  }

  return {browser, browserJson, countTabs};
}
