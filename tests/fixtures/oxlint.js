/** @file Isolated Oxlint fixture execution shared by imported tests. */
import {spawnSync} from 'node:child_process';
import {mkdtempSync, rmSync, writeFileSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const PROJECT_ROOT = path.resolve(import.meta.dirname, '../..');
const PLUGIN_PATH = path.join(PROJECT_ROOT, 'tools/oxlint-plugin-df12/index.js');
const JSDOC_RULES = {
  'df12/require-module-jsdoc': 'error',
  'df12/require-private-jsdoc': 'error',
  'df12/require-public-jsdoc': 'error'
};

/** Creates a temporary plugin fixture workspace. */
function createWorkspace() {
  const directory = mkdtempSync(path.join(os.tmpdir(), 'ishiban-oxlint-plugin-'));
  return {
    cleanup() {
      rmSync(directory, {force: true, recursive: true});
    },
    directory
  };
}

/** Converts the plugin path to a config-local import specifier. */
function pluginSpecifier(directory) {
  const relativePath = path.relative(directory, PLUGIN_PATH).replaceAll(path.sep, '/');
  return relativePath.startsWith('.') ? relativePath : `./${relativePath}`;
}

/** Writes an Oxlint config for a selected rule set. */
function writeConfig({directory, rules}) {
  const configPath = path.join(directory, '.oxlintrc.json');
  writeFileSync(
    configPath,
    JSON.stringify(
      {
        categories: {
          correctness: 'off',
          nursery: 'off',
          pedantic: 'off',
          perf: 'off',
          restriction: 'off',
          style: 'off',
          suspicious: 'off'
        },
        jsPlugins: [pluginSpecifier(directory)],
        rules
      },
      null,
      2
    ),
    'utf8'
  );
  return configPath;
}

/** Writes one TypeScript fixture file. */
function writeSource({directory, name, source}) {
  const filePath = path.join(directory, name);
  writeFileSync(filePath, source, 'utf8');
  return filePath;
}

/** Runs Oxlint against a fixture workspace. */
function runOxlint({configPath, cwd = PROJECT_ROOT, filePath}) {
  return spawnSync(
    path.join(PROJECT_ROOT, 'node_modules/.bin/oxlint'),
    ['-c', configPath, '--format', 'unix', filePath],
    {
      cwd,
      encoding: 'utf8'
    }
  );
}

/** Counts diagnostics for one rule id. */
function countRuleFindings(output, ruleId) {
  return output.split('\n').filter((line) => line.includes(ruleId)).length;
}

/** Replaces fixture-local absolute paths with stable snapshot text. */
function normalizeDiagnostics(output, directory) {
  return output.replaceAll(directory, '<workspace>');
}

/** Runs Oxlint against a temporary fixture workspace. */
function runFixture({rules, name, source, cwd}) {
  const workspace = createWorkspace();
  try {
    const configPath = writeConfig({directory: workspace.directory, rules});
    const filePath = writeSource({directory: workspace.directory, name, source});
    const options = {configPath, filePath};
    if (cwd !== undefined) options.cwd = cwd;
    const result = runOxlint(options);
    return {
      status: result.status,
      stdout: normalizeDiagnostics(result.stdout, workspace.directory),
      stderr: normalizeDiagnostics(result.stderr, workspace.directory)
    };
  } finally {
    workspace.cleanup();
  }
}

export default {
  PROJECT_ROOT,
  JSDOC_RULES,
  createWorkspace,
  writeConfig,
  writeSource,
  runOxlint,
  countRuleFindings,
  runFixture
};
