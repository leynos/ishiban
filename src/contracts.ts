/** @file Validated public session and collector projections shared by the UI. */
import {Schema} from 'effect';

export const CursorSchema = Schema.Number.check(
  Schema.isInt(),
  Schema.isGreaterThanOrEqualTo(0),
  Schema.isLessThanOrEqualTo(Number.MAX_SAFE_INTEGER)
);

export const TurnSchema = Schema.Struct({
  userTurnId: Schema.String,
  state: Schema.String,
  error: Schema.optional(Schema.NullOr(Schema.String))
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
  activitySource: Schema.optional(Schema.Literal('lazy')),
  activityNotice: Schema.optional(Schema.String),
  repoFullName: Schema.NullOr(Schema.String),
  branchName: Schema.NullOr(Schema.String),
  stage: Schema.Literals(['planning', 'ready', 'building', 'refine', 'merged', 'closed', 'unclassified']),
  stageReason: Schema.String,
  pullRequests: Schema.Array(PullRequestSchema),
  latestTurn: Schema.NullOr(TurnSchema),
  activeTurns: Schema.Array(TurnSchema),
  activeTurnCount: Schema.optional(Schema.Natural),
  activeTurnsTruncated: Schema.optional(Schema.Boolean),
  activeTurnsRevision: Schema.optional(Schema.String),
  lastActivityEventId: Schema.optional(Schema.Number),
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
export const InterfaceStateSchema = Schema.Struct({
  density: Schema.Literals(['overview', 'compact', 'balanced', 'roomy', 'comfortable']),
  presentation: Schema.Literals(['panorama', 'matrix', 'list'])
});
export type InterfaceState = typeof InterfaceStateSchema.Type;
export const SnapshotSchema = Schema.Struct({
  version: Schema.Literal(1),
  workspaceId: Schema.String,
  workspaceSlug: Schema.optional(Schema.String),
  interfaceState: Schema.optional(InterfaceStateSchema),
  cursor: CursorSchema,
  collector: CollectorSchema,
  sessions: Schema.Array(SessionSchema)
});
export type Session = typeof SessionSchema.Type;
export type Snapshot = typeof SnapshotSchema.Type;
export type Collector = typeof CollectorSchema.Type;
export const SessionActivitySuccessFrameSchema = Schema.Struct({
  workspaceId: Schema.String,
  sessionId: Schema.String,
  session: Schema.NullOr(SessionSchema)
});
export const SessionActivityOversizeFrameSchema = Schema.Struct({
  workspaceId: Schema.String,
  sessionId: Schema.String,
  outcome: Schema.Literal('response_too_large')
});
export const SessionActivityFrameSchema = Schema.Union([
  SessionActivitySuccessFrameSchema,
  SessionActivityOversizeFrameSchema
]);
export type SessionActivityFrame = typeof SessionActivityFrameSchema.Type;
export const SessionActivityResponseSchema = Schema.Struct({
  workspaceId: Schema.String,
  session: Schema.NullOr(SessionSchema)
});
export type SessionActivityResponse = typeof SessionActivityResponseSchema.Type;
