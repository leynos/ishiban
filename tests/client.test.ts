/** @file Projection replay is immutable, ordered, and identity-based. */
import {describe, expect, it} from 'bun:test';
import fc from 'fast-check';
import {createBoardStore} from '../src/client';
import {createDemoSnapshot} from '../src/demo';

describe('browser projection replay', () => {
  it('ignores duplicate and older cursors without changing the snapshot', () => {
    const store = createBoardStore();
    const initial = createDemoSnapshot();
    store.replace(initial);
    const session = initial.sessions[0];
    expect(session).toBeDefined();
    if (!session) throw new Error('Demo fixture must have a session');
    store.session(initial.cursor + 1, {...session, title: 'Committed update'});
    const updated = store.getSnapshot();
    store.session(initial.cursor, session);
    store.session(initial.cursor + 1, session);
    expect(store.getSnapshot()).toBe(updated);
    expect(initial.sessions[0]?.title).not.toBe('Committed update');
  });

  it('preserves the newest projection under generated duplicate replay', () => {
    const cursorLists = fc.array(fc.integer({min: 1, max: 1000}), {minLength: 1});
    fc.assert(
      fc.property(cursorLists, (cursors) => {
        const store = createBoardStore();
        const initial = createDemoSnapshot();
        store.replace({...initial, cursor: 0});
        const session = initial.sessions[0];
        if (!session) throw new Error('Demo fixture must have a session');
        for (const cursor of cursors) store.session(cursor, {...session, title: String(cursor)});
        const latest = Math.max(...cursors);
        expect(store.getSnapshot().snapshot?.cursor).toBe(latest);
        expect(store.getSnapshot().snapshot?.sessions[0]?.title).toBe(String(latest));
      }),
      {numRuns: 30}
    );
  });
});
