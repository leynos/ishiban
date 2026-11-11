/** @file Match Falcon request identity bounds without changing raw catalogue IDs. */
import {expect, it} from 'bun:test';
import {isRequestableSessionId} from '../src/lookup-session-id';

it('counts Unicode code points and rejects NUL or unsupported lengths', () => {
  expect(isRequestableSessionId('😀'.repeat(256))).toBe(true);
  expect(isRequestableSessionId('😀'.repeat(257))).toBe(false);
  expect(isRequestableSessionId('x'.repeat(256))).toBe(true);
  expect(isRequestableSessionId('x'.repeat(257))).toBe(false);
  expect(isRequestableSessionId('ok\0id')).toBe(false);
  expect(isRequestableSessionId('')).toBe(false);
  expect(isRequestableSessionId('..')).toBe(true);
});
