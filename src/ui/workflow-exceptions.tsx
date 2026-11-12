/** @file Keep unclassified and closed sessions separate from the five workflow stages. */
import type {ReactElement} from 'react';
import type {SessionFamily} from '../session-families';
import {groupByRepository, STAGE_LABELS, type WorkflowStage} from './board-model';
import type {SessionSelectionProps} from './session-mark';
import {SessionList} from './session-list';

interface WorkflowExceptionsProps extends SessionSelectionProps {
  readonly sessions: readonly SessionFamily[];
}

/** Render the sessions assigned to one separate non-workflow group. */
function ExceptionGroup({
  stage,
  sessions,
  currentGeneration,
  selectedSessionId,
  pulseRevisions,
  onMarkNode,
  onSelect,
  canOpenThread,
  onOpenThread
}: WorkflowExceptionsProps & {readonly stage: Extract<WorkflowStage, 'unclassified' | 'closed'>}): ReactElement {
  const stageSessions = sessions.filter((session) => session.context.stage === stage);
  const groupedSessions = groupByRepository(stageSessions);
  const count = stageSessions.length;
  return (
    <section aria-labelledby={`exception-${stage}`} className="exception-group" data-exception-stage={stage}>
      <header className="exception-group__heading">
        <h2 id={`exception-${stage}`}>{STAGE_LABELS[stage]}</h2>
        <span>{count} sessions</span>
      </header>
      {groupedSessions.length === 0 ? (
        <p>No sessions in this group.</p>
      ) : (
        groupedSessions.map((repository) => (
          <section className="exception-repository" key={repository.name}>
            <h3>{repository.name}</h3>
            <SessionList
              canOpenThread={canOpenThread}
              currentGeneration={currentGeneration}
              onMarkNode={onMarkNode}
              onOpenThread={onOpenThread}
              onSelect={onSelect}
              pulseRevisions={pulseRevisions}
              selectedSessionId={selectedSessionId}
              sessions={repository.sessions}
            />
          </section>
        ))
      )}
    </section>
  );
}

/**
 * Render Unclassified and Closed groups outside the five workflow columns.
 * @param props Visible sessions and their local selection state.
 * @returns Two independent, repository-grouped session collections.
 */
export function WorkflowExceptions(props: WorkflowExceptionsProps): ReactElement {
  return (
    <section aria-label="Other workflow groups" className="workflow-exceptions">
      <ExceptionGroup {...props} stage="unclassified" />
      <ExceptionGroup {...props} stage="closed" />
    </section>
  );
}
