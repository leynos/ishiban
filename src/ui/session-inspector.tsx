/** @file Render accessible evidence and pull-request details in a Radix dialog. */
import * as Dialog from '@radix-ui/react-dialog';
import type {ReactElement} from 'react';
import type {Session} from '../contracts';
import {activityOf, evidenceLabel, REPOSITORY_UNAVAILABLE, STAGE_LABELS} from './board-model';

interface SessionInspectorProps {
  readonly session: Session;
  readonly currentGeneration: number;
  readonly onRestoreFocus: () => void;
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

/**
 * Render session provenance, exact workflow reasoning, runtime evidence, and PR metadata.
 * @param props Selected backend session and the snapshot generation for comparison.
 * @returns A Radix modal dialog with an accessible title, description, and close controls.
 */
export function SessionInspector(props: SessionInspectorProps): ReactElement {
  const {session, currentGeneration, onRestoreFocus} = props;
  const repository = session.repoFullName ?? REPOSITORY_UNAVAILABLE;
  const stage = STAGE_LABELS[session.stage];
  const latestTurn = session.latestTurn?.state ?? 'No turn evidence supplied';
  const activeTurnSummary =
    session.activeTurns.length === 0
      ? 'None supplied'
      : session.activeTurns.map((turn) => `${turn.userTurnId} (${turn.state})`).join(', ');
  return (
    <Dialog.Portal>
      <Dialog.Overlay className="inspector-overlay" />
      <Dialog.Content
        aria-describedby="inspector-description"
        className="session-inspector"
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          onRestoreFocus();
        }}
      >
        <header className="session-inspector__header">
          <p className="eyebrow">Session inspector</p>
          <Dialog.Close aria-label="Close session inspector" className="btn btn-ghost btn-sm inspector-close">
            Close
          </Dialog.Close>
        </header>
        <Dialog.Title className="session-inspector__title">{session.title}</Dialog.Title>
        <Dialog.Description className="session-inspector__description" id="inspector-description">
          {session.stageReason}
        </Dialog.Description>
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
            {activityOf(session.state)} ({session.state})
          </dd>
          <dt>Evidence</dt>
          <dd>{evidenceLabel(session, currentGeneration)}</dd>
          <dt>Source</dt>
          <dd>
            {session.source} · {session.freshness}
          </dd>
          <dt>Last turn</dt>
          <dd>{latestTurn}</dd>
          <dt>Active turns</dt>
          <dd>{activeTurnSummary}</dd>
          <dt>Observed</dt>
          <dd>{observedAtLabel(session.lastObservedAt)}</dd>
        </dl>
        <PullRequestDetails session={session} />
        <Dialog.Close className="btn btn-primary inspector-dismiss">Close inspector</Dialog.Close>
      </Dialog.Content>
    </Dialog.Portal>
  );
}
