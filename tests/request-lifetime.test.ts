/** @file Verify deadline ownership lasts through request children and releases on failure. */
import {expect, it} from 'bun:test';
import {withRequestLifetime} from '../src/request-lifetime';
import {deferred} from './deferred';

it('keeps a completed response cancellable until its child work settles', async () => {
  const controllers = new Set<AbortController>();
  const child = deferred<void>();
  const aborted = deferred<void>();
  const request = withRequestLifetime(controllers, async (signal) => {
    signal.addEventListener('abort', () => aborted.resolve(), {once: true});
    await child.promise;
  });
  expect(controllers.size).toBe(1);
  for (const controller of controllers) controller.abort();
  await aborted.promise;
  expect(controllers.size).toBe(1);
  child.resolve();
  await request;
  expect(controllers.size).toBe(0);
});

it('aborts a pending operation at its deadline and releases the owner', async () => {
  const controllers = new Set<AbortController>();
  let wasAborted = false;
  await withRequestLifetime(
    controllers,
    async (signal) => {
      const deadline = deferred<void>();
      signal.addEventListener(
        'abort',
        () => {
          wasAborted = signal.aborted;
          deadline.resolve();
        },
        {once: true}
      );
      await deadline.promise;
    },
    1
  );
  expect(wasAborted).toBe(true);
  expect(controllers.size).toBe(0);
});

it('releases a rejected request without clearing another active request', async () => {
  const controllers = new Set<AbortController>();
  const sibling = new AbortController();
  controllers.add(sibling);
  await expect(
    withRequestLifetime(controllers, async () => {
      throw new Error('Read failed');
    })
  ).rejects.toThrow('Read failed');
  expect([...controllers]).toEqual([sibling]);
  expect(sibling.signal.aborted).toBe(false);
});
