/** @file Fill missing inspector PR titles lazily without changing workflow evidence. */
import {useEffect, useState} from 'react';
import {Schema} from 'effect';
import {CursorSchema, type Session} from '../contracts';
import type {PrStackFacts} from './pr-stack-order';

const StackFactsSchema = Schema.Struct({
  baseRefName: Schema.NullOr(Schema.String),
  headRefName: Schema.NullOr(Schema.String),
  isCrossRepository: Schema.NullOr(Schema.Boolean),
  mergedAt: Schema.NullOr(Schema.String)
});

const ResultSchema = Schema.Struct({
  workspaceId: Schema.String,
  sessionId: Schema.String,
  lastEventId: CursorSchema,
  titles: Schema.Record(Schema.String, Schema.String),
  stack: Schema.Record(Schema.String, StackFactsSchema)
});
interface Titles {
  readonly scope: string;
  readonly values: Readonly<Record<string, string>>;
  readonly stack: Readonly<Record<string, PrStackFacts>>;
}

/** Overlay validated inspector facts without replacing catalogue titles. */
function applyInspectorDetails(
  session: Session,
  cached: Titles
): Session & {readonly inspectorStack: Readonly<Record<string, PrStackFacts>>} {
  return {
    ...session,
    inspectorStack: cached.stack,
    pullRequests: session.pullRequests.map((pr) => ({...pr, title: pr.title?.trim() || cached.values[pr.url] || null}))
  };
}

/** Read only the selected session's titles; for example, reject a stale workspace response. */
async function readTitles(workspaceId: string, sessionId: string, revision: number, signal: AbortSignal) {
  const response = await fetch(`/api/v1/session-pull-requests?${new URLSearchParams({sessionId})}`, {
    signal,
    cache: 'no-store'
  });
  if (!response.ok) throw new Error('Pull request titles unavailable');
  const result = Schema.decodeUnknownSync(ResultSchema)(await response.json());
  if (result.workspaceId !== workspaceId) throw new Error('Foreign workspace titles');
  if (result.sessionId !== sessionId || result.lastEventId !== revision) {
    throw new Error('Stale session pull request details');
  }
  return result;
}

/** Own timeout and cancellation; for example, the returned stop() aborts an unfinished lookup. */
function startTitleLookup(
  workspaceId: string,
  sessionId: string,
  revision: number,
  onTitles: (details: {titles: Readonly<Record<string, string>>; stack: Readonly<Record<string, PrStackFacts>>}) => void
): () => void {
  const controller = new AbortController();
  let isCurrent = true;
  const timeout = setTimeout(() => controller.abort(), 45_000);
  void readTitles(workspaceId, sessionId, revision, controller.signal)
    .then(
      (details) => {
        if (isCurrent) onTitles(details);
      },
      () => {
        /* Keep explicit unavailable labels when title enrichment fails. */
      }
    )
    .finally(() => clearTimeout(timeout));
  return () => {
    isCurrent = false;
    clearTimeout(timeout);
    controller.abort();
  };
}

/**
 * Fill missing PR names and stack facts; for example, merged PRs may lack names.
 * @param session Selected immutable source projection.
 * @param workspaceId Workspace identity used to reject mismatched responses.
 * @returns An inspector-local view with available names, preserving all source facts.
 * @example
 * const displayed = usePullRequestTitles(session, snapshot.workspaceId);
 */
export function usePullRequestTitles(
  session: Session,
  workspaceId: string
): Session & {readonly inspectorStack?: Readonly<Record<string, PrStackFacts>>} {
  const scope = JSON.stringify([
    workspaceId,
    session.sessionId,
    session.lastEventId,
    session.pullRequests.map((pr) => pr.url)
  ]);
  const [cached, setCached] = useState<Titles>({scope: '', values: {}, stack: {}});
  const hasMissing = session.pullRequests.some((pr) => !pr.title?.trim());
  useEffect(() => {
    if (session.source === 'demo') return;
    if (!hasMissing && session.pullRequests.length < 2) return;
    return startTitleLookup(workspaceId, session.sessionId, session.lastEventId, ({titles, stack}) =>
      setCached({scope, values: titles, stack})
    );
  }, [
    workspaceId,
    session.sessionId,
    session.lastEventId,
    session.source,
    hasMissing,
    scope,
    session.pullRequests.length
  ]);
  if (cached.scope !== scope) return session;
  return applyInspectorDetails(session, cached);
}
