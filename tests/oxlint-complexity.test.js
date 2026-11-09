/** @file Imported complexity examples, diagnostics, and property tests. */
import {describe, expect, it} from 'bun:test';
import fc from 'fast-check';
import {z} from 'zod';
import {testInternals} from '../tools/oxlint-plugin-df12/index.js';
import fixtures from './fixtures/oxlint.js';
const {countRuleFindings, runFixture} = fixtures;
/** Creates an identifier AST node. */
function identifier(name) {
  return {type: 'Identifier', name};
}

/** Creates a logical expression AST node. */
function logicalExpression(operator, left = identifier('left'), right = identifier('right')) {
  return {type: 'LogicalExpression', operator, left, right};
}

/** Counts expected predicate operators for synthetic AST nodes. */
function expectedPredicateCount(node, options) {
  if (!node || ['ArrowFunctionExpression', 'FunctionDeclaration', 'FunctionExpression'].includes(node.type)) return 0;
  const ownCount = expectedOwnPredicateCount(node, options);
  return (
    ownCount + Object.entries(node).reduce((sum, [key, value]) => sum + expectedNodeValueCount(key, value, options), 0)
  );
}

/** Counts the current synthetic predicate node. */
function expectedOwnPredicateCount(node, options) {
  const logicalOperatorCount = {
    '&&': 1,
    '||': 1,
    '??': options.includeNullishCoalescing ? 1 : 0
  };
  if (node.type === 'LogicalExpression') return logicalOperatorCount[node.operator] ?? 0;
  if (node.type === 'ConditionalExpression') return options.includeTernary ? 1 : 0;
  return 0;
}

/** Counts expected predicate operators inside one AST-like property value. */
function expectedNodeValueCount(key, value, options) {
  if (key === 'parent') return 0;
  if (Array.isArray(value)) {
    return value.reduce(
      (sum, child) => sum + (isSyntheticAstNode(child) ? expectedPredicateCount(child, options) : 0),
      0
    );
  }
  return isSyntheticAstNode(value) ? expectedPredicateCount(value, options) : 0;
}

/** Reports whether a generated value is an AST-like node. */
function isSyntheticAstNode(value) {
  return Boolean(value && z.string().safeParse(value.type).success);
}

/** Builds a generated synthetic predicate AST. */
function predicateAst(maxDepth = 3) {
  const leaf = fc.record({
    name: fc.string({minLength: 1, maxLength: 8}),
    type: fc.constant('Identifier')
  });

  return fc.letrec((tie) => ({
    node:
      maxDepth <= 0 ? leaf : fc.oneof(leaf, tie('logical'), tie('conditional'), tie('wrapper'), tie('functionNode')),
    child: maxDepth <= 1 ? leaf : predicateAst(maxDepth - 1),
    logical: fc.record({
      type: fc.constant('LogicalExpression'),
      operator: fc.constantFrom('&&', '||', '??'),
      left: tie('child'),
      right: tie('child')
    }),
    conditional: fc.record({
      type: fc.constant('ConditionalExpression'),
      test: tie('child'),
      consequent: tie('child'),
      alternate: tie('child')
    }),
    wrapper: fc.record({
      type: fc.constant('CallExpression'),
      callee: leaf,
      arguments: fc.array(tie('child'), {minLength: 0, maxLength: 3})
    }),
    functionNode: fc.record({
      type: fc.constantFrom('ArrowFunctionExpression', 'FunctionDeclaration', 'FunctionExpression'),
      body: tie('logical')
    })
  })).node;
}

describe('df12/complex-conditional', () => {
  it('counts logical operators in branch predicates without counting nested callback predicates', () => {
    const result = runFixture({
      rules: {
        'df12/complex-conditional': [
          'error',
          {includeNullishCoalescing: false, includeTernary: true, maxLogicalOperators: 1}
        ]
      },
      name: 'complex-conditional.ts',
      source: `
      function checks(a, b, c, items, ready) {
        if (a) {}
        if (a && b) {}
        if (a && b && c) {}
        if ((a || b) && c) {}
        if (items.some((item) => item.ready && item.enabled) && ready) {}
      }
    `
    });

    expect(result.status).toBe(1);
    expect(countRuleFindings(result.stdout, 'df12(complex-conditional)')).toBe(2);
  });

  it('counts ternary roots and nested logical operators when ternaries are included', () => {
    const result = runFixture({
      rules: {
        'df12/complex-conditional': ['error', {includeTernary: true, maxLogicalOperators: 1}]
      },
      name: 'complex-ternary.ts',
      source: `
      const x = a ? (b && c) : d;
    `
    });

    expect(result.status).toBe(1);
    expect(countRuleFindings(result.stdout, 'df12(complex-conditional)')).toBe(1);
  });

  it('does not double-report ternaries used directly as statement tests', () => {
    const result = runFixture({
      name: 'direct-test-ternary.ts',
      rules: {
        'df12/complex-conditional': [
          'error',
          {
            includeTernary: true,
            maxLogicalOperators: 1
          }
        ]
      },
      source: `
          if (a ? (b && c) : d) {}
        `
    });

    expect(result.status).toBe(1);
    expect(countRuleFindings(result.stdout, 'df12(complex-conditional)')).toBe(1);
  });
});

describe('df12/complex-conditional diagnostics', () => {
  it('checks diagnostic output for a complex conditional', () => {
    const result = runFixture({
      rules: {
        'df12/complex-conditional': ['error', {includeTernary: true, maxLogicalOperators: 1}]
      },
      name: 'diagnostic.ts',
      source: `
      if (a && b && c) {}
    `
    });
    expect(result.stdout).toMatchSnapshot();
  });
});

describe('df12/complex-conditional properties', () => {
  it('counts generated predicate operators consistently', () => {
    const countedLogicalOperator = fc.constantFrom('&&', '||');
    const valueExpression = fc.record({
      type: fc.constant('Identifier'),
      name: fc.string({minLength: 1, maxLength: 8})
    });
    const logicalExpression = fc.record({
      type: fc.constant('LogicalExpression'),
      operator: countedLogicalOperator,
      left: valueExpression,
      right: valueExpression
    });
    const conditionalExpression = fc.record({
      type: fc.constant('ConditionalExpression'),
      test: valueExpression,
      consequent: logicalExpression,
      alternate: valueExpression
    });

    fc.assert(
      fc.property(fc.array(logicalExpression, {minLength: 0, maxLength: 20}), (expressions) => {
        const body = {
          type: 'SequenceExpression',
          expressions
        };
        expect(testInternals.countPredicateOperators(body, {includeTernary: false})).toBe(expressions.length);
      })
    );

    fc.assert(
      fc.property(conditionalExpression, (expression) => {
        expect(testInternals.countPredicateOperators(expression, {includeTernary: true})).toBe(2);
        expect(testInternals.countPredicateOperators(expression, {includeTernary: false})).toBe(1);
      })
    );
  });

  it('matches generated nested predicate counts for all options', () => {
    const optionsArbitrary = fc.record({
      includeNullishCoalescing: fc.boolean(),
      includeTernary: fc.boolean()
    });

    fc.assert(
      fc.property(predicateAst(), optionsArbitrary, (node, options) => {
        expect(testInternals.countPredicateOperators(node, options)).toBe(expectedPredicateCount(node, options));
      })
    );
  });
});

describe('df12/export collection properties', () => {
  it('collects local names from generated export declarations', () => {
    const exportName = fc.string({minLength: 1, maxLength: 8});
    const exportStatement = exportName.chain((name) =>
      fc.oneof(
        fc.constant({
          specifiers: [{local: identifier(name)}],
          type: 'ExportNamedDeclaration'
        }),
        fc.constant({
          declaration: identifier(name),
          type: 'ExportDefaultDeclaration'
        })
      )
    );

    fc.assert(
      fc.property(fc.array(exportStatement, {minLength: 0, maxLength: 20}), (body) => {
        const expected = new Set(
          body.flatMap((statement) =>
            statement.type === 'ExportNamedDeclaration'
              ? statement.specifiers.map((specifier) => specifier.local.name)
              : [statement.declaration.name]
          )
        );
        expect(testInternals.collectExportedNames({body})).toEqual(expected);
      })
    );
  });
});

describe('df12/tree traversal helpers', () => {
  it('finds matching descendants while skipping nested function bodies', () => {
    const root = {
      type: 'BlockStatement',
      body: [logicalExpression('&&'), {type: 'ArrowFunctionExpression', body: logicalExpression('||')}],
      parent: logicalExpression('??')
    };

    expect(testInternals.containsNode(root, root, (node) => node.operator === '&&')).toBe(true);
    expect(testInternals.containsNode(root, root, (node) => node.operator === '||')).toBe(false);
    expect(testInternals.containsNode(root, root, (node) => node.operator === '??')).toBe(false);
  });
});
