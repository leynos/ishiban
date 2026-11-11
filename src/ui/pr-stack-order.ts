/** @file Select an inspector heading from bounded, read-only PR stack facts. */
import type {Session} from '../contracts';

export interface PrStackFacts {
  readonly baseRefName: string | null;
  readonly headRefName: string | null;
  readonly isCrossRepository: boolean | null;
  readonly mergedAt: string | null;
}

type Pr = Session['pullRequests'][number];
const ISO_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/u;

/** Read repository identity only from canonical GitHub PR URLs. */
function repositoryOf(url: string): string | null {
  const match = /^https:\/\/github\.com\/([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)\/pull\/[1-9]\d*\/?$/u.exec(url);
  return match?.[1]?.toLowerCase() ?? null;
}

/** Require an explicit non-fork fact before using a branch identity. */
function hasLocalStackFacts(facts: PrStackFacts | undefined): facts is PrStackFacts {
  return facts?.isCrossRepository === false;
}

/** Accept branch edges only for same-repository, non-forked PRs. */
function isPrerequisite(lower: Pr, upper: Pr, facts: Readonly<Record<string, PrStackFacts>>): boolean {
  const lowerFacts = facts[lower.url];
  const upperFacts = facts[upper.url];
  const repository = repositoryOf(lower.url);
  if (repository === null || repository !== repositoryOf(upper.url)) return false;
  if (!hasLocalStackFacts(lowerFacts) || !hasLocalStackFacts(upperFacts)) return false;
  return Boolean(lowerFacts.headRefName) && lowerFacts.headRefName === upperFacts.baseRefName;
}

/** Exclude a PR only when another associated PR demonstrably depends on it. */
function isTip(pr: Pr, prs: readonly Pr[], facts: Readonly<Record<string, PrStackFacts>>): boolean {
  return !prs.some((other) => other.url !== pr.url && isPrerequisite(pr, other, facts));
}

/** Prefer active work to its merged prerequisites after GitHub retargets bases. */
function lifecycleRank(pr: Pr): number {
  if (pr.status === 'open' || pr.status === 'draft') return 2;
  if (pr.status === 'merged') return 1;
  return 0;
}

/** Compare strings without locale-dependent ordering. */
function compareStrings(a: string, b: string): number {
  if (a === b) return 0;
  return a < b ? -1 : 1;
}

/** Reject malformed provider timestamps before using merge chronology. */
function mergeTime(value: string | null | undefined): number {
  if (!value || !ISO_UTC.test(value)) return Number.NEGATIVE_INFINITY;
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return Number.NEGATIVE_INFINITY;
  if (new Date(parsed).toISOString().slice(0, 19) !== value.slice(0, 19)) return Number.NEGATIVE_INFINITY;
  return parsed;
}

/** Use merge time then URL for a deterministic fallback. */
function compareFallback(a: Pr, b: Pr, facts: Readonly<Record<string, PrStackFacts>>): number {
  const aMergedAt = mergeTime(facts[a.url]?.mergedAt);
  const bMergedAt = mergeTime(facts[b.url]?.mergedAt);
  if (aMergedAt !== bMergedAt) return aMergedAt > bMergedAt ? -1 : 1;
  return compareStrings(a.url, b.url);
}

/** Rank candidate tips by lifecycle and stable fallback evidence. */
function compareHeadingCandidates(a: Pr, b: Pr, facts: Readonly<Record<string, PrStackFacts>>): number {
  const byLifecycle = lifecycleRank(b) - lifecycleRank(a);
  if (byLifecycle !== 0) return byLifecycle;
  return compareFallback(a, b, facts);
}

/**
 * Choose among proven stack tips, then use lifecycle facts.
 * GitHub can retarget a dependent branch after its prerequisite merges, so
 * lifecycle and merge time are fallbacks, not claims of a proven stack edge.
 * Cyclic or incomplete branch facts leave deterministic lifecycle/URL fallback.
 * @param prs The session's PR associations, in any catalogue order.
 * @param facts Inspector-only GitHub branch and merge facts keyed by PR URL.
 * @returns The best supported heading PR, or undefined when none are associated.
 * @example
 * selectStackTop([{url: 'https://github.com/a/b/pull/1', status: 'open', title: 'Top'}], {})?.title;
 * // 'Top'
 */
export function selectStackTop(prs: readonly Pr[], facts: Readonly<Record<string, PrStackFacts>>): Pr | undefined {
  const tips = prs.filter((pr) => isTip(pr, prs, facts));
  const candidates = tips.length > 0 ? tips : prs;
  return candidates.toSorted((a, b) => compareHeadingCandidates(a, b, facts))[0];
}
