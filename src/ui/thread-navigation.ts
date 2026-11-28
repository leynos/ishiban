/** @file Map middle-button gestures on real task controls to one Lody window. */
import type {MouseEvent} from 'react';
import type {SessionFamily} from '../session-families';

const MIDDLE_BUTTON = 1;

/** Native middle-button handlers for one board task control. */
export interface ThreadNavigationHandlers {
  readonly onMouseDown: (event: MouseEvent<HTMLButtonElement>) => void;
  readonly onAuxClick: (event: MouseEvent<HTMLButtonElement>) => void;
}

/** Report whether this gesture is the non-primary button that opens a thread. */
function isMiddleButtonPress(event: MouseEvent<HTMLButtonElement>): boolean {
  return event.button === MIDDLE_BUTTON;
}

/**
 * Build middle-button handlers that open a thread without disturbing selection.
 *
 * The default mousedown is suppressed only when the family resolves to an
 * openable destination, so non-Lody controls retain ordinary middle-click
 * behaviour. The auxclick handler opens exactly one browsing context; it never
 * selects the task and never calls stopPropagation.
 *
 * @param family Grouped session family rendered by the control.
 * @param canOpenThread Reports whether the family has an openable destination.
 * @param onOpenThread Opens the family's displayed thread once.
 * @returns Handlers for the task button's middle-button lifecycle.
 * @example
 * <button {...threadNavigationHandlers(family, canOpen, open)} onClick={select} />
 */
export function threadNavigationHandlers(
  family: SessionFamily,
  canOpenThread: (family: SessionFamily) => boolean,
  onOpenThread: (family: SessionFamily) => boolean
): ThreadNavigationHandlers {
  return {
    onMouseDown(event) {
      if (isMiddleButtonPress(event) && canOpenThread(family)) event.preventDefault();
    },
    onAuxClick(event) {
      if (!isMiddleButtonPress(event)) return;
      event.preventDefault();
      onOpenThread(family);
    }
  };
}
