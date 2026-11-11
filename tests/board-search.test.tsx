/** @file Verify repository and branch terms through the rendered board search. */
import {afterEach, expect, it} from 'bun:test';
import {cleanup, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type {Session, Snapshot} from '../src/contracts';
import {Board} from '../src/ui/board';
import {createFamilySnapshot} from './board-fixtures';

afterEach(cleanup);

/** Give each family unique titles, repository and branch terms. */
function searchSnapshot(): Snapshot {
  const baseline = createFamilySnapshot(2);
  const changes = new Map<string, Partial<Session>>([
    ['root-0', {title: 'Alpha task', repoFullName: 'leynos/copper-signal', branchName: 'feature/amber-path'}],
    ['child-0', {title: 'Alpha execution'}],
    ['root-1', {title: 'Beta task', repoFullName: 'leynos/quiet-cedar', branchName: 'feature/quartz-ribbon'}],
    ['child-1', {title: 'Beta execution'}]
  ]);
  return {
    ...baseline,
    sessions: baseline.sessions.map((session) => ({...session, ...changes.get(session.sessionId)}))
  };
}

/** Assert that exactly the requested family mark remains after user search. */
function expectOnlyFamily(rootId: string): void {
  const visible = screen.getAllByRole('button', {name: /(?:Alpha|Beta) task; Refine; running/u});
  expect(visible.map((mark) => mark.getAttribute('data-family-id'))).toEqual([rootId]);
  expect(document.querySelector('.board-summary')?.textContent).toContain('1 visible sessions');
}

it('finds a family by its repository when titles, IDs and branches do not contain the query', async () => {
  const user = userEvent.setup();
  render(<Board connection="Connected" snapshot={searchSnapshot()} />);
  expect(screen.getAllByRole('button', {name: /(?:Alpha|Beta) task; Refine; running/u})).toHaveLength(2);

  await user.type(screen.getByRole('searchbox', {name: 'Find repository, session or branch'}), 'COPPER-SIGNAL');
  expectOnlyFamily('root-0');
});

it('finds a family by its branch when titles, IDs and repositories do not contain the query', async () => {
  const user = userEvent.setup();
  render(<Board connection="Connected" snapshot={searchSnapshot()} />);
  expect(screen.getAllByRole('button', {name: /(?:Alpha|Beta) task; Refine; running/u})).toHaveLength(2);

  await user.type(screen.getByRole('searchbox', {name: 'Find repository, session or branch'}), 'quartz-ribbon');
  expectOnlyFamily('root-1');
});
