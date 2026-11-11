/** @file Fill missing inspector PR titles lazily without changing workflow evidence. */
import {useEffect, useState} from 'react';
import {Schema} from 'effect';
import type {Session} from '../contracts';

const ResultSchema = Schema.Struct({
  workspaceId: Schema.String,
  sessionId: Schema.String,
  titles: Schema.Record(Schema.String, Schema.String)
});
interface Titles {
  readonly scope: string;
  readonly values: Readonly<Record<string, string>>;
}

/** Read only the selected session's titles; for example, reject a stale workspace response. */
async function readTitles(workspaceId: string, sessionId: string, signal: AbortSignal) {
  const response = await fetch(`/api/v1/session-pull-requests?${new URLSearchParams({sessionId})}`, {
    signal,
    cache: 'no-store'
  });
  if (!response.ok) throw new Error('Pull request titles unavailable');
  const result = Schema.decodeUnknownSync(ResultSchema)(await response.json());
  if (result.workspaceId !== workspaceId) throw new Error('Foreign workspace titles');
  if (result.sessionId !== sessionId) throw new Error('Foreign session titles');
  return result.titles;
}

/** Own timeout and cancellation; for example, the returned stop() aborts an unfinished lookup. */
function startTitleLookup(
  workspaceId: string,
  session: Session,
  onTitles: (values: Readonly<Record<string, string>>) => void
): () => void {
  const controller = new AbortController();
  let isCurrent = true;
  const timeout = setTimeout(() => controller.abort(), 45_000);
  void readTitles(workspaceId, session.sessionId, controller.signal)
    .then(
      (values) => {
        if (isCurrent) onTitles(values);
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
 * Fill only missing PR names; for example, merged PRs may have no catalogue title.
 * @param session Selected immutable source projection.
 * @param workspaceId Workspace identity used to reject mismatched responses.
 * @returns An inspector-local view with available names, preserving all source facts.
 * @example
 * const displayed = usePullRequestTitles(session, snapshot.workspaceId);
 */
export function usePullRequestTitles(session: Session, workspaceId: string): Session {
  const scope = `${workspaceId}:${session.sessionId}`;
  const [cached, setCached] = useState<Titles>({scope: '', values: {}});
  const hasMissing = session.pullRequests.some((pr) => !pr.title?.trim());
  const urls = session.pullRequests.map((pr) => pr.url).join('\n');
  useEffect(() => {
    if (session.source === 'demo' || !hasMissing) return;
    return startTitleLookup(workspaceId, session, (values) => setCached({scope, values}));
  }, [workspaceId, session.sessionId, session.source, hasMissing, urls, scope]);
  if (cached.scope !== scope) return session;
  return {
    ...session,
    pullRequests: session.pullRequests.map((pr) => ({...pr, title: pr.title?.trim() || cached.values[pr.url] || null}))
  };
}
