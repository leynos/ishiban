/** @file Compile-only contracts for the public preference callbacks; this file is never executed. */
import type {InterfaceStateControls} from '../src/ui/interface-state';

/**
 * Check supported values and rejected cross-preference values at the hook boundary.
 * @param controls Public preference callbacks under compile-time verification.
 * @returns No value; this fixture is checked by tsc and is never invoked.
 */
export function preferenceCallbackTypeContract(controls: InterfaceStateControls): void {
  controls.onDensityChange('balanced');
  controls.onPresentationChange('matrix');

  // @ts-expect-error A presentation value cannot select a density.
  controls.onDensityChange('panorama');
  // @ts-expect-error A density value cannot select a presentation.
  controls.onPresentationChange('compact');
  // @ts-expect-error Unsupported values cannot become persisted density preferences.
  controls.onDensityChange('extra-large');
}
