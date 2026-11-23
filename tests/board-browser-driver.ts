/** @file Drive one uniquely named Chromium session against the built board. */
import {runCapturedCommand} from './browser-command';

/** Bound on one browser CLI invocation, including page waits. */
const BROWSER_DEADLINE_MS = 20_000;

/** One browser CLI bound to a session name that only this suite owns. */
export interface BoardBrowserDriver {
  run(...args: string[]): Promise<string>;
  json<Value>(expression: string): Promise<Value>;
}

/**
 * Create a browser driver bound to a suite-private session name.
 * @param sessionName Unique Chromium session identity for the owning suite.
 * @returns Bounded text and JSON command helpers.
 * @example
 * const browser = boardBrowser('ishiban-tooltip-1234');
 * await browser.run('open', 'http://127.0.0.1:8080');
 */
export function boardBrowser(sessionName: string): BoardBrowserDriver {
  const run = async (...args: string[]): Promise<string> => {
    const {stdout, stderr, status} = await runCapturedCommand(
      ['agent-browser', '--session', sessionName, ...args],
      BROWSER_DEADLINE_MS
    );
    if (status !== 0) {
      throw new Error(`Browser command ${JSON.stringify(args)} failed (${status}): ${stderr || stdout}`);
    }
    return stdout.trim();
  };
  return {
    run,
    /** Decode one bounded browser measurement returned by the owned CLI. */
    json: async <Value>(expression: string): Promise<Value> => JSON.parse(await run('eval', expression))
  };
}
