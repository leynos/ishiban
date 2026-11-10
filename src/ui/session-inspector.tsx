/** @file Render selected session evidence in the board's nonmodal dock. */
import type {ReactElement} from 'react';
import type {Session} from '../contracts';
import {AgentDetails} from './agent-details';
import {usePullRequestTitles} from './pull-request-titles';
import {activityOf, evidenceLabel, REPOSITORY_UNAVAILABLE, STAGE_LABELS} from './board-model';

interface SessionInspectorProps {
  readonly session: Session;
  readonly currentGeneration: number;
  readonly onClose: () => void;
  readonly workspaceId: string;
  readonly workspaceSlug?: string | undefined;
}

/** Link real sessions only; for example, an unknown slug uses Lody's native URI. */
function SessionLink({session, workspaceId, workspaceSlug}: SessionInspectorProps): ReactElement {
  if (session.source === 'demo') return <p>Synthetic demo session</p>;
  const hasSlug = workspaceSlug !== undefined && workspaceSlug !== workspaceId;
  const hasWebRoute = hasSlug && /^[a-z0-9]+(?:-[a-z0-9]+)*$/u.test(workspaceSlug);
  const id = encodeURIComponent(session.sessionId);
  const href = hasWebRoute
    ? `https://lody.ai/${encodeURIComponent(workspaceSlug)}/sessions/${id}`
    : `lody://session/${id}?workspace=${encodeURIComponent(workspaceId)}`;
  return (
    <p>
      <a className="link link-hover" href={href} target="_blank" rel="noreferrer">
        Open in Lody
      </a>
    </p>
  );
}

/** Show the failed turn's supplied error; for example, old journals explain its absence. */
function TurnError({session}: {readonly session: Session}): ReactElement | null {
  if (session.latestTurn?.state !== 'failed') return null;
  return (
    <section className="inspector-section" aria-labelledby="session-error-heading">
      <h3 id="session-error-heading">Last turn error</h3>
      <p className="session-inspector__error">
        {session.latestTurn.error?.trim() || 'Lody did not provide error details for this turn.'}
      </p>
    </section>
  );
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

/** Prefer the first supplied PR title; for example, keep the session name below it. */
function InspectorTitle({session}: {readonly session: Session}): ReactElement {
  const primary = session.pullRequests.find((pr) => pr.title?.trim());
  const prTitle = primary?.title?.trim();
  const title = prTitle || session.title;
  const href = primary?.url;
  const canLink = href !== undefined && isWebUrl(href);
  return (
    <>
      <h3 className="session-inspector__title">
        {canLink ? (
          <a className="link link-hover" href={href} target="_blank" rel="noreferrer">
            {title}
          </a>
        ) : (
          title
        )}
      </h3>
      {prTitle ? <p className="session-inspector__subtitle">{session.title}</p> : null}
    </>
  );
}

/** Show a supplied PR number; for example, /pull/123 becomes #123. */
function PullRequestNumber({url}: {readonly url: string}): ReactElement | null {
  const number = /\/pull\/([1-9][0-9]*)\/?(?:[?#].*)?$/u.exec(url)?.[1];
  return number ? <small className="session-pr-number">#{number}</small> : null;
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
                <a className="link link-hover" href={pullRequest.url} rel="noreferrer" target="_blank">
                  {pullRequest.title ?? 'Open pull request'}
                </a>
              ) : (
                <span>{pullRequest.title ?? 'Pull request URL unavailable'}</span>
              )}
              <PullRequestNumber url={pullRequest.url} />
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
  const {currentGeneration, onClose} = props;
  const session = usePullRequestTitles(props.session, props.workspaceId);
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
      <InspectorTitle session={session} />
      <SessionLink {...props} />
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
      <AgentDetails
        key={session.sessionId}
        workspaceId={props.workspaceId}
        sessionId={session.sessionId}
        isDemo={session.source === 'demo'}
      />
      <TurnError session={session} />
      <PullRequestDetails session={session} />
    </aside>
  );
}
