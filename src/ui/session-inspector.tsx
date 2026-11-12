/** @file Render selected session evidence in the board's nonmodal dock. */
import type {ReactElement} from 'react';
import type {Session} from '../contracts';
import {AgentDetails} from './agent-details';
import {usePullRequestTitles} from './pull-request-titles';
import {selectStackTop, type PrStackFacts} from './pr-stack-order';
import {activityOf, evidenceLabel, REPOSITORY_UNAVAILABLE, STAGE_LABELS} from './board-model';
import {resolveLodyLinkTarget} from './lody-link';

interface SessionInspectorProps {
  readonly session: Session;
  readonly activitySession?: Session;
  readonly recencyIncomplete?: boolean;
  readonly recencyBudgetLimited?: boolean;
  readonly currentGeneration: number;
  readonly onClose: () => void;
  readonly workspaceId: string;
  readonly workspaceSlug?: string | undefined;
}

const WEB_PROTOCOLS = new Set(['http:', 'https:']);
const OBSERVED_AT_FORMATTER = new Intl.DateTimeFormat('en-GB', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'UTC'
});

/** Link real sessions only; for example, an unknown slug uses Lody's native URI. */
function SessionLink(props: SessionInspectorProps): ReactElement {
  const target = resolveLodyLinkTarget(props);
  if (target.kind === 'synthetic') return <p>Synthetic demo session</p>;
  if (target.kind === 'unavailable') {
    return <p>Lody link unavailable for this session identifier.</p>;
  }
  return (
    <p>
      <a className="link link-hover" href={target.href} target="_blank" rel="noreferrer">
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

/** Link a heading only when its text is the actual PR title. */
function canLinkPrTitle(title: string | undefined, href: string | undefined): boolean {
  return Boolean(title) && href !== undefined && isWebUrl(href);
}

/** Choose a PR before checking titles, so late titles cannot replace its identity. */
function InspectorTitle({
  session,
  stack
}: {
  readonly session: Session;
  readonly stack: Readonly<Record<string, PrStackFacts>>;
}): ReactElement {
  const primary = selectStackTop(session.pullRequests, stack);
  const prTitle = primary?.title?.trim();
  const title = prTitle || session.title;
  const href = primary?.url;
  const canLink = canLinkPrTitle(prTitle, href);
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
  if (timestamp === null) return 'Not observed';
  const date = new Date(timestamp);
  if (!Number.isFinite(date.getTime())) return 'Timestamp unavailable';
  return OBSERVED_AT_FORMATTER.format(date);
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
  activitySession,
  currentGeneration
}: {
  readonly session: Session;
  readonly activitySession: Session;
  readonly currentGeneration: number;
}): ReactElement {
  const repository = session.repoFullName ?? REPOSITORY_UNAVAILABLE;
  const stage = STAGE_LABELS[session.stage];
  const activeTurnSummary =
    activitySession.activeTurns.length === 0
      ? 'None supplied'
      : activitySession.activeTurns.map((turn) => `${turn.userTurnId} (${turn.state})`).join(', ');
  const activeTurnCount = activitySession.activeTurnCount ?? activitySession.activeTurns.length;
  const isActiveTurnPreview = activitySession.activeTurnsTruncated ?? false;
  return (
    <dl className="inspector-facts">
      {activitySession.sessionId === session.sessionId ? null : (
        <>
          <dt>Selected tab</dt>
          <dd>{activitySession.title}</dd>
        </>
      )}
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
        <ActivityValue session={activitySession} />
      </dd>
      <dt>Evidence</dt>
      <dd>{evidenceLabel(activitySession, currentGeneration)}</dd>
      <dt>Source</dt>
      <dd>
        {activitySession.source} · {activitySession.freshness}
      </dd>
      <dt>Last known turn</dt>
      <dd>{latestTurnLabel(activitySession)}</dd>
      <dt>Active turns</dt>
      <dd>
        {isActiveTurnPreview ? (
          <p>
            Showing {activitySession.activeTurns.length} of {activeTurnCount} active turns.
          </p>
        ) : null}
        {activeTurnSummary}
      </dd>
      <dt>Observed</dt>
      <dd>{observedAtLabel(activitySession.lastObservedAt)}</dd>
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
  const activitySession = props.activitySession ?? props.session;
  const recencyNotice = props.recencyBudgetLimited
    ? 'This family cannot fit within the visible tab lookup budget. Its selected tab is provisional.'
    : "Tab recency is pending or unavailable. This family's selected tab is provisional.";
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
      <InspectorTitle session={session} stack={session.inspectorStack ?? {}} />
      <SessionLink {...props} />
      <p className="session-inspector__description" id="inspector-description">
        {session.stageReason}
      </p>
      {props.recencyIncomplete ? <p role="status">{recencyNotice}</p> : null}
      <SessionFacts session={session} activitySession={activitySession} currentGeneration={currentGeneration} />
      <AgentDetails
        key={activitySession.sessionId}
        workspaceId={props.workspaceId}
        sessionId={activitySession.sessionId}
        isDemo={activitySession.source === 'demo'}
      />
      <TurnError session={activitySession} />
      <PullRequestDetails session={session} />
    </aside>
  );
}
