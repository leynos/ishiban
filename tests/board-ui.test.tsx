/** @file Verify the board's rendered workflow, evidence, and demonstration data. */
import {describe, expect, it} from 'bun:test';
import {renderToStaticMarkup} from 'react-dom/server';
import {Board} from '../src/ui/board';
import {createDemoSnapshot} from '../src/demo';
import type {Session, Snapshot} from '../src/contracts';

/** Create a complete live-shaped session for focused rendering assertions. */
function makeSession(overrides: Partial<Session> = {}): Session {
  return {
    sessionId: 'session-live-001',
    machineId: 'machine-live-001',
    title: 'Inspect release pipeline',
    archived: false,
    removed: false,
    state: 'idle',
    source: 'metadata',
    freshness: 'synced',
    repoFullName: 'leynos/ishiban',
    branchName: 'main',
    stage: 'unclassified',
    stageReason: 'No associated pull request was supplied.',
    pullRequests: [],
    latestTurn: null,
    activeTurns: [],
    lastEvidenceGeneration: null,
    lastMetadataGeneration: 4,
    lastObservedAt: 1_793_823_720_000,
    lastEventId: 11,
    ...overrides
  };
}

/** Build a compact snapshot with metadata and carried-forward evidence. */
function makeSnapshot(): Snapshot {
  return {
    version: 1,
    workspaceId: 'leynos',
    cursor: 12,
    collector: {
      state: 'unavailable',
      generation: 5,
      lastError: 'Lody observer disconnected.',
      lastReceivedAt: '2026-11-09T09:00:00Z'
    },
    sessions: [
      makeSession(),
      makeSession({
        sessionId: 'session-live-002',
        title: 'Update dependency policy',
        source: 'persisted',
        freshness: 'unavailable',
        stage: 'building',
        stageReason: 'One non-plan draft pull request is associated.',
        pullRequests: [
          {url: 'https://github.com/leynos/ishiban/pull/12', title: 'Update dependency policy', status: 'draft'}
        ],
        lastEvidenceGeneration: 3,
        lastMetadataGeneration: 5
      }),
      makeSession({
        sessionId: 'session-archived-001',
        title: 'Archived-only fixture session',
        archived: true,
        source: 'persisted',
        freshness: 'unavailable',
        stage: 'closed',
        stageReason: 'The archived fixture is excluded by default.'
      })
    ]
  };
}

/** Render a board snapshot without mounting a browser application. */
function renderBoard(snapshot: Snapshot): string {
  return renderToStaticMarkup(<Board snapshot={snapshot} connection="reconnecting" />);
}

describe('Ishiban board renderer', () => {
  it('renders five workflow stages with separate unclassified and closed groups', () => {
    const markup = renderBoard(createDemoSnapshot());
    const stageHeadings = markup.match(/class="stage-heading"/gu) ?? [];

    for (const label of ['Planning', 'Ready', 'Building', 'Refine', 'Merged', 'Unclassified', 'Closed']) {
      expect(markup).toContain(label);
    }
    expect(stageHeadings).toHaveLength(20);
  });

  it('shows source health and labels metadata-only and carried-forward evidence', () => {
    const markup = renderBoard(makeSnapshot());

    expect(markup).toContain('<b>Connection</b> reconnecting');
    expect(markup).toContain('unavailable');
    expect(markup).toContain('Lody observer disconnected.');
    expect(markup).toContain('Metadata only');
    expect(markup).toContain('Carried forward from generation 3');
  });

  it('does not invent completed activity for metadata-only sessions', () => {
    const markup = renderBoard(makeSnapshot());

    expect(markup).toContain('idle');
    expect(markup).toContain('Include archived and removed');
    expect(markup).not.toContain('Archived-only fixture session');
    expect(markup).not.toContain('Turn completed');
    expect(markup).not.toContain('Activity stream');
    expect(markup).not.toContain('last known turn failed');
  });

  it('keeps last-known turn failures separate from waiting and workflow stage', () => {
    const snapshot = makeSnapshot();
    const failedSession = makeSession({
      latestTurn: {userTurnId: 'turn-failed-001', state: 'failed'},
      stage: 'planning'
    });
    const blockedSession = makeSession({
      sessionId: 'session-blocked-001',
      title: 'Waiting on review',
      state: 'waiting',
      latestTurn: {userTurnId: 'turn-failed-002', state: 'failed'},
      stage: 'building',
      stageReason: 'The supplied pull request remains a draft.'
    });
    const markup = renderBoard({...snapshot, sessions: [failedSession, blockedSession]});

    expect(markup).toContain('last known turn failed');
    expect(markup).toContain('blocked');
    expect(markup).toContain('data-last-turn-failed="true"');
    expect(markup).toContain('data-blocked="true"');
    expect(markup).toContain('data-stage="planning"');
    expect(markup).toContain('data-stage="building"');
  });

  it('renders 120 repositories and exposes the 6, 10, and 13 mark stage totals', () => {
    const markup = renderBoard(createDemoSnapshot());
    const repositoryRows = markup.match(/data-repository-row=/gu) ?? [];

    expect(repositoryRows).toHaveLength(120);
    expect(markup).toContain('data-repository-stage-count="6" data-stage="planning"');
    expect(markup).toContain('data-repository-stage-count="10" data-stage="building"');
    expect(markup).toContain('data-repository-stage-count="13" data-stage="refine"');
  });

  it('labels the synthetic failed turn without changing its idle activity', () => {
    const demo = createDemoSnapshot();
    const first = demo.sessions[0];

    expect(first?.latestTurn).toEqual({userTurnId: 'demo-turn-001', state: 'failed'});
    const markup = renderBoard(demo);
    expect(markup).toContain('Synthetic planning task 01');
    expect(markup).toContain('idle');
    expect(markup).toContain('last known turn failed');
    expect(markup).toContain('data-stage="planning"');
  });
});
