/** @file Bound browser CLI child capture, termination and reap in tests. */

export interface CapturedCommand {
  readonly stdout: string;
  readonly stderr: string;
  readonly status: number;
}

const MAX_PIPE_BYTES = 64 * 1024;
const REAP_GRACE_MS = 2000;

/** Stop a pending pipe read when its owner aborts, with a per-pipe byte cap. */
async function readPipe(pipe: ReadableStream<Uint8Array>, signal: AbortSignal): Promise<string> {
  const reader = pipe.getReader();
  const decoder = new TextDecoder();
  let output = '';
  let bytes = 0;
  const aborted = new Promise<never>((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(new Error('Browser command aborted.')), {once: true});
  });
  try {
    for (;;) {
      const chunk = await Promise.race([reader.read(), aborted]);
      if (chunk.done) return output + decoder.decode();
      bytes += chunk.value.byteLength;
      if (bytes > MAX_PIPE_BYTES) throw new Error(`Browser command pipe exceeded ${MAX_PIPE_BYTES} bytes.`);
      output += decoder.decode(chunk.value, {stream: true});
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

/** Bound one await without leaving its deadline timer referenced after settlement. */
async function withinDeadline<T>(task: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<never>((_resolve, reject) => {
    timer = setTimeout(() => reject(new Error(message)), timeoutMs);
  });
  try {
    return await Promise.race([task, deadline]);
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Capture one test CLI command with a deadline, then kill and reap its child.
 * Both output pipes are limited to 64 KiB; cleanup has a separate two-second bound.
 * @param command Executable and literal arguments, without a shell.
 * @param deadlineMs Maximum command lifetime before SIGKILL.
 * @returns Captured output and the actual exit status.
 * @throws {Error} When the command expires, exceeds a pipe cap, or cannot be reaped.
 * @example
 * await runCapturedCommand([process.execPath, '-e', "console.log('ready')"], 1000);
 */
export async function runCapturedCommand(command: readonly string[], deadlineMs: number): Promise<CapturedCommand> {
  const owner = new AbortController();
  const child = Bun.spawn({cmd: [...command], stdout: 'pipe', stderr: 'pipe'});
  const work = [readPipe(child.stdout, owner.signal), readPipe(child.stderr, owner.signal), child.exited] as const;
  const settled = Promise.allSettled(work);
  const timer = setTimeout(() => {
    child.kill('SIGKILL');
    owner.abort();
  }, deadlineMs);
  try {
    const [stdout, stderr, status] = await withinDeadline(
      Promise.all(work),
      deadlineMs + REAP_GRACE_MS,
      'Browser command pipes did not close after termination.'
    );
    if (owner.signal.aborted) throw new Error(`Browser command timed out after ${deadlineMs} ms.`);
    return {stdout, stderr, status};
  } catch (error) {
    if (owner.signal.aborted) throw new Error(`Browser command timed out after ${deadlineMs} ms.`, {cause: error});
    throw error;
  } finally {
    clearTimeout(timer);
    if (child.exitCode === null) child.kill('SIGKILL');
    owner.abort();
    await withinDeadline(settled, REAP_GRACE_MS, 'Browser command child did not reap after SIGKILL.');
  }
}
