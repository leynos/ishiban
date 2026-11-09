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
  readonly onSelect: (sessionId: string, trigger?: HTMLButtonElement) => void;
}

interface RepositoryTableProps extends SessionSelectionProps {
  readonly repositories: readonly RepositorySessions[];
  readonly visibleSessions: readonly Session[];
}

interface SessionListProps extends SessionSelectionProps {
  readonly sessions: readonly Session[];
}

interface BoardBanksProps extends RepositoryTableProps {
  readonly presentation: Presentation;
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

/** Render a keyboard-operable session mark with stage and evidence context. */
function SessionMark({
  session,
  repository,
  currentGeneration,
  selected,
  onSelect
}: {
  readonly session: Session;
  readonly repository: string;
  readonly currentGeneration: number;
  readonly selected: boolean;
  readonly onSelect: (sessionId: string, trigger?: HTMLButtonElement) => void;
}): ReactElement {
  const activity = activityOf(session.state);
  const provenance = evidenceLabel(session, currentGeneration);
  const label = `${repository}: ${session.title}; ${STAGE_LABELS[session.stage]}; ${activity}; ${provenance}`;
  return (
    <button
      aria-expanded={selected}
      aria-haspopup="dialog"
      aria-label={label}
      aria-pressed={selected}
      className={`session-mark activity-${activity}`}
      data-stage={session.stage}
      onClick={(event) => onSelect(session.sessionId, event.currentTarget)}
      title={label}
      type="button"
    >
      <span aria-hidden="true">{activitySymbol(activity)}</span>
      <small aria-hidden="true">{evidenceSymbol(provenance)}</small>
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

/** Render one stage cell, padding mark slots to complete five-wide rows. */
function StageCell({
  repository,
  stage,
  currentGeneration,
  selectedSessionId,
  onSelect
}: {
  readonly repository: RepositorySessions;
  readonly stage: WorkflowStage;
  readonly currentGeneration: number;
  readonly selectedSessionId: string | null;
  readonly onSelect: (sessionId: string, trigger?: HTMLButtonElement) => void;
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
            onSelect={onSelect}
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
  onSelect
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
                onSelect={onSelect}
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
  const {repositories, visibleSessions, currentGeneration, selectedSessionId, presentation, onSelect} = props;
  const banks = createBanks(repositories, presentation);
  return (
    <div className="board-banks">
      {banks.map((bank, index) => (
        <div className="board-bank" data-bank={index + 1} key={`bank-${index + 1}`}>
          <RepositoryTable
            currentGeneration={currentGeneration}
            onSelect={onSelect}
            repositories={bank}
            selectedSessionId={selectedSessionId}
            visibleSessions={visibleSessions}
          />
        </div>
      ))}
    </div>
  );
}

/**
 * Render a roomy list presentation with the same native selection buttons.
 * @param props Filtered sessions and local selection state for the board.
 * @returns A list of keyboard-operable session inspector triggers.
 */
export function SessionList(props: SessionListProps): ReactElement {
  const {sessions, currentGeneration, selectedSessionId, onSelect} = props;
  return (
    <ul className="session-list">
      {sessions.map((session) => {
        const repository = session.repoFullName ?? REPOSITORY_UNAVAILABLE;
        const activity = activityOf(session.state);
        const evidence = evidenceLabel(session, currentGeneration);
        const label = `${repository}: ${session.title}; ${STAGE_LABELS[session.stage]}; ${activity}; ${evidence}`;
        return (
          <li key={session.sessionId}>
            <button
              aria-expanded={selectedSessionId === session.sessionId}
              aria-haspopup="dialog"
              aria-label={label}
              aria-pressed={selectedSessionId === session.sessionId}
              className="session-list-item"
              onClick={(event) => onSelect(session.sessionId, event.currentTarget)}
              type="button"
            >
              <span className="session-list-item__title">{session.title}</span>
              <span>
                {repository} · {STAGE_LABELS[session.stage]}
              </span>
              <small>
                {activity} · {evidence}
              </small>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
