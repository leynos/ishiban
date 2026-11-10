/** @file Resolve visible unknown activity without manufacturing journal events. */
import {Schema} from 'effect';
import {SessionActivitySchema} from './contracts';
import type {BoardStore} from './client';

interface Lookup {
  readonly workspaceId: string;
  readonly sessionId: string;
  readonly revision: number;
}
const MARKS = 'button[data-session-id]';

/** Own two bounded browser lookups; for example, enqueue a visible unknown session. */
class ActivityRequests {
  private readonly queue: Lookup[] = [];
  private readonly attempted = new Map<string, number>();
  private readonly controllers = new Set<AbortController>();
  private running = 0;
  private isStopped = false;
  constructor(
    private readonly store: BoardStore,
    private readonly isVisible: (id: string) => boolean
  ) {}

  /** Queue a real unknown mark; for example, skip duplicate entries for its revision. */
  enqueue(sessionId: string): void {
    const snapshot = this.store.getSnapshot().snapshot;
    if (!snapshot) return;
    const session = snapshot.sessions.find((item) => item.sessionId === sessionId);
    if (!session) return;
    if (session.state !== 'unknown') return;
    if (session.source === 'demo') return;
    if (this.queue.length >= 256) return;
    const key = `${snapshot.workspaceId}:${sessionId}:${session.lastEventId}`;
    if (Date.now() - (this.attempted.get(key) ?? -Infinity) < 30_000) return;
    this.remember(key);
    this.queue.push({workspaceId: snapshot.workspaceId, sessionId, revision: session.lastEventId});
    this.drain();
  }

  /** Bound retry bookkeeping; for example, discard the oldest of 513 revisions. */
  private remember(key: string): void {
    this.attempted.set(key, Date.now());
    if (this.attempted.size > 512) {
      const oldest = this.attempted.keys().next().value;
      if (oldest !== undefined) this.attempted.delete(oldest);
    }
  }

  /** Close owned work; for example, switching to demo aborts outstanding reads. */
  close(): void {
    this.isStopped = true;
    this.queue.length = 0;
    for (const controller of this.controllers) controller.abort();
  }

  /** Reject stale queue entries; for example, a newer journal event wins. */
  private matches(task: Lookup): boolean {
    const snapshot = this.store.getSnapshot().snapshot;
    const session = snapshot?.sessions.find((item) => item.sessionId === task.sessionId);
    if (snapshot?.workspaceId !== task.workspaceId) return false;
    if (session?.state !== 'unknown') return false;
    if (session.lastEventId !== task.revision) return false;
    return this.isVisible(task.sessionId);
  }

  /** Start at most two reads; for example, leave off-screen work unrequested. */
  private drain(): void {
    while (!this.isStopped && this.running < 2) {
      const task = this.queue.shift();
      if (!task) return;
      if (!this.matches(task)) continue;
      this.running += 1;
      void this.run(task);
    }
  }

  /** Apply only current validated responses; for example, preserve the journal cursor. */
  private async run(task: Lookup): Promise<void> {
    const controller = new AbortController();
    this.controllers.add(controller);
    const timeout = setTimeout(() => controller.abort(), 25_000);
    try {
      const response = await fetch(`/api/v1/sessions/${encodeURIComponent(task.sessionId)}/activity`, {
        signal: controller.signal,
        cache: 'no-store'
      });
      if (!response.ok) return;
      const result = Schema.decodeUnknownSync(SessionActivitySchema)(await response.json());
      if (this.isStopped) return;
      if (result.workspaceId !== task.workspaceId) return;
      const session = result.session;
      if (!session) return;
      if (session.sessionId !== task.sessionId) return;
      if (session.lastEventId !== task.revision) return;
      this.store.activity(result.workspaceId, session);
    } catch {
      // Source failures retain unknown activity; a later visible retry may succeed.
    } finally {
      clearTimeout(timeout);
      this.controllers.delete(controller);
      this.running -= 1;
      this.drain();
    }
  }
}

/** Visit matching descendants; for example, React may insert a whole repository bank. */
function visitMarks(node: Node, visit: (element: Element) => void): void {
  if (!(node instanceof Element)) return;
  if (node.matches(MARKS)) visit(node);
  for (const mark of node.querySelectorAll(MARKS)) visit(mark);
}

/**
 * Resolve activity only as real marks enter the viewport.
 * @param store Live browser projection, with revision-checked ephemeral updates.
 * @returns Cleanup for observers, subscription and bounded HTTP requests.
 * @example
 * const stop = startLazyActivity(store); stop();
 */
export function startLazyActivity(store: BoardStore): () => void {
  if (typeof IntersectionObserver === 'undefined') return () => {};
  const visible = new Set<Element>();
  const requests = new ActivityRequests(store, (id) => {
    for (const mark of visible) if (mark.getAttribute('data-session-id') === id) return true;
    return false;
  });
  const enqueue = (element: Element) => {
    const id = element.getAttribute('data-session-id');
    if (id) requests.enqueue(id);
  };
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        visible.add(entry.target);
        enqueue(entry.target);
      } else visible.delete(entry.target);
    }
  });
  const mutation = new MutationObserver((records) => {
    for (const record of records) {
      for (const node of record.addedNodes) visitMarks(node, (mark) => observer.observe(mark));
      for (const node of record.removedNodes)
        visitMarks(node, (mark) => {
          observer.unobserve(mark);
          visible.delete(mark);
        });
    }
  });
  for (const mark of document.querySelectorAll(MARKS)) observer.observe(mark);
  mutation.observe(document.body, {childList: true, subtree: true});
  const unsubscribe = store.subscribe(() => {
    for (const mark of visible) enqueue(mark);
  });
  return () => {
    mutation.disconnect();
    observer.disconnect();
    unsubscribe();
    requests.close();
    visible.clear();
  };
}
