/** @file Durable evidence remains visible through metadata-only refreshes. */
import {expect, it} from 'bun:test';
import {createDemoSnapshot} from '../src/demo';
import {evidenceLabel} from '../src/ui/board-model';

it('distinguishes carried durable evidence from a never-observed metadata session', () => {
  const sample = createDemoSnapshot().sessions[0];
  if (!sample) throw new Error('Demo corpus needs a session');
  const carried = {...sample, source: 'metadata', freshness: 'unavailable', lastEvidenceGeneration: 3} as const;
  expect(evidenceLabel(carried, 4)).toContain('Carried forward from generation 3');
  expect(evidenceLabel({...carried, lastEvidenceGeneration: null}, 4)).toBe('Metadata only');
});
