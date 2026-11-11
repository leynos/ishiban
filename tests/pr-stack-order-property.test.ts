/** @file Check PR stack headings against generated indexed graphs. */
import {expect, it} from 'bun:test';
import fc from 'fast-check';
import type {Session} from '../src/contracts';
import {selectStackTop, type PrStackFacts} from '../src/ui/pr-stack-order';

type Pr = Session['pullRequests'][number];
type Topology = 'branch' | 'cycle' | 'incomplete' | 'random';
type FactMode = 'known' | 'missing' | 'fork' | 'unknownFork' | 'noHead' | 'noBase';

interface NodeSeed {
  readonly parentKey: number;
  readonly repository: 0 | 1;
  readonly repositoryCase: number;
  readonly mode: FactMode;
  readonly status: 'open' | 'draft' | 'merged' | 'closed';
  readonly mergeBucket: number;
}

interface ModelNode extends NodeSeed {
  readonly index: number;
  readonly parent: number | null;
  readonly url: string;
}

interface GraphCase {
  readonly topology: Topology;
  readonly seeds: readonly NodeSeed[];
  readonly orderKeys: readonly number[];
}

const FORCED_PARENTS: Readonly<Record<Topology, readonly (number | null)[]>> = {
  branch: [null, 0, 0],
  cycle: [2, 0, 1],
  incomplete: [null, 0, 0],
  random: []
};
const FORCED_MODES: Readonly<Record<Topology, readonly FactMode[]>> = {
  branch: ['known', 'known', 'known'],
  cycle: ['known', 'known', 'known'],
  incomplete: ['known', 'missing', 'fork'],
  random: []
};
const USABLE_HEAD = new Set<FactMode>(['known', 'noBase']);
const USABLE_BASE = new Set<FactMode>(['known', 'noHead']);
const INVALID_MERGE_TIMES = ['2026-02-30T00:00:00Z', 'not-a-time'] as const;
const LIFECYCLE_PRIORITY: Readonly<Record<NodeSeed['status'], number>> = {
  open: 2,
  draft: 2,
  merged: 1,
  closed: 0
};

/** Keep provider precision separate from the model's known merge instant. */
function encodedMergeTime(bucket: number, index: number): string | null {
  if (bucket < 0) return bucket === -1 ? null : (INVALID_MERGE_TIMES[index % 2] ?? null);
  const instant = new Date(1_700_000_000_000 + bucket * 1000 + (bucket === 3 ? 500 : 0)).toISOString();
  if (index % 2 === 0) return instant;
  const fraction = bucket === 3 ? '.5Z' : 'Z';
  return instant.replace(bucket === 3 ? '.500Z' : '.000Z', fraction);
}

/** Supply indexed parent evidence, including genuine branch and cycle controls. */
function parentFor(seed: NodeSeed, index: number, count: number, topology: Topology): number | null {
  const forced = FORCED_PARENTS[topology][index];
  if (forced !== undefined) return forced;
  return seed.parentKey < 0 ? null : seed.parentKey % count;
}

/** Keep the first three topology witnesses in one repository. */
function repositoryFor(seed: NodeSeed, index: number, topology: Topology): 0 | 1 {
  if (topology === 'random') return seed.repository;
  return index < 3 ? 0 : seed.repository;
}

/** Vary the ASCII case of each URL spelling without changing repository identity. */
function repositoryPath(repository: 0 | 1, caseKey: number): string {
  const owner = caseKey % 2 === 0 ? 'owner' : 'Owner';
  const name = caseKey < 2 ? 'project' : 'Project';
  return `${owner}${repository}/${name}`;
}

/** Turn generated indexes into distinct canonical GitHub identities. */
function modelNodes(graph: GraphCase): ModelNode[] {
  return graph.seeds.map((seed, index) => {
    const repository = repositoryFor(seed, index, graph.topology);
    const forcedStatus = graph.topology === 'incomplete' ? (['merged', 'open', 'closed'] as const)[index] : undefined;
    return {
      ...seed,
      index,
      parent: parentFor(seed, index, graph.seeds.length, graph.topology),
      repository,
      mode: FORCED_MODES[graph.topology][index] ?? seed.mode,
      status: forcedStatus ?? seed.status,
      url: `https://github.com/${repositoryPath(repository, seed.repositoryCase)}/pull/${1000 + index}${index % 2 === 0 ? '' : '/'}`
    };
  });
}

/** Encode one model parent identity without reading selector branch comparisons. */
function baseBranch(node: ModelNode): string | null {
  if (node.mode === 'noBase') return null;
  return node.parent === null ? 'main' : `branch-${node.parent}`;
}

/** Preserve the distinction between known same-repo, fork and unknown facts. */
function forkFact(mode: FactMode): boolean | null {
  if (mode === 'fork') return true;
  if (mode === 'unknownFork') return null;
  return false;
}

/** Publish only the provider facts selected by the generated evidence mode. */
function stackFacts(nodes: readonly ModelNode[]): Readonly<Record<string, PrStackFacts>> {
  const entries = nodes.flatMap((node) => {
    if (node.mode === 'missing') return [];
    const fact: PrStackFacts = {
      baseRefName: baseBranch(node),
      headRefName: node.mode === 'noHead' ? null : `branch-${node.index}`,
      isCrossRepository: forkFact(node.mode),
      mergedAt: encodedMergeTime(node.mergeBucket, node.index)
    };
    return [[node.url, fact] as const];
  });
  return Object.fromEntries(entries);
}

/** Decide edge eligibility from indexed intent and known evidence, not branch text. */
function hasModelEdge(parent: ModelNode, child: ModelNode): boolean {
  if (!USABLE_HEAD.has(parent.mode) || !USABLE_BASE.has(child.mode)) return false;
  if (parent.repository !== child.repository) return false;
  return child.parent === parent.index && child.index !== parent.index;
}

/** Missing or invalid provider facts cannot contribute merge chronology. */
function mergeRank(node: ModelNode): number {
  if (node.mode === 'missing' || node.mergeBucket < 0) return Number.NEGATIVE_INFINITY;
  return node.mergeBucket;
}

/** Select the best graph tip by independent candidate-set refinement. */
function expectedTop(nodes: readonly ModelNode[]): string {
  const prerequisites = new Set(
    nodes.flatMap((child) => nodes.flatMap((parent) => (hasModelEdge(parent, child) ? [parent.index] : [])))
  );
  const tips = nodes.filter((node) => !prerequisites.has(node.index));
  const candidates = tips.length > 0 ? tips : nodes;
  const highestLifecycle = Math.max(...candidates.map((node) => LIFECYCLE_PRIORITY[node.status]));
  const lifecycleWinners = candidates.filter((node) => LIFECYCLE_PRIORITY[node.status] === highestLifecycle);
  const latestMerge = Math.max(...lifecycleWinners.map((node) => mergeRank(node)));
  return lifecycleWinners.flatMap((node) => (mergeRank(node) === latestMerge ? [node.url] : [])).toSorted()[0] ?? '';
}

/** Render each semantic node as one public PR association. */
function publicPrs(nodes: readonly ModelNode[]): Pr[] {
  return nodes.map((node) => ({url: node.url, title: `PR ${node.index}`, status: node.status}));
}

/** Exercise three catalogue orders; generated keys induce arbitrary permutations. */
function checkGraph(graph: GraphCase): void {
  const nodes = modelNodes(graph);
  const prs = publicPrs(nodes);
  const facts = stackFacts(nodes);
  const expected = expectedTop(nodes);
  const shuffled = prs.toSorted((left, right) => {
    const leftIndex = nodes.findIndex((node) => node.url === left.url);
    const rightIndex = nodes.findIndex((node) => node.url === right.url);
    return (graph.orderKeys[leftIndex] ?? 0) - (graph.orderKeys[rightIndex] ?? 0) || leftIndex - rightIndex;
  });
  for (const order of [prs, prs.toReversed(), shuffled]) {
    expect(selectStackTop(order, facts)?.url).toBe(expected);
  }
}

const seed = fc.record({
  parentKey: fc.integer({min: -1, max: 7}),
  repository: fc.constantFrom(0 as const, 1 as const),
  repositoryCase: fc.integer({min: 0, max: 3}),
  mode: fc.constantFrom<FactMode>('known', 'missing', 'fork', 'unknownFork', 'noHead', 'noBase'),
  status: fc.constantFrom<'open' | 'draft' | 'merged' | 'closed'>('open', 'draft', 'merged', 'closed'),
  mergeBucket: fc.integer({min: -2, max: 3})
});

it.each([
  'branch',
  'cycle',
  'incomplete',
  'random'
] as const)('selects from generated %s PR graphs regardless of catalogue order', async (topology) => {
  const isClosedCycle = topology === 'cycle';
  const graph = fc.record({
    topology: fc.constant(topology),
    seeds: fc.array(seed, {minLength: isClosedCycle ? 3 : 4, maxLength: isClosedCycle ? 3 : 8}),
    orderKeys: fc.array(fc.integer({min: 0, max: 100_000}), {minLength: 8, maxLength: 8})
  });
  await fc.assert(fc.property(graph, checkGraph), {numRuns: 40});
});
