/**
 * @file Group related Lody sessions for presentation without changing their records.
 * This pure model owns parent-chain resolution and activity selection only; API
 * reads, board state, and transport caching belong to their existing owners.
 */
import type {Session} from './contracts';

/** One root's stable context and the family member selected to represent activity. */
export interface SessionFamily {
  readonly rootId: string;
  readonly context: Session;
  readonly activity: Session;
  readonly members: readonly Session[];
  readonly recencyIncomplete: boolean;
  readonly recencyBudgetLimited: boolean;
}

/**
 * The state of a member's history lookup; a successful empty history differs from failure.
 */
export type RecencyFact =
  | {readonly outcome: 'available'; readonly latestHistoryAt: string | null}
  | {readonly outcome: 'unavailable'};

interface ParsedTimestamp {
  readonly epochSecond: bigint;
  readonly fraction: string;
}

type RootWalkStep =
  | {readonly outcome: 'resolved'; readonly rootId: string}
  | {readonly outcome: 'next'; readonly nextId: string};

interface RootWalkState {
  readonly path: string[];
  readonly pathIndices: Map<string, number>;
}

const ISO_TIMESTAMP = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|([+-])(\d{2}):(\d{2}))$/;

/**
 * Resolve parent links into presentation families and select activity per family.
 * Context always remains the raw canonical root record. Input sessions are
 * expected to have unique session IDs; returned members and families are sorted
 * by ID so catalogue order cannot alter the result.
 *
 * While any lookup is pending or unavailable, an observed running member is
 * provisional; without one, the newest available effective recency preserves a
 * known winner. When every lookup succeeds, recency takes precedence over
 * running state. Successful empty or invalid history uses that member's creation
 * time as effective recency, while unavailable facts contribute no history time.
 *
 * @param sessions Unmodified records from one workspace catalogue.
 * @param recency Per-session history lookup outcomes; missing keys remain pending.
 * @param limitedRoots Visible families excluded from the bounded lookup budget.
 * @returns Stable families whose context and members preserve their original records.
 * @example
 * const family = groupSessions([root, child], new Map())[0];
 * family?.context === root; // true, even when activity is the running child
 */
export function groupSessions(
  sessions: readonly Session[],
  recency: ReadonlyMap<string, RecencyFact>,
  limitedRoots: ReadonlySet<string> = new Set()
): readonly SessionFamily[] {
  const orderedSessions = sessions.toSorted((left, right) => compareIds(left.sessionId, right.sessionId));
  const sessionsById = new Map(orderedSessions.map((session) => [session.sessionId, session]));
  const resolvedRoots = new Map<string, string>();
  const membersByRoot = new Map<string, Session[]>();

  for (const session of orderedSessions) {
    const rootId = resolveRootId(session.sessionId, sessionsById, resolvedRoots);
    const members = membersByRoot.get(rootId) ?? [];
    members.push(session);
    membersByRoot.set(rootId, members);
  }

  return [...membersByRoot.entries()]
    .toSorted(([leftRoot], [rightRoot]) => compareIds(leftRoot, rightRoot))
    .map(([rootId, members]) => {
      const context = sessionsById.get(rootId);
      if (context === undefined) throw new Error(`Session family root ${rootId} is missing its record.`);
      const recencyBudgetLimited = limitedRoots.has(rootId);
      const recencyIncomplete =
        recencyBudgetLimited ||
        (members.length > 1 &&
          members.some((member) => member.source !== 'demo' && recency.get(member.sessionId)?.outcome !== 'available'));
      return {
        rootId,
        context,
        activity: selectActivity(members, recency),
        members,
        recencyIncomplete,
        recencyBudgetLimited
      };
    });
}

/** Resolve one member by walking its parent graph and memoizing the result. */
function resolveRootId(
  sessionId: string,
  sessionsById: ReadonlyMap<string, Session>,
  resolvedRoots: Map<string, string>
): string {
  const walk: RootWalkState = {path: [], pathIndices: new Map()};
  let currentId = sessionId;
  let rootId: string | undefined;

  while (rootId === undefined && walk.path.length <= sessionsById.size) {
    const step = nextRootWalkStep(currentId, sessionsById, resolvedRoots, walk);
    if (step.outcome === 'resolved') rootId = step.rootId;
    else currentId = step.nextId;
  }

  // The bound is defensive; a finite functional graph must end or repeat by here.
  if (rootId === undefined) rootId = smallestId(walk.path);
  for (const memberId of walk.path) resolvedRoots.set(memberId, rootId);
  return rootId;
}

/** Classify the current parent edge and record the newly visited identity. */
function nextRootWalkStep(
  currentId: string,
  sessionsById: ReadonlyMap<string, Session>,
  resolvedRoots: ReadonlyMap<string, string>,
  walk: RootWalkState
): RootWalkStep {
  const resolvedRoot = resolvedRoots.get(currentId);
  if (resolvedRoot !== undefined) return {outcome: 'resolved', rootId: resolvedRoot};

  const cycleStart = walk.pathIndices.get(currentId);
  if (cycleStart !== undefined) return {outcome: 'resolved', rootId: smallestId(walk.path.slice(cycleStart))};

  walk.pathIndices.set(currentId, walk.path.length);
  walk.path.push(currentId);
  const parentId = parentIdOf(currentId, sessionsById);
  return parentId === null ? {outcome: 'resolved', rootId: currentId} : {outcome: 'next', nextId: parentId};
}

/** Return a linked parent only when its record is present in this catalogue. */
function parentIdOf(sessionId: string, sessionsById: ReadonlyMap<string, Session>): string | null {
  const session = sessionsById.get(sessionId);
  if (session === undefined) return null;
  const parentId = session.parentSessionId;
  if (parentId === undefined || parentId === null) return null;
  return sessionsById.has(parentId) ? parentId : null;
}

/** Select the raw member that supplies activity presentation for one family. */
function selectActivity(members: readonly Session[], recency: ReadonlyMap<string, RecencyFact>): Session {
  const allLookupsAvailable = members.every((member) => recency.get(member.sessionId)?.outcome === 'available');
  const shouldPreferRunning = !allLookupsAvailable;

  const selected = members.toSorted((left, right) =>
    compareActivityCandidates(left, right, recency, shouldPreferRunning)
  )[0];
  if (selected === undefined) throw new Error('A session family must contain at least one member.');
  return selected;
}

/** Compare family candidates using the current lookup phase's ordering rules. */
function compareActivityCandidates(
  left: Session,
  right: Session,
  recency: ReadonlyMap<string, RecencyFact>,
  shouldPreferRunning: boolean
): number {
  if (shouldPreferRunning) {
    const runningOrder = Number(isObservedRunning(right)) - Number(isObservedRunning(left));
    if (runningOrder !== 0) return runningOrder;
  }
  const recencyOrder = compareTimestampsDescending(
    effectiveRecencyFor(left, recency),
    effectiveRecencyFor(right, recency)
  );
  if (recencyOrder !== 0) return recencyOrder;
  const creationOrder = compareTimestampsDescending(parseTimestamp(left.createdAt), parseTimestamp(right.createdAt));
  return creationOrder || compareIds(left.sessionId, right.sessionId);
}

/** Resolve successful history recency, using creation time for empty history. */
function effectiveRecencyFor(session: Session, recency: ReadonlyMap<string, RecencyFact>): ParsedTimestamp | undefined {
  const fact = recency.get(session.sessionId);
  if (fact?.outcome !== 'available') return undefined;
  return parseTimestamp(fact.latestHistoryAt) ?? parseTimestamp(session.createdAt);
}

/** Parse a strict extended ISO timestamp without losing sub-millisecond precision. */
function parseTimestamp(value: string | null | undefined): ParsedTimestamp | undefined {
  if (value === undefined || value === null) return undefined;
  const match = ISO_TIMESTAMP.exec(value);
  if (match === null) return undefined;

  const parts = timestampParts(match);
  if (!hasValidTimestamp(parts)) return undefined;

  const epochMilliseconds = Date.parse(value);
  if (!Number.isFinite(epochMilliseconds)) return undefined;
  const fractionMilliseconds = Number(`${parts.fraction}000`.slice(0, 3));
  const wholeEpochSecond = BigInt(epochMilliseconds - fractionMilliseconds) / 1000n;
  return {epochSecond: wholeEpochSecond, fraction: parts.fraction.replace(/0+$/, '')};
}

interface TimestampParts {
  readonly year: number;
  readonly month: number;
  readonly day: number;
  readonly hour: number;
  readonly minute: number;
  readonly second: number;
  readonly fraction: string;
  readonly offsetHour: number;
  readonly offsetMinute: number;
}

/** Extract validated-shape numeric fields from a matched ISO timestamp. */
function timestampParts(match: RegExpExecArray): TimestampParts {
  return {
    year: Number(match[1]),
    month: Number(match[2]),
    day: Number(match[3]),
    hour: Number(match[4]),
    minute: Number(match[5]),
    second: Number(match[6]),
    fraction: match[7] ?? '',
    offsetHour: Number(match[10] ?? '0'),
    offsetMinute: Number(match[11] ?? '0')
  };
}

/** Validate calendar, clock, and numeric offset components without date rollover. */
function hasValidTimestamp(parts: TimestampParts): boolean {
  if (!hasValidCalendarDate(parts)) return false;
  if (parts.hour > 23) return false;
  if (parts.minute > 59) return false;
  if (parts.second > 59) return false;
  if (parts.offsetHour > 23) return false;
  return parts.offsetMinute <= 59;
}

/** Check Gregorian month lengths without Date's rollover of invalid calendar days. */
function hasValidCalendarDate(parts: TimestampParts): boolean {
  if (parts.month < 1 || parts.month > 12) return false;
  if (parts.day < 1) return false;
  return parts.day <= maximumDayInMonth(parts);
}

/** Return the Gregorian month length for one year. */
function maximumDayInMonth(parts: TimestampParts): number {
  if (parts.month === 2) return isLeapYear(parts.year) ? 29 : 28;
  if ([4, 6, 9, 11].includes(parts.month)) return 30;
  return 31;
}

/** Check leap years without combining the Gregorian divisibility clauses. */
function isLeapYear(year: number): boolean {
  const isFourYearCycle = year % 4 === 0;
  const isCentury = year % 100 === 0;
  const isFourHundredYearCycle = year % 400 === 0;
  return isFourYearCycle && (!isCentury || isFourHundredYearCycle);
}

/** Compare timestamps newest first, placing missing or invalid values after valid ones. */
function compareTimestampsDescending(left?: ParsedTimestamp, right?: ParsedTimestamp): number {
  if (left === undefined || right === undefined) return compareMissingTimestamps(left, right);
  return comparePresentTimestamps(left, right);
}

/** Put absent timestamps after present ones, treating two absent values as equal. */
function compareMissingTimestamps(left?: ParsedTimestamp, right?: ParsedTimestamp): number {
  if (left === undefined && right === undefined) return 0;
  return left === undefined ? 1 : -1;
}

/** Compare two valid timestamps without losing sub-millisecond precision. */
function comparePresentTimestamps(left: ParsedTimestamp, right: ParsedTimestamp): number {
  if (left.epochSecond > right.epochSecond) return -1;
  if (left.epochSecond < right.epochSecond) return 1;
  const width = Math.max(left.fraction.length, right.fraction.length);
  const leftFraction = left.fraction.padEnd(width, '0');
  const rightFraction = right.fraction.padEnd(width, '0');
  if (leftFraction > rightFraction) return -1;
  if (leftFraction < rightFraction) return 1;
  return 0;
}

/** Prefer live observer records over synthetic demo activity. */
function isObservedRunning(session: Session): boolean {
  return session.state === 'running' && session.source !== 'demo';
}

/** Return the lexically first value from a nonempty set of identities. */
function smallestId(ids: readonly string[]): string {
  const smallest = ids.toSorted(compareIds)[0];
  if (smallest === undefined) throw new Error('Cannot resolve a root without any session IDs.');
  return smallest;
}

/** Compare opaque IDs by code point without locale-dependent collation. */
function compareIds(left: string, right: string): number {
  if (left < right) return -1;
  if (left > right) return 1;
  return 0;
}
