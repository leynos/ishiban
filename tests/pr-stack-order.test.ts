/** @file Verify inspector heading selection against actual session PR identities. */
import {expect, it} from 'bun:test';
import {selectStackTop} from '../src/ui/pr-stack-order';
import {
  AXINITE_DEPENDENT as dependent,
  AXINITE_DEPENDENT_FACTS as dependentFacts,
  AXINITE_PREREQUISITE as prerequisite,
  AXINITE_PREREQUISITE_FACTS as prerequisiteFacts
} from './pr-stack-fixtures';
const stack = {
  [prerequisite.url]: prerequisiteFacts,
  [dependent.url]: dependentFacts
};

it.each([
  [prerequisite, dependent],
  [dependent, prerequisite]
])('selects the dependent PR regardless of catalogue order', (first, second) => {
  expect(selectStackTop([first, second], stack)).toEqual(dependent);
});

it('does not infer a stack edge between forked PRs with matching branch names', () => {
  const forked = {...dependent, status: 'closed'};
  const facts = {...stack, [dependent.url]: {...dependentFacts, isCrossRepository: true}};
  expect(selectStackTop([prerequisite, forked], facts)).toEqual(prerequisite);
});

it.each([false, true])('uses a same-repository branch edge with trailing slash %s', (hasTrailingSlash) => {
  const suffix = hasTrailingSlash ? '/' : '';
  const lower = {...prerequisite, url: `https://github.com/leynos/axinite/pull/100${suffix}`, status: 'open'};
  const upper = {...dependent, url: 'https://github.com/leynos/axinite/pull/200'};
  const facts = {
    [lower.url]: {...prerequisiteFacts, headRefName: 'base-of-upper'},
    [upper.url]: {...dependentFacts, baseRefName: 'base-of-upper'}
  };
  expect(selectStackTop([lower, upper], facts)).toEqual(upper);
});

it.each([false, true])('recognizes a mixed-case GitHub repository in catalogue order %s', (isReversed) => {
  const lower = {...prerequisite, url: 'https://github.com/Leynos/Axinite/pull/100', status: 'open'};
  const upper = {...dependent, url: 'https://github.com/leynos/axinite/pull/200', status: 'open'};
  const facts = {
    [lower.url]: {...prerequisiteFacts, headRefName: 'shared-branch'},
    [upper.url]: {...dependentFacts, baseRefName: 'shared-branch'}
  };
  const order = isReversed ? [upper, lower] : [lower, upper];
  expect(selectStackTop(order, facts)).toEqual(upper);
});

it('chooses an unrelated active tip over a closed tip of a deeper historical chain', () => {
  const middle = {...dependent, url: 'https://github.com/leynos/axinite/pull/741', status: 'merged'};
  const closedTip = {...dependent, url: 'https://github.com/leynos/axinite/pull/742', status: 'closed'};
  const active = {...dependent, url: 'https://github.com/leynos/axinite/pull/900'};
  const facts = {
    [prerequisite.url]: prerequisiteFacts,
    [middle.url]: {...dependentFacts, headRefName: 'middle-branch'},
    [closedTip.url]: {...dependentFacts, baseRefName: 'middle-branch'},
    [active.url]: {...dependentFacts, baseRefName: 'main'}
  };
  expect(selectStackTop([prerequisite, middle, closedTip, active], facts)).toEqual(active);
});

it('uses lifecycle and merge time when GitHub has retargeted the dependent branch', () => {
  const retargeted = {...stack, [dependent.url]: {...dependentFacts, baseRefName: 'main'}};
  expect(selectStackTop([prerequisite, dependent], retargeted)).toEqual(dependent);
});

it('falls back to a stable URL when GitHub stack facts are unavailable', () => {
  const first = {...prerequisite, status: 'open'};
  const second = {...dependent, status: 'open'};
  expect(selectStackTop([first, second], {})).toEqual(dependent);
  expect(selectStackTop([second, first], {})).toEqual(dependent);
});

it('ignores invalid merge times and compares equal instants without textual precision bias', () => {
  const lower = {...prerequisite, status: 'merged'};
  const upper = {...dependent, status: 'merged'};
  const invalid = {
    [lower.url]: {...prerequisiteFacts, mergedAt: '2026-11-10T12:00:00Z'},
    [upper.url]: {...dependentFacts, mergedAt: 'not-a-time', baseRefName: 'main'}
  };
  expect(selectStackTop([upper, lower], invalid)).toEqual(lower);
  const equal = {
    [lower.url]: {...prerequisiteFacts, mergedAt: '2026-11-10T12:00:00.000Z'},
    [upper.url]: {...dependentFacts, mergedAt: '2026-11-10T12:00:00Z', baseRefName: 'main'}
  };
  expect(selectStackTop([lower, upper], equal)).toEqual(upper);
});
