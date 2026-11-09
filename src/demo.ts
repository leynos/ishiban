/** @file Create deterministic, visibly synthetic sessions for board demonstrations. */
import type {Session, Snapshot} from './contracts';

const SAMPLE_ACTIVITY = ['idle', 'running', 'waiting', 'pending', 'unknown'] as const;
const DEMO_STAGE_CYCLE: readonly Session['stage'][] = [
  'ready',
  'building',
  'refine',
  'merged',
  'closed',
  'unclassified',
  'planning'
];
const WRAPPING_REPOSITORIES = new Map<number, {readonly stage: Session['stage']; readonly count: number}>([
  [0, {stage: 'planning', count: 6}],
  [1, {stage: 'building', count: 10}],
  [2, {stage: 'refine', count: 13}]
]);

const STAGE_REASONS: Record<Session['stage'], string> = {
  planning: 'Demo classification: no pull request is associated.',
  ready: 'Demo classification: one Plan-prefixed pull request is open.',
  building: 'Demo classification: one non-plan pull request is draft.',
  refine: 'Demo classification: one non-plan pull request is ready for review.',
  merged: 'Demo classification: the associated pull request is merged.',
  closed: 'Demo classification: the associated pull request is closed and unmerged.',
  unclassified: 'Demo classification: source metadata is intentionally incomplete.'
};

/** Build stage-specific synthetic pull-request metadata with a distinct title. */
function demoPullRequests(
  repository: string,
  sessionTitle: string,
  ordinal: number,
  stage: Session['stage']
): Session['pullRequests'] {
  if (stage === 'planning' || stage === 'unclassified') {
    return [];
  }
  const title = stage === 'ready' ? `Plan: ${sessionTitle}` : sessionTitle;
  const statusByStage: Partial<Record<Session['stage'], string>> = {
    ready: 'open',
    building: 'draft',
    refine: 'ready-for-review',
    merged: 'merged',
    closed: 'closed'
  };
  const status = statusByStage[stage];
  if (status === undefined) {
    return [];
  }
  return [
    {
      url: `https://example.invalid/${repository}/pull/${ordinal + 1}`,
      title,
      status
    }
  ];
}

/** Create one complete synthetic session without inventing durable turn evidence. */
function demoSession(repositoryOrdinal: number, taskOrdinal: number, stage: Session['stage']): Session {
  const repository = `demo/repository-${String(repositoryOrdinal + 1).padStart(3, '0')}`;
  const sessionTitle = `Synthetic ${stage} task ${String(taskOrdinal + 1).padStart(2, '0')} for ${repository}`;
  const activity = SAMPLE_ACTIVITY[(repositoryOrdinal + taskOrdinal) % SAMPLE_ACTIVITY.length] ?? 'unknown';
  return {
    sessionId: `demo-session-${String(repositoryOrdinal + 1).padStart(3, '0')}-${String(taskOrdinal + 1).padStart(2, '0')}`,
    machineId: `demo-machine-${String((repositoryOrdinal % 4) + 1).padStart(2, '0')}`,
    title: sessionTitle,
    archived: false,
    removed: false,
    state: activity,
    source: 'demo',
    freshness: 'illustrative',
    repoFullName: repository,
    branchName: `demo/${String(taskOrdinal + 1).padStart(2, '0')}-${stage}`,
    stage,
    stageReason: STAGE_REASONS[stage],
    pullRequests: demoPullRequests(repository, sessionTitle, taskOrdinal, stage),
    latestTurn: null,
    activeTurns: [],
    lastEvidenceGeneration: null,
    lastMetadataGeneration: 1,
    lastObservedAt: null,
    lastEventId: repositoryOrdinal * 20 + taskOrdinal + 1
  };
}

/**
 * Create a labelled 120-repository snapshot with 6, 10, and 13 mark samples.
 * @returns A deterministic synthetic snapshot with no fabricated durable turns.
 */
export function createDemoSnapshot(): Snapshot {
  const sessions: Session[] = [];
  for (let repositoryOrdinal = 0; repositoryOrdinal < 120; repositoryOrdinal += 1) {
    const wrappingSample = WRAPPING_REPOSITORIES.get(repositoryOrdinal);
    const sampleCount = wrappingSample?.count ?? 8;
    const sampleStage = wrappingSample?.stage;
    for (let taskOrdinal = 0; taskOrdinal < sampleCount; taskOrdinal += 1) {
      const stage =
        sampleStage ?? DEMO_STAGE_CYCLE[(repositoryOrdinal + taskOrdinal) % DEMO_STAGE_CYCLE.length] ?? 'unclassified';
      sessions.push(demoSession(repositoryOrdinal, taskOrdinal, stage));
    }
  }
  return {
    version: 1,
    workspaceId: 'leynos',
    cursor: sessions.length,
    collector: {
      state: 'demo',
      generation: 1,
      lastError: null,
      lastReceivedAt: null
    },
    sessions
  };
}
