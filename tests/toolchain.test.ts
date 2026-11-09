/** @file Verify compiler, formatter, type-aware rules, and Bun bundling. */
import {afterEach, describe, expect, it} from 'bun:test';
import {spawnSync} from 'node:child_process';
import {mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const workspaces: string[] = [];

afterEach(() => {
  for (const directory of workspaces.splice(0)) {
    rmSync(directory, {force: true, recursive: true});
  }
});

/** Create a disposable TypeScript project inheriting the repository policy. */
function fixture(source: string) {
  const directory = mkdtempSync(path.join(root, '.toolchain-fixture-'));
  workspaces.push(directory);
  const filename = path.join(directory, 'probe.ts');
  writeFileSync(filename, source);
  writeFileSync(
    path.join(directory, 'tsconfig.json'),
    JSON.stringify({extends: '../tsconfig.json', include: ['probe.ts']})
  );
  return {directory, filename};
}

/** Run a locally installed quality tool without resolving registry packages. */
function runTool(tool: string, args: string[]) {
  return spawnSync(path.join(root, 'node_modules/.bin', tool), args, {cwd: root, encoding: 'utf8'});
}

describe('TypeScript quality gates', () => {
  it('accepts a valid module and rejects a type mismatch', () => {
    const valid = fixture('export const count: number = 1;\n');
    const invalid = fixture("export const count: number = 'one';\n");
    expect(runTool('tsc', ['--project', valid.directory]).status).toBe(0);
    const result = runTool('tsc', ['--project', invalid.directory]);
    expect(result.status).not.toBe(0);
    expect(result.stdout).toContain('TS2322');
  });

  it('checks formatting without modifying source', () => {
    const {filename} = fixture('export const count:number=1\n');
    const result = runTool('biome', [
      'check',
      '--linter-enabled=false',
      '--assist-enabled=false',
      '--vcs-enabled=false',
      filename
    ]);
    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain('format');
    expect(readFileSync(filename, 'utf8')).toBe('export const count:number=1\n');
  });

  it('runs the type-aware promise rule', () => {
    const {filename, directory} = fixture('/** @file Floating promise fixture. */\nPromise.resolve(1);\n');
    const result = runTool('oxlint', ['--no-ignore', '--tsconfig', path.join(directory, 'tsconfig.json'), filename]);
    expect(result.status).not.toBe(0);
    expect(result.stdout).toContain('no-floating-promises');
  });

  it('bundles TypeScript with the Bun API', async () => {
    const {filename} = fixture('export const count: number = 1;\n');
    const result = await Bun.build({entrypoints: [filename], target: 'browser'});
    expect(result.success).toBe(true);
    expect(result.outputs).toHaveLength(1);
    expect(await result.outputs[0]?.text()).toContain('count');
  });
});
