/** @file Resolve canonical Lody destinations shared by the inspector and board. */
import type {Session} from '../contracts';
import type {SessionFamily} from '../session-families';

// URL parsers normalize dot-segment paths, even when IDs are percent-encoded.
const URL_NORMALIZED_PATH_SEGMENTS = new Set(['.', '..']);

/** The inspector's outcome for one session's external Lody destination. */
export type LodyLinkTarget =
  | {readonly kind: 'synthetic'}
  | {readonly kind: 'unavailable'}
  | {readonly kind: 'link'; readonly href: string};

/** Identities and workspace routing metadata that locate one Lody thread. */
export interface LodyLinkInput {
  readonly session: Session;
  readonly activitySession?: Session | undefined;
  readonly workspaceId: string;
  readonly workspaceSlug?: string | undefined;
}

/** Keep child identity in the query; for example, root/child uses /sessions/root?tab=session%3Achild. */
function webSessionLinkTarget(context: Session, activity: Session, slug: string): LodyLinkTarget {
  if (URL_NORMALIZED_PATH_SEGMENTS.has(context.sessionId)) return {kind: 'unavailable'};
  const tabQuery =
    activity.sessionId === context.sessionId ? '' : `?${new URLSearchParams({tab: `session:${activity.sessionId}`})}`;
  return {
    kind: 'link',
    href: `https://lody.ai/${encodeURIComponent(slug)}/sessions/${encodeURIComponent(context.sessionId)}${tabQuery}`
  };
}

/**
 * Resolve a safe Lody destination for one selected session and its displayed tab.
 * @param session Root context supplying the canonical web session path.
 * @param activitySession Displayed tab whose identity is retained in the web query or native route.
 * @param workspaceId Opaque workspace identity used by the native fallback.
 * @param workspaceSlug Optional web-facing workspace selector.
 * @returns A synthetic marker, an unavailable marker, or the canonical external link.
 * @example
 * resolveLodyLinkTarget({session: root, activitySession: child, workspaceId: 'w1', workspaceSlug: 'leynos'});
 * // {kind: 'link', href: 'https://lody.ai/leynos/sessions/root?tab=session%3Achild'}
 */
export function resolveLodyLinkTarget({
  session,
  activitySession = session,
  workspaceId,
  workspaceSlug
}: LodyLinkInput): LodyLinkTarget {
  if (activitySession.source === 'demo') return {kind: 'synthetic'};
  const hasSlug = workspaceSlug !== undefined && workspaceSlug !== workspaceId;
  const hasWebRoute = hasSlug && /^[a-z0-9]+(?:-[a-z0-9]+)*$/u.test(workspaceSlug);
  if (hasWebRoute) return webSessionLinkTarget(session, activitySession, workspaceSlug);
  if (URL_NORMALIZED_PATH_SEGMENTS.has(activitySession.sessionId)) return {kind: 'unavailable'};
  return {
    kind: 'link',
    href: `lody://session/${encodeURIComponent(activitySession.sessionId)}?workspace=${encodeURIComponent(workspaceId)}`
  };
}

/**
 * Resolve the destination for a family's displayed tab, using its root context route.
 * @param family Grouped session family shown on the board.
 * @param workspaceId Opaque workspace identity used by the native fallback.
 * @param workspaceSlug Optional web-facing workspace selector.
 * @returns The canonical destination for the displayed member.
 * @example
 * const [family] = groupSessions(snapshot.sessions, new Map());
 * resolveFamilyLodyLink(family, 'family-workspace', 'leynos');
 */
export function resolveFamilyLodyLink(
  family: SessionFamily,
  workspaceId: string,
  workspaceSlug?: string | undefined
): LodyLinkTarget {
  return resolveLodyLinkTarget({
    session: family.context,
    activitySession: family.activity,
    workspaceId,
    workspaceSlug
  });
}

/**
 * Open a family's displayed Lody thread in a new, opener-isolated browsing context.
 * @param family Grouped session family whose displayed tab should open.
 * @param workspaceId Opaque workspace identity used by the native fallback.
 * @param workspaceSlug Optional web-facing workspace selector.
 * @returns Whether the family supplied an openable destination.
 * @example
 * openLodyThread(realFamily, 'w1', 'leynos'); // true, after window.open resolves the link
 */
export function openLodyThread(
  family: SessionFamily,
  workspaceId: string,
  workspaceSlug?: string | undefined
): boolean {
  const target = resolveFamilyLodyLink(family, workspaceId, workspaceSlug);
  if (target.kind !== 'link') return false;
  window.open(target.href, '_blank', 'noopener,noreferrer');
  return true;
}
