"""Cycle-safe bounded traversals of observed import edges; no vulnerability analysis."""
from collections import deque
from copy import deepcopy
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TraversalLimits:
    max_depth: int = 32
    max_nodes: int = 1000
    max_edges: int = 10000
    max_paths: int = 128

    def validate(self):
        if type(self.max_depth) is not int or not 0 <= self.max_depth <= 256:
            raise ValueError('Traversal depth must be an integer between 0 and 256')
        for value in (self.max_nodes, self.max_edges, self.max_paths):
            if type(value) is not int or value < 1:
                raise ValueError('Traversal budgets must be positive integers')


@dataclass
class TraversalResult:
    root_id: str
    direction: str
    nodes: list[dict]
    paths: list[dict]
    evidence_edges: list[dict]
    examined_edges: int
    visited_nodes: int
    truncated: bool
    limit_reasons: list[str]
    limits: dict
    coverage_status: str

    def to_dict(self):
        return asdict(self)


def traverse_dependencies(architecture, module_id, *, direction='outgoing', limits=None):
    """One deterministic shortest evidence path per reached module, not all paths.

    Incoming traversal walks upstream, but returned paths and edge evidence are
    always oriented importer -> imported. Paths refer to de-duplicated evidence
    edges rather than copying potentially large import lists into every path.
    """
    architecture._require(module_id)
    if direction not in {'outgoing', 'incoming'}:
        raise ValueError('Direction must be outgoing or incoming')
    limits = limits or TraversalLimits()
    limits.validate()
    graph = architecture._graph
    neighbors = graph.successors if direction == 'outgoing' else graph.predecessors
    queue = deque([module_id])
    depths = {module_id: 0}
    parents = {}
    reasons = set()
    examined = 0
    stopped = False
    while queue and not stopped:
        current = queue.popleft()
        adjacent = sorted(neighbors(current))
        if depths[current] >= limits.max_depth:
            if any(node not in depths for node in adjacent):
                reasons.add('max_depth')
            continue
        for neighbor in adjacent:
            if examined >= limits.max_edges:
                reasons.add('max_edges')
                stopped = True
                break
            examined += 1
            if neighbor in depths:
                continue
            if len(depths) >= limits.max_nodes:
                reasons.add('max_nodes')
                stopped = True
                break
            parents[neighbor] = current
            depths[neighbor] = depths[current] + 1
            queue.append(neighbor)
    reached = sorted((node for node in depths if node != module_id), key=lambda node: (depths[node], node))
    paths = []
    evidence = {}
    for target in reached[:limits.max_paths]:
        chain = [target]
        while chain[-1] != module_id:
            chain.append(parents[chain[-1]])
        if direction == 'outgoing':
            chain.reverse()
        edge_ids = []
        for source, destination in zip(chain, chain[1:]):
            data = graph.edges[source, destination]
            evidence[data['id']] = deepcopy(data)
            edge_ids.append(data['id'])
        paths.append({'target_id': target, 'depth': depths[target], 'node_ids': chain, 'edge_ids': edge_ids})
    if len(reached) > limits.max_paths:
        reasons.add('max_paths')
    return TraversalResult(module_id, direction,
        [{'id': node, 'depth': depths[node]} for node in reached], paths,
        [evidence[key] for key in sorted(evidence)], examined, len(depths), bool(reasons),
        sorted(reasons), asdict(limits), architecture.status)
