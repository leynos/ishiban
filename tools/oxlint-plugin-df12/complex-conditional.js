/** @file Predicate complexity rule imported from Simulacat. */
import helpers from './jsdoc-helpers.js';
const {childNodes, isFunctionNode} = helpers;
const TEST_STATEMENT_NODE_TYPES = new Set(['DoWhileStatement', 'ForStatement', 'IfStatement', 'WhileStatement']);
/** Returns configured complex conditional rule options. */
function complexConditionalOptions(context) {
  const options = context.options?.[0] ?? {};
  return {
    includeNullishCoalescing: options.includeNullishCoalescing ?? false,
    includeTernary: options.includeTernary ?? true,
    maxLogicalOperators: options.maxLogicalOperators ?? 1
  };
}

/** Reports whether a logical operator should count as predicate complexity. */
function shouldCountLogicalOperator(operator, options) {
  if (operator === '&&' || operator === '||') return true;
  return operator === '??' && options.includeNullishCoalescing;
}

/** Counts logical operators inside one predicate expression. */
function countPredicateOperators(node, options) {
  if (!node || isFunctionNode(node)) return 0;
  const ownCount = predicateNodeCount(node, options);
  return ownCount + childNodes(node).reduce((sum, child) => sum + countPredicateOperators(child, options), 0);
}

/** Counts the current predicate node when it is an operator of interest. */
function predicateNodeCount(node, options) {
  if (node.type === 'LogicalExpression' && shouldCountLogicalOperator(node.operator, options)) return 1;
  if (node.type === 'ConditionalExpression' && options.includeTernary) return 1;
  return 0;
}

/** Reports whether a ternary is already checked as a statement test. */
function isDirectStatementTest(node) {
  return TEST_STATEMENT_NODE_TYPES.has(node.parent?.type) && node.parent.test === node;
}

/** Reports a predicate when it exceeds the configured operator threshold. */
function checkPredicate(context, node) {
  if (!node) return;
  const options = complexConditionalOptions(context);
  const count = countPredicateOperators(node, options);
  if (count <= options.maxLogicalOperators) return;
  context.report({
    node,
    message: `Conditional has ${count} logical operators; extract a named predicate or split into guard clauses.`
  });
}

const complexConditionalRule = {
  meta: {
    type: 'suggestion',
    schema: [
      {
        type: 'object',
        additionalProperties: false,
        properties: {
          includeNullishCoalescing: {type: 'boolean'},
          includeTernary: {type: 'boolean'},
          maxLogicalOperators: {type: 'number'}
        }
      }
    ]
  },
  create(context) {
    return {
      ConditionalExpression(node) {
        if (isDirectStatementTest(node)) return;
        const options = complexConditionalOptions(context);
        checkPredicate(context, options.includeTernary ? node : node.test);
      },
      DoWhileStatement(node) {
        checkPredicate(context, node.test);
      },
      ForStatement(node) {
        checkPredicate(context, node.test);
      },
      IfStatement(node) {
        checkPredicate(context, node.test);
      },
      WhileStatement(node) {
        checkPredicate(context, node.test);
      }
    };
  }
};

export default {complexConditionalRule, countPredicateOperators};
