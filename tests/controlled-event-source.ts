/** @file Control EventSource callbacks and disposal in browser connection tests. */
import type {Collector, Session} from '../src/contracts';

interface StreamFrame {
  readonly cursor: number;
  readonly workspaceId: string;
  readonly sessionId?: string;
  readonly projection?: Collector | Session;
}

/** Retain replay URLs, browser ready states, and scoped close calls. */
export class ControlledEventSource extends EventTarget {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSED = 2;
  readonly withCredentials = false;
  readonly url: string;
  readyState = 1;
  closeCount = 0;
  onerror: EventSource['onerror'] = null;
  onmessage: EventSource['onmessage'] = null;
  onopen: EventSource['onopen'] = null;
  static instances: ControlledEventSource[] = [];

  /** Retain the requested replay URL, as the browser transport does. */
  constructor(url: string | URL) {
    super();
    this.url = String(url);
    ControlledEventSource.instances.push(this);
  }

  /** Record scoped disposal separately from a server-induced closed state. */
  close(): void {
    this.readyState = this.CLOSED;
    this.closeCount += 1;
  }

  /** Deliver one browser event with its independent SSE cursor. */
  send(name: string, payload: StreamFrame, cursor: number): void {
    this.dispatchEvent(new MessageEvent(name, {data: JSON.stringify(payload), lastEventId: String(cursor)}));
  }
}

/**
 * Install a fresh stream registry for one connection scenario.
 * @returns Cleanup restoring the browser's previous EventSource constructor.
 * @example
 * const restore = installControlledEventSource();
 * restore();
 */
export function installControlledEventSource(): () => void {
  const previousSource = Reflect.getOwnPropertyDescriptor(globalThis, 'EventSource');
  ControlledEventSource.instances.length = 0;
  Object.defineProperty(globalThis, 'EventSource', {configurable: true, value: ControlledEventSource});
  return () => {
    if (previousSource === undefined) Reflect.deleteProperty(globalThis, 'EventSource');
    else Object.defineProperty(globalThis, 'EventSource', previousSource);
  };
}
