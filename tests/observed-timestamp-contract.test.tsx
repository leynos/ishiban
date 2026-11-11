/** @file Verify the persisted observer timestamp renders at the UI boundary. */
import {afterEach, expect, it} from 'bun:test';
import {cleanup, render, screen} from '@testing-library/react';
import {Schema} from 'effect';
import {SessionSchema} from '../src/contracts';
import {SessionInspector} from '../src/ui/session-inspector';
import {writeCapturedText} from './capture-writer';

const {ISHIBAN_OBSERVED_TIMESTAMP_SESSION: sessionPath} = Bun.env;
const {ISHIBAN_OBSERVED_TIMESTAMP_RESULT: resultPath} = Bun.env;

afterEach(cleanup);

it.skipIf(!sessionPath || !resultPath)('renders the protocol timestamp persisted in the session snapshot', async () => {
  if (!sessionPath || !resultPath) {
    throw new Error('The protocol contract must supply its captured session and result paths.');
  }
  const session = Schema.decodeUnknownSync(SessionSchema)(await Bun.file(sessionPath).json());
  render(
    <SessionInspector
      session={session}
      currentGeneration={1}
      onClose={() => {}}
      workspaceId="w1"
      workspaceSlug="leynos"
    />
  );

  const visibleTimestamp = new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC'
  }).format(new Date(session.lastObservedAt ?? Number.NaN));
  expect(screen.getByText(visibleTimestamp)).toBeTruthy();
  writeCapturedText(
    resultPath,
    JSON.stringify({sessionId: session.sessionId, lastObservedAt: session.lastObservedAt, visibleTimestamp})
  );
});
