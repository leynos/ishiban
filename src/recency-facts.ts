/** @file Keep a history timestamp separate from its current lookup status. */

/** A successful history read or a provisional status with optional last-known evidence. */
export type RecencyFact =
  | {readonly outcome: 'available'; readonly latestHistoryAt: string | null}
  | {readonly outcome: 'pending' | 'unavailable'; readonly lastKnownHistoryAt?: string | null};

/** One bounded owner's fact, execution basis, and next refresh time. */
export interface CacheEntry {
  readonly basis: number;
  readonly fact: RecencyFact;
  readonly expiresAt: number;
}

/** Published recency evidence and the currently budget-limited family roots. */
export interface RecencyState {
  readonly facts: ReadonlyMap<string, RecencyFact>;
  readonly limitedRoots: ReadonlySet<string>;
}

/**
 * Read the timestamp retained by a current or previously successful lookup.
 * @param fact Current per-member lookup fact, if one exists.
 * @returns Known history timestamp, null for known empty history, or undefined.
 * @example
 * historyTimestamp({outcome: 'pending', lastKnownHistoryAt: '2026-11-10T12:00:00Z'});
 * // '2026-11-10T12:00:00Z'
 */
export function historyTimestamp(fact: RecencyFact | undefined): string | null | undefined {
  if (fact?.outcome === 'available') return fact.latestHistoryAt;
  return fact?.lastKnownHistoryAt;
}

/**
 * Carry last-known history into an unconfirmed status without claiming success.
 * @param prior Fact from the same execution watermark, if present.
 * @param outcome Pending refresh or failed lookup.
 * @returns A provisional fact retaining available history evidence.
 * @example
 * unconfirmedFact({outcome: 'available', latestHistoryAt: null}, 'pending');
 * // {outcome: 'pending', lastKnownHistoryAt: null}
 */
export function unconfirmedFact(prior: RecencyFact | undefined, outcome: 'pending' | 'unavailable'): RecencyFact {
  const lastKnownHistoryAt = historyTimestamp(prior);
  return lastKnownHistoryAt === undefined ? {outcome} : {outcome, lastKnownHistoryAt};
}

/**
 * Settle a member without treating retained history as a successful refresh.
 * @param fact New endpoint result.
 * @param prior Previous cache entry, if any.
 * @param basis Current execution watermark.
 * @returns Current status with only same-execution history retained.
 * @example
 * settleFact({outcome: 'unavailable'}, {basis: 1, fact: {outcome: 'available', latestHistoryAt: null}, expiresAt: 0}, 1);
 * // {outcome: 'unavailable', lastKnownHistoryAt: null}
 */
export function settleFact(fact: RecencyFact, prior: CacheEntry | undefined, basis: number): RecencyFact {
  if (fact.outcome === 'available') return fact;
  return unconfirmedFact(prior?.basis === basis ? prior.fact : undefined, 'unavailable');
}
