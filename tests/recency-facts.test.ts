/** @file Preserve known history only within the same execution watermark. */
import {expect, it} from 'bun:test';
import {settleFact, unconfirmedFact, type CacheEntry} from '../src/recency-facts';

it('keeps empty and dated history provisional without carrying it across executions', () => {
  const prior: CacheEntry = {
    basis: 7,
    fact: {outcome: 'available', latestHistoryAt: '2026-11-10T18:41:02.707Z'},
    expiresAt: 0
  };
  expect(unconfirmedFact(prior.fact, 'pending')).toEqual({
    outcome: 'pending',
    lastKnownHistoryAt: '2026-11-10T18:41:02.707Z'
  });
  expect(settleFact({outcome: 'unavailable'}, prior, 7)).toEqual({
    outcome: 'unavailable',
    lastKnownHistoryAt: '2026-11-10T18:41:02.707Z'
  });
  expect(settleFact({outcome: 'unavailable'}, prior, 8)).toEqual({outcome: 'unavailable'});
  expect(unconfirmedFact({outcome: 'available', latestHistoryAt: null}, 'pending')).toEqual({
    outcome: 'pending',
    lastKnownHistoryAt: null
  });
});
