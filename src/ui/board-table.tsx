/** @file Render repository stage cells and the session-mark matrix. */
import type {ReactElement} from 'react';
import type {SessionFamily} from '../session-families';
import {
  type activityOf,
  createBanks,
  countStage,
  STAGE_GUIDANCE,
  STAGE_LABELS,
  WORKFLOW_STAGES,
  type Presentation,
  type RepositorySessions,
  type WorkflowStage
} from './board-model';
import {markFacts, type SessionSelectionProps, UpdatePulse} from './session-mark';
import {threadNavigationHandlers} from './thread-navigation';

const COMPACT_STAGE_LABELS: Record<WorkflowStage, string> = {
  planning: 'Plan',
  ready: 'Ready',
  building: 'Build',
  refine: 'Refine',
  merged: 'Merged',
  closed: 'Closed',
  unclassified: 'Other'
};

interface RepositoryTableProps extends SessionSelectionProps {
  readonly repositories: readonly RepositorySessions[];
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
  pulseRevision,
  onSelect,
  onMarkNode,
  canOpenThread,
  onOpenThread
}: {
  readonly session: SessionFamily;
  readonly repository: string;
  readonly currentGeneration: number;
  readonly selected: boolean;
  readonly pulseRevision: number | undefined;
  readonly onSelect: (sessionId: string, trigger?: HTMLButtonElement) => void;
  readonly onMarkNode: (sessionId: string, node: HTMLButtonElement | null) => void;
  readonly canOpenThread: (family: SessionFamily) => boolean;
  readonly onOpenThread: (family: SessionFamily) => boolean;
}): ReactElement {
  const {activity, evidence: provenance, condition, label} = markFacts(repository, session, currentGeneration);
  return (
    <button
      aria-controls={selected ? 'session-inspector' : undefined}
      aria-expanded={selected}
      aria-label={label}
      aria-pressed={selected}
      className={`session-mark activity-${activity}`}
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
  onMarkNode,
  canOpenThread,
  onOpenThread
}: {
  readonly repository: RepositorySessions;
  readonly stage: WorkflowStage;
  readonly currentGeneration: number;
  readonly selectedSessionId: string | null;
  readonly pulseRevisions: ReadonlyMap<string, number>;
  readonly onSelect: (sessionId: string, trigger?: HTMLButtonElement) => void;
  readonly onMarkNode: (sessionId: string, node: HTMLButtonElement | null) => void;
  readonly canOpenThread: (family: SessionFamily) => boolean;
  readonly onOpenThread: (family: SessionFamily) => boolean;
}): ReactElement {
  const matchingSessions = repository.sessions.filter((session) => session.context.stage === stage);
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
            canOpenThread={canOpenThread}
            currentGeneration={currentGeneration}
            key={session.rootId}
            onMarkNode={onMarkNode}
            onOpenThread={onOpenThread}
            onSelect={onSelect}
            pulseRevision={pulseRevisions.get(session.rootId)}
            repository={repository.name}
            selected={selectedSessionId === session.rootId}
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
  onMarkNode,
  canOpenThread,
  onOpenThread
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
                canOpenThread={canOpenThread}
                currentGeneration={currentGeneration}
                key={stage}
                onMarkNode={onMarkNode}
                onOpenThread={onOpenThread}
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
  const {
    repositories,
    currentGeneration,
    selectedSessionId,
    presentation,
    pulseRevisions,
    onSelect,
    onMarkNode,
    canOpenThread,
    onOpenThread
  } = props;
  const banks = createBanks(repositories, presentation);
  return (
    <div className="board-banks" data-bank-count={banks.length}>
      {banks.map((bank, index) => (
        <div className="board-bank" data-bank={index + 1} key={`bank-${index + 1}`}>
          <RepositoryTable
            canOpenThread={canOpenThread}
            currentGeneration={currentGeneration}
            onMarkNode={onMarkNode}
            onOpenThread={onOpenThread}
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
