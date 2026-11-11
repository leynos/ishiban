/** @file Verify ordered bootstrap frames establish a quiet board baseline. */
import {afterEach, expect, it} from 'bun:test';
import {act, cleanup, render, screen} from '@testing-library/react';
import {useSyncExternalStore} from 'react';
import {createBoardStore, type BoardStore} from '../src/client';
import {Board} from '../src/ui/board';
import {createBoardSnapshot, firstSession} from './board-fixtures';

afterEach(cleanup);

/** Render the actual board subscription while each stored event is applied. */
function LiveBoard({store}: {readonly store: BoardStore}) {
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
  return state.snapshot ? <Board connection={state.connection} snapshot={state.snapshot} /> : null;
}

it('keeps each bootstrap catalogue frame quiet and pulses a later change', () => {
  const base = createBoardSnapshot();
  const first = firstSession(base);
  const initial = {
    ...base,
    cursor: 100,
    collector: {...base.collector, state: 'catalogue_ready', generation: 2},
    sessions: [{...first, source: 'metadata', state: 'unknown'}]
  } as const;
  const store = createBoardStore((notify) => notify());
  store.replace(initial);
  render(<LiveBoard store={store} />);

  const observed = {...initial.sessions[0], lastEventId: 101, state: 'running', source: 'persisted'} as const;
  act(() => store.session(101, observed));
  const liveMark = screen.getByRole('button', {name: /Synthetic planning task 01/u});
  expect(liveMark.className).toContain('activity-running');
  expect(document.querySelectorAll('[data-session-update-pulse]').length).toBe(0);

  const enriched = {
    ...observed,
    lastEventId: 102,
    title: 'Bootstrap association',
    repoFullName: 'demo/enriched',
    stage: 'ready',
    pullRequests: [{url: 'https://github.com/acme/repo/pull/1', title: 'Plan: Bootstrap', status: 'open'}]
  } as const;
  act(() => store.session(102, enriched));
  expect(screen.getByRole('button', {name: /Bootstrap association/u})).toBeTruthy();
  expect(document.querySelectorAll('[data-session-update-pulse]').length).toBe(0);

  const catalogueOnly = {...enriched, sessionId: 'catalogue-only', title: 'Catalogue only', lastEventId: 103};
  act(() => store.session(103, catalogueOnly));
  expect(screen.getByRole('button', {name: /Catalogue only/u})).toBeTruthy();
  expect(document.querySelectorAll('[data-session-update-pulse]').length).toBe(0);

  act(() => store.collector(104, {...initial.collector, state: 'following'}));
  expect(document.querySelectorAll('[data-session-update-pulse]').length).toBe(0);

  act(() => store.session(105, {...enriched, lastEventId: 105, title: 'Later task change'}));
  const later = screen.getByRole('button', {name: /Later task change/u});
  expect(later.getAttribute('data-update-revision')).toBe('105');
  expect(later.querySelector('[data-session-update-pulse]')).not.toBeNull();
});
