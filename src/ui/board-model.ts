/** @file Hold pure filters and labels for the Ishiban board projection. */
import type {Session} from '../contracts';

export type WorkflowStage = Session['stage'];
export type Activity = 'idle' | 'pending' | 'running' | 'waiting' | 'unknown';
export type ActivityFilter = 'all' | Activity;
export type Density = 'overview' | 'compact' | 'balanced' | 'roomy' | 'comfortable';
export type Presentation = 'panorama' | 'matrix' | 'list';

export interface RepositorySessions {
  readonly name: string;
  readonly sessions: readonly Session[];
}

export const STAGES: readonly WorkflowStage[] = [
  'planning',
  'ready',
  'building',
  'refine',
  'merged',
  'unclassified',
  'closed'
];

export const WORKFLOW_STAGES: readonly WorkflowStage[] = STAGES.slice(0, 5);

export const STAGE_LABELS: Record<WorkflowStage, string> = {
  planning: 'Planning',
  ready: 'Ready',
  building: 'Building',
  refine: 'Refine',
  merged: 'Merged',
  unclassified: 'Unclassified',
  closed: 'Closed'
};

export const STAGE_GUIDANCE: Record<WorkflowStage, string> = {
  planning: 'No pull request is associated',
  ready: 'Plan pull request is open',
  building: 'Implementation pull request is draft',
  refine: 'Pull request is ready for review',
  merged: 'Pull request is merged',
  unclassified: 'Workflow stage is not known',
  closed: 'Pull request is closed and unmerged'
};

export const ACTIVITIES: readonly Activity[] = ['running', 'waiting', 'pending', 'idle', 'unknown'];
export const DENSITIES: readonly Density[] = ['overview', 'compact', 'balanced', 'roomy', 'comfortable'];
export const DENSITY_LABELS: Record<Density, string> = {
  overview: 'Overview',
  compact: 'Compact',
  balanced: 'Balanced',
  roomy: 'Roomy',
  comfortable: 'Comfortable'
};
export const REPOSITORY_UNAVAILABLE = 'Repository not supplied';

/**
 * Convert a runtime activity string without changing its workflow stage.
 * @param state Upstream Lody activity state.
 * @returns A supported activity label for filtering and presentation.
 */
export function activityOf(state: string): Activity {
  switch (state.toLowerCase()) {
    case 'running': {
      return 'running';
    }
    case 'waiting': {
      return 'waiting';
    }
    case 'pending': {
      return 'pending';
    }
    case 'idle': {
      return 'idle';
    }
    default: {
      return 'unknown';
    }
  }
}

/**
 * Accept only known activity filters from the native select control.
 * @param value Native select value.
 * @returns A supported activity filter, or all activity.
 */
export function activityFilterOf(value: string): ActivityFilter {
  if (value === 'all') {
    return 'all';
  }
  return ACTIVITIES.find((activity) => activity === value) ?? 'all';
}

/**
 * Accept only a named mark density from the native select control.
 * @param value Native select value.
 * @returns One exact density option, or Overview for unknown values.
 */
export function densityOf(value: string): Density {
  return DENSITIES.find((density) => density === value) ?? 'overview';
}

/**
 * Describe durable evidence separately from collector connection health.
 * @param session Session projection from the API.
 * @param currentGeneration Current collector generation.
 * @returns An explicit evidence provenance label.
 */
export function evidenceLabel(session: Session, currentGeneration: number): string {
  if (session.source === 'demo') {
    return 'Synthetic demo record';
  }
  if (session.source === 'metadata' && session.lastEvidenceGeneration !== null) {
    return `Carried forward from generation ${session.lastEvidenceGeneration}; metadata refresh`;
  }
  if (session.source === 'metadata') {
    return 'Metadata only';
  }
  if (session.lastEvidenceGeneration === null) {
    return 'No durable evidence recorded';
  }
  if (session.lastEvidenceGeneration !== currentGeneration) {
    return `Carried forward from generation ${session.lastEvidenceGeneration}`;
  }
  return `Durable evidence in generation ${session.lastEvidenceGeneration}; ${session.freshness}`;
}

/** Search only the session's supplied repository, title, and branch values. */
function matchesSearch(session: Session, searchTerm: string): boolean {
  if (searchTerm.length === 0) {
    return true;
  }
  const searchableText = [session.repoFullName, session.title, session.branchName]
    .filter((value): value is string => value !== null)
    .join(' ')
    .toLocaleLowerCase('en-GB');
  return searchableText.includes(searchTerm);
}

/** Check one session against search, activity, and archive controls. */
function sessionMatchesFilters(
  session: Session,
  searchTerm: string,
  activityFilter: ActivityFilter,
  includeArchived: boolean
): boolean {
  if (!includeArchived && session.archived) {
    return false;
  }
  if (!includeArchived && session.removed) {
    return false;
  }
  if (activityFilter !== 'all' && activityOf(session.state) !== activityFilter) {
    return false;
  }
  return matchesSearch(session, searchTerm);
}

/**
 * Keep sessions matching search, activity, and archive controls.
 * @param sessions Session projections to filter.
 * @param query Search text for repository, title, and branch.
 * @param activityFilter Selected exact activity state.
 * @param includeArchived Whether archived and removed sessions are visible.
 * @returns A new array of sessions matching all selected controls.
 */
export function filterSessions(
  sessions: readonly Session[],
  query: string,
  activityFilter: ActivityFilter,
  includeArchived: boolean
): Session[] {
  const searchTerm = query.trim().toLocaleLowerCase('en-GB');
  return sessions.filter((session) => sessionMatchesFilters(session, searchTerm, activityFilter, includeArchived));
}

/**
 * Group sessions by repository without deriving an association from the title.
 * @param sessions Visible session projections.
 * @returns Sorted repository groups, including a group for missing associations.
 */
export function groupByRepository(sessions: readonly Session[]): RepositorySessions[] {
  const groups = new Map<string, Session[]>();
  for (const session of sessions) {
    const name = session.repoFullName ?? REPOSITORY_UNAVAILABLE;
    const current = groups.get(name);
    if (current === undefined) {
      groups.set(name, [session]);
    } else {
      current.push(session);
    }
  }
  return [...groups.entries()]
    .map(([name, groupedSessions]) => ({name, sessions: groupedSessions}))
    .toSorted((left, right) => left.name.localeCompare(right.name));
}

/**
 * Divide panorama rows into banks, or keep matrix mode continuous.
 * @param repositories Sorted repository rows.
 * @param presentation Current board presentation.
 * @returns Repository banks to render in order.
 */
export function createBanks(
  repositories: readonly RepositorySessions[],
  presentation: Presentation
): RepositorySessions[][] {
  if (presentation === 'matrix') {
    return [[...repositories]];
  }
  const banks: RepositorySessions[][] = [];
  for (let offset = 0; offset < repositories.length; offset += 30) {
    banks.push(repositories.slice(offset, offset + 30));
  }
  return banks.length === 0 ? [[]] : banks;
}

/**
 * Count sessions assigned to the supplied backend workflow stage.
 * @param sessions Visible sessions.
 * @param stage Explicit workflow stage.
 * @returns Number of sessions assigned to that stage.
 */
export function countStage(sessions: readonly Session[], stage: WorkflowStage): number {
  return sessions.filter((session) => session.stage === stage).length;
}
