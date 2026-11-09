/** @file Imported public, private, and module documentation tests. */
import {describe, expect, it} from 'bun:test';
import {mkdtempSync, rmSync, writeFileSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {testInternals} from '../tools/oxlint-plugin-df12/index.js';
import fixtures from './fixtures/oxlint.js';
const {JSDOC_RULES, createWorkspace, writeConfig, writeSource, runOxlint, countRuleFindings, runFixture} = fixtures;
describe('df12 JSDoc rules', () => {
  it('reports module, public function, and private function documentation contract violations', () => {
    const result = runFixture({
      rules: JSDOC_RULES,
      name: 'missing-jsdoc.ts',
      source: `
          export function publicApi(value) {
            if (!value) {
              throw new Error('missing');
            }
            return value;
          }

          const privateHelper = () => 'value';

          function reExported(value) {
            return value;
          }

          export { reExported };
        `
    });

    expect(result.status).toBe(1);
    expect(result.stdout).toContain('df12(require-module-jsdoc)');
    expect(result.stdout).toContain('df12(require-public-jsdoc)');
    expect(result.stdout).toContain('df12(require-private-jsdoc)');
  });

  it('accepts supported documented function declaration shapes', () => {
    const result = runFixture({
      rules: JSDOC_RULES,
      name: 'documented.ts',
      source: `
          /** @file Documented fixture. */

          /**
           * Reads one public value.
           *
           * @param value Value to read.
           * @returns The original value.
           */
          export function publicApi(value) {
            return value;
          }

          /**
           * Reads one default value.
           *
           * @param value Value to read.
           * @returns The original value.
           */
          export default function defaultApi(value) {
            return value;
          }

          /**
           * Reads one arrow value.
           *
           * @param value Value to read.
           * @returns The original value.
           */
          export const arrowApi = (value) => value;

          /**
           * Raises a documented fixture failure.
           *
           * @throws Always raises a fixture failure.
           */
          export function throwsApi() {
            throw new Error('failure');
          }

          /**
           * Reads a trailing re-exported value.
           *
           * @param value Value to read.
           * @returns The original value.
           */
          function reExported(value) {
            return value;
          }

          /** Builds a private value. */
          function privateHelper() {
            return 'value';
          }

          /** Builds a private arrow value. */
          const privateArrow = () => 'value';

          export { reExported };
        `
    });

    expect(result.status).toBe(0);
    expect(result.stdout).toBe('');
  });
});

describe('df12 JSDoc default exports', () => {
  it('reports missing JSDoc for default-exported expressions and aliases', () => {
    const expressionResult = runFixture({
      rules: JSDOC_RULES,
      name: 'default-expression.ts',
      source: `
          /** @file Default expression fixture. */

          export default (value) => value;
        `
    });
    const aliasResult = runFixture({
      rules: JSDOC_RULES,
      name: 'default-alias.ts',
      source: `
          /** @file Default alias fixture. */

          const defaultAlias = (value) => value;

          export default defaultAlias;
        `
    });

    expect(countRuleFindings(expressionResult.stdout, 'df12(require-public-jsdoc)')).toBeGreaterThan(0);
    expect(countRuleFindings(aliasResult.stdout, 'df12(require-public-jsdoc)')).toBeGreaterThan(0);
    expect(aliasResult.stdout).not.toContain('df12(require-private-jsdoc)');
  });
});

describe('df12 JSDoc negative cases', () => {
  it('reports targeted public JSDoc tag omissions', () => {
    const result = runFixture({
      rules: JSDOC_RULES,
      name: 'missing-tags.ts',
      source: `
          /** @file Missing tag fixture. */

          /**
           * Reads a value.
           *
           * @returns The original value.
           */
          export function missingParam(value) {
            return value;
          }

          /**
           * Reads a value.
           *
           * @param value Value to read.
           */
          export function missingReturn(value) {
            return value;
          }
        `
    });

    expect(result.stdout).toContain('Exported function "missingParam" must document parameter "value".');
    expect(result.stdout).toContain('Exported function "missingReturn" must document its return value.');
  });

  it('accepts a documented default-exported alias as public JSDoc', () => {
    const result = runFixture({
      rules: JSDOC_RULES,
      name: 'documented-default-alias.ts',
      source: `
          /** @file Documented default alias fixture. */

          /**
           * Reads one default aliased value.
           *
           * @param value Value to read.
           * @returns The original value.
           */
          const defaultAlias = (value) => value;

          export default defaultAlias;
        `
    });

    expect(result.status).toBe(0);
    expect(result.stdout).toBe('');
  });
});

describe('df12 JSDoc baseline', () => {
  it('uses the current baseline file for each lint process', () => {
    const workspace = createWorkspace();
    try {
      const configPath = writeConfig({
        directory: workspace.directory,
        rules: JSDOC_RULES
      });
      const filePath = writeSource({
        directory: workspace.directory,
        name: 'baseline.ts',
        source: `
          /** @file Baseline fixture. */

          export function skipped(value) {
            return value;
          }
        `
      });
      const baselinePath = path.join(workspace.directory, '.jsdoc-baseline.json');
      writeFileSync(baselinePath, JSON.stringify({entries: ['baseline.ts#skipped']}), 'utf8');

      const skippedResult = runOxlint({configPath, cwd: workspace.directory, filePath});
      writeFileSync(baselinePath, JSON.stringify({entries: []}), 'utf8');
      const reportedResult = runOxlint({configPath, cwd: workspace.directory, filePath});

      expect(skippedResult.stdout).not.toContain('df12(require-public-jsdoc)');
      expect(reportedResult.stdout).toContain('df12(require-public-jsdoc)');
    } finally {
      workspace.cleanup();
    }
  });

  it('caches an empty baseline when the baseline JSON is invalid', () => {
    testInternals.resetBaselineCache();
    const directory = mkdtempSync(path.join(os.tmpdir(), 'simulacat-oxlint-plugin-'));
    const previousCwd = process.cwd();
    try {
      const baselinePath = path.join(directory, '.jsdoc-baseline.json');
      writeFileSync(baselinePath, '{', 'utf8');
      process.chdir(directory);

      const invalidBaseline = testInternals.loadBaseline();
      writeFileSync(baselinePath, JSON.stringify({entries: ['later.ts#value']}), 'utf8');
      const cachedBaseline = testInternals.loadBaseline();

      expect(invalidBaseline.size).toBe(0);
      expect(cachedBaseline.size).toBe(0);
      expect(cachedBaseline).toBe(invalidBaseline);
    } finally {
      process.chdir(previousCwd);
      rmSync(directory, {force: true, recursive: true});
    }
  });
});
