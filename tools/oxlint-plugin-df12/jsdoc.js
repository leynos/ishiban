/** @file Public, private, and module documentation rules imported from Simulacat. */
import helpers from './jsdoc-helpers.js';

const MODULE_JSDOC_PATTERN =
  /^(?:#![^\n]*\n)?(?:\/\*![\s\S]*?\*\/\s*)?(?:(?:'use strict'|"use strict");\s*)?\s*\/\*\*[\s\S]*?@file[\s\S]*?\*\//;

const {
  baselineKey,
  canThrow,
  collectExportedNames,
  defaultFunctionExpressionRecord,
  functionRecord,
  isFunctionNode,
  isTopLevelFunctionVariable,
  isTopLevelStatement,
  loadBaseline,
  parameterNames,
  parseLeadingJsDoc,
  returnsValue,
  variableFunctionRecord
} = helpers;
/** Reports whether a function record is skipped by the baseline. */
function isBaselined(context, record, baseline) {
  return baseline.has(baselineKey(context, record));
}

/** Reports a missing JSDoc block for a covered function. */
function reportMissingJsDoc(context, record) {
  const visibility = record.isPublic ? 'Exported' : 'Private';
  context.report({node: record.docsNode, message: `${visibility} function "${record.name}" needs JSDoc.`});
}

/** Validates public JSDoc description text. */
function checkPublicDescription(context, record, docs) {
  if (docs.descriptionLines.length > 0) return;
  context.report({
    node: record.docsNode,
    message: `Exported function "${record.name}" needs a usage-oriented description.`
  });
}

/** Validates public JSDoc parameter tags. */
function checkPublicParams(context, record, docs) {
  const paramTags = docs.tags.get('param') ?? [];
  for (const name of parameterNames(record.functionNode)) {
    if (hasParamTag(paramTags, name)) continue;
    context.report({
      node: record.docsNode,
      message: `Exported function "${record.name}" must document parameter "${name}".`
    });
  }
}

/** Reports whether a parameter has a matching tag. */
function hasParamTag(paramTags, name) {
  return paramTags.some((tag) => tag === name || tag.startsWith(`${name} `));
}

/** Reports whether return documentation is absent. */
function lacksReturnDocumentation(docs) {
  return !docs.tags.has('returns') && !docs.tags.has('return');
}

/** Reports whether error documentation is absent. */
function lacksErrorDocumentation(docs) {
  return !docs.tags.has('throws') && !docs.tags.has('rejects');
}

/** Validates public JSDoc return tags. */
function checkPublicReturn(context, record, docs) {
  if (!returnsValue(record.functionNode)) return;
  if (!lacksReturnDocumentation(docs)) return;
  context.report({
    node: record.docsNode,
    message: `Exported function "${record.name}" must document its return value.`
  });
}

/** Validates public JSDoc error tags. */
function checkPublicThrows(context, record, docs) {
  if (!canThrow(record.functionNode)) return;
  if (!lacksErrorDocumentation(docs)) return;
  context.report({
    node: record.docsNode,
    message: `Exported function "${record.name}" must document thrown or rejected errors.`
  });
}

/** Validates the complete public JSDoc contract. */
function checkPublicFunction(context, record, docs) {
  checkPublicDescription(context, record, docs);
  checkPublicParams(context, record, docs);
  checkPublicReturn(context, record, docs);
  checkPublicThrows(context, record, docs);
}

/** Reports whether private JSDoc is a one-line summary. */
function hasConcisePrivateSummary(docs) {
  const nonInternalTags = [...docs.tags.keys()].filter((tag) => tag !== 'internal');
  return docs.descriptionLines.length === 1 && nonInternalTags.length === 0;
}

/** Validates the private JSDoc contract. */
function checkPrivateFunction(context, record, docs) {
  if (hasConcisePrivateSummary(docs)) return;
  context.report({
    node: record.docsNode,
    message: `Private function "${record.name}" needs a concise one-line JSDoc summary.`
  });
}

/** Checks a single covered function record. */
function checkFunctionRecord(context, record, baseline) {
  if (!record.name || isBaselined(context, record, baseline)) return;
  const docs = parseLeadingJsDoc(context, record.docsNode);
  if (!docs) {
    reportMissingJsDoc(context, record);
    return;
  }
  if (record.isPublic) checkPublicFunction(context, record, docs);
  else checkPrivateFunction(context, record, docs);
}

const requireModuleJsDocRule = {
  meta: {type: 'suggestion', schema: []},
  create(context) {
    return {
      Program(node) {
        if (MODULE_JSDOC_PATTERN.test(context.sourceCode.text)) return;
        context.report({node, message: 'JS/TS files must start with a module-level JSDoc block containing @file.'});
      }
    };
  }
};

const requirePublicJsDocRule = {
  meta: {type: 'suggestion', schema: []},
  create(context) {
    const baseline = loadBaseline();
    let exportedNames = new Set();
    return {
      Program(node) {
        exportedNames = collectExportedNames(node);
      },
      FunctionDeclaration(node) {
        const record = functionRecord(node, exportedNames);
        if (!record.isPublic) return;
        checkFunctionRecord(context, record, baseline);
      },
      ExportDefaultDeclaration(node) {
        if (!isFunctionNode(node.declaration) || node.declaration.type === 'FunctionDeclaration') return;
        checkFunctionRecord(context, defaultFunctionExpressionRecord(node.declaration), baseline);
      },
      VariableDeclarator(node) {
        if (!isFunctionNode(node.init)) return;
        const record = variableFunctionRecord(node, exportedNames);
        if (record.isPublic) checkFunctionRecord(context, record, baseline);
      }
    };
  }
};

const requirePrivateJsDocRule = {
  meta: {type: 'suggestion', schema: []},
  create(context) {
    const baseline = loadBaseline();
    let exportedNames = new Set();
    return {
      Program(node) {
        exportedNames = collectExportedNames(node);
      },
      FunctionDeclaration(node) {
        if (!isTopLevelStatement(node)) return;
        const record = functionRecord(node, exportedNames);
        if (record.isPublic) return;
        checkFunctionRecord(context, record, baseline);
      },
      VariableDeclarator(node) {
        if (!isFunctionNode(node.init) || !isTopLevelFunctionVariable(node)) return;
        const record = variableFunctionRecord(node, exportedNames);
        if (!record.isPublic) checkFunctionRecord(context, record, baseline);
      }
    };
  }
};

export default {requireModuleJsDocRule, requirePublicJsDocRule, requirePrivateJsDocRule};
