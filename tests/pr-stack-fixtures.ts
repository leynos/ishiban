/** @file Shared inspector regression facts from the axinite session family. */
import type {PrStackFacts} from '../src/ui/pr-stack-order';

export const AXINITE_PREREQUISITE = {
  url: 'https://github.com/leynos/axinite/pull/740',
  title: 'chore(deps): clear the SQLite advisory and yanked lock entries',
  status: 'merged'
};

export const AXINITE_DEPENDENT = {
  url: 'https://github.com/leynos/axinite/pull/364',
  title: 'Eliminate in-process environment mutation from tests (#333)',
  status: 'open'
};

export const AXINITE_PREREQUISITE_FACTS: PrStackFacts = {
  baseRefName: 'main',
  headRefName: 'clear-sqlite-advisory',
  isCrossRepository: false,
  mergedAt: '2026-11-10T12:00:00Z'
};

export const AXINITE_DEPENDENT_FACTS: PrStackFacts = {
  baseRefName: 'clear-sqlite-advisory',
  headRefName: 'eliminate-environment-mutation',
  isCrossRepository: false,
  mergedAt: null
};
