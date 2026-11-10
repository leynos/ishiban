/** @file Read cached agent metadata on inspector demand and copy Lody CLI identity. */
import {useEffect, useState, type ReactElement} from 'react';
import {Schema} from 'effect';

const AgentSchema = Schema.Struct({
  agentType: Schema.NullOr(Schema.String),
  configurationId: Schema.NullOr(Schema.String),
  configurationName: Schema.NullOr(Schema.String)
});
const DetailsSchema = Schema.Struct({
  workspaceId: Schema.String,
  sessionId: Schema.String,
  agent: Schema.NullOr(AgentSchema)
});
interface AgentDetailsProps {
  readonly workspaceId: string;
  readonly sessionId: string;
  readonly isDemo: boolean;
}

/** Read a matching identity only; for example, reject another session's cached response. */
async function readAgentDetails(workspaceId: string, sessionId: string, signal: AbortSignal) {
  const response = await fetch(`/api/v1/sessions/${encodeURIComponent(sessionId)}/agent`, {signal, cache: 'no-store'});
  if (!response.ok) throw new Error('Agent metadata unavailable');
  const details = Schema.decodeUnknownSync(DetailsSchema)(await response.json());
  if (details.workspaceId !== workspaceId) throw new Error('Foreign workspace metadata');
  if (details.sessionId !== sessionId) throw new Error('Foreign session metadata');
  return details.agent;
}

/** Load only the selected identity; for example, discard a late response after closing. */
function useAgentDetails({workspaceId, sessionId, isDemo}: AgentDetailsProps) {
  const [agent, setAgent] = useState<typeof AgentSchema.Type | null>(null);
  const [status, setStatus] = useState(isDemo ? 'Demo metadata' : 'Loading agent details…');
  useEffect(() => {
    if (isDemo) return;
    const controller = new AbortController();
    let isCurrent = true;
    const timeout = setTimeout(() => controller.abort(), 60_000);
    void readAgentDetails(workspaceId, sessionId, controller.signal)
      .then(
        (details) => {
          if (!isCurrent) return;
          setAgent(details);
          setStatus(details ? '' : 'Agent details unavailable.');
        },
        () => {
          if (isCurrent) setStatus('Agent details unavailable.');
        }
      )
      .finally(() => clearTimeout(timeout));
    return () => {
      isCurrent = false;
      clearTimeout(timeout);
      controller.abort();
    };
  }, [workspaceId, sessionId, isDemo]);
  return {agent, status};
}

/**
 * Present lazily collected agent metadata and the exact Lody command-line session ID.
 * @param props The selected Lody identity, rather than the provider conversation ID.
 * @returns Agent facts and accessible clipboard feedback.
 * @example
 * <AgentDetails workspaceId="workspace-1" sessionId="session-1" isDemo={false} />;
 */
export function AgentDetails(props: AgentDetailsProps): ReactElement {
  const {agent, status} = useAgentDetails(props);
  const [copyStatus, setCopyStatus] = useState('');
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(props.sessionId);
      setCopyStatus('Session ID copied.');
    } catch {
      setCopyStatus('Could not copy. Select the session ID and copy it manually.');
    }
  };
  return (
    <section className="inspector-section" aria-labelledby="agent-details-heading">
      <h3 id="agent-details-heading">Agent details</h3>
      <dl className="inspector-facts">
        <dt>Session ID</dt>
        <dd>
          <code>{props.sessionId}</code>{' '}
          <button
            className="btn btn-ghost btn-xs"
            type="button"
            disabled={props.isDemo}
            aria-label="Copy session ID"
            onClick={() => {
              void copy();
            }}
          >
            Copy
          </button>
        </dd>
        <dt>Agent type</dt>
        <dd>{agent?.agentType ?? 'Not supplied'}</dd>
        <dt>Agent configuration</dt>
        <dd>{agent?.configurationName ?? 'Name unavailable'}</dd>
      </dl>
      <p role="status">{copyStatus || status}</p>
    </section>
  );
}
