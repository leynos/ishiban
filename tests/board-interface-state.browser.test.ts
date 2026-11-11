/** @file Exercise saved interface state through a real server and Chromium. */
import {afterAll, beforeAll, describe, expect, it} from 'bun:test';
import {mkdtemp, rm, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Schema} from 'effect';
import {SnapshotSchema} from '../src/contracts';
import {runCapturedCommand} from './browser-command';
import {isBrowserEnabled} from './native-browser-environment';

const repository = fileURLToPath(new URL('..', import.meta.url));
const python = path.join(repository, '.venv/bin/python');
const sessionName = `ishiban-prefs-${process.pid}-${crypto.randomUUID()}`;
const workspaceId = `browser-${crypto.randomUUID()}`;
const SETUP_TIMEOUT_MS = 100_000;
const DEFAULT_CASE_TIMEOUT_MS = 120_000;
const SAVED_CASE_TIMEOUT_MS = 240_000;
const CLEANUP_TIMEOUT_MS = 40_000;
const SERVER_WATCHDOG_MS = SETUP_TIMEOUT_MS + 2 * DEFAULT_CASE_TIMEOUT_MS + SAVED_CASE_TIMEOUT_MS + CLEANUP_TIMEOUT_MS;
const defaultVisiblePreferences = {
  density: 'overview',
  presentation: 'panorama',
  matrixPressed: 'false'
};
let stateDirectory: string | undefined;
let server: ReturnType<typeof Bun.spawn> | undefined;
let serverWatchdog: ReturnType<typeof setTimeout> | undefined;
let origin: string | undefined;
let browserMayBeOpen = false;

/** Run one bounded CLI command without a shell or inherited output pipes. */
async function command(args: readonly string[]): Promise<string> {
  const {stdout, stderr, status} = await runCapturedCommand(args, 20_000);
  if (status !== 0) throw new Error(`Command failed (${status}): ${stderr || stdout}`);
  return stdout.trim();
}

/** Address only the uniquely named browser context owned by this test. */
async function browser(...args: string[]): Promise<string> {
  return command(['agent-browser', '--session', sessionName, ...args]);
}

/** Bound one server exit wait while allowing the caller to reap after SIGKILL. */
async function exitedWithin(timeoutMs: number): Promise<boolean> {
  if (!server) return true;
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      server.exited.then(() => true),
      new Promise<boolean>((resolve) => {
        timer = setTimeout(() => resolve(false), timeoutMs);
      })
    ]);
  } finally {
    clearTimeout(timer);
  }
}

/** Give the owned server a graceful exit before a bounded force-reap. */
async function stopServer(): Promise<void> {
  if (server?.exitCode !== null) return;
  server.kill('SIGINT');
  if (await exitedWithin(8000)) return;
  server.kill('SIGKILL');
  if (!(await exitedWithin(2000))) throw new Error('Test server did not reap after SIGKILL.');
}

/** Reap only the owned server; release its private state even after a failed test. */
async function stopFixture(): Promise<void> {
  clearTimeout(serverWatchdog);
  try {
    await stopServer();
  } finally {
    if (stateDirectory) await rm(stateDirectory, {recursive: true, force: true});
  }
}

/** Read the startup snapshot with a one-second request budget. */
async function observedWorkspace(base: string): Promise<string | undefined> {
  try {
    const response = await fetch(`${base}/api/v1/snapshot`, {signal: AbortSignal.timeout(1000)});
    if (!response.ok) return undefined;
    const snapshot = Schema.decodeUnknownSync(SnapshotSchema)(await response.json());
    return snapshot.workspaceId;
  } catch {
    return undefined;
  }
}

/** Reject a listener that belongs to another test process or workspace. */
function assertOwnWorkspace(observed: string): void {
  if (observed !== workspaceId) throw new Error('The loopback port served a different workspace.');
}

/** Wait for this process's snapshot, not another listener on a reused port. */
async function waitForOwnSnapshot(base: string): Promise<void> {
  const child = server;
  if (!child) throw new Error('Test server was not started.');
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error('Test server exited before readiness.');
    const observed = await observedWorkspace(base);
    if (observed !== undefined) {
      assertOwnWorkspace(observed);
      return;
    }
    await Bun.sleep(50);
  }
  throw new Error('Test server did not expose its own snapshot within 10 seconds.');
}

/** Read visible controls after the real snapshot has rendered. */
async function visiblePreferences(): Promise<{density: string; presentation: string; matrixPressed: string}> {
  const result = await browser(
    'eval',
    `(()=>{const board=document.querySelector('.ishiban-board');
      const density=document.querySelector('select[aria-label="Mark density"]');
      const matrix=[...document.querySelectorAll('.presentation-control button')]
        .find((button)=>button.textContent?.trim()==='Matrix');
      return {density:density?.value,presentation:board?.dataset.presentation,
        matrixPressed:matrix?.getAttribute('aria-pressed')};})()`
  );
  return JSON.parse(result);
}

/** Start one private, migrated server and browser, cleaning up failed setup. */
async function startFixture(): Promise<void> {
  try {
    stateDirectory = await mkdtemp(path.join(tmpdir(), 'ishiban-prefs-'));
    await writeFile(
      path.join(stateDirectory, 'workspace.json'),
      JSON.stringify({workspaceId, selector: 'browser-fixture'})
    );
    const bootstrap = `import asyncio, sys\nfrom pathlib import Path\nfrom ishiban.cli import database_url\nfrom ishiban.storage import Store\nasync def main():\n    store = Store(database_url(Path(sys.argv[1])), sys.argv[2])\n    try:\n        await store.initialize()\n    finally:\n        await store.close()\nasyncio.run(main())`;
    await command([python, '-c', bootstrap, stateDirectory, workspaceId]);

    const reservation = Bun.serve({hostname: '127.0.0.1', port: 0, fetch: () => new Response()});
    const port = reservation.port;
    await reservation.stop(true);
    origin = `http://127.0.0.1:${port}`;
    server = Bun.spawn({
      cmd: [python, '-m', 'ishiban.cli', 'serve', '--state-directory', stateDirectory, '--port', String(port)],
      cwd: repository,
      stdout: 'ignore',
      stderr: 'ignore'
    });
    serverWatchdog = setTimeout(() => server?.kill('SIGKILL'), SERVER_WATCHDOG_MS);
    await waitForOwnSnapshot(origin);
    browserMayBeOpen = true;
    await browser('open', origin);
    await browser('wait', '--fn', 'document.querySelector(".ishiban-board") !== null');
  } catch (error) {
    try {
      if (browserMayBeOpen) await browser('close');
    } finally {
      browserMayBeOpen = false;
      await stopFixture();
    }
    throw error;
  }
}

describe.skipIf(!isBrowserEnabled)('real browser saved preferences', () => {
  beforeAll(startFixture, SETUP_TIMEOUT_MS);

  afterAll(async () => {
    try {
      if (browserMayBeOpen) await browser('close');
    } finally {
      browserMayBeOpen = false;
      await stopFixture();
    }
  }, CLEANUP_TIMEOUT_MS);

  it(
    'uses default controls when the browser has no cookie',
    async () => {
      await browser('cookies', 'clear');
      await browser('reload');
      await browser('wait', '--fn', 'document.querySelector(".ishiban-board") !== null');
      expect(await visiblePreferences()).toEqual(defaultVisiblePreferences);
    },
    DEFAULT_CASE_TIMEOUT_MS
  );

  it(
    'saves both visible controls and restores them from the real snapshot after reload',
    async () => {
      await browser('select', 'select[aria-label="Mark density"]', 'roomy');
      await browser('wait', '--fn', 'document.querySelector(".board-footer [role=status]")?.textContent === ""');
      await browser('find', 'role', 'button', 'click', '--name', 'Matrix', '--exact');
      await browser('wait', '--fn', 'document.querySelector(".board-footer [role=status]")?.textContent === ""');
      expect(await browser('cookies')).toContain('ishiban_interface_state');
      await browser('reload');
      await browser('wait', '--fn', 'document.querySelector(".ishiban-board") !== null');
      expect(await visiblePreferences()).toEqual({
        density: 'roomy',
        presentation: 'matrix',
        matrixPressed: 'true'
      });
    },
    SAVED_CASE_TIMEOUT_MS
  );

  it(
    'returns visible controls to defaults for a tampered signed cookie',
    async () => {
      if (!origin) throw new Error('The owned test server has no origin.');
      await browser(
        'cookies',
        'set',
        'ishiban_interface_state',
        'tampered',
        '--url',
        origin,
        '--path',
        '/',
        '--httpOnly'
      );
      await browser('reload');
      await browser('wait', '--fn', 'document.querySelector(".ishiban-board") !== null');
      expect(await visiblePreferences()).toEqual(defaultVisiblePreferences);
    },
    DEFAULT_CASE_TIMEOUT_MS
  );
});
