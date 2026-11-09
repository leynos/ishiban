/** @file Render selected session evidence in the board's nonmodal dock. */
import type {ReactElement} from 'react';
import type {Session} from '../contracts';
import {activityOf, evidenceLabel, REPOSITORY_UNAVAILABLE, STAGE_LABELS} from './board-model';

interface SessionInspectorProps {
  readonly session: Session;
  readonly currentGeneration: number;
  readonly onClose: () => void;
}

/** Allow pull-request links only when they use HTTP or HTTPS. */
function isWebUrl(value: string): boolean {
  try {
    const protocol = new URL(value).protocol;
    return protocol === 'https:' || protocol === 'http:';
  } catch {
    return false;
  }
}

/** Render PR title, status, and a safe external link when supplied. */
function PullRequestDetails({session}: {readonly session: Session}): ReactElement {
  return (
    <section aria-labelledby="pull-request-heading" className="inspector-section">
      <h3 id="pull-request-heading">Pull requests</h3>
      {session.pullRequests.length === 0 ? (
        <p>None supplied.</p>
      ) : (
        <ul>
          {session.pullRequests.map((pullRequest) => (
            <li key={pullRequest.url}>
              {isWebUrl(pullRequest.url) ? (
                <a href={pullRequest.url} rel="noreferrer" target="_blank">
                  {pullRequest.title ?? pullRequest.url}
                </a>
              ) : (
                <span>{pullRequest.title ?? 'Pull request URL unavailable'}</span>
              )}
              <small>{pullRequest.status.replaceAll('-', ' ')}</small>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Render a timestamp in an explicit, stable locale and timezone. */
function observedAtLabel(timestamp: number | null): string {
  if (timestamp === null) {
    return 'Not observed';
  }
  return new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC'
  }).format(timestamp);
}

/** Describe only the supplied latest turn, retaining its identity. */
function latestTurnLabel(session: Session): string {
  if (session.latestTurn === null) {
    return 'No turn evidence supplied';
  }
  const failedContext = session.latestTurn.state === 'failed' ? ' (last known turn outcome)' : '';
  return `${session.latestTurn.state}${failedContext} · ${session.latestTurn.userTurnId}`;
}

/**
 * Render session provenance, workflow reasoning, runtime evidence, and PR metadata.
 * @param props Selected backend session and the snapshot generation for comparison.
 * @returns A named complementary panel with a keyboard-reachable close control.
 */
export function SessionInspector(props: SessionInspectorProps): ReactElement {
  const {session, currentGeneration, onClose} = props;
  const repository = session.repoFullName ?? REPOSITORY_UNAVAILABLE;
  const stage = STAGE_LABELS[session.stage];
  const latestTurn = latestTurnLabel(session);
  const activity = activityOf(session.state);
  const activityLabel = activity === 'waiting' ? `${activity} (blocked)` : activity;
  const activeTurnSummary =
    session.activeTurns.length === 0
      ? 'None supplied'
      : session.activeTurns.map((turn) => `${turn.userTurnId} (${turn.state})`).join(', ');
  return (
    <aside aria-labelledby="session-inspector-heading" className="session-inspector" id="session-inspector">
      <header className="session-inspector__header">
        <h2 className="eyebrow" id="session-inspector-heading">
          Session inspector
        </h2>
        <button
          aria-label="Close session inspector"
          className="btn btn-ghost btn-sm inspector-close"
          onClick={onClose}
          type="button"
        >
          Close
        </button>
      </header>
      <h3 className="session-inspector__title">{session.title}</h3>
      <p className="session-inspector__description" id="inspector-description">
        {session.stageReason}
      </p>
      <dl className="inspector-facts">
        <dt>Repository</dt>
        <dd>{repository}</dd>
        <dt>Branch</dt>
        <dd>{session.branchName ?? 'Not supplied'}</dd>
        <dt>Workflow stage</dt>
        <dd>{stage}</dd>
        <dt>Stage reason</dt>
        <dd>{session.stageReason}</dd>
        <dt>Activity</dt>
        <dd>{activityLabel}</dd>
        <dt>Evidence</dt>
        <dd>{evidenceLabel(session, currentGeneration)}</dd>
        <dt>Source</dt>
        <dd>
          {session.source} · {session.freshness}
        </dd>
        <dt>Last known turn</dt>
        <dd>{latestTurn}</dd>
        <dt>Active turns</dt>
        <dd>{activeTurnSummary}</dd>
        <dt>Observed</dt>
        <dd>{observedAtLabel(session.lastObservedAt)}</dd>
      </dl>
      <PullRequestDetails session={session} />
    </aside>
  );
}
