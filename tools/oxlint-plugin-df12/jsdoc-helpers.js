/**
 * @file Local Oxlint rules for maintainability and documentation contracts.
 *
 * The plugin uses Oxlint's ESLint-compatible JavaScript plugin API so the
 * project can enforce local rules without a separate linting process.
 */
import {existsSync, readFileSync} from 'node:fs';
import path from 'node:path';
import {z} from 'zod';

const FUNCTION_NODE_TYPES = new Set(['ArrowFunctionExpression', 'FunctionDeclaration', 'FunctionExpression']);
let baselineCache = null;

/** Loads baseline entries from the repository root. */
function loadBaseline() {
  if (baselineCache) return baselineCache;

  const baselinePath = path.join(process.cwd(), '.jsdoc-baseline.json');
  if (!existsSync(baselinePath)) {
    baselineCache = new Set();
    return baselineCache;
  }

  try {
    const parsed = JSON.parse(readFileSync(baselinePath, 'utf8'));
    baselineCache = new Set(parsed.entries);
    return baselineCache;
  } catch (error) {
    console.warn(
      `Failed to load JSDoc baseline JSON at ${baselinePath}; ignoring baseline entries: ${
        error instanceof Error ? error.message : String(error)
      }`
    );
    baselineCache = new Set();
    return baselineCache;
  }
}

/** Clears cached baseline state for deterministic unit tests. */
function resetBaselineCache() {
  baselineCache = null;
}

/** Returns a repository-relative path for a linted file. */
function relativeFilename(context) {
  const filename = context.filename ?? context.getFilename?.() ?? '';
  return path.relative(process.cwd(), filename).replaceAll(path.sep, '/');
}

/** Builds the documentation baseline key for a function record. */
function baselineKey(context, record) {
  return `${relativeFilename(context)}#${record.name}`;
}

/** Reports whether an AST node is a function-like node. */
function isFunctionNode(node) {
  return Boolean(node && FUNCTION_NODE_TYPES.has(node.type));
}

/** Reports whether a statement is directly under the program. */
function isTopLevelStatement(node) {
  return node?.parent?.type === 'Program';
}

/** Reports whether a declaration is exported directly or by re-export. */
function isExported(node, exportedNames = new Set()) {
  const directlyExported =
    node?.parent?.type === 'ExportNamedDeclaration' || node?.parent?.type === 'ExportDefaultDeclaration';
  return directlyExported || exportedNames.has(functionName(node));
}

/** Collects local names exported through named and default export declarations. */
function collectExportedNames(program) {
  return new Set(program.body.flatMap((statement) => exportedNamesFromStatement(statement)));
}

/** Returns local names from one export statement. */
function exportedNamesFromStatement(statement) {
  if (statement.type === 'ExportDefaultDeclaration') return defaultExportedNames(statement);
  if (statement.type === 'ExportNamedDeclaration') {
    return (statement.specifiers ?? []).flatMap((specifier) => exportedSpecifierName(specifier));
  }
  return [];
}

/** Returns the local name exported by one export specifier. */
function exportedSpecifierName(specifier) {
  const local = specifier.local;
  return local?.type === 'Identifier' ? [local.name] : [];
}

/** Returns local names from `export default name` statements. */
function defaultExportedNames(statement) {
  const declaration = statement.declaration;
  if (declaration?.type === 'Identifier') return [declaration.name];
  return [];
}

/** Returns the top-level statement that owns declaration comments. */
function docsNodeForFunction(node) {
  return isExported(node) ? node.parent : node;
}

/** Returns the top-level statement that owns variable comments. */
function docsNodeForVariable(node) {
  const declaration = node.parent;
  return declaration?.parent?.type === 'ExportNamedDeclaration' ? declaration.parent : declaration;
}

/** Reports whether a variable declarator is a covered top-level function. */
function isTopLevelFunctionVariable(node) {
  const declaration = node.parent;
  return declaration?.parent?.type === 'Program' || declaration?.parent?.type === 'ExportNamedDeclaration';
}

/** Returns a stable name for a function declaration. */
function functionName(node) {
  return node.id?.name ?? 'default';
}

/** Returns a stable name for a variable declarator. */
function variableName(node) {
  return node.id?.type === 'Identifier' ? node.id.name : undefined;
}

/** Creates a function record for a top-level function declaration. */
function functionRecord(node, exportedNames = new Set()) {
  return {
    docsNode: docsNodeForFunction(node),
    functionNode: node,
    isPublic: isExported(node, exportedNames),
    name: functionName(node)
  };
}

/** Creates a function record for a top-level function variable. */
function variableFunctionRecord(node, exportedNames = new Set()) {
  const name = variableName(node);
  return {
    docsNode: docsNodeForVariable(node),
    functionNode: node.init,
    isPublic: node.parent?.parent?.type === 'ExportNamedDeclaration' || exportedNames.has(name),
    name
  };
}

/** Creates a function record for an inline default-exported function expression. */
function defaultFunctionExpressionRecord(node) {
  return {
    docsNode: node.parent,
    functionNode: node,
    isPublic: true,
    name: functionName(node)
  };
}

/** Parses the closest leading JSDoc block for a declaration. */
function parseLeadingJsDoc(context, node) {
  const comments = context.sourceCode.getCommentsBefore(node) ?? [];
  const jsdoc = comments.findLast((comment) => comment.type === 'Block' && comment.value.trimStart().startsWith('*'));
  if (!jsdoc) return;
  return parseJsDocBlock(`/*${jsdoc.value}*/`);
}

/** Parses a raw JSDoc block into description lines and tags. */
function parseJsDocBlock(rawComment) {
  const descriptionLines = [];
  const tags = new Map();
  for (const line of jsDocLines(rawComment)) {
    recordJsDocLine(line, descriptionLines, tags);
  }

  return {descriptionLines, tags};
}

/** Normalizes a raw JSDoc block into trimmed content lines. */
function jsDocLines(rawComment) {
  return rawComment
    .replace(/^\/\*\*/, '')
    .replace(/\*\/$/, '')
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*\* ?/, '').trim());
}

/** Records one JSDoc content line as description text or a tag. */
function recordJsDocLine(line, descriptionLines, tags) {
  if (!line) return;
  if (line.startsWith('@')) {
    recordJsDocTag(line, tags);
    return;
  }
  if (tags.size === 0) descriptionLines.push(line);
}

/** Records one normalized JSDoc tag line. */
function recordJsDocTag(line, tags) {
  const [, tagName, tagText = ''] = /^@(\S+)\s*(.*)$/.exec(line) ?? [];
  if (!tagName) return;
  tags.set(tagName, [...(tags.get(tagName) ?? []), tagText.trim()]);
}

/** Returns public parameter names that should have `@param` entries. */
function parameterNames(node) {
  return (node.params ?? []).flatMap((param) => boundNames(param));
}

/** Returns identifier names bound by a parameter pattern. */
function boundNames(node) {
  if (!node) return [];
  if (node.type === 'Identifier') return [node.name];
  if (node.type === 'AssignmentPattern') return boundNames(node.left);
  if (node.type === 'RestElement') return boundNames(node.argument);
  if (node.type === 'ObjectPattern') return node.properties.flatMap((property) => propertyNames(property));
  if (node.type === 'ArrayPattern') return node.elements.flatMap((element) => boundNames(element));
  return [];
}

/** Returns identifier names bound by an object pattern property. */
function propertyNames(node) {
  if (node.type === 'Property') return boundNames(node.value);
  if (node.type === 'RestElement') return boundNames(node.argument);
  return [];
}

/** Reports whether a node is a return statement with a value. */
function isValueReturn(node) {
  return node?.type === 'ReturnStatement' && Boolean(node.argument);
}

/** Reports whether an arrow function has an expression body. */
function hasExpressionBody(node) {
  return node.type === 'ArrowFunctionExpression' && node.body?.type !== 'BlockStatement';
}

/** Reports whether a function body returns a value. */
function returnsValue(node) {
  if (hasExpressionBody(node)) return true;
  return containsNode(node.body, node, isValueReturn);
}

/** Reports whether a node is a throw or promise rejection. */
function isThrowOrReject(node) {
  return node?.type === 'ThrowStatement' || isPromiseRejectCall(node);
}

/** Reports whether a function can throw or reject from its own body. */
function canThrow(node) {
  return containsNode(node.body, node, isThrowOrReject);
}

/** Reports whether a node calls `Promise.reject(...)`. */
function isPromiseRejectCall(node) {
  if (node?.type !== 'CallExpression') return false;
  return isPromiseRejectMember(node.callee);
}

/** Reports whether a member expression reads `Promise.reject`. */
function isPromiseRejectMember(node) {
  if (node?.type !== 'MemberExpression') return false;
  return isPromiseObject(node.object) && isRejectProperty(node.property);
}

/** Reports whether a member object is the global `Promise` identifier. */
function isPromiseObject(node) {
  return node?.type === 'Identifier' && node.name === 'Promise';
}

/** Reports whether a member property is the `reject` identifier. */
function isRejectProperty(node) {
  return node?.type === 'Identifier' && node.name === 'reject';
}

/** Searches a subtree while skipping nested function bodies. */
function containsNode(node, root, predicate) {
  if (!node) return false;
  if (node !== root && isFunctionNode(node)) return false;
  if (predicate(node)) return true;
  return childNodes(node).some((child) => containsNode(child, root, predicate));
}

/** Returns child AST nodes for a generic ESTree node. */
function childNodes(node) {
  return Object.entries(node).flatMap(([key, value]) => (key === 'parent' ? [] : nodeValues(value)));
}

/** Converts a node property value into child AST nodes. */
function nodeValues(value) {
  if (Array.isArray(value)) return value.filter((item) => isAstNode(item));
  return isAstNode(value) ? [value] : [];
}

/** Reports whether a value looks like an ESTree AST node. */
function isAstNode(value) {
  return Boolean(value && z.string().safeParse(value.type).success);
}

export default {
  baselineKey,
  canThrow,
  childNodes,
  collectExportedNames,
  defaultFunctionExpressionRecord,
  functionRecord,
  isFunctionNode,
  isTopLevelFunctionVariable,
  isTopLevelStatement,
  loadBaseline,
  parameterNames,
  parseLeadingJsDoc,
  resetBaselineCache,
  returnsValue,
  variableFunctionRecord,
  containsNode
};
