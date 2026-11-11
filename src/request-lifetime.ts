/** @file Own cancellation and deadlines shared by the browser's two batch transports. */

/**
 * Register one bounded request until its operation and owned children settle.
 * @param controllers The caller's active controllers, aborted when its owner closes.
 * @param operation The request and all child work that must share its deadline.
 * @param timeoutMilliseconds The total request lifetime, normally fifty seconds.
 * @returns Completion of the operation after releasing its timer and registration.
 * @example
 * await withRequestLifetime(controllers, async (signal) => {
 *   await fetch('/api/v1/sessions/recency', {signal});
 * });
 */
export async function withRequestLifetime(
  controllers: Set<AbortController>,
  operation: (signal: AbortSignal) => Promise<void>,
  timeoutMilliseconds = 50_000
): Promise<void> {
  const controller = new AbortController();
  controllers.add(controller);
  const timeout = setTimeout(() => controller.abort(), timeoutMilliseconds);
  try {
    await operation(controller.signal);
  } finally {
    clearTimeout(timeout);
    controllers.delete(controller);
  }
}
