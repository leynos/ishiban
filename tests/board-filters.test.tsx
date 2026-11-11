/** @file Verify activity and reset filters through rendered board controls. */
import {afterEach, expect, it} from 'bun:test';
import {cleanup, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type {Snapshot} from '../src/contracts';
import {Board} from '../src/ui/board';
import {createBoardSnapshot, firstSession} from './board-fixtures';

afterEach(cleanup);

/** Build three distinct activities; makeFilterSnapshot() hides the archived waiting mark initially. */
function makeFilterSnapshot(): Snapshot {
  const snapshot = createBoardSnapshot();
  const first = firstSession(snapshot);
  const second = snapshot.sessions[1];
  if (second === undefined) throw new Error('The board fixture needs a second session.');
  return {
    ...snapshot,
    sessions: [
      {...first, title: 'Idle board fixture', state: 'idle'},
      {...second, title: 'Running board fixture', state: 'running'},
      {
        ...first,
        sessionId: 'archived-waiting-fixture',
        title: 'Archived waiting board fixture',
        state: 'waiting',
        archived: true
      }
    ]
  };
}

it('shows only sessions matching the selected activity and archive controls', async () => {
  const user = userEvent.setup();
  render(<Board connection="demo" snapshot={makeFilterSnapshot()} />);
  const activity = screen.getByRole('combobox', {name: 'Filter by activity'});

  expect(screen.getByRole('button', {name: /Idle board fixture; Planning; idle/u})).toBeTruthy();
  expect(screen.getByRole('button', {name: /Running board fixture; Planning; running/u})).toBeTruthy();
  expect(screen.queryByRole('button', {name: /Archived waiting board fixture/u})).toBeNull();

  await user.selectOptions(activity, 'running');
  expect(screen.getByRole('button', {name: /Running board fixture; Planning; running/u})).toBeTruthy();
  expect(screen.queryByRole('button', {name: /Idle board fixture/u})).toBeNull();
  expect(screen.queryByRole('button', {name: /Archived waiting board fixture/u})).toBeNull();

  await user.selectOptions(activity, 'waiting');
  expect(screen.queryByRole('button', {name: /Running board fixture/u})).toBeNull();
  await user.click(screen.getByRole('checkbox', {name: 'Include archived and removed'}));
  expect(screen.getByRole('button', {name: /Archived waiting board fixture; Planning; waiting/u})).toBeTruthy();
  expect(screen.queryByRole('button', {name: /Idle board fixture/u})).toBeNull();
});

it('resets search, activity, and archive controls and restores the default visible sessions', async () => {
  const user = userEvent.setup();
  render(<Board connection="demo" snapshot={makeFilterSnapshot()} />);
  const search = screen.getByRole('searchbox', {name: 'Find repository, session or branch'});
  const activity = screen.getByRole('combobox', {name: 'Filter by activity'});
  const archived = screen.getByRole('checkbox', {name: 'Include archived and removed'});
  if (!(search instanceof HTMLInputElement)) throw new Error('Search must remain a native input.');
  if (!(activity instanceof HTMLSelectElement)) throw new Error('Activity must remain a native select.');
  if (!(archived instanceof HTMLInputElement)) throw new Error('Archive must remain a native checkbox.');

  await user.click(archived);
  await user.selectOptions(activity, 'waiting');
  await user.type(search, 'Archived waiting');
  expect(screen.getByRole('button', {name: /Archived waiting board fixture; Planning; waiting/u})).toBeTruthy();
  expect(screen.queryByRole('button', {name: /Running board fixture/u})).toBeNull();

  await user.click(screen.getByRole('button', {name: 'Reset filters'}));
  expect(search.value).toBe('');
  expect(activity.value).toBe('all');
  expect(archived.checked).toBe(false);
  expect(screen.getByRole('button', {name: /Idle board fixture; Planning; idle/u})).toBeTruthy();
  expect(screen.getByRole('button', {name: /Running board fixture; Planning; running/u})).toBeTruthy();
  expect(screen.queryByRole('button', {name: /Archived waiting board fixture/u})).toBeNull();
});
