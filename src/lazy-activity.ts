/** @file Resolve visible unknown activity without manufacturing journal events. */
import type {SessionActivityFrame} from './contracts';
import {readActivityFrames} from './activity-batch';
import type {BoardStore} from './client';

interface Lookup {
  readonly workspaceId: string;
  readonly sessionId: string;
  readonly revision: number;
  readonly retryKey: string;
  readonly retryToken: symbol;
}
interface AttemptStamp {
  readonly timestamp: number;
  readonly token: symbol;
}
const MARKS = 'button[data-session-id]';
const BATCH_SIZE = 4;
const MAX_BATCHES = 2;

/** Own two bounded browser lookups; for example, enqueue a visible unknown session. */
class ActivityRequests {
  private readonly queue: Lookup[] = [];
  private readonly attempted = new Map<string, AttemptStamp>();
  private readonly controllers = new Set<AbortController>();
  private readonly activeSessionIds = new Set<string>();
  private running = 0;
  private isDrainScheduled = false;
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
    if (this.queue.length >= 256 || this.activeSessionIds.has(sessionId)) return;
    const key = `${snapshot.workspaceId}:${sessionId}:${session.lastEventId}`;
    if (this.isRecentlyAttempted(key)) return;
    const retryToken = Symbol(key);
    this.remember(key, {timestamp: Date.now(), token: retryToken});
    this.queue.push({
      workspaceId: snapshot.workspaceId,
      sessionId,
      revision: session.lastEventId,
      retryKey: key,
      retryToken
    });
    this.scheduleDrain();
  }

  /** Bound retry bookkeeping; for example, discard the oldest of 513 revisions. */
  private remember(key: string, stamp: AttemptStamp): void {
    this.attempted.set(key, stamp);
    if (this.attempted.size > 512) {
      const oldest = this.attempted.keys().next().value;
      if (oldest !== undefined) this.attempted.delete(oldest);
    }
  }

  /** Check the retry window without weakening an active or replaced stamp. */
  private isRecentlyAttempted(key: string): boolean {
    const stamp = this.attempted.get(key);
    return stamp !== undefined && Date.now() - stamp.timestamp < 30_000;
  }

  /** Forget a dropped queue entry only while its retry stamp is still its own. */
  private forgetDropped(task: Lookup): void {
    if (this.attempted.get(task.retryKey)?.token === task.retryToken) {
      this.attempted.delete(task.retryKey);
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

  /** Coalesce viewport entries from one browser turn before sending a batch. */
  private scheduleDrain(): void {
    if (this.isDrainScheduled) return;
    this.isDrainScheduled = true;
    queueMicrotask(() => {
      this.isDrainScheduled = false;
      this.drain();
    });
  }

  /** Start two streaming batches, leaving offscreen queued work unrequested. */
  private drain(): void {
    while (!this.isStopped && this.running < MAX_BATCHES) {
      const tasks = this.nextBatch();
      if (tasks.length === 0) return;
      this.running += 1;
      void this.run(tasks);
    }
  }

  /** Gather current visible revisions; for example, discard a mark scrolled away. */
  private nextBatch(): Lookup[] {
    const tasks: Lookup[] = [];
    while (tasks.length < BATCH_SIZE) {
      const task = this.queue.shift();
      if (!task) break;
      if (!this.matches(task)) {
        this.forgetDropped(task);
        continue;
      }
      tasks.push(task);
    }
    return tasks;
  }

  /** Apply only current validated responses; for example, preserve the journal cursor. */
  private async run(tasks: readonly Lookup[]): Promise<void> {
    const controller = new AbortController();
    this.controllers.add(controller);
    const timeout = setTimeout(() => controller.abort(), 50_000);
    const lookups = new Map(tasks.map((task) => [task.sessionId, task]));
    for (const task of tasks) this.activeSessionIds.add(task.sessionId);
    try {
      const response = await fetch('/api/v1/sessions/activity', {
        method: 'POST',
        headers: {'content-type': 'application/json'},
        body: JSON.stringify({sessionIds: [...lookups.keys()]}),
        signal: controller.signal,
        cache: 'no-store'
      });
      if (!response.ok) return;
      await readActivityFrames(response, (frame) => this.applyFrame(lookups, frame));
    } catch {
      // Source failures retain unknown activity; a later visible retry may succeed.
    } finally {
      clearTimeout(timeout);
      this.controllers.delete(controller);
      this.running -= 1;
      for (const task of tasks) {
        this.activeSessionIds.delete(task.sessionId);
        if (!this.isStopped && this.isVisible(task.sessionId)) this.enqueue(task.sessionId);
      }
      this.scheduleDrain();
    }
  }

  /** Match every streamed result against the request's workspace, identity and revision. */
  private applyFrame(lookups: ReadonlyMap<string, Lookup>, frame: SessionActivityFrame): void {
    if (this.isStopped) return;
    const task = lookups.get(frame.sessionId);
    if (!task || frame.workspaceId !== task.workspaceId) return;
    const session = frame.session;
    if (!session || session.sessionId !== task.sessionId) return;
    if (session.lastEventId < task.revision) return;
    this.store.activity(frame.workspaceId, session);
  }
}

/** Visit matching descendants; for example, React may insert a whole repository bank. */
function visitMarks(node: Node, visit: (element: Element) => void): void {
  if (!(node instanceof Element)) return;
  if (node.matches(MARKS)) visit(node);
  for (const mark of node.querySelectorAll(MARKS)) visit(mark);
}

/** Track real marks that are visible and rediscoverable after leaving the viewport. */
class ActivityVisibility {
  private readonly visible = new Set<Element>();
  private observer: IntersectionObserver | undefined;
  private mutation: MutationObserver | undefined;

  /** Start observing existing and newly rendered marks; for example, watch a mounted board. */
  start(enqueue: (element: Element) => void): void {
    this.observer = new IntersectionObserver((entries) => this.update(entries, enqueue));
    this.mutation = new MutationObserver((records) => this.applyMutations(records));
    document.querySelectorAll(MARKS).forEach((mark) => this.observer?.observe(mark));
    this.mutation.observe(document.body, {childList: true, subtree: true});
  }

  /** Answer whether a session still has a visible mark; for example, retain visible retries. */
  hasSession(sessionId: string): boolean {
    for (const mark of this.visible) {
      if (mark.getAttribute('data-session-id') === sessionId) return true;
    }
    return false;
  }

  /** Revisit visible marks after metadata changes; for example, retry newly unknown sessions. */
  revisit(enqueue: (element: Element) => void): void {
    for (const mark of this.visible) enqueue(mark);
  }

  /** Release observers and visible marks; for example, close on a board unmount. */
  close(): void {
    this.mutation?.disconnect();
    this.observer?.disconnect();
    this.visible.clear();
  }

  private update(entries: readonly IntersectionObserverEntry[], enqueue: (element: Element) => void): void {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        this.visible.add(entry.target);
        enqueue(entry.target);
      } else this.visible.delete(entry.target);
    }
  }

  private applyMutations(records: readonly MutationRecord[]): void {
    for (const record of records) {
      for (const node of record.addedNodes) {
        visitMarks(node, (mark) => this.observer?.observe(mark));
      }
      for (const node of record.removedNodes) {
        visitMarks(node, (mark) => {
          this.observer?.unobserve(mark);
          this.visible.delete(mark);
        });
      }
    }
  }
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
  const visibility = new ActivityVisibility();
  const requests = new ActivityRequests(store, (id) => visibility.hasSession(id));
  const enqueue = (element: Element): void => {
    const id = element.getAttribute('data-session-id');
    if (id) requests.enqueue(id);
  };
  visibility.start(enqueue);
  const unsubscribe = store.subscribe(() => visibility.revisit(enqueue));
  return () => {
    unsubscribe();
    requests.close();
    visibility.close();
  };
}
