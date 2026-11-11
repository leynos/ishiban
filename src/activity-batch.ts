/** @file Decode bounded, independently validated streaming activity results. */
import {Schema} from 'effect';
import {SessionActivityFrameSchema, type SessionActivityFrame} from './contracts';
import {readBoundedFrames} from './bounded-frames';

const MAX_FRAME_CHARS = 1_048_576;
export const MAX_ACTIVITY_RESPONSE_BYTES = 8_388_608;
const MAX_RESULTS = 8;

/**
 * Apply each completed activity result without waiting for the slowest member.
 * @param response An NDJSON batch response owned by the caller's AbortController.
 * @param consume Validated member callback; identity and revision checks remain caller-owned.
 * @returns Completion after all frames have arrived and the reader is released.
 * @throws {Error} Rejects on transport failure or response limits; invalid members are skipped.
 * @example
 * await readActivityFrames(response, (frame) => applyCurrentLookup(frame));
 */
export async function readActivityFrames(
  response: Response,
  consume: (frame: SessionActivityFrame) => void
): Promise<void> {
  return readBoundedFrames(
    response,
    {maxFrameChars: MAX_FRAME_CHARS, maxResponseBytes: MAX_ACTIVITY_RESPONSE_BYTES, maxResults: MAX_RESULTS},
    (line) => Schema.decodeUnknownSync(SessionActivityFrameSchema)(JSON.parse(line)),
    consume
  );
}
