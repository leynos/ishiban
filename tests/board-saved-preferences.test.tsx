/** @file Verify saved snapshot preferences initialize the rendered board. */
import {afterEach, expect, it} from 'bun:test';
import {cleanup, render, screen} from '@testing-library/react';
import {Board} from '../src/ui/board';
import {createBoardSnapshot} from './board-fixtures';

afterEach(cleanup);

it('opens with both saved controls and the saved presentation', () => {
  const snapshot = {
    ...createBoardSnapshot(),
    interfaceState: {density: 'roomy' as const, presentation: 'matrix' as const}
  };
  const {container} = render(<Board connection="Connected" snapshot={snapshot} />);
  expect(screen.getByRole('option', {name: 'Roomy', selected: true})).toBeTruthy();
  expect(screen.getByRole('button', {name: 'Matrix'}).getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByRole('button', {name: 'Panorama'}).getAttribute('aria-pressed')).toBe('false');
  expect(container.querySelector('.ishiban-board')?.getAttribute('data-density')).toBe('roomy');
  expect(container.querySelector('.ishiban-board')?.getAttribute('data-presentation')).toBe('matrix');
  expect(screen.getByRole('table', {name: 'Repository sessions by workflow stage'})).toBeTruthy();
});
