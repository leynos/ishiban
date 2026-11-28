/** @file Share bounded agent-browser commands between native Chromium suites. */
import {Option, Schema} from 'effect';
import {runCapturedCommand} from './browser-command';

const TabSchema = Schema.Struct({
  active: Schema.Boolean,
  tabId: Schema.String,
  targetId: Schema.String,
  title: Schema.String,
  type: Schema.String,
  url: Schema.String
});
const TabListSchema = Schema.Struct({data: Schema.Struct({tabs: Schema.Array(TabSchema)})});

/** One tab reported by the owned agent-browser session. */
export interface BrowserTab {
  readonly active: boolean;
  readonly tabId: string;
  readonly targetId: string;
  readonly title: string;
  readonly type: string;
  readonly url: string;
}

/** One owned Chromium session whose commands fail loudly when the CLI refuses them. */
export interface BrowserSession {
  readonly browser: (...args: string[]) => Promise<string>;
  readonly browserJson: <S extends Schema.ConstraintDecoder<unknown>>(
    expression: string,
    schema: S
  ) => Promise<S['Type']>;
  readonly tabs: () => Promise<readonly BrowserTab[]>;
  readonly countTabs: () => Promise<number>;
}

/**
 * Create the browser command boundary for one uniquely named CLI session.
 * @param sessionName Unique agent-browser session owned by the calling suite.
 * @returns Commands, schema-decoded JSON evaluation and real-tab access for that session.
 * @example
 * const {browser, browserJson} = createBrowserSession('layout-1');
 * await browser('reload');
 * const width = await browserJson('innerWidth', Schema.Number);
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

  /** Decode one bounded browser measurement against the caller's expected shape. */
  async function browserJson<S extends Schema.ConstraintDecoder<unknown>>(
    expression: string,
    schema: S
  ): Promise<S['Type']> {
    const parsed = Schema.decodeUnknownOption(schema)(JSON.parse(await browser('eval', expression)));
    if (Option.isNone(parsed)) {
      throw new Error(`Browser evaluation returned an unexpected shape: ${expression}`);
    }
    return parsed.value;
  }

  /** List real browser tabs without deriving them from app state. */
  async function tabs(): Promise<readonly BrowserTab[]> {
    const parsed = Schema.decodeUnknownOption(TabListSchema)(JSON.parse(await browser('tab', 'list', '--json')));
    if (Option.isNone(parsed)) {
      throw new Error('Expected agent-browser tab list output shaped {"data":{"tabs":[]}}.');
    }
    return parsed.value.data.tabs;
  }

  /** Count real browser tabs without deriving it from app state. */
  async function countTabs(): Promise<number> {
    const openTabs = await tabs();
    return openTabs.length;
  }

  return {browser, browserJson, tabs, countTabs};
}
