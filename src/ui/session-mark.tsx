/** @file Share the session mark selection contract, condition cues and pulse rendering. */
import type {ReactElement} from 'react';
import type {Session} from '../contracts';
import type {SessionFamily} from '../session-families';
import {activityOf, evidenceLabel, STAGE_LABELS} from './board-model';

/** Shared selection contract for table, list, and workflow-exception marks. */
export interface SessionSelectionProps {
  readonly currentGeneration: number;
  readonly selectedSessionId: string | null;
  readonly pulseRevisions: ReadonlyMap<string, number>;
  readonly onSelect: (sessionId: string, trigger?: HTMLButtonElement) => void;
  readonly onMarkNode: (sessionId: string, node: HTMLButtonElement | null) => void;
  readonly canOpenThread: (family: SessionFamily) => boolean;
  readonly onOpenThread: (family: SessionFamily) => boolean;
}

export interface SessionCondition {
  readonly isBlocked: boolean;
  readonly hasLastTurnFailure: boolean;
  readonly label: string;
  readonly glyph: string | null;
}

/**
 * Describe only explicit waiting activity and a supplied failed turn.
 * @param session Activity projection whose explicit state supplies the cue.
 * @returns Whether the task is blocked or failed, with its accessible text and glyph.
 */
export function conditionOf(session: Session): SessionCondition {
  const isBlocked = session.state === 'waiting';
  const hasLastTurnFailure = session.latestTurn?.state === 'failed';
  const labels: string[] = [];
  if (isBlocked) {
    labels.push('blocked');
  }
  if (hasLastTurnFailure) {
    labels.push('last known turn failed');
  }
  let glyph: string | null = null;
  if (hasLastTurnFailure) {
    glyph = '!';
  } else if (isBlocked) {
    glyph = '⌛';
  }
  return {isBlocked, hasLastTurnFailure, label: labels.join('; '), glyph};
}

/** Presentation facts shared by table and list marks. */
export interface SessionMarkFacts {
  readonly activity: ReturnType<typeof activityOf>;
  readonly evidence: string;
  readonly condition: SessionCondition;
  readonly label: string;
}

/**
 * Derive the accessible name and visible cues for one displayed family.
 * @param repository Repository name shown before the task title.
 * @param family Grouped family whose displayed activity supplies the mark.
 * @param currentGeneration Collector generation used to label evidence freshness.
 * @returns Activity, evidence, condition and accessible label for the mark.
 */
export function markFacts(repository: string, family: SessionFamily, currentGeneration: number): SessionMarkFacts {
  const condition = conditionOf(family.activity);
  const activity = activityOf(family.activity.state);
  const evidence = evidenceLabel(family.activity, currentGeneration);
  const conditionLabel = condition.label.length === 0 ? '' : `; ${condition.label}`;
  const label = `${repository}: ${family.context.title}; ${STAGE_LABELS[family.context.stage]}; ${activity}${conditionLabel}; ${evidence}`;
  return {activity, evidence, condition, label};
}

/**
 * Render one keyed, aria-hidden pulse overlay only for a recent event.
 * @param revision Event revision that owns the pulse, or undefined when settled.
 * @returns The pulse overlay, or null when the mark has no current cue.
 */
export function UpdatePulse({revision}: {readonly revision: number | undefined}): ReactElement | null {
  return revision === undefined ? null : (
    <span
      aria-hidden="true"
      className="session-update-pulse"
      data-session-update-pulse={revision}
      key={revision}
      role="presentation"
    />
  );
}
