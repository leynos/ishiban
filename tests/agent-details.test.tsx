/** @file Inspect lazy agent metadata and copy the Lody command-line identity. */
import {afterEach, beforeEach, expect, it, spyOn} from 'bun:test';
import {cleanup, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {AgentDetails} from '../src/ui/agent-details';

const metadataFetch = Object.assign(
  async () =>
    Response.json({
      workspaceId: 'workspace-1',
      sessionId: 'lody-session-1',
      agent: {
        agentType: 'codex',
        configurationId: 'config-1',
        configurationName: 'My Codex configuration',
        acpSessionId: 'provider-conversation-id'
      }
    }),
  {preconnect: () => null}
);
let fetchSpy: ReturnType<typeof spyOn<typeof globalThis, 'fetch'>>;

beforeEach(() => {
  fetchSpy = spyOn(globalThis, 'fetch').mockImplementation(metadataFetch);
});
afterEach(() => {
  cleanup();
  fetchSpy.mockRestore();
});

it('collects agent type and configuration name when the inspector mounts', async () => {
  render(<AgentDetails workspaceId="workspace-1" sessionId="lody-session-1" isDemo={false} />);
  expect(await screen.findByText('My Codex configuration')).toBeTruthy();
  expect(screen.getByText('codex')).toBeTruthy();
  expect(fetchSpy.mock.calls[0]?.[0]).toBe('/api/v1/session-agent?sessionId=lody-session-1');
});

it('copies the Lody CLI session ID rather than the provider conversation ID', async () => {
  const user = userEvent.setup();
  const write = spyOn(navigator.clipboard, 'writeText').mockResolvedValue();
  try {
    render(<AgentDetails workspaceId="workspace-1" sessionId="lody-session-1" isDemo={false} />);
    await user.click(screen.getByRole('button', {name: 'Copy session ID'}));
    expect(write).toHaveBeenCalledWith('lody-session-1');
    expect(screen.getByRole('status').textContent).toBe('Session ID copied.');
  } finally {
    write.mockRestore();
  }
});

it('shows clipboard failures without falsely reporting a successful copy', async () => {
  const user = userEvent.setup();
  const write = spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('denied'));
  try {
    render(<AgentDetails workspaceId="workspace-1" sessionId="lody-session-1" isDemo={false} />);
    await user.click(screen.getByRole('button', {name: 'Copy session ID'}));
    expect(screen.getByRole('status').textContent).toContain('Could not copy.');
  } finally {
    write.mockRestore();
  }
});

it('does not query metadata or enable CLI copying for synthetic demo records', () => {
  render(<AgentDetails workspaceId="workspace-1" sessionId="demo-1" isDemo />);
  expect(fetchSpy).not.toHaveBeenCalled();
  expect(screen.getByRole('button', {name: 'Copy session ID'}).hasAttribute('disabled')).toBe(true);
});
