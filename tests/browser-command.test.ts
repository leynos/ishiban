/** @file Check browser child ownership with real bounded Bun executables. */
import {expect, it} from 'bun:test';
import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {runCapturedCommand} from './browser-command';

it('captures both real child pipes and exit status', async () => {
  const result = await runCapturedCommand(
    [process.execPath, '-e', "process.stdout.write('ready'); process.stderr.write('detail')"],
    2000
  );
  expect(result).toEqual({stdout: 'ready', stderr: 'detail', status: 0});
});

it('ends a stalled child at its owned command deadline', async () => {
  await expect(
    runCapturedCommand([process.execPath, '-e', "await Bun.sleep(800); console.log('late')"], 75)
  ).rejects.toThrow('timed out');
});

it('reaps the timed-out child before returning', async () => {
  const directory = await mkdtemp(path.join(tmpdir(), 'ishiban-browser-command-'));
  const pidFile = path.join(directory, 'pid');
  try {
    const script = `process.on('SIGTERM',()=>{}); await Bun.write(${JSON.stringify(pidFile)}, String(process.pid)); await Bun.sleep(10_000)`;
    await expect(runCapturedCommand([process.execPath, '-e', script], 2000)).rejects.toThrow('timed out');
    const pid = Number(await Bun.file(pidFile).text());
    expect(() => process.kill(pid, 0)).toThrow();
  } finally {
    await rm(directory, {recursive: true, force: true});
  }
});

it.each(['stdout', 'stderr'] as const)('stops a real child that exceeds its %s pipe budget', async (pipe) => {
  await expect(
    runCapturedCommand([process.execPath, '-e', `process.${pipe}.write('x'.repeat(70_000))`], 2000)
  ).rejects.toThrow('exceeded 65536 bytes');
});
