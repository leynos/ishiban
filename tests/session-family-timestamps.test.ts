/** @file Compare settled family activity with independently generated instants. */
import {expect, it} from 'bun:test';
import fc from 'fast-check';
import type {Session} from '../src/contracts';
import {groupSessions, type RecencyFact} from '../src/session-families';
import {createBoardSnapshot, firstSession} from './board-fixtures';

const template = firstSession(createBoardSnapshot());
const offsets = [-720, -330, -60, 0, 60, 330, 840] as const;
const widths = [0, 1, 3, 6] as const;
const invalidTimestamps = [
  '2026-02-30T12:00:00Z',
  '2026-13-01T12:00:00Z',
  '2026-11-10T12:00:00+24:00',
  '2026-11-10T12:00:00-05:60',
  'not-an-iso-timestamp'
] as const;

interface TimestampCase {
  readonly text: string;
  readonly instantMicroseconds: number;
}

/** Format an instant: encodeTimestamp(t, 330, 6) uses a +05:30 local clock. */
function encodeTimestamp(instantMicroseconds: number, offsetMinutes: number, width: number): TimestampCase {
  const quantum = 10 ** (6 - width);
  const exact = Math.floor(instantMicroseconds / quantum) * quantum;
  const second = Math.floor(exact / 1_000_000);
  const fraction = exact - second * 1_000_000;
  const local = new Date((second + offsetMinutes * 60) * 1000).toISOString().slice(0, 19);
  const suffix = offsetMinutes === 0 ? 'Z' : offsetSuffix(offsetMinutes);
  const digits = width === 0 ? '' : `.${String(fraction).padStart(6, '0').slice(0, width)}`;
  return {text: `${local}${digits}${suffix}`, instantMicroseconds: exact};
}

/** Format an offset: offsetSuffix(-330) gives '-05:30'. */
function offsetSuffix(minutes: number): string {
  const sign = minutes < 0 ? '-' : '+';
  const absolute = Math.abs(minutes);
  return `${sign}${String(Math.floor(absolute / 60)).padStart(2, '0')}:${String(absolute % 60).padStart(2, '0')}`;
}

/** Select a family: selectedActivityId(left, right) reads real public grouping. */
function selectedActivityId(left: string, right: string): string | undefined {
  const root: Session = {
    ...template,
    sessionId: 'a-root',
    parentSessionId: null,
    source: 'metadata',
    state: 'running',
    createdAt: null
  };
  const child: Session = {
    ...root,
    sessionId: 'b-child',
    parentSessionId: root.sessionId,
    state: 'idle'
  };
  const recency: ReadonlyMap<string, RecencyFact> = new Map([
    [root.sessionId, {outcome: 'available', latestHistoryAt: left}],
    [child.sessionId, {outcome: 'available', latestHistoryAt: right}]
  ]);
  return groupSessions([child, root], recency)[0]?.activity.sessionId;
}

it('orders equal instants across offsets and fractional spellings by lexical identity', () => {
  expect(selectedActivityId('2026-11-10T12:00:00.5Z', '2026-11-10T17:30:00.500000+05:30')).toBe('a-root');
});

it('selects the later sub-millisecond instant despite the other tab running', () => {
  expect(selectedActivityId('2026-11-10T12:00:00.123456Z', '2026-11-10T07:00:00.123457-05:00')).toBe('b-child');
});

it('uses lexical identity when neither history timestamp is valid', () => {
  expect(selectedActivityId('2026-02-30T12:00:00Z', '2026-11-10T12:00:00+24:00')).toBe('a-root');
});

it('matches a generated microsecond oracle across offset and precision encodings', () => {
  const scenario = fc.record({
    second: fc.integer({min: 1_780_000_000, max: 1_790_000_000}),
    fraction: fc.integer({min: 0, max: 999_999}),
    difference: fc.integer({min: -5, max: 5}),
    leftOffset: fc.constantFrom(...offsets),
    rightOffset: fc.constantFrom(...offsets),
    leftWidth: fc.constantFrom(...widths),
    rightWidth: fc.constantFrom(...widths)
  });
  fc.assert(
    fc.property(scenario, ({second, fraction, difference, leftOffset, rightOffset, leftWidth, rightWidth}) => {
      const base = second * 1_000_000 + fraction;
      const left = encodeTimestamp(base, leftOffset, leftWidth);
      const right = encodeTimestamp(base + difference, rightOffset, rightWidth);
      const expected = left.instantMicroseconds >= right.instantMicroseconds ? 'a-root' : 'b-child';
      expect(selectedActivityId(left.text, right.text)).toBe(expected);
    }),
    {numRuns: 150}
  );
});

it('rejects generated invalid calendar and offset strings before recency selection', () => {
  const scenario = fc.record({
    invalid: fc.constantFrom(...invalidTimestamps),
    invalidOnRoot: fc.boolean(),
    // A 2025 control is older than every rejected 2026 value if one is accidentally accepted.
    second: fc.integer({min: Date.UTC(2025, 0, 1) / 1000, max: Date.UTC(2025, 0, 31) / 1000}),
    offset: fc.constantFrom(...offsets)
  });
  fc.assert(
    fc.property(scenario, ({invalid, invalidOnRoot, second, offset}) => {
      const valid = encodeTimestamp(second * 1_000_000, offset, 6).text;
      const selected = invalidOnRoot ? selectedActivityId(invalid, valid) : selectedActivityId(valid, invalid);
      expect(selected).toBe(invalidOnRoot ? 'b-child' : 'a-root');
    }),
    {numRuns: 100}
  );
});
