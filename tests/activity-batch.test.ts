/** @file Verify streaming member validation without waiting for a whole batch. */
import {expect, it} from 'bun:test';
import {readActivityFrames} from '../src/activity-batch';
import type {SessionActivityFrame} from '../src/contracts';
import {createBoardSnapshot, firstSession} from './board-fixtures';

/** Build a protocol frame with a multibyte title; for example, split its UTF-8 bytes. */
function frame(): SessionActivityFrame {
  const session = {...firstSession(createBoardSnapshot()), title: 'Session ☃', state: 'idle' as const};
  return {workspaceId: 'workspace', sessionId: session.sessionId, session};
}

/** Emit one byte chunk and record reader cancellation for size-bound tests. */
function cancellationObservedStream(chunk: Uint8Array, onCancel: () => void): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      controller.enqueue(chunk);
    },
    cancel: onCancel
  });
}

it('handles multibyte characters split across streaming chunks', async () => {
  const expected = frame();
  const bytes = new TextEncoder().encode(`${JSON.stringify(expected)}\n`);
  const split = bytes.findIndex((byte) => byte > 127) + 1;
  const received: SessionActivityFrame[] = [];
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(bytes.slice(0, split));
      controller.enqueue(bytes.slice(split));
      controller.close();
    }
  });
  await readActivityFrames(new Response(stream), (result) => received.push(result));
  expect(received).toEqual([expected]);
});

it('skips an invalid member and accepts an independently valid later result', async () => {
  const expected = frame();
  const received: SessionActivityFrame[] = [];
  await readActivityFrames(new Response(`not-json\n${JSON.stringify(expected)}\n`), (result) => received.push(result));
  expect(received).toEqual([expected]);
});

it('preserves an oversized-member marker and continues to a later success', async () => {
  const expected = frame();
  const marker = {workspaceId: 'workspace', sessionId: 'large-session', outcome: 'response_too_large'};
  const received: unknown[] = [];

  await readActivityFrames(new Response(`${JSON.stringify(marker)}\n${JSON.stringify(expected)}\n`), (result) =>
    received.push(result)
  );

  expect(received).toEqual([marker, expected]);
});

it('rejects an oversized unfinished frame and cancels its reader', async () => {
  let isCancelled = false;
  const stream = cancellationObservedStream(new TextEncoder().encode('x'.repeat(1_048_577)), () => {
    isCancelled = true;
  });
  await expect(readActivityFrames(new Response(stream), () => {})).rejects.toThrow('size limit');
  expect(isCancelled).toBe(true);
});

it('rejects a batch over 8 MiB and cancels its reader', async () => {
  let isCancelled = false;
  const stream = cancellationObservedStream(new Uint8Array(8_388_609), () => {
    isCancelled = true;
  });

  await expect(readActivityFrames(new Response(stream), () => {})).rejects.toThrow('byte limit');
  expect(isCancelled).toBe(true);
});

it('bounds the number of supplied frames even when their contents are malformed', async () => {
  const response = new Response('null\n'.repeat(9));
  await expect(readActivityFrames(response, () => {})).rejects.toThrow('too many results');
});
