/** @file Decode bounded, independently validated streaming activity results. */
import {Schema} from 'effect';
import {SessionActivityFrameSchema, type SessionActivityFrame} from './contracts';

const MAX_FRAME_CHARS = 1_048_576;
export const MAX_ACTIVITY_RESPONSE_BYTES = 8_388_608;
const MAX_RESULTS = 8;

/** Reject a malformed member without discarding other completed lookups. */
function decodeFrame(line: string): SessionActivityFrame | null {
  try {
    return Schema.decodeUnknownSync(SessionActivityFrameSchema)(JSON.parse(line));
  } catch {
    return null;
  }
}

/** Own framing state; for example, a UTF-8 character may span network chunks. */
class ActivityFrames {
  private readonly decoder = new TextDecoder();
  private buffer = '';
  private bytes = 0;
  private results = 0;

  constructor(private readonly consume: (frame: SessionActivityFrame) => void) {}

  /** Accumulate complete lines while bounding the response and unfinished frame. */
  feed(chunk: Uint8Array): void {
    this.bytes += chunk.byteLength;
    if (this.bytes > MAX_ACTIVITY_RESPONSE_BYTES) throw new Error('Activity batch exceeds its byte limit');
    this.buffer += this.decoder.decode(chunk, {stream: true});
    const lines = this.buffer.split('\n');
    this.buffer = lines.pop() ?? '';
    if (this.buffer.length > MAX_FRAME_CHARS) throw new Error('Activity frame exceeds its size limit');
    for (const line of lines) this.emit(line);
  }

  /** Accept a complete final frame even if a transport omits the final newline. */
  finish(): void {
    this.emit(this.buffer + this.decoder.decode());
    this.buffer = '';
  }

  /** Count every supplied member so invalid input cannot bypass the batch bound. */
  private emit(line: string): void {
    if (!line.trim()) return;
    this.results += 1;
    if (line.length > MAX_FRAME_CHARS) throw new Error('Activity frame exceeds its size limit');
    if (this.results > MAX_RESULTS) throw new Error('Activity batch has too many results');
    const frame = decodeFrame(line);
    if (frame) this.consume(frame);
  }
}

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
  if (!response.body) throw new Error('Activity batch has no response stream');
  const reader = response.body.getReader();
  const frames = new ActivityFrames(consume);
  try {
    let chunk = await reader.read();
    while (!chunk.done) {
      frames.feed(chunk.value);
      chunk = await reader.read();
    }
    frames.finish();
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
