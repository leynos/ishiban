/** @file Verify the inspector heading against the axinite stacked PR family. */
import {afterEach, expect, it} from 'bun:test';
import {cleanup, render, screen} from '@testing-library/react';
import {SessionInspector} from '../src/ui/session-inspector';
import {createBoardSnapshot, firstSession} from './board-fixtures';
import {AXINITE_DEPENDENT, AXINITE_PREREQUISITE} from './pr-stack-fixtures';

afterEach(cleanup);

it.each([false, true])('keeps the dependent PR as heading across catalogue order %s', (reverse) => {
  const original = firstSession(createBoardSnapshot());
  const pullRequests = reverse ? [AXINITE_DEPENDENT, AXINITE_PREREQUISITE] : [AXINITE_PREREQUISITE, AXINITE_DEPENDENT];
  const {rerender} = render(
    <SessionInspector
      session={{
        ...original,
        pullRequests: pullRequests.map((pr) => (pr.url === AXINITE_PREREQUISITE.url ? {...pr, title: null} : pr))
      }}
      workspaceId="workspace-1"
      currentGeneration={1}
      onClose={() => {}}
    />
  );
  const heading = screen.getByRole('heading', {name: AXINITE_DEPENDENT.title, level: 3});
  expect(heading.querySelector('a')?.href).toBe(AXINITE_DEPENDENT.url);
  expect(screen.getByText(original.title).className).toBe('session-inspector__subtitle');
  rerender(
    <SessionInspector
      session={{...original, pullRequests}}
      workspaceId="workspace-1"
      currentGeneration={1}
      onClose={() => {}}
    />
  );
  expect(screen.getByRole('heading', {name: AXINITE_DEPENDENT.title, level: 3}).querySelector('a')?.href).toBe(
    AXINITE_DEPENDENT.url
  );
});

it('does not substitute a prerequisite title when the top PR title is unavailable', () => {
  const original = firstSession(createBoardSnapshot());
  render(
    <SessionInspector
      session={{...original, pullRequests: [AXINITE_PREREQUISITE, {...AXINITE_DEPENDENT, title: null}]}}
      workspaceId="workspace-1"
      currentGeneration={1}
      onClose={() => {}}
    />
  );
  expect(screen.getByRole('heading', {name: original.title, level: 3}).querySelector('a')).toBeNull();
  expect(screen.queryByRole('heading', {name: AXINITE_PREREQUISITE.title, level: 3})).toBeNull();
});
