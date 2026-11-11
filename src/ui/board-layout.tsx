/** @file Compose the board's health, controls, panorama, and inspector. */
import {useMemo, type FocusEvent, type ReactElement, type RefObject} from 'react';
import type {Snapshot} from '../contracts';
import type {SessionFamily} from '../session-families';
import {BoardControls} from './board-controls';
import {BoardBanks, SessionList} from './board-table';
import {groupByRepository, type ActivityFilter, type Density, type Presentation, WORKFLOW_STAGES} from './board-model';
import {SessionInspector} from './session-inspector';
import {WorkflowExceptions} from './workflow-exceptions';

/** Controlled board values shared by the layout and its parent. */
export interface BoardViewState {
  readonly query: string;
  readonly activityFilter: ActivityFilter;
  readonly includeArchived: boolean;
  readonly density: Density;
  readonly presentation: Presentation;
  readonly selectedSessionId: string | null;
  readonly saveStatus: string;
  readonly onQueryChange: (value: string) => void;
  readonly onActivityChange: (value: ActivityFilter) => void;
  readonly onArchivedChange: (value: boolean) => void;
  readonly onDensityChange: (density: Density) => void;
  readonly onPresentationChange: (value: Presentation) => void;
  readonly onReset: () => void;
  readonly onSelect: (sessionId: string) => void;
  readonly onClose: () => void;
}

/** Present collector and transport health as separate, visible facts. */
function SourceHealth({
  snapshot,
  connection
}: {
  readonly snapshot: Snapshot;
  readonly connection: string;
}): ReactElement {
  const receivedAt = snapshot.collector.lastReceivedAt ?? 'No event received';
  return (
    <section aria-label="Source health" className="source-health" role="status">
      <span>
        <b>Connection</b> {connection.trim() || 'unknown'}
      </span>
      <span>
        <b>Source health</b> {snapshot.collector.state}
      </span>
      <span>
        <b>Generation</b> {snapshot.collector.generation}
      </span>
      <span>
        <b>Last received</b> {receivedAt}
      </span>
      {snapshot.collector.lastError === null ? null : (
        <span className="source-health__error">
          <b>Latest source error</b> {snapshot.collector.lastError}
        </span>
      )}
    </section>
  );
}

/** Render the selected table, list, or empty state. */
function BoardDisplay({
  currentGeneration,
  onSelect,
  onMarkNode,
  pulseRevisions,
  presentation,
  selectedSessionId,
  visibleSessions
}: {
  readonly currentGeneration: number;
  readonly onSelect: (sessionId: string, trigger?: HTMLButtonElement) => void;
  readonly onMarkNode: (sessionId: string, node: HTMLButtonElement | null) => void;
  readonly pulseRevisions: ReadonlyMap<string, number>;
  readonly presentation: Presentation;
  readonly selectedSessionId: string | null;
  readonly visibleSessions: readonly SessionFamily[];
}): ReactElement {
  if (visibleSessions.length === 0) {
    return <p className="empty-result">No sessions match these filters.</p>;
  }
  if (presentation === 'list') {
    return (
      <SessionList
        currentGeneration={currentGeneration}
        onMarkNode={onMarkNode}
        onSelect={onSelect}
        pulseRevisions={pulseRevisions}
        selectedSessionId={selectedSessionId}
        sessions={visibleSessions}
      />
    );
  }
  const workflowSessions = visibleSessions.filter((session) => WORKFLOW_STAGES.includes(session.context.stage));
  const workflowRepositories = groupByRepository(workflowSessions);
  return (
    <>
      {workflowSessions.length === 0 ? (
        <p className="empty-result">No sessions have a classified workflow stage.</p>
      ) : (
        <BoardBanks
          currentGeneration={currentGeneration}
          onMarkNode={onMarkNode}
          onSelect={onSelect}
          pulseRevisions={pulseRevisions}
          presentation={presentation}
          repositories={workflowRepositories}
          selectedSessionId={selectedSessionId}
        />
      )}
      <WorkflowExceptions
        currentGeneration={currentGeneration}
        onMarkNode={onMarkNode}
        onSelect={onSelect}
        pulseRevisions={pulseRevisions}
        selectedSessionId={selectedSessionId}
        sessions={visibleSessions}
      />
    </>
  );
}

interface BoardLayoutProps {
  readonly snapshot: Snapshot;
  readonly totalFamilies: number;
  readonly connection: string;
  readonly viewState: BoardViewState;
  readonly visibleSessions: readonly SessionFamily[];
  readonly inspectorSession: SessionFamily | null;
  readonly pulseRevisions: ReadonlyMap<string, number>;
  readonly onMarkNode: (sessionId: string, node: HTMLButtonElement | null) => void;
  readonly onFocusCapture: (event: FocusEvent<HTMLDivElement>) => void;
  readonly onClose: () => void;
  readonly boardFallbackRef: RefObject<HTMLElement | null>;
  readonly onSelect: (sessionId: string, trigger?: HTMLButtonElement) => void;
}

/**
 * Render the board controls, panorama, health, and currently selected inspector.
 * @param props Snapshot data and local board interaction state.
 * @returns The complete nonmodal board layout.
 * @example
 * <BoardLayout {...boardLayoutProps} />
 */
export function BoardLayout(props: BoardLayoutProps): ReactElement {
  const {
    snapshot,
    connection,
    viewState,
    visibleSessions,
    inspectorSession,
    pulseRevisions,
    onMarkNode,
    onFocusCapture,
    onClose,
    boardFallbackRef,
    onSelect
  } = props;
  const repositories = useMemo(() => groupByRepository(visibleSessions), [visibleSessions]);
  const isDemo = snapshot.collector.state === 'demo';
  return (
    <div
      className="ishiban-board"
      data-density={viewState.density}
      data-inspector-open={inspectorSession !== null}
      data-presentation={viewState.presentation}
      onFocusCapture={onFocusCapture}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && inspectorSession !== null) {
          event.preventDefault();
          onClose();
        }
      }}
    >
      <a className="skip-link" href="#programme-board">
        Skip to the programme board
      </a>
      <header className="board-topbar">
        <a aria-label="Ishiban programme board" className="board-brand" href="#programme-board">
          Ishiban <small>Engineering observatory</small>
        </a>
        <p className="board-workspace">Workspace / {snapshot.workspaceId}</p>
      </header>
      <main className="board-main" id="programme-board" ref={boardFallbackRef} tabIndex={-1}>
        <header className="board-heading">
          <div>
            <p className="eyebrow">Programme / session observation</p>
            <h1>The programme, at a glance.</h1>
            <p>{props.totalFamilies} sessions · workflow stages are supplied by the collector.</p>
          </div>
          {isDemo ? <span className="demo-label">Demo data · synthetic records</span> : null}
        </header>
        <SourceHealth connection={connection} snapshot={snapshot} />
        <BoardControls
          activityFilter={viewState.activityFilter}
          density={viewState.density}
          includeArchived={viewState.includeArchived}
          onActivityChange={viewState.onActivityChange}
          onArchivedChange={viewState.onArchivedChange}
          onDensityChange={viewState.onDensityChange}
          onPresentationChange={viewState.onPresentationChange}
          onQueryChange={viewState.onQueryChange}
          onReset={viewState.onReset}
          presentation={viewState.presentation}
          query={viewState.query}
        />
        <div aria-live="polite" className="board-summary">
          <span>
            <b>{visibleSessions.length}</b> visible sessions
          </span>
          <span>
            <b>{repositories.length}</b> repositories
          </span>
          <span>Each stage has five marks across; rows expand with the work.</span>
          <span>Activity: ↗ running · ! waiting · ◷ pending · · idle · ? unknown</span>
          <span>Outcome: oxide failed last turn · oxide and amber stripes blocked waiting</span>
          <span>Evidence: M metadata only · ↶ carried forward · ● durable · ○ none recorded</span>
        </div>
        <section aria-label="Session panorama" className="board-scroll">
          <BoardDisplay
            currentGeneration={snapshot.collector.generation}
            onMarkNode={onMarkNode}
            onSelect={onSelect}
            pulseRevisions={pulseRevisions}
            presentation={viewState.presentation}
            selectedSessionId={viewState.selectedSessionId}
            visibleSessions={visibleSessions}
          />
        </section>
        <footer className="board-footer">
          <span>
            {isDemo ? 'Demo data' : 'Read-only observation'} · {visibleSessions.length} / {props.totalFamilies} sessions
          </span>
          <span>Select a mark to inspect its source evidence.</span>
          <span>A cookie saves interface state: density and presentation.</span>
          <span role="status">{viewState.saveStatus}</span>
        </footer>
      </main>
      {inspectorSession === null ? null : (
        <SessionInspector
          workspaceId={snapshot.workspaceId}
          workspaceSlug={snapshot.workspaceSlug}
          currentGeneration={snapshot.collector.generation}
          onClose={onClose}
          session={inspectorSession.context}
          activitySession={inspectorSession.activity}
          recencyIncomplete={inspectorSession.recencyIncomplete}
          recencyBudgetLimited={inspectorSession.recencyBudgetLimited}
        />
      )}
    </div>
  );
}
