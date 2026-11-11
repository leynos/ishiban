/** @file Read history recency for visible session families with bounded ownership. */
import {useEffect, useRef, useState} from 'react';
import {Schema} from 'effect';
import {readBoundedFrames} from './bounded-frames';
import type {Snapshot} from './contracts';
import {groupSessions, type RecencyFact, type SessionFamily} from './session-families';
import {withRequestLifetime} from './request-lifetime';
import {isRequestableSessionId} from './lookup-session-id';
import {settleFact, unconfirmedFact, type CacheEntry, type RecencyState} from './recency-facts';
export type {RecencyState} from './recency-facts';

const FrameSchema = Schema.Union([
  Schema.Struct({
    workspaceId: Schema.String,
    sessionId: Schema.String,
    lastActivityEventId: Schema.Number,
    outcome: Schema.Literal('available'),
    latestHistoryAt: Schema.NullOr(Schema.String)
  }),
  Schema.Struct({
    workspaceId: Schema.String,
    sessionId: Schema.String,
    lastActivityEventId: Schema.Number,
    outcome: Schema.Literal('unavailable')
  })
]);
type Frame = typeof FrameSchema.Type;
interface Lookup {
  readonly workspaceId: string;
  readonly sessionId: string;
  readonly basis: number;
}
interface ScopedFacts extends RecencyState {
  readonly workspaceId: string;
}
const MARKS = 'button[data-family-id]';
const MAX_BATCH = 8;
const MAX_RUNNING = 2;
const MAX_BODY = 8192;
const MAX_FRAME = 1_048_576;
const MAX_RESPONSE = 8_388_608;
const MAX_CACHE = 512;

// Example: ['tab'] measures the bytes in {"sessionIds":["tab"]}.
/** Measure the exact recency POST request shape; only this endpoint reuses it. */
function encodedBodyBytes(sessionIds: readonly string[]): number {
  return new TextEncoder().encode(JSON.stringify({sessionIds})).byteLength;
}

/** Own queued visible lookups and cancel all network work on scope or unmount. */
class RecencyRequests {
  private snapshot: Snapshot;
  // Viewport notifications share a membership graph until the raw records change.
  private families: readonly SessionFamily[];
  private readonly visible = new Set<string>();
  private readonly queue: Lookup[] = [];
  private readonly active = new Set<string>();
  private readonly controllers = new Set<AbortController>();
  private readonly cache = new Map<string, CacheEntry>();
  private readonly familyByMember = new Map<string, string>();
  private eligible = new Set<string>();
  private limitedRoots = new Set<string>();
  private running = 0;
  private transportRetryAt = 0;
  private stopped = false;
  constructor(
    snapshot: Snapshot,
    private readonly publish: (state: RecencyState) => void
  ) {
    this.snapshot = snapshot;
    this.families = groupSessions(snapshot.sessions, new Map());
  }

  /** Replace the current basis without treating a metadata refresh as new history. */
  update(snapshot: Snapshot): void {
    if (this.snapshot.workspaceId !== snapshot.workspaceId) {
      this.close();
      return;
    }
    if (this.snapshot.sessions !== snapshot.sessions) {
      this.families = groupSessions(snapshot.sessions, new Map());
    }
    this.snapshot = snapshot;
    let hasStaleFacts = false;
    for (const [id, entry] of this.cache) {
      const current = snapshot.sessions.find((session) => session.sessionId === id);
      if (!current || (current.lastActivityEventId ?? 0) !== entry.basis) {
        this.cache.delete(id);
        hasStaleFacts = true;
      }
    }
    if (hasStaleFacts) this.publishState();
    this.revisit();
  }

  /** Admit only members of one visible, multi-tab family. */
  visibleFamily(rootId: string): void {
    this.visible.add(rootId);
    this.revisit();
  }

  /** Stop requesting a family when every mark has left the viewport. */
  hiddenFamily(rootId: string): void {
    if (this.visible.delete(rootId)) this.revisit();
  }

  /** Retry expired facts and changed execution bases for visible family members. */
  revisit(): void {
    if (this.stopped) return;
    this.expireFacts();
    this.familyByMember.clear();
    const eligible = new Set<string>();
    const limitedRoots = new Set<string>();
    for (const family of this.families) {
      this.indexFamily(family, eligible, limitedRoots);
    }
    this.eligible = eligible;
    this.queue.splice(0, this.queue.length, ...this.queue.filter((task) => this.isVisibleCurrent(task)));
    this.enqueueAdmittedMembers(eligible);
    const hasLimitChange =
      limitedRoots.size !== this.limitedRoots.size ||
      [...limitedRoots].some((rootId) => !this.limitedRoots.has(rootId));
    this.limitedRoots = limitedRoots;
    if (hasLimitChange) this.publishState();
    this.drain();
  }

  /** Mark expired timestamps provisional, even while their family is hidden. */
  private expireFacts(): void {
    const now = Date.now();
    let hasExpiredFact = false;
    for (const [id, entry] of this.cache) {
      if (entry.expiresAt > now || entry.fact.outcome !== 'available') continue;
      this.cache.set(id, {...entry, fact: unconfirmedFact(entry.fact, 'pending')});
      hasExpiredFact = true;
    }
    if (hasExpiredFact) this.publishState();
  }

  /** Preserve stable family member order when filling the bounded queue. */
  private enqueueAdmittedMembers(eligible: ReadonlySet<string>): void {
    for (const family of this.families) {
      for (const member of family.members) {
        if (eligible.has(member.sessionId)) this.enqueue(member.sessionId, member.lastActivityEventId ?? 0);
      }
    }
  }

  /** Admit whole visible families so every admitted member can settle in the fact cache. */
  private indexFamily(family: SessionFamily, eligible: Set<string>, limitedRoots: Set<string>): void {
    for (const member of family.members) this.familyByMember.set(member.sessionId, family.rootId);
    if (family.members.length < 2 || !this.visible.has(family.rootId)) return;
    const realMembers = family.members.filter(
      (member) => member.source !== 'demo' && isRequestableSessionId(member.sessionId)
    );
    if (realMembers.length > MAX_CACHE - eligible.size) {
      limitedRoots.add(family.rootId);
      return;
    }
    for (const member of realMembers) {
      eligible.add(member.sessionId);
    }
  }

  /** Admit one current member without duplicating its in-flight basis. */
  private enqueue(sessionId: string, basis: number): void {
    const cached = this.cache.get(sessionId);
    if (cached?.basis === basis && cached.expiresAt > Date.now()) return;
    if (this.active.has(sessionId) || this.queue.some((task) => task.sessionId === sessionId)) return;
    if (this.queue.length >= 256) return;
    this.queue.push({workspaceId: this.snapshot.workspaceId, sessionId, basis});
  }

  /** Match the raw execution watermark before publishing a lookup fact. */
  private isCurrent(task: Lookup): boolean {
    if (this.stopped || this.snapshot.workspaceId !== task.workspaceId) return false;
    if (!this.eligible.has(task.sessionId)) return false;
    const current = this.snapshot.sessions.find((session) => session.sessionId === task.sessionId);
    return current !== undefined && (current.lastActivityEventId ?? 0) === task.basis;
  }

  /** Evict only non-admitted facts when a complete visible family needs room. */
  private record(task: Lookup, fact: RecencyFact): void {
    if (!this.isCurrent(task)) return;
    const prior = this.cache.get(task.sessionId);
    const finalFact = settleFact(fact, prior, task.basis);
    this.cache.delete(task.sessionId);
    if (this.cache.size >= MAX_CACHE) {
      const evictable = [...this.cache.keys()].find((sessionId) => !this.eligible.has(sessionId));
      if (evictable === undefined) return;
      this.cache.delete(evictable);
    }
    this.cache.set(task.sessionId, {
      basis: task.basis,
      fact: finalFact,
      expiresAt: Date.now() + (fact.outcome === 'available' ? 300_000 : 30_000)
    });
    this.publishState();
  }

  /** Publish one scoped projection without retaining an unbounded retry history. */
  private publishState(): void {
    this.publish({
      facts: new Map([...this.cache].map(([id, entry]) => [id, entry.fact])),
      limitedRoots: new Set(this.limitedRoots)
    });
  }

  /** Pack queued members by both request count and actual encoded byte size. */
  private takeBatch(): Lookup[] {
    const tasks: Lookup[] = [];
    while (tasks.length < MAX_BATCH) {
      const candidate = this.nextCurrentQueued();
      if (!candidate) break;
      const proposed = [...tasks.map((task) => task.sessionId), candidate.sessionId];
      if (encodedBodyBytes(proposed) <= MAX_BODY) {
        tasks.push(candidate);
        continue;
      }
      if (tasks.length > 0) {
        this.queue.unshift(candidate);
        break;
      }
      this.record(candidate, {outcome: 'unavailable'});
    }
    return tasks;
  }

  /** Remove stale queued work until the next current visible member appears. */
  private nextCurrentQueued(): Lookup | undefined {
    while (this.queue.length > 0) {
      const candidate = this.queue.shift();
      if (candidate && this.isVisibleCurrent(candidate)) return candidate;
    }
    return undefined;
  }

  /** Send at most two eight-member requests, retaining all later visible work. */
  private drain(): void {
    while (this.canStartBatch()) {
      const tasks = this.takeBatch();
      if (tasks.length === 0) continue;
      for (const task of tasks) this.active.add(task.sessionId);
      this.running += 1;
      void this.run(tasks);
    }
  }

  /** Respect the browser's request and queue ownership bounds. */
  private canStartBatch(): boolean {
    return !this.stopped && this.running < MAX_RUNNING && this.queue.length > 0 && Date.now() >= this.transportRetryAt;
  }

  /** Drop queued work when its mark or execution basis has moved. */
  private isVisibleCurrent(task: Lookup): boolean {
    if (!this.isCurrent(task)) return false;
    const rootId = this.familyByMember.get(task.sessionId);
    return rootId !== undefined && this.visible.has(rootId);
  }

  /** Apply streaming members as they arrive, then reap this request's controller. */
  private async run(tasks: readonly Lookup[]): Promise<void> {
    const outstanding = new Map(tasks.map((task) => [task.sessionId, task]));
    try {
      await withRequestLifetime(this.controllers, async (signal) => {
        const body = JSON.stringify({sessionIds: tasks.map((task) => task.sessionId)});
        if (encodedBodyBytes(tasks.map((task) => task.sessionId)) > MAX_BODY)
          throw new Error('Recency request exceeds byte limit');
        const response = await fetch('/api/v1/sessions/recency', {
          method: 'POST',
          headers: {'content-type': 'application/json'},
          body,
          signal
        });
        if (!response.ok) throw new Error('Recency request failed');
        const integrity = {isMalformed: false};
        await readBoundedFrames(
          response,
          {maxFrameChars: MAX_FRAME, maxResponseBytes: MAX_RESPONSE, maxResults: MAX_BATCH},
          (line) => {
            try {
              return Schema.decodeUnknownSync(FrameSchema)(JSON.parse(line));
            } catch (error) {
              integrity.isMalformed = true;
              throw error;
            }
          },
          (frame) => this.applyFrame(outstanding, frame)
        );
        if (integrity.isMalformed || outstanding.size > 0) throw new Error('Recency response is incomplete');
      });
    } catch {
      // A broken transport must not spin through visible members as the LRU evicts failures.
      this.transportRetryAt = Math.max(this.transportRetryAt, Date.now() + 30_000);
    } finally {
      for (const task of outstanding.values()) this.record(task, {outcome: 'unavailable'});
      for (const task of tasks) this.active.delete(task.sessionId);
      this.running -= 1;
      this.revisit();
    }
  }

  /** Admit one scoped member; for example, ignore history from a superseded execution. */
  private applyFrame(outstanding: Map<string, Lookup>, frame: Frame): void {
    const task = outstanding.get(frame.sessionId);
    if (!task) return;
    if (frame.workspaceId !== task.workspaceId) return;
    outstanding.delete(frame.sessionId);
    // Changed execution settles this member without a transport cooldown.
    const isAvailable = frame.lastActivityEventId === task.basis && frame.outcome === 'available';
    this.record(
      task,
      isAvailable ? {outcome: 'available', latestHistoryAt: frame.latestHistoryAt} : {outcome: 'unavailable'}
    );
  }

  /** Release queued, active and shared browser work. */
  close(): void {
    this.stopped = true;
    this.queue.length = 0;
    for (const controller of this.controllers) controller.abort();
  }
}

/** Attach viewport observation to family marks without traversing offscreen tabs. */
function observeFamilies(requests: RecencyRequests): () => void {
  if (typeof IntersectionObserver === 'undefined') return () => {};
  const observer = new IntersectionObserver((entries) => updateVisibleFamilies(entries, requests));
  const observed = new Set<Element>();
  const scan = (): void => scanFamilyMarks(observer, observed, requests);
  scan();
  const mutation = new MutationObserver(scan);
  mutation.observe(document.body, {childList: true, subtree: true});
  return () => {
    mutation.disconnect();
    observer.disconnect();
  };
}

/** Apply viewport changes to current family roots. */
function updateVisibleFamilies(entries: readonly IntersectionObserverEntry[], requests: RecencyRequests): void {
  for (const entry of entries) {
    const id = entry.target.getAttribute('data-family-id');
    if (!id) continue;
    if (entry.isIntersecting) requests.visibleFamily(id);
    else requests.hiddenFamily(id);
  }
}

/** Observe newly rendered marks and release removed marks. */
function scanFamilyMarks(observer: IntersectionObserver, observed: Set<Element>, requests: RecencyRequests): void {
  for (const mark of document.querySelectorAll(MARKS)) {
    if (observed.has(mark)) continue;
    observed.add(mark);
    observer.observe(mark);
  }
  releaseDetachedMarks(observer, observed, requests);
}

/** Release visibility as well as observation; for example, a search removes a mark. */
function releaseDetachedMarks(observer: IntersectionObserver, observed: Set<Element>, requests: RecencyRequests): void {
  for (const mark of observed) {
    if (mark.isConnected) continue;
    const rootId = mark.getAttribute('data-family-id');
    if (rootId) requests.hiddenFamily(rootId);
    observed.delete(mark);
    observer.unobserve(mark);
  }
}

/**
 * Resolve only visible family members; for example, a refresh reuses process facts.
 * @param snapshot Current validated workspace projection.
 * @returns Current scoped history recency facts for family selection.
 */
export function useSessionRecency(snapshot: Snapshot): RecencyState {
  const [scoped, setScoped] = useState<ScopedFacts>(() => ({
    workspaceId: snapshot.workspaceId,
    facts: new Map(),
    limitedRoots: new Set()
  }));
  const requestsRef = useRef<RecencyRequests | null>(null);
  useEffect(() => {
    const requests = new RecencyRequests(snapshot, (state) => setScoped({workspaceId: snapshot.workspaceId, ...state}));
    requestsRef.current = requests;
    const stopObservation = observeFamilies(requests);
    const retry = setInterval(() => requests.revisit(), 15_000);
    return () => {
      clearInterval(retry);
      stopObservation();
      requests.close();
      requestsRef.current = null;
    };
  }, [snapshot.workspaceId]);
  useEffect(() => requestsRef.current?.update(snapshot), [snapshot]);
  return scoped.workspaceId === snapshot.workspaceId ? scoped : {facts: new Map(), limitedRoots: new Set()};
}
