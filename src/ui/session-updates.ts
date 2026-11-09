/** @file Track recent committed session event revisions for visual pulses. */
import {useEffect, useMemo, useState} from 'react';
import type {Snapshot} from '../contracts';

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

/** Keep only cues that belong to sessions in the current snapshot. */
function unexpiredCues(cues: ReadonlyMap<string, PulseCue>, now: number): Map<string, PulseCue> {
  return new Map([...cues].filter(([, cue]) => cue.expiresAt > now));
}

/** Record new sessions and changed event identifiers after a committed snapshot. */
function cuesForSnapshot(
  previous: Snapshot,
  current: Snapshot,
  existing: ReadonlyMap<string, PulseCue>
): Map<string, PulseCue> {
  const previousSessions = new Map(previous.sessions.map((session) => [session.sessionId, session]));
  const now = Date.now();
  const cues = unexpiredCues(existing, now);
  for (const session of current.sessions) {
    const previousSession = previousSessions.get(session.sessionId);
    if (previousSession === undefined || previousSession.lastEventId !== session.lastEventId) {
      cues.set(session.sessionId, {revision: session.lastEventId, expiresAt: now + PULSE_LIFETIME_MS});
    }
  }
  return cues;
}

/**
 * Return active event revisions, excluding initial, workspace, and metadata-only snapshots.
 * @param snapshot The latest immutable snapshot received from the client.
 * @returns Session IDs mapped to event revisions whose 900 ms cue is still active.
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
