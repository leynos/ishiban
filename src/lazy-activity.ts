/** @file Resolve visible unknown activity without manufacturing journal events. */
import type {Session, SessionActivityFrame, SessionActivityResponse} from './contracts';
import {readActivityFrames} from './activity-batch';
import {readSessionActivityResponse} from './activity-fallback';
import type {BoardStore} from './client';
import {withRequestLifetime} from './request-lifetime';
import {isRequestableSessionId} from './lookup-session-id';

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
interface BatchContext {
  readonly lookups: ReadonlyMap<string, Lookup>;
  readonly signal: AbortSignal;
  readonly fallbackSessionIds: Set<string>;
  readonly fallbackTasks: Promise<void>[];
}

/** Validate the fallback response against its requested identity and revision. */
function fallbackProjectionFor(task: Lookup, result: SessionActivityResponse): Session | undefined {
  if (result.workspaceId !== task.workspaceId) return undefined;
  const session = result.session;
  if (!session) return undefined;
  if (session.sessionId !== task.sessionId) return undefined;
  if (session.lastEventId !== task.revision) return undefined;
  return session;
}

const MARKS = 'button[data-session-id]';
const BATCH_SIZE = 4;
const MAX_BATCHES = 2;
const TRANSFER_NOTICE = 'Activity details exceed the transfer limit. Open the session in Lody.';

/** Require one real unknown session whose raw ID can cross the API boundary. */
function isActivityLookupCandidate(session: Session): boolean {
  if (session.state !== 'unknown') return false;
  if (session.source === 'demo') return false;
  return isRequestableSessionId(session.sessionId);
}

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
    if (!isActivityLookupCandidate(session)) return;
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
    for (const task of tasks) this.activeSessionIds.add(task.sessionId);
    try {
      await withRequestLifetime(this.controllers, async (signal) => {
        const context: BatchContext = {
          lookups: new Map(tasks.map((task) => [task.sessionId, task])),
          signal,
          fallbackSessionIds: new Set<string>(),
          fallbackTasks: []
        };
        try {
          await this.consumeBatch(tasks, context);
        } finally {
          await Promise.allSettled(context.fallbackTasks);
        }
      });
    } catch {
      // Source failures retain unknown activity; a later visible retry may succeed.
    } finally {
      this.running -= 1;
      for (const task of tasks) {
        this.activeSessionIds.delete(task.sessionId);
        if (!this.isStopped && this.isVisible(task.sessionId)) this.enqueue(task.sessionId);
      }
      this.scheduleDrain();
    }
  }

  /** Stream independently completed members while retaining one batch owner. */
  private async consumeBatch(tasks: readonly Lookup[], context: BatchContext): Promise<void> {
    const response = await fetch('/api/v1/sessions/activity', {
      method: 'POST',
      headers: {'content-type': 'application/json'},
      body: JSON.stringify({sessionIds: [...context.lookups.keys()]}),
      signal: context.signal,
      cache: 'no-store'
    });
    if (response.status === 413) {
      for (const task of tasks) this.showTransferNotice(task, context.signal);
      return;
    }
    if (!response.ok) return;
    await readActivityFrames(response, (frame) => this.applyFrame(context, frame));
  }

  /** Match each member and own any slower same-session fallback through batch cleanup. */
  private applyFrame(context: BatchContext, frame: SessionActivityFrame): void {
    if (this.isStopped) return;
    const task = context.lookups.get(frame.sessionId);
    if (!task || frame.workspaceId !== task.workspaceId) return;
    if ('outcome' in frame) {
      this.admitFallback(context, task);
      return;
    }
    const session = frame.session;
    if (!session || session.sessionId !== task.sessionId) return;
    if (session.lastEventId < task.revision) return;
    this.store.activity(frame.workspaceId, session);
  }

  /** Start one request for a marked member without delaying later stream frames. */
  private admitFallback(context: BatchContext, task: Lookup): void {
    if (context.fallbackSessionIds.has(task.sessionId)) return;
    if (!this.matches(task)) return;
    context.fallbackSessionIds.add(task.sessionId);
    context.fallbackTasks.push(this.resolveOversizedMember(task, context.signal));
  }

  /** Recover one cached oversized result while the batch continues reading siblings. */
  private async resolveOversizedMember(task: Lookup, signal: AbortSignal): Promise<void> {
    try {
      const id = encodeURIComponent(task.sessionId);
      const response = await fetch(`/api/v1/session-activity?sessionId=${id}&includeKnown=true`, {
        signal,
        cache: 'no-store'
      });
      const result = await readSessionActivityResponse(response, signal);
      const session = fallbackProjectionFor(task, result);
      if (!session) return;
      if (!this.matches(task)) return;
      this.store.activity(result.workspaceId, session);
    } catch {
      this.showTransferNotice(task, signal);
    }
  }

  /** Keep transport failures quiet and revision-local; for example, report a 413 response. */
  private showTransferNotice(task: Lookup, signal: AbortSignal): void {
    if (this.isStopped) return;
    if (signal.aborted) return;
    if (!this.matches(task)) return;
    this.store.activityNotice(task.workspaceId, task.sessionId, task.revision, TRANSFER_NOTICE);
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
    this.mutation = new MutationObserver((records) => this.applyMutations(records, enqueue));
    document.querySelectorAll(MARKS).forEach((mark) => this.observer?.observe(mark));
    this.mutation.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['data-session-id']
    });
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

  private applyMutations(records: readonly MutationRecord[], enqueue: (element: Element) => void): void {
    for (const record of records) {
      if (record.type === 'attributes') {
        this.enqueueChangedIdentity(record.target, enqueue);
        continue;
      }
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

  /** Revisit only a mark already visible when its selected raw tab changes. */
  private enqueueChangedIdentity(target: Node, enqueue: (element: Element) => void): void {
    if (!(target instanceof Element)) return;
    if (!this.visible.has(target)) return;
    enqueue(target);
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
