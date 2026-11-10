/** @file Own restored interface preferences and serialize cookie writes. */
import {useCallback, useEffect, useRef, useState} from 'react';
import type {InterfaceState} from '../contracts';
import type {Density, Presentation} from './board-model';

const DEFAULT_INTERFACE_STATE: InterfaceState = {
  density: 'overview',
  presentation: 'panorama'
};
const SAVING = 'Saving interface state…';
const SAVE_FAILED = 'Could not save interface state.';

export type InterfaceStateSaveStatus = '' | typeof SAVING | typeof SAVE_FAILED;

export interface InterfaceStateControls {
  readonly density: Density;
  readonly presentation: Presentation;
  readonly onDensityChange: (density: Density) => void;
  readonly onPresentationChange: (presentation: Presentation) => void;
  readonly saveStatus: InterfaceStateSaveStatus;
}

/**
 * Restore board preferences and persist only explicit user changes.
 *
 * Example
 * -------
 * const preferences = useInterfaceState(snapshot.interfaceState);
 *
 * With no saved state, the hook starts at overview/panorama and makes no
 * request until a density or presentation control changes.
 *
 * @param initial Validated preferences from the first workspace snapshot, if available.
 * @returns Current preference values, change handlers, and asynchronous save status.
 */
export function useInterfaceState(initial?: InterfaceState): InterfaceStateControls {
  const [state, setState] = useState<InterfaceState>(() => initial ?? DEFAULT_INTERFACE_STATE);
  const [saveStatus, setSaveStatus] = useState<InterfaceStateSaveStatus>('');
  const latestState = useRef(state);
  const saveQueue = useRef<Promise<void>>(Promise.resolve());
  const pendingSaveCount = useRef(0);
  const isMounted = useRef(false);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  const queueSave = useCallback((nextState: InterfaceState) => {
    pendingSaveCount.current += 1;
    if (isMounted.current) {
      setSaveStatus(SAVING);
    }
    const request = saveQueue.current.then(() =>
      fetch('/api/v1/interface-state', {
        method: 'POST',
        headers: {'content-type': 'application/json'},
        body: JSON.stringify(nextState),
        keepalive: true
      })
    );
    saveQueue.current = request
      .then(
        (response): InterfaceStateSaveStatus => (response.ok ? '' : SAVE_FAILED),
        (): InterfaceStateSaveStatus => SAVE_FAILED
      )
      .then((result) => {
        pendingSaveCount.current -= 1;
        if (isMounted.current && pendingSaveCount.current === 0) {
          setSaveStatus(result);
        }
      });
  }, []);

  const commitPreference = useCallback(
    <Key extends keyof InterfaceState>(key: Key, value: InterfaceState[Key]) => {
      const nextState: InterfaceState = {...latestState.current, [key]: value};
      latestState.current = nextState;
      setState(nextState);
      queueSave(nextState);
    },
    [queueSave]
  );

  const onDensityChange = useCallback((density: Density) => commitPreference('density', density), [commitPreference]);

  const onPresentationChange = useCallback(
    (presentation: Presentation) => commitPreference('presentation', presentation),
    [commitPreference]
  );

  return {
    density: state.density,
    presentation: state.presentation,
    onDensityChange,
    onPresentationChange,
    saveStatus
  };
}
