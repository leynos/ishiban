/** @file Render a filterable, accessible Ishiban session board. */
import * as Dialog from '@radix-ui/react-dialog';
import {useMemo, useRef, useState, type ReactElement, type RefObject} from 'react';
import type {Session, Snapshot} from '../contracts';
import {BoardControls} from './board-controls';
import {BoardBanks, SessionList} from './board-table';
import {
  filterSessions,
  groupByRepository,
  type ActivityFilter,
  type Density,
  type Presentation,
  WORKFLOW_STAGES
} from './board-model';
import {SessionInspector} from './session-inspector';
import {WorkflowExceptions} from './workflow-exceptions';

interface BoardProps {
  readonly snapshot: Snapshot;
  readonly connection: string;
}

interface BoardViewState {
  readonly query: string;
  readonly activityFilter: ActivityFilter;
  readonly includeArchived: boolean;
  readonly density: Density;
  readonly presentation: Presentation;
  readonly selectedSessionId: string | null;
  readonly onQueryChange: (value: string) => void;
  readonly onActivityChange: (value: ActivityFilter) => void;
  readonly onArchivedChange: (value: boolean) => void;
  readonly onDensityChange: () => void;
  readonly onPresentationChange: (value: Presentation) => void;
  readonly onReset: () => void;
  readonly onSelect: (sessionId: string) => void;
  readonly onClose: () => void;
}

/** Keep filters, density, mode, and selection local to the board view. */
function useBoardViewState(): BoardViewState {
  const [query, setQuery] = useState('');
  const [activityFilter, setActivityFilter] = useState<ActivityFilter>('all');
  const [includeArchived, setIncludeArchived] = useState(false);
  const [density, setDensity] = useState<Density>('overview');
  const [presentation, setPresentation] = useState<Presentation>('panorama');
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const clearSelection = (): void => setSelectedSessionId(null);
  const onQueryChange = (value: string): void => {
    setQuery(value);
    clearSelection();
  };
  const onActivityChange = (value: ActivityFilter): void => {
    setActivityFilter(value);
    clearSelection();
  };
  const onArchivedChange = (value: boolean): void => {
    setIncludeArchived(value);
    clearSelection();
  };
  const onReset = (): void => {
    setQuery('');
    setActivityFilter('all');
    setIncludeArchived(false);
    clearSelection();
  };
  return {
    query,
    activityFilter,
    includeArchived,
    density,
    presentation,
    selectedSessionId,
    onQueryChange,
    onActivityChange,
    onArchivedChange,
    onDensityChange: () => setDensity((current) => (current === 'overview' ? 'comfortable' : 'overview')),
    onPresentationChange: setPresentation,
    onReset,
    onSelect: setSelectedSessionId,
    onClose: clearSelection
  };
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

/** Render the board controls, panorama, health, and currently selected inspector. */
function BoardContent({
  snapshot,
  connection,
  viewState,
  visibleSessions,
  inspectorSession,
  onSelect,
  onRestoreFocus,
  boardFallbackRef
}: {
  readonly snapshot: Snapshot;
  readonly connection: string;
  readonly viewState: BoardViewState;
  readonly visibleSessions: readonly Session[];
  readonly inspectorSession: Session | null;
  readonly onSelect: (sessionId: string, trigger?: HTMLButtonElement) => void;
  readonly onRestoreFocus: () => void;
  readonly boardFallbackRef: RefObject<HTMLElement | null>;
}): ReactElement {
  const repositories = useMemo(() => groupByRepository(visibleSessions), [visibleSessions]);
  const isDemo = snapshot.collector.state === 'demo';
  return (
    <div className="ishiban-board" data-density={viewState.density} data-presentation={viewState.presentation}>
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
            <p>{snapshot.sessions.length} sessions · workflow stages are supplied by the collector.</p>
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
          <span>Evidence: M metadata only · ↶ carried forward · ● durable · ○ none recorded</span>
        </div>
        <section aria-label="Session panorama" className="board-scroll">
          <BoardDisplay
            currentGeneration={snapshot.collector.generation}
            onSelect={onSelect}
            presentation={viewState.presentation}
            selectedSessionId={viewState.selectedSessionId}
            visibleSessions={visibleSessions}
          />
        </section>
        <footer className="board-footer">
          <span>
            {isDemo ? 'Demo data' : 'Read-only observation'} · {visibleSessions.length} / {snapshot.sessions.length}{' '}
            sessions
          </span>
          <span>Select a mark to inspect its source evidence.</span>
        </footer>
      </main>
      {inspectorSession === null ? null : (
        <SessionInspector
          currentGeneration={snapshot.collector.generation}
          onRestoreFocus={onRestoreFocus}
          session={inspectorSession}
        />
      )}
    </div>
  );
}

/** Render the selected table, list, or empty state. */
function BoardDisplay({
  currentGeneration,
  onSelect,
  presentation,
  selectedSessionId,
  visibleSessions
}: {
  readonly currentGeneration: number;
  readonly onSelect: (sessionId: string, trigger?: HTMLButtonElement) => void;
  readonly presentation: Presentation;
  readonly selectedSessionId: string | null;
  readonly visibleSessions: readonly Session[];
}): ReactElement {
  if (visibleSessions.length === 0) {
    return <p className="empty-result">No sessions match these filters.</p>;
  }
  if (presentation === 'list') {
    return (
      <SessionList
        currentGeneration={currentGeneration}
        onSelect={onSelect}
        selectedSessionId={selectedSessionId}
        sessions={visibleSessions}
      />
    );
  }
  const workflowSessions = visibleSessions.filter((session) => WORKFLOW_STAGES.includes(session.stage));
  const workflowRepositories = groupByRepository(workflowSessions);
  return (
    <>
      {workflowSessions.length === 0 ? (
        <p className="empty-result">No sessions have a classified workflow stage.</p>
      ) : (
        <BoardBanks
          currentGeneration={currentGeneration}
          onSelect={onSelect}
          presentation={presentation}
          repositories={workflowRepositories}
          selectedSessionId={selectedSessionId}
          visibleSessions={workflowSessions}
        />
      )}
      <WorkflowExceptions
        currentGeneration={currentGeneration}
        onSelect={onSelect}
        selectedSessionId={selectedSessionId}
        sessions={visibleSessions}
      />
    </>
  );
}

/**
 * Render the filtered live or demonstration session board.
 * @param props Validated snapshot and client connection state.
 * @returns An accessible repository panorama and its session inspector.
 * @example
 * <Board snapshot={createDemoSnapshot()} connection="demo" />
 */
export function Board(props: BoardProps): ReactElement {
  const {snapshot, connection} = props;
  const viewState = useBoardViewState();
  const initiatingTriggerRef = useRef<HTMLElement | null>(null);
  const boardFallbackRef = useRef<HTMLElement | null>(null);
  const lastSelectedSessionRef = useRef<Session | null>(null);
  const visibleSessions = useMemo(
    () => filterSessions(snapshot.sessions, viewState.query, viewState.activityFilter, viewState.includeArchived),
    [snapshot.sessions, viewState.query, viewState.activityFilter, viewState.includeArchived]
  );
  const selectedSession = visibleSessions.find((session) => session.sessionId === viewState.selectedSessionId) ?? null;
  const inspectorSession = selectedSession ?? lastSelectedSessionRef.current;
  const onSelect = (sessionId: string, trigger?: HTMLButtonElement): void => {
    if (trigger instanceof HTMLElement) {
      initiatingTriggerRef.current = trigger;
    }
    lastSelectedSessionRef.current = visibleSessions.find((session) => session.sessionId === sessionId) ?? null;
    viewState.onSelect(sessionId);
  };
  const onRestoreFocus = (): void => {
    const initiatingTrigger = initiatingTriggerRef.current;
    if (initiatingTrigger instanceof HTMLElement && initiatingTrigger.isConnected) {
      initiatingTrigger.focus();
      return;
    }
    boardFallbackRef.current?.focus();
  };
  return (
    <Dialog.Root
      open={selectedSession !== null}
      onOpenChange={(open) => {
        if (!open) {
          viewState.onClose();
        }
      }}
    >
      <BoardContent
        connection={connection}
        boardFallbackRef={boardFallbackRef}
        onRestoreFocus={onRestoreFocus}
        onSelect={onSelect}
        inspectorSession={inspectorSession}
        snapshot={snapshot}
        viewState={viewState}
        visibleSessions={visibleSessions}
      />
    </Dialog.Root>
  );
}
