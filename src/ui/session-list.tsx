/** @file Render the roomy session-list presentation with native selection buttons. */
import type {ReactElement} from 'react';
import type {SessionFamily} from '../session-families';
import {REPOSITORY_UNAVAILABLE, STAGE_LABELS} from './board-model';
import {markFacts, type SessionSelectionProps, UpdatePulse} from './session-mark';
import {threadNavigationHandlers} from './thread-navigation';

type SessionListProps = SessionSelectionProps & {readonly sessions: readonly SessionFamily[]};
type SessionListItemProps = SessionSelectionProps & {readonly session: SessionFamily};

/** Render one session in the larger list presentation. */
function SessionListItem({
  session,
  currentGeneration,
  selectedSessionId,
  pulseRevisions,
  onSelect,
  onMarkNode,
  canOpenThread,
  onOpenThread
}: SessionListItemProps): ReactElement {
  const repository = session.context.repoFullName ?? REPOSITORY_UNAVAILABLE;
  const facts = markFacts(repository, session, currentGeneration);
  const {activity, evidence, condition, label} = facts;
  const pulseRevision = pulseRevisions.get(session.rootId);
  const classes = [
    'session-list-item',
    condition.hasLastTurnFailure ? 'session-list-item--failed' : null,
    condition.isBlocked ? 'session-list-item--blocked' : null
  ].filter((value) => value !== null);
  return (
    <li>
      <button
        aria-controls={selectedSessionId === session.rootId ? 'session-inspector' : undefined}
        aria-expanded={selectedSessionId === session.rootId}
        aria-label={label}
        aria-pressed={selectedSessionId === session.rootId}
        className={classes.join(' ')}
        data-blocked={condition.isBlocked || undefined}
        data-last-turn-failed={condition.hasLastTurnFailure || undefined}
        data-family-id={session.rootId}
        data-session-id={session.activity.sessionId}
        data-stage={session.context.stage}
        data-update-revision={pulseRevision}
        {...threadNavigationHandlers(session, canOpenThread, onOpenThread)}
        onClick={(event) => {
          if (event.button !== 0) return;
          onSelect(session.rootId, event.currentTarget);
        }}
        ref={(node) => onMarkNode(session.rootId, node)}
        type="button"
      >
        <span className="session-list-item__title">{session.context.title}</span>
        <span>{`${repository} · ${STAGE_LABELS[session.context.stage]}`}</span>
        <small>
          {activity}
          {condition.label.length === 0 ? '' : ` · ${condition.label}`} · {evidence}
        </small>
        <UpdatePulse revision={pulseRevision} />
      </button>
    </li>
  );
}

/**
 * Render a roomy list presentation with the same native selection buttons.
 * @param props Filtered sessions and local selection state for the board.
 * @returns A list of keyboard-operable session inspector triggers.
 */
export function SessionList(props: SessionListProps): ReactElement {
  const {
    sessions,
    currentGeneration,
    selectedSessionId,
    pulseRevisions,
    onSelect,
    onMarkNode,
    canOpenThread,
    onOpenThread
  } = props;
  return (
    <ul className="session-list">
      {sessions.map((session) => (
        <SessionListItem
          canOpenThread={canOpenThread}
          currentGeneration={currentGeneration}
          key={session.rootId}
          onMarkNode={onMarkNode}
          onOpenThread={onOpenThread}
          onSelect={onSelect}
          pulseRevisions={pulseRevisions}
          selectedSessionId={selectedSessionId}
          session={session}
        />
      ))}
    </ul>
  );
}
