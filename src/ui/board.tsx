/** @file Own local interaction state for the Ishiban session board. */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FocusEvent,
  type ReactElement,
  type RefObject
} from 'react';
import type {InterfaceState, Session, Snapshot} from '../contracts';
import {BoardLayout, type BoardViewState} from './board-layout';
import {filterSessions, type ActivityFilter, type Presentation} from './board-model';
import {useInterfaceState} from './interface-state';
import {useSessionUpdates} from './session-updates';

interface BoardProps {
  readonly snapshot: Snapshot;
  readonly connection: string;
}

interface BoardFocusRestorationProps {
  readonly inspectorSession: Session | null;
  readonly snapshotSessions: Snapshot['sessions'];
  readonly selectedSessionId: string | null;
  readonly presentation: Presentation;
  readonly visibleSessions: readonly Session[];
  readonly onClose: () => void;
  readonly initiatingTriggerRef: RefObject<HTMLButtonElement | null>;
  readonly boardFallbackRef: RefObject<HTMLElement | null>;
  readonly markNodesRef: RefObject<Map<string, HTMLButtonElement>>;
  readonly focusedSessionIdRef: RefObject<string | null>;
}

/** Keep filters, density, mode, and selection local to the board view. */
function useBoardViewState(initial?: InterfaceState): BoardViewState {
  const [query, setQuery] = useState('');
  const [activityFilter, setActivityFilter] = useState<ActivityFilter>('all');
  const [includeArchived, setIncludeArchived] = useState(false);
  const preferences = useInterfaceState(initial);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const onClose = useCallback((): void => setSelectedSessionId(null), []);
  return {
    query,
    activityFilter,
    includeArchived,
    density: preferences.density,
    presentation: preferences.presentation,
    saveStatus: preferences.saveStatus,
    selectedSessionId,
    onQueryChange: setQuery,
    onActivityChange: setActivityFilter,
    onArchivedChange: setIncludeArchived,
    onDensityChange: preferences.onDensityChange,
    onPresentationChange: preferences.onPresentationChange,
    onReset: () => {
      setQuery('');
      setActivityFilter('all');
      setIncludeArchived(false);
    },
    onSelect: setSelectedSessionId,
    onClose
  };
}

/** Restore session focus after moves and focus the board when a selected session vanishes. */
function useBoardFocusRestoration(props: BoardFocusRestorationProps): void {
  const {
    inspectorSession,
    snapshotSessions,
    selectedSessionId,
    presentation,
    visibleSessions,
    onClose,
    initiatingTriggerRef,
    boardFallbackRef,
    markNodesRef,
    focusedSessionIdRef
  } = props;
  useEffect(() => {
    if (selectedSessionId !== null && inspectorSession === null) {
      initiatingTriggerRef.current = null;
      focusedSessionIdRef.current = null;
      onClose();
      boardFallbackRef.current?.focus();
      return;
    }
    const focusedSessionId = focusedSessionIdRef.current;
    if (focusedSessionId === null || document.activeElement !== document.body) {
      return;
    }
    const movedMark = markNodesRef.current.get(focusedSessionId);
    if (movedMark?.isConnected === true) {
      movedMark.focus();
      return;
    }
    focusedSessionIdRef.current = null;
  }, [
    boardFallbackRef,
    focusedSessionIdRef,
    initiatingTriggerRef,
    inspectorSession,
    markNodesRef,
    onClose,
    presentation,
    selectedSessionId,
    snapshotSessions,
    visibleSessions
  ]);
}

/** Read the focused session identity without treating controls as marks. */
function focusedSessionId(target: EventTarget): string | null {
  if (!(target instanceof HTMLButtonElement)) {
    return null;
  }
  return target.getAttribute('data-session-id');
}

/**
 * Render the filtered live or demonstration session board.
 * @param props Validated snapshot and client connection state.
 * @returns An accessible repository panorama and its nonmodal session inspector.
 * @example
 * <Board snapshot={createDemoSnapshot()} connection="demo" />
 */
export function Board(props: BoardProps): ReactElement {
  const {snapshot, connection} = props;
  const viewState = useBoardViewState(snapshot.interfaceState);
  const pulseRevisions = useSessionUpdates(snapshot);
  const initiatingTriggerRef = useRef<HTMLButtonElement | null>(null);
  const boardFallbackRef = useRef<HTMLElement | null>(null);
  const markNodesRef = useRef(new Map<string, HTMLButtonElement>());
  const focusedSessionIdRef = useRef<string | null>(null);
  const visibleSessions = useMemo(
    () => filterSessions(snapshot.sessions, viewState.query, viewState.activityFilter, viewState.includeArchived),
    [snapshot.sessions, viewState.query, viewState.activityFilter, viewState.includeArchived]
  );
  const inspectorSession =
    snapshot.sessions.find((session) => session.sessionId === viewState.selectedSessionId) ?? null;

  const onSelect = (sessionId: string, trigger?: HTMLButtonElement): void => {
    if (trigger instanceof HTMLButtonElement) {
      initiatingTriggerRef.current = trigger;
    }
    viewState.onSelect(sessionId);
  };
  const onClose = (): void => {
    viewState.onClose();
    const initiatingTrigger = initiatingTriggerRef.current;
    const currentSessionMark =
      viewState.selectedSessionId === null ? undefined : markNodesRef.current.get(viewState.selectedSessionId);
    initiatingTriggerRef.current = null;
    if (initiatingTrigger?.isConnected === true) {
      initiatingTrigger.focus();
      return;
    }
    if (currentSessionMark?.isConnected === true) {
      currentSessionMark.focus();
      return;
    }
    boardFallbackRef.current?.focus();
  };
  const onMarkNode = useCallback((sessionId: string, node: HTMLButtonElement | null): void => {
    if (node === null) {
      markNodesRef.current.delete(sessionId);
      return;
    }
    markNodesRef.current.set(sessionId, node);
  }, []);
  const onFocusCapture = useCallback((event: FocusEvent<HTMLDivElement>): void => {
    focusedSessionIdRef.current = focusedSessionId(event.target);
  }, []);

  useBoardFocusRestoration({
    boardFallbackRef,
    focusedSessionIdRef,
    initiatingTriggerRef,
    inspectorSession,
    markNodesRef,
    onClose: viewState.onClose,
    presentation: viewState.presentation,
    selectedSessionId: viewState.selectedSessionId,
    snapshotSessions: snapshot.sessions,
    visibleSessions
  });

  return (
    <BoardLayout
      boardFallbackRef={boardFallbackRef}
      connection={connection}
      inspectorSession={inspectorSession}
      onClose={onClose}
      onFocusCapture={onFocusCapture}
      onMarkNode={onMarkNode}
      onSelect={onSelect}
      pulseRevisions={pulseRevisions}
      snapshot={snapshot}
      viewState={viewState}
      visibleSessions={visibleSessions}
    />
  );
}
