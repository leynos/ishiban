/** @file Validated public session and collector projections shared by the UI. */
import {Schema} from 'effect';

export const CursorSchema = Schema.Number.check(
  Schema.isInt(),
  Schema.isGreaterThanOrEqualTo(0),
  Schema.isLessThanOrEqualTo(Number.MAX_SAFE_INTEGER)
);

export const TurnSchema = Schema.Struct({
  userTurnId: Schema.String,
  state: Schema.String
});
export const PullRequestSchema = Schema.Struct({
  url: Schema.String,
  title: Schema.NullOr(Schema.String),
  status: Schema.String
});
export const SessionSchema = Schema.Struct({
  sessionId: Schema.String,
  machineId: Schema.String,
  title: Schema.String,
  archived: Schema.Boolean,
  removed: Schema.Boolean,
  state: Schema.Literals(['idle', 'pending', 'running', 'waiting', 'unknown']),
  source: Schema.Literals(['metadata', 'persisted', 'demo']),
  freshness: Schema.Literals(['synced', 'unavailable', 'illustrative']),
  repoFullName: Schema.NullOr(Schema.String),
  branchName: Schema.NullOr(Schema.String),
  stage: Schema.Literals(['planning', 'ready', 'building', 'refine', 'merged', 'closed', 'unclassified']),
  stageReason: Schema.String,
  pullRequests: Schema.Array(PullRequestSchema),
  latestTurn: Schema.NullOr(TurnSchema),
  activeTurns: Schema.Array(TurnSchema),
  lastEvidenceGeneration: Schema.NullOr(Schema.Number),
  lastMetadataGeneration: Schema.NullOr(Schema.Number),
  lastObservedAt: Schema.NullOr(Schema.Number),
  lastEventId: Schema.Number
});
export const CollectorSchema = Schema.Struct({
  state: Schema.String,
  generation: Schema.Number,
  lastError: Schema.NullOr(Schema.String),
  lastReceivedAt: Schema.NullOr(Schema.String)
});
export const SnapshotSchema = Schema.Struct({
  version: Schema.Literal(1),
  workspaceId: Schema.String,
  cursor: CursorSchema,
  collector: CollectorSchema,
  sessions: Schema.Array(SessionSchema)
});
export type Session = typeof SessionSchema.Type;
export type Snapshot = typeof SnapshotSchema.Type;
export type Collector = typeof CollectorSchema.Type;
