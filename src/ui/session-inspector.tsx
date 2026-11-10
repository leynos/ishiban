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

const WEB_PROTOCOLS = new Set(['http:', 'https:']);

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
    return WEB_PROTOCOLS.has(new URL(value).protocol);
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
            <PullRequestRow key={pullRequest.url} pullRequest={pullRequest} />
          ))}
        </ul>
      )}
    </section>
  );
}

/** Render one safe PR link with its status; for example, show a fallback for a blank title. */
function PullRequestRow({pullRequest}: {readonly pullRequest: Session['pullRequests'][number]}): ReactElement {
  const hasWebUrl = isWebUrl(pullRequest.url);
  const fallback = hasWebUrl ? 'Open pull request' : 'Pull request URL unavailable';
  const title = pullRequest.title?.trim() || fallback;
  return (
    <li>
      {hasWebUrl ? (
        <a className="link link-hover" href={pullRequest.url} rel="noreferrer" target="_blank">
          {title}
        </a>
      ) : (
        <span>{title}</span>
      )}
      <PullRequestNumber url={pullRequest.url} />
      <small>{pullRequest.status.replaceAll('-', ' ')}</small>
    </li>
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

/** Keep transport diagnostics beside activity rather than turn-error evidence. */
function ActivityValue({session}: {readonly session: Session}): ReactElement {
  const activity = activityOf(session.state);
  const label = activity === 'waiting' ? `${activity} (blocked)` : activity;
  return (
    <>
      {label}
      {session.activityNotice ? (
        <p className="text-base-content/70" role="status">
          {session.activityNotice}
        </p>
      ) : null}
    </>
  );
}

/** Render the selected session's current facts; for example, show unknown activity explicitly. */
function SessionFacts({
  session,
  currentGeneration
}: {
  readonly session: Session;
  readonly currentGeneration: number;
}): ReactElement {
  const repository = session.repoFullName ?? REPOSITORY_UNAVAILABLE;
  const stage = STAGE_LABELS[session.stage];
  const activeTurnSummary =
    session.activeTurns.length === 0
      ? 'None supplied'
      : session.activeTurns.map((turn) => `${turn.userTurnId} (${turn.state})`).join(', ');
  const activeTurnCount = session.activeTurnCount ?? session.activeTurns.length;
  const isActiveTurnPreview = session.activeTurnsTruncated ?? false;
  return (
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
      <dd>
        <ActivityValue session={session} />
      </dd>
      <dt>Evidence</dt>
      <dd>{evidenceLabel(session, currentGeneration)}</dd>
      <dt>Source</dt>
      <dd>
        {session.source} · {session.freshness}
      </dd>
      <dt>Last known turn</dt>
      <dd>{latestTurnLabel(session)}</dd>
      <dt>Active turns</dt>
      <dd>
        {isActiveTurnPreview ? (
          <p>
            Showing {session.activeTurns.length} of {activeTurnCount} active turns.
          </p>
        ) : null}
        {activeTurnSummary}
      </dd>
      <dt>Observed</dt>
      <dd>{observedAtLabel(session.lastObservedAt)}</dd>
    </dl>
  );
}

/**
 * Render session provenance, workflow reasoning, runtime evidence, and PR metadata.
 * @param props Selected backend session and the snapshot generation for comparison.
 * @returns A named complementary panel with a keyboard-reachable close control.
 */
export function SessionInspector(props: SessionInspectorProps): ReactElement {
  const {currentGeneration, onClose} = props;
  const session = usePullRequestTitles(props.session, props.workspaceId);
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
      <SessionFacts session={session} currentGeneration={currentGeneration} />
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
