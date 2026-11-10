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
import type {InterfaceState, Snapshot} from '../contracts';
import {groupSessions, type SessionFamily} from '../session-families';
import {useSessionRecency} from '../session-recency';
import {BoardLayout, type BoardViewState} from './board-layout';
import {filterSessions, type ActivityFilter, type Presentation} from './board-model';
import {useInterfaceState} from './interface-state';
import {useSessionUpdates} from './session-updates';

interface BoardProps {
  readonly snapshot: Snapshot;
  readonly connection: string;
}

interface BoardFocusRestorationProps {
  readonly inspectorSession: SessionFamily | null;
  readonly snapshotSessions: Snapshot['sessions'];
  readonly selectedSessionId: string | null;
  readonly presentation: Presentation;
  readonly visibleSessions: readonly SessionFamily[];
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
    const movedMark = markForSelectedFamily(visibleSessions, focusedSessionId, markNodesRef.current);
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
  return target.getAttribute('data-family-id');
}

/** Map meaningful raw updates to their stable family selection identity. */
function familyPulseRevisions(
  families: readonly SessionFamily[],
  rawRevisions: ReadonlyMap<string, number>
): ReadonlyMap<string, number> {
  const cues = new Map<string, number>();
  for (const family of families) {
    let revision = 0;
    for (const member of family.members) {
      revision = Math.max(revision, rawRevisions.get(member.sessionId) ?? 0);
    }
    if (revision > 0) cues.set(family.rootId, revision);
  }
  return cues;
}

/** Preserve selection during discovery; for example, a selected child now resolves to its parent family. */
function selectedFamily(families: readonly SessionFamily[], selectedId: string | null): SessionFamily | null {
  if (selectedId === null) return null;
  return (
    families.find(
      (family) => family.rootId === selectedId || family.members.some((member) => member.sessionId === selectedId)
    ) ?? null
  );
}

/** Follow changed containment; for example, an old child ID locates the new root mark. */
function markForSelectedFamily(
  families: readonly SessionFamily[],
  selectedId: string,
  markNodes: ReadonlyMap<string, HTMLButtonElement>
): HTMLButtonElement | undefined {
  const rootId = selectedFamily(families, selectedId)?.rootId ?? selectedId;
  return markNodes.get(rootId);
}

/** Keep focus on the task; for example, replace a detached child trigger with its current root mark. */
function focusAfterInspectorClose(
  initiatingTrigger: HTMLButtonElement | null,
  selectedFamilyId: string | null,
  markNodes: ReadonlyMap<string, HTMLButtonElement>,
  boardFallback: HTMLElement | null
): void {
  const currentMark = selectedFamilyId === null ? undefined : markNodes.get(selectedFamilyId);
  if (initiatingTrigger?.isConnected === true) {
    initiatingTrigger.focus();
    return;
  }
  if (currentMark?.isConnected === true) {
    currentMark.focus();
    return;
  }
  boardFallback?.focus();
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
  const recency = useSessionRecency(snapshot);
  const families = useMemo(
    () => groupSessions(snapshot.sessions, recency.facts, recency.limitedRoots),
    [snapshot.sessions, recency]
  );
  const familyPulses = useMemo(() => familyPulseRevisions(families, pulseRevisions), [families, pulseRevisions]);
  const initiatingTriggerRef = useRef<HTMLButtonElement | null>(null);
  const boardFallbackRef = useRef<HTMLElement | null>(null);
  const markNodesRef = useRef(new Map<string, HTMLButtonElement>());
  const focusedSessionIdRef = useRef<string | null>(null);
  const visibleSessions = useMemo(
    () => filterSessions(families, viewState.query, viewState.activityFilter, viewState.includeArchived),
    [families, viewState.query, viewState.activityFilter, viewState.includeArchived]
  );
  const inspectorSession = selectedFamily(families, viewState.selectedSessionId);
  const selectedFamilyId = inspectorSession?.rootId ?? viewState.selectedSessionId;

  const onSelect = (sessionId: string, trigger?: HTMLButtonElement): void => {
    if (trigger instanceof HTMLButtonElement) {
      initiatingTriggerRef.current = trigger;
    }
    viewState.onSelect(sessionId);
  };
  const onClose = (): void => {
    viewState.onClose();
    const initiatingTrigger = initiatingTriggerRef.current;
    initiatingTriggerRef.current = null;
    focusAfterInspectorClose(initiatingTrigger, selectedFamilyId, markNodesRef.current, boardFallbackRef.current);
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
    selectedSessionId: selectedFamilyId,
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
      pulseRevisions={familyPulses}
      snapshot={snapshot}
      totalFamilies={families.length}
      viewState={{...viewState, selectedSessionId: selectedFamilyId}}
      visibleSessions={visibleSessions}
    />
  );
}
