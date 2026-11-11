/** @file Write exact UTF-8 fixture bytes into the Python-owned bounded FIFO. */
import {closeSync, openSync, writeSync} from 'node:fs';

/**
 * Write the complete test payload, including across partial FIFO writes.
 * @param path Private capture path supplied by the Python contract test.
 * @param content UTF-8 text captured for the cross-runtime assertion.
 * @throws {Error} If the filesystem write fails or makes no progress.
 * @example
 * writeCapturedText(capturePath, JSON.stringify({sessionId: 'root'}));
 */
export function writeCapturedText(path: string, content: string): void {
  const bytes = Buffer.from(content, 'utf8');
  const fd = openSync(path, 'w');
  try {
    let offset = 0;
    while (offset < bytes.length) {
      const written = writeSync(fd, bytes, offset, bytes.length - offset);
      if (written <= 0) throw new Error(`Capture writer made no progress at byte ${offset}.`);
      offset += written;
    }
  } finally {
    closeSync(fd);
  }
}
