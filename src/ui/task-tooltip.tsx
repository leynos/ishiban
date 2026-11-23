/** @file Present passive, formatted task facts in a portalled Radix tooltip. */
import * as Tooltip from '@radix-ui/react-tooltip';
import {Fragment, type ReactElement, type ReactNode} from 'react';
import {NO_CONDITIONS_LABEL, type TaskTooltipFacts} from './board-model';

/**
 * Shared pointer-hover delay before a task tooltip opens.
 * Keyboard focus opens immediately, and a tooltip opened within
 * {@link TASK_TOOLTIP_SKIP_DELAY_MS} of another closing skips this wait, so
 * sweeping across marks reads as one gesture rather than many popups.
 */
export const TASK_TOOLTIP_DELAY_MS = 300;

/** Shared window after a close during which the next tooltip opens without delay. */
export const TASK_TOOLTIP_SKIP_DELAY_MS = 300;

/** Pointer offset keeping the tooltip clear of the mark it describes. */
const CONTENT_SIDE_OFFSET_PX = 6;

/** Viewport inset used by collision avoidance so content never touches an edge. */
const CONTENT_COLLISION_PADDING_PX = 8;

/** Fixed, non-interactive hint explaining where detailed errors and links live. */
export const TASK_TOOLTIP_INSPECTOR_HINT = 'Select this task to open the inspector for detailed errors and links.';

/** One labelled detail row; the label is also the tooltip body's visible caption. */
interface DetailRow {
  readonly label: string;
  readonly value: string;
}

/** Return every labelled detail in canonical order, adding only Condition's fallback. */
function detailRows(facts: TaskTooltipFacts): readonly DetailRow[] {
  const condition = facts.condition.length === 0 ? NO_CONDITIONS_LABEL : facts.condition;
  return [
    {label: 'Repository', value: facts.repository},
    {label: 'Workflow stage', value: facts.stage},
    {label: 'Current tab activity', value: facts.activity},
    {label: 'Condition', value: condition},
    {label: 'Evidence', value: facts.evidence}
  ];
}

/** Compose the supplementary description; the mark's own label already names every fact. */
function describedBy(facts: TaskTooltipFacts): string {
  const notice = facts.provisionalNotice === null ? '' : `${facts.provisionalNotice} `;
  return `${notice}${TASK_TOOLTIP_INSPECTOR_HINT}`;
}

/** Render labelled detail rows, an optional provisional row and the non-interactive hint. */
function TooltipBody({facts}: {readonly facts: TaskTooltipFacts}): ReactElement {
  return (
    <>
      <p className="task-tooltip__title">{facts.title}</p>
      <dl className="task-tooltip__facts">
        {detailRows(facts).map((row) => (
          <Fragment key={row.label}>
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </Fragment>
        ))}
      </dl>
      {facts.provisionalNotice === null ? null : <p className="task-tooltip__provisional">{facts.provisionalNotice}</p>}
      <p className="task-tooltip__hint">{TASK_TOOLTIP_INSPECTOR_HINT}</p>
    </>
  );
}

/**
 * Wrap the board's real task marks in one shared tooltip provider.
 * @param children Board output rendered inside the one shared provider.
 * @returns The provider applying shared delay behaviour to every task tooltip.
 * @example
 * <TaskTooltipProvider><BoardBanks {...props} /></TaskTooltipProvider>
 */
export function TaskTooltipProvider({children}: {readonly children: ReactNode}): ReactElement {
  return (
    <Tooltip.Provider delayDuration={TASK_TOOLTIP_DELAY_MS} skipDelayDuration={TASK_TOOLTIP_SKIP_DELAY_MS}>
      {children}
    </Tooltip.Provider>
  );
}

/**
 * Attach formatted task facts to one real task mark without changing the mark.
 * The trigger is the existing native button, so its accessible name, focus
 * behaviour, data attributes and click handler stay with their owner. Content
 * is portalled to the document body, clear of the scrolling table.
 * @param facts Formatted task facts describing the mark.
 * @param children Existing native task button acting as the tooltip trigger.
 * @returns The mark wrapped in a tooltip root with portalled content.
 * @example
 * <TaskTooltip facts={taskTooltipFacts(family, 'leynos/ishiban', 5)}>
 *   <button className="session-mark" type="button" />
 * </TaskTooltip>
 */
export function TaskTooltip({
  facts,
  children
}: {
  readonly facts: TaskTooltipFacts;
  readonly children: ReactElement;
}): ReactElement {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          aria-label={describedBy(facts)}
          className="task-tooltip"
          collisionPadding={CONTENT_COLLISION_PADDING_PX}
          side="top"
          sideOffset={CONTENT_SIDE_OFFSET_PX}
        >
          <div aria-hidden="true">
            <TooltipBody facts={facts} />
          </div>
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
