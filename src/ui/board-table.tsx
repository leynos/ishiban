/** @file Render repository stage cells and the larger session-list mode. */
import type {ReactElement} from 'react';
import type {Session} from '../contracts';
import {
  activityOf,
  createBanks,
  countStage,
  evidenceLabel,
  REPOSITORY_UNAVAILABLE,
  STAGE_GUIDANCE,
  STAGE_LABELS,
  WORKFLOW_STAGES,
  type Presentation,
  type RepositorySessions,
  type WorkflowStage
} from './board-model';

const COMPACT_STAGE_LABELS: Record<WorkflowStage, string> = {
  planning: 'Plan',
  ready: 'Ready',
  building: 'Build',
  refine: 'Refine',
  merged: 'Merged',
  closed: 'Closed',
  unclassified: 'Other'
};

/** Shared selection contract for table, list, and workflow-exception marks. */
export interface SessionSelectionProps {
  readonly currentGeneration: number;
  readonly selectedSessionId: string | null;
  readonly pulseRevisions: ReadonlyMap<string, number>;
  readonly onSelect: (sessionId: string, trigger?: HTMLButtonElement) => void;
  readonly onMarkNode: (sessionId: string, node: HTMLButtonElement | null) => void;
}

interface RepositoryTableProps extends SessionSelectionProps {
  readonly repositories: readonly RepositorySessions[];
}

type SessionListProps = SessionSelectionProps & {readonly sessions: readonly Session[]};
type SessionListItemProps = SessionSelectionProps & {readonly session: Session};

interface BoardBanksProps extends RepositoryTableProps {
  readonly presentation: Presentation;
}

interface SessionCondition {
  readonly isBlocked: boolean;
  readonly hasLastTurnFailure: boolean;
  readonly label: string;
  readonly glyph: string | null;
}

/** Describe only explicit waiting activity and a supplied failed turn. */
function conditionOf(session: Session): SessionCondition {
  const isBlocked = session.state === 'waiting';
  const hasLastTurnFailure = session.latestTurn?.state === 'failed';
  const labels: string[] = [];
  if (isBlocked) {
    labels.push('blocked');
  }
  if (hasLastTurnFailure) {
    labels.push('last known turn failed');
  }
  let glyph: string | null = null;
  if (hasLastTurnFailure) {
    glyph = '!';
  } else if (isBlocked) {
    glyph = '⌛';
  }
  return {isBlocked, hasLastTurnFailure, label: labels.join('; '), glyph};
}

/** Compose the session's concise accessible name without inferring activity. */
function sessionLabel(repository: string, session: Session, currentGeneration: number): string {
  const condition = conditionOf(session);
  const activity = activityOf(session.state);
  const provenance = evidenceLabel(session, currentGeneration);
  return `${repository}: ${session.title}; ${STAGE_LABELS[session.stage]}; ${activity}${condition.label.length === 0 ? '' : `; ${condition.label}`}; ${provenance}`;
}

/** Render the title and filtered count for one explicit workflow stage. */
function StageHeading({stage, count}: {readonly stage: WorkflowStage; readonly count: number}): ReactElement {
  return (
    <th className="stage-heading" data-stage-count={count} scope="col">
      <span className="stage-label-wide">{STAGE_LABELS[stage]}</span>
      <span aria-hidden="true" className="stage-label-compact">
        {COMPACT_STAGE_LABELS[stage]}
      </span>
      <small>{STAGE_GUIDANCE[stage]}</small>
      <b>
        {count}
        <span className="sr-only"> sessions</span>
      </b>
    </th>
  );
}

/** Render one keyed, aria-hidden pulse overlay only for a recent event. */
function UpdatePulse({revision}: {readonly revision: number | undefined}): ReactElement | null {
  return revision === undefined ? null : (
    <span
      aria-hidden="true"
      className="session-update-pulse"
      data-session-update-pulse={revision}
      key={revision}
      role="presentation"
    />
  );
}

/** Render a keyboard-operable session mark with stage and evidence context. */
function SessionMark({
  session,
  repository,
  currentGeneration,
  selected,
  pulseRevision,
  onSelect,
  onMarkNode
}: {
  readonly session: Session;
  readonly repository: string;
  readonly currentGeneration: number;
  readonly selected: boolean;
  readonly pulseRevision: number | undefined;
  readonly onSelect: (sessionId: string, trigger?: HTMLButtonElement) => void;
  readonly onMarkNode: (sessionId: string, node: HTMLButtonElement | null) => void;
}): ReactElement {
  const activity = activityOf(session.state);
  const provenance = evidenceLabel(session, currentGeneration);
  const condition = conditionOf(session);
  const label = sessionLabel(repository, session, currentGeneration);
  return (
    <button
      aria-controls={selected ? 'session-inspector' : undefined}
      aria-expanded={selected}
      aria-label={label}
      aria-pressed={selected}
      className={`session-mark activity-${activity}`}
      data-blocked={condition.isBlocked || undefined}
      data-last-turn-failed={condition.hasLastTurnFailure || undefined}
      data-session-id={session.sessionId}
      data-stage={session.stage}
      data-update-revision={pulseRevision}
      onClick={(event) => onSelect(session.sessionId, event.currentTarget)}
      ref={(node) => onMarkNode(session.sessionId, node)}
      title={label}
      type="button"
    >
      <span aria-hidden="true">{activitySymbol(activity)}</span>
      {condition.glyph === null ? null : (
        <span aria-hidden="true" className="session-mark__condition">
          {condition.glyph}
        </span>
      )}
      <small aria-hidden="true">{evidenceSymbol(provenance)}</small>
      <UpdatePulse revision={pulseRevision} />
    </button>
  );
}

/** Return the compact glyph for a normalized runtime activity. */
function activitySymbol(activity: ReturnType<typeof activityOf>): string {
  switch (activity) {
    case 'running': {
      return '↗';
    }
    case 'waiting': {
      return '!';
    }
    case 'pending': {
      return '◷';
    }
    case 'idle': {
      return '·';
    }
    case 'unknown': {
      return '?';
    }
  }
}

/** Return a compact evidence glyph; the button label carries its full meaning. */
function evidenceSymbol(provenance: string): string {
  if (provenance === 'Metadata only') {
    return 'M';
  }
  if (provenance.startsWith('Carried forward')) {
    return '↶';
  }
  if (provenance.startsWith('Durable evidence')) {
    return '●';
  }
  return '○';
}

/** Render one stage cell and inert placeholders completing five-wide rows. */
function StageCell({
  repository,
  stage,
  currentGeneration,
  selectedSessionId,
  pulseRevisions,
  onSelect,
  onMarkNode
}: {
  readonly repository: RepositorySessions;
  readonly stage: WorkflowStage;
  readonly currentGeneration: number;
  readonly selectedSessionId: string | null;
  readonly pulseRevisions: ReadonlyMap<string, number>;
  readonly onSelect: (sessionId: string, trigger?: HTMLButtonElement) => void;
  readonly onMarkNode: (sessionId: string, node: HTMLButtonElement | null) => void;
}): ReactElement {
  const matchingSessions = repository.sessions.filter((session) => session.stage === stage);
  const rowSlots = Math.max(5, Math.ceil(matchingSessions.length / 5) * 5);
  const emptySlots = Array.from({length: rowSlots - matchingSessions.length}, (_, index) => (
    <span aria-hidden="true" className="session-mark session-mark--empty" key={`empty-${stage}-${index}`} />
  ));
  return (
    <td className="stage-cell" data-repository-stage-count={matchingSessions.length} data-stage={stage}>
      <fieldset className="session-mark-grid">
        <legend className="sr-only">{STAGE_LABELS[stage]} sessions</legend>
        {matchingSessions.map((session) => (
          <SessionMark
            currentGeneration={currentGeneration}
            key={session.sessionId}
            onMarkNode={onMarkNode}
            onSelect={onSelect}
            pulseRevision={pulseRevisions.get(session.sessionId)}
            repository={repository.name}
            selected={selectedSessionId === session.sessionId}
            session={session}
          />
        ))}
        {emptySlots}
      </fieldset>
    </td>
  );
}

/** Render a semantic repository table for one panorama or matrix bank. */
function RepositoryTable({
  repositories,
  currentGeneration,
  selectedSessionId,
  pulseRevisions,
  onSelect,
  onMarkNode
}: RepositoryTableProps): ReactElement {
  const bankSessions = repositories.flatMap((repository) => repository.sessions);
  return (
    <table aria-label="Repository sessions by workflow stage" className="repository-table">
      <thead>
        <tr>
          <th className="repository-heading" scope="col">
            Repository
          </th>
          {WORKFLOW_STAGES.map((stage) => (
            <StageHeading count={countStage(bankSessions, stage)} key={stage} stage={stage} />
          ))}
        </tr>
      </thead>
      <tbody>
        {repositories.map((repository) => (
          <tr data-repository-row={repository.name} key={repository.name}>
            <th className="repository-name" scope="row">
              <span className="repository-label" title={repository.name}>
                <span className="repository-title">{repository.name.split('/').at(-1)}</span>
                <small>
                  {repository.sessions.length}
                  <span className="sr-only"> sessions</span>
                </small>
              </span>
            </th>
            {WORKFLOW_STAGES.map((stage) => (
              <StageCell
                currentGeneration={currentGeneration}
                key={stage}
                onMarkNode={onMarkNode}
                onSelect={onSelect}
                pulseRevisions={pulseRevisions}
                repository={repository}
                selectedSessionId={selectedSessionId}
                stage={stage}
              />
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * Render a wide table with five-stage marks and separate unclassified and closed columns.
 * @param props Repository groups and local selection state for the board.
 * @returns A semantic repository and workflow stage table.
 */
export function BoardBanks(props: BoardBanksProps): ReactElement {
  const {repositories, currentGeneration, selectedSessionId, presentation, pulseRevisions, onSelect, onMarkNode} =
    props;
  const banks = createBanks(repositories, presentation);
  return (
    <div className="board-banks" data-bank-count={banks.length}>
      {banks.map((bank, index) => (
        <div className="board-bank" data-bank={index + 1} key={`bank-${index + 1}`}>
          <RepositoryTable
            currentGeneration={currentGeneration}
            onMarkNode={onMarkNode}
            onSelect={onSelect}
            pulseRevisions={pulseRevisions}
            repositories={bank}
            selectedSessionId={selectedSessionId}
          />
        </div>
      ))}
    </div>
  );
}

/** Render one session in the larger list presentation. */
function SessionListItem({
  session,
  currentGeneration,
  selectedSessionId,
  pulseRevisions,
  onSelect,
  onMarkNode
}: SessionListItemProps): ReactElement {
  const repository = session.repoFullName ?? REPOSITORY_UNAVAILABLE;
  const activity = activityOf(session.state);
  const evidence = evidenceLabel(session, currentGeneration);
  const condition = conditionOf(session);
  const label = sessionLabel(repository, session, currentGeneration);
  const pulseRevision = pulseRevisions.get(session.sessionId);
  const classes = [
    'session-list-item',
    condition.hasLastTurnFailure ? 'session-list-item--failed' : null,
    condition.isBlocked ? 'session-list-item--blocked' : null
  ].filter((value) => value !== null);
  return (
    <li>
      <button
        aria-controls={selectedSessionId === session.sessionId ? 'session-inspector' : undefined}
        aria-expanded={selectedSessionId === session.sessionId}
        aria-label={label}
        aria-pressed={selectedSessionId === session.sessionId}
        className={classes.join(' ')}
        data-blocked={condition.isBlocked || undefined}
        data-last-turn-failed={condition.hasLastTurnFailure || undefined}
        data-session-id={session.sessionId}
        data-stage={session.stage}
        data-update-revision={pulseRevision}
        onClick={(event) => onSelect(session.sessionId, event.currentTarget)}
        ref={(node) => onMarkNode(session.sessionId, node)}
        type="button"
      >
        <span className="session-list-item__title">{session.title}</span>
        <span>
          {repository} · {STAGE_LABELS[session.stage]}
        </span>
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
  const {sessions, currentGeneration, selectedSessionId, pulseRevisions, onSelect, onMarkNode} = props;
  return (
    <ul className="session-list">
      {sessions.map((session) => (
        <SessionListItem
          currentGeneration={currentGeneration}
          key={session.sessionId}
          onMarkNode={onMarkNode}
          onSelect={onSelect}
          pulseRevisions={pulseRevisions}
          selectedSessionId={selectedSessionId}
          session={session}
        />
      ))}
    </ul>
  );
}
