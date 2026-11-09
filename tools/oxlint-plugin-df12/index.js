/** @file Ishiban's imported df12 Oxlint plugin entrypoint. */
import complexity from './complex-conditional.js';
import documentation from './jsdoc.js';
import helpers from './jsdoc-helpers.js';

export const testInternals = {
  collectExportedNames: helpers.collectExportedNames,
  containsNode: helpers.containsNode,
  countPredicateOperators: complexity.countPredicateOperators,
  loadBaseline: helpers.loadBaseline,
  resetBaselineCache: helpers.resetBaselineCache
};

export default {
  meta: {name: 'df12'},
  rules: {
    'complex-conditional': complexity.complexConditionalRule,
    'require-module-jsdoc': documentation.requireModuleJsDocRule,
    'require-private-jsdoc': documentation.requirePrivateJsDocRule,
    'require-public-jsdoc': documentation.requirePublicJsDocRule
  }
};
