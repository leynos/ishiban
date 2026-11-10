/** @file Frame bounded NDJSON streams while callers own schema and identity checks. */

export interface FrameLimits {
  readonly maxFrameChars: number;
  readonly maxResponseBytes: number;
  readonly maxResults: number;
}

/** Preserve byte, character and result bounds across network chunks. */
class BoundedFrames<Frame> {
  private readonly decoder = new TextDecoder();
  private buffer = '';
  private bytes = 0;
  private results = 0;

  constructor(
    private readonly limits: FrameLimits,
    private readonly decode: (line: string) => Frame,
    private readonly consume: (frame: Frame) => void
  ) {}

  /** Add one chunk and deliver each complete member independently. */
  feed(chunk: Uint8Array): void {
    this.bytes += chunk.byteLength;
    if (this.bytes > this.limits.maxResponseBytes) throw new Error('Batch response exceeds its byte limit');
    this.buffer += this.decoder.decode(chunk, {stream: true});
    const lines = this.buffer.split('\n');
    this.buffer = lines.pop() ?? '';
    if (this.buffer.length > this.limits.maxFrameChars) throw new Error('Batch frame exceeds its size limit');
    for (const line of lines) this.emit(line);
  }

  /** Decode a final member even when the server omits a trailing newline. */
  finish(): void {
    this.emit(this.buffer + this.decoder.decode());
  }

  /** Count malformed members toward the result bound while preserving later siblings. */
  private emit(line: string): void {
    if (!line.trim()) return;
    this.results += 1;
    if (this.results > this.limits.maxResults) throw new Error('Batch has too many results');
    if (line.length > this.limits.maxFrameChars) throw new Error('Batch frame exceeds its size limit');
    let frame: Frame;
    try {
      frame = this.decode(line);
    } catch {
      // A malformed member cannot discard another completed member.
      return;
    }
    this.consume(frame);
  }
}

/**
 * Read one bounded NDJSON stream, releasing its reader on success or failure.
 * @param response The fetch response owned by the caller's abort controller.
 * @param limits Maximum frame characters, total bytes and member count.
 * @param decode Endpoint-specific schema decoder; throw for malformed members.
 * @param consume Callback for each valid member as it arrives.
 * @returns Completion after the stream and reader have been released.
 * @throws {Error} When framing or transport limits are exceeded.
 * @example
 * await readBoundedFrames(response, {maxFrameChars: 1024, maxResponseBytes: 2048, maxResults: 2}, decode, apply);
 */
export async function readBoundedFrames<Frame>(
  response: Response,
  limits: FrameLimits,
  decode: (line: string) => Frame,
  consume: (frame: Frame) => void
): Promise<void> {
  if (!response.body) throw new Error('Batch response has no stream');
  const reader = response.body.getReader();
  const frames = new BoundedFrames(limits, decode, consume);
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
