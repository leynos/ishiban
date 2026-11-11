/** @file Read one oversized activity result under the batch response budget. */
import {Schema} from 'effect';
import {MAX_ACTIVITY_RESPONSE_BYTES} from './activity-batch';
import {SessionActivityResponseSchema, type SessionActivityResponse} from './contracts';

/**
 * Read and parse a bounded single-session response; for example, recover a 1.1 MiB cached preview.
 * @param response Successful response returned by the existing activity endpoint.
 * @param signal The owning batch request's cancellation signal.
 * @returns A schema-validated workspace and session response.
 * @throws {Error} When HTTP, body size, cancellation, UTF-8, JSON, or schema validation fails.
 * @example
 * const result = await readSessionActivityResponse(response, signal);
 * if (result.session) store.activity(result.workspaceId, result.session);
 */
export async function readSessionActivityResponse(
  response: Response,
  signal: AbortSignal
): Promise<SessionActivityResponse> {
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error('Activity fallback unavailable');
  }
  if (!response.body) throw new Error('Activity fallback has no response stream');
  const bytes = await readResponseBytes(response.body, signal);
  const body = new TextDecoder('utf-8', {fatal: true}).decode(bytes);
  return Schema.decodeUnknownSync(SessionActivityResponseSchema)(JSON.parse(body));
}

/** Own stream cleanup for one response; cancellation also releases a stalled read. */
async function readResponseBytes(body: ReadableStream<Uint8Array>, signal: AbortSignal): Promise<Uint8Array> {
  if (signal.aborted) {
    await body.cancel().catch(() => {});
    throw new Error('Activity fallback cancelled');
  }
  const reader = body.getReader();
  const cancelOnAbort = () => {
    void reader.cancel().catch(() => {});
  };
  signal.addEventListener('abort', cancelOnAbort, {once: true});
  try {
    return await readBoundedBytes(reader, signal);
  } finally {
    signal.removeEventListener('abort', cancelOnAbort);
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

/** Count incoming bytes before retaining each chunk; for example, reject the first byte over 8 MiB. */
async function readBoundedBytes(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  signal: AbortSignal
): Promise<Uint8Array> {
  const chunks: Uint8Array[] = [];
  let byteLength = 0;
  let chunk = await reader.read();
  while (!chunk.done) {
    signal.throwIfAborted();
    byteLength += chunk.value.byteLength;
    if (byteLength > MAX_ACTIVITY_RESPONSE_BYTES) throw new Error('Activity fallback exceeds its byte limit');
    chunks.push(chunk.value);
    chunk = await reader.read();
  }
  signal.throwIfAborted();
  return combineChunks(chunks, byteLength);
}

/** Join byte chunks after the stream has passed its total-size bound. */
function combineChunks(chunks: readonly Uint8Array[], byteLength: number): Uint8Array {
  const bytes = new Uint8Array(byteLength);
  let offset = 0;
  for (const part of chunks) {
    bytes.set(part, offset);
    offset += part.byteLength;
  }
  return bytes;
}
