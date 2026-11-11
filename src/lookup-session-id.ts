/** @file Check raw session IDs before either bounded browser lookup is queued. */

/**
 * Match Falcon's JSON/query session-ID contract without normalizing source IDs.
 * @param sessionId Raw identity from the catalogue or a visible mark.
 * @returns Whether the ID fits the nonempty, 256-code-point, NUL-free request limit.
 * @example
 * isRequestableSessionId('😀'.repeat(256)); // true
 */
export function isRequestableSessionId(sessionId: string): boolean {
  if (sessionId.length === 0) return false;
  if (sessionId.length > 512) return false;
  if (sessionId.includes('\0')) return false;
  return [...sessionId].length <= 256;
}
