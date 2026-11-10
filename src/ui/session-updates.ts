/** @file Track short visual cues for meaningful session changes. */
import {useEffect, useMemo, useState} from 'react';
import type {Session, Snapshot} from '../contracts';

const PULSE_LIFETIME_MS = 900;

interface PulseCue {
  readonly revision: number;
  readonly expiresAt: number;
}

interface CommittedSnapshot {
  readonly workspaceId: string;
  readonly isDemo: boolean;
  readonly snapshot: Snapshot;
  readonly cues: ReadonlyMap<string, PulseCue>;
}

type TurnFact = NonNullable<Session['latestTurn']>;
type PullRequestFact = Session['pullRequests'][number];

/** Keep only cues that belong to sessions in the current snapshot. */
function unexpiredCues(cues: ReadonlyMap<string, PulseCue>, now: number): Map<string, PulseCue> {
  return new Map([...cues].filter(([, cue]) => cue.expiresAt > now));
}

/** Compare unordered facts; for example, reordered pull requests remain equivalent. */
function sameUnorderedFacts<Item>(
  previous: readonly Item[],
  current: readonly Item[],
  keyOf: (item: Item) => string
): boolean {
  if (previous.length !== current.length) return false;
  const previousKeys = previous.map((item) => keyOf(item)).toSorted();
  const currentKeys = current.map((item) => keyOf(item)).toSorted();
  return previousKeys.every((key, index) => key === currentKeys[index]);
}

/** Encode the user-visible turn facts; for example, omit timing and provenance fields. */
function turnFactKey(turn: TurnFact): string {
  return JSON.stringify([turn.userTurnId, turn.state, turn.error ?? null]);
}

/** Encode the user-visible pull-request facts; for example, preserve URL association. */
function pullRequestFactKey(pullRequest: PullRequestFact): string {
  return JSON.stringify([pullRequest.url, pullRequest.title, pullRequest.status]);
}

/** Compare latest-turn outcome fields without object-identity noise. */
function sameLatestTurn(previous: TurnFact | null, current: TurnFact | null): boolean {
  if (previous === null) return current === null;
  if (current === null) return false;
  return turnFactKey(previous) === turnFactKey(current);
}

/** Compare fields that identify the session's visible title, repository and branch. */
function sameBoardMetadata(previous: Session, current: Session): boolean {
  return (
    previous.title === current.title &&
    previous.repoFullName === current.repoFullName &&
    previous.branchName === current.branchName
  );
}

/** Compare workflow state that explains where the session belongs on the board. */
function sameWorkflowMetadata(previous: Session, current: Session): boolean {
  return (
    previous.stage === current.stage &&
    previous.stageReason === current.stageReason &&
    previous.archived === current.archived &&
    previous.removed === current.removed
  );
}

/** Compare fields that describe the session's board and inspector metadata. */
function sameSessionMetadata(previous: Session, current: Session): boolean {
  return (
    sameBoardMetadata(previous, current) &&
    sameWorkflowMetadata(previous, current) &&
    sameUnorderedFacts(previous.pullRequests, current.pullRequests, pullRequestFactKey)
  );
}

/** Compare execution state while ignoring observation timestamps and source labels. */
function sameRuntime(previous: Session, current: Session): boolean {
  return (
    previous.state === current.state &&
    sameLatestTurn(previous.latestTurn, current.latestTurn) &&
    sameUnorderedFacts(previous.activeTurns, current.activeTurns, turnFactKey)
  );
}

/** Detect a meaningful new-revision change; for example, ignore metadata generation alone. */
function hasMeaningfulChange(previous: Session, current: Session): boolean {
  if (previous === current) return false;
  if (sameSessionMetadata(previous, current)) {
    if (current.activitySource === 'lazy') return false;
    return !sameRuntime(previous, current);
  }
  return true;
}

/** Startup replay and generation transitions establish a quiet semantic baseline. */
function shouldResetBaseline(previous: Snapshot, current: Snapshot): boolean {
  return (
    previous.collector.state === 'connecting' ||
    current.collector.state === 'connecting' ||
    previous.collector.generation !== current.collector.generation
  );
}

/** Apply one session's revision outcome; for example, preserve a cue for timestamp-only refreshes. */
function recordSessionCue(
  session: Session,
  previousSession: Session | undefined,
  cues: Map<string, PulseCue>,
  now: number
): void {
  if (previousSession === undefined) {
    cues.set(session.sessionId, {revision: session.lastEventId, expiresAt: now + PULSE_LIFETIME_MS});
    return;
  }
  const isUnchangedRevision = previousSession.lastEventId === session.lastEventId;
  if (session.activitySource === 'lazy' && isUnchangedRevision) {
    cues.delete(session.sessionId);
    return;
  }
  if (isUnchangedRevision || !hasMeaningfulChange(previousSession, session)) return;
  cues.set(session.sessionId, {revision: session.lastEventId, expiresAt: now + PULSE_LIFETIME_MS});
}

/** Record new sessions and semantically changed event revisions after a committed snapshot. */
function cuesForSnapshot(
  previous: Snapshot,
  current: Snapshot,
  existing: ReadonlyMap<string, PulseCue>
): Map<string, PulseCue> {
  if (shouldResetBaseline(previous, current)) return new Map();
  const previousSessions = new Map(previous.sessions.map((session) => [session.sessionId, session]));
  const now = Date.now();
  const cues = unexpiredCues(existing, now);
  for (const session of current.sessions) {
    recordSessionCue(session, previousSessions.get(session.sessionId), cues, now);
  }
  return cues;
}

/**
 * Return active revisions for meaningful session changes, excluding initial and restart replay.
 * @param snapshot The latest immutable snapshot received from the client.
 * @returns Session IDs mapped to 900 ms cues for meaningful new revisions.
 */
export function useSessionUpdates(snapshot: Snapshot): ReadonlyMap<string, number> {
  const [committed, setCommitted] = useState<CommittedSnapshot>(() => ({
    workspaceId: snapshot.workspaceId,
    isDemo: snapshot.collector.state === 'demo',
    snapshot,
    cues: new Map()
  }));

  if (committed.snapshot !== snapshot) {
    const isDemo = snapshot.collector.state === 'demo';
    const isSameScope = committed.workspaceId === snapshot.workspaceId && committed.isDemo === isDemo;
    const cues = isSameScope
      ? cuesForSnapshot(committed.snapshot, snapshot, committed.cues)
      : new Map<string, PulseCue>();
    setCommitted({workspaceId: snapshot.workspaceId, isDemo, snapshot, cues});
  }

  const cues = committed.snapshot === snapshot ? committed.cues : new Map<string, PulseCue>();
  useEffect(() => {
    if (cues.size === 0) {
      return;
    }
    const expiresAt = Math.min(...[...cues.values()].map((cue) => cue.expiresAt));
    const timeout = globalThis.setTimeout(
      () => {
        setCommitted((current) => ({
          ...current,
          cues: unexpiredCues(current.cues, Date.now())
        }));
      },
      Math.max(0, expiresAt - Date.now())
    );
    return () => globalThis.clearTimeout(timeout);
  }, [cues]);

  return useMemo(() => new Map([...cues].map(([sessionId, cue]) => [sessionId, cue.revision])), [cues]);
}
