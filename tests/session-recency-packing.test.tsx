/** @file Check the browser hook's actual recency request packing over eligible IDs. */
import {expect, it} from 'bun:test';
import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import fc from 'fast-check';
import {Schema} from 'effect';
import type {Session, Snapshot} from '../src/contracts';
import {useSessionRecency} from '../src/session-recency';
import {createFamilySnapshot} from './board-fixtures';
import {availableRecencyResponse, installFamilyBrowser, installFamilyMarks} from './family-browser-fixture';

interface IdScenario {
  readonly count: number;
  readonly glyph: string;
  readonly width: number;
  readonly limit?: 'count' | 'bytes';
}

/** Build linked eligible IDs; for example, width 255 with 😀 yields 256-code-point IDs. */
function familyWithIds(scenario: IdScenario): Snapshot {
  const baseline = createFamilySnapshot(1);
  const [root, child] = baseline.sessions;
  if (!root || !child) throw new Error('The packing fixture requires root and child templates.');
  const ids = Array.from(
    {length: scenario.count},
    (_, index) => `${scenario.glyph.repeat(scenario.width)}${String.fromCodePoint(57_344 + index)}`
  );
  const rootId = ids[0];
  if (!rootId) throw new Error('The packing fixture requires a root ID.');
  const sessions: Session[] = [
    {...root, sessionId: rootId},
    ...ids.slice(1).map((sessionId) => ({...child, sessionId, parentSessionId: rootId}))
  ];
  return {...baseline, sessions};
}

const RequestBodySchema = Schema.Struct({sessionIds: Schema.Array(Schema.String)});

/** Decode the intercepted JSON POST; for example, {"sessionIds":["root"]} returns ["root"]. */
function requestIds(body: string): readonly string[] {
  const raw = JSON.parse(body);
  const request = Schema.decodeUnknownSync(RequestBodySchema)(raw);
  if (Object.keys(raw).length !== 1) throw new Error('The recency request must contain only sessionIds.');
  return request.sessionIds;
}

/** Verify one real hook run; for example, nine short IDs require a second POST. */
async function verifyPacking(scenario: IdScenario): Promise<void> {
  const snapshot = familyWithIds(scenario);
  const expected = snapshot.sessions.map((session) => session.sessionId);
  const mark = installFamilyMarks(1)[0];
  if (!mark) throw new Error('The packing fixture requires one family mark.');
  mark.setAttribute('data-family-id', expected[0] ?? '');
  const bodies: string[] = [];
  const browser = installFamilyBrowser(async (_input, init) => {
    const body = String(init?.body);
    bodies.push(body);
    return availableRecencyResponse(snapshot, requestIds(body));
  });
  try {
    const {result} = renderHook(() => useSessionRecency(snapshot));
    act(() => browser.visibility(mark, true));
    await waitFor(() => expect(result.current.facts.size).toBe(expected.length), {timeout: 2000});
    const requested = bodies.flatMap((body) => requestIds(body));
    expect(requested).toHaveLength(expected.length);
    expect(new Set(requested)).toEqual(new Set(expected));
    for (const body of bodies) {
      const ids = requestIds(body);
      expect(ids.length).toBeGreaterThanOrEqual(1);
      expect(ids.length).toBeLessThanOrEqual(8);
      expect(new TextEncoder().encode(body).byteLength).toBeLessThanOrEqual(8192);
    }
    if (scenario.limit === 'count') expect(bodies.some((body) => requestIds(body).length === 8)).toBe(true);
    if (scenario.limit === 'bytes') expect(bodies.length).toBeGreaterThan(1);
  } finally {
    cleanup();
    browser.restore();
    document.body.replaceChildren();
  }
}

const glyph = fc.constantFrom('a', 'é', '😀', '𝄞', '"', '\\', '\n');
const scenario = fc.oneof(
  fc.record({count: fc.integer({min: 9, max: 24}), glyph, width: fc.integer({min: 0, max: 8})}),
  fc.record({count: fc.constant(8), glyph: fc.constantFrom('😀', '𝄞'), width: fc.constant(255)}),
  fc.record({count: fc.integer({min: 2, max: 24}), glyph, width: fc.integer({min: 0, max: 255})})
);

it('packs every eligible family member exactly once within count and UTF-8 limits', async () => {
  const boundaries: IdScenario[] = [
    {count: 9, glyph: 'a', width: 1, limit: 'count'},
    {count: 8, glyph: '😀', width: 255, limit: 'bytes'},
    {count: 10, glyph: '"\\\n', width: 40}
  ];
  for (const boundary of boundaries) {
    await verifyPacking(boundary);
  }
  await fc.assert(fc.asyncProperty(scenario, verifyPacking), {numRuns: 50});
}, 60_000);
