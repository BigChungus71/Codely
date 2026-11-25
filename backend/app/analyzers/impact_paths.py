"""Bounded shortest import paths supplement the existing reverse traversal helper."""
from .structure_extractor import stable_id


def dependency_analysis(architecture, node_id, options, edge_index):
    traversal = architecture.reverse_dependencies(node_id, limits=options.traversal)
    distances = {node_id: 0, **{node['id']: node['depth'] for node in traversal.nodes}}
    reasons = set(traversal.limit_reasons)
    paths = {}

    def add(chain):
        identifier = stable_id('impact_path', *chain)
        if identifier not in paths:
            paths[identifier] = {'id': identifier, 'target_id': chain[0],
                'distance': len(chain)-1, 'node_ids': chain,
                'edge_ids': [edge_index[source, target]['id'] for source, target in zip(chain, chain[1:])]}

    for path in traversal.paths:
        add(path['node_ids'])
    reached = sorted((node for node in distances if node != node_id), key=lambda node: (distances[node], node))
    # Edges must decrease shortest distance; cycles cannot recur in this path DAG.
    successors = {}
    searched = 0
    search_stopped = False
    for source in reached:
        steps = []
        for target in architecture.direct_dependencies(source):
            if searched >= options.max_path_search_edges:
                reasons.add('max_path_search_edges')
                search_stopped = True
                break
            searched += 1
            if target in distances and distances[target] == distances[source]-1:
                steps.append(target)
        successors[source] = steps
        if search_stopped:
            break
    expansions = 0
    exhausted = False
    for target in reached:
        stack = [[target]]
        while stack:
            if expansions >= options.max_path_expansions:
                reasons.add('max_path_expansions')
                exhausted = True
                break
            chain = stack.pop()
            expansions += 1
            if chain[-1] == node_id:
                identifier = stable_id('impact_path', *chain)
                if identifier not in paths and len(paths) >= options.traversal.max_paths:
                    reasons.add('max_paths')
                    exhausted = True
                    break
                add(chain)
            else:
                for step in reversed(successors.get(chain[-1], [])):
                    stack.append(chain + [step])
        if exhausted:
            break
    direct = [node for node in reached if distances[node] == 1]
    transitive = [node for node in reached if distances[node] > 1]
    ordered_paths = sorted(paths.values(), key=lambda item: (item['distance'], item['target_id'], item['node_ids']))
    edge_ids = {edge for path in ordered_paths for edge in path['edge_ids']}
    edge_ids.update(edge_index[source, node_id]['id'] for source in direct)
    return {'id': stable_id('module_impact', node_id), 'vulnerable_node_id': node_id,
        'direct_dependent_node_ids': direct, 'transitive_dependent_node_ids': transitive,
        'dependency_distances': [{'node_id': node, 'distance': distances[node],
            'exposure': 'direct_dependent' if distances[node] == 1 else 'transitive_dependent'} for node in reached],
        'paths': ordered_paths, 'relevant_edge_ids': sorted(edge_ids),
        'summary': {'direct_dependents': len(direct), 'transitive_dependents': len(transitive),
            'observed_direct_dependents': len([node for node in architecture.direct_dependents(node_id) if node != node_id]),
            'returned_paths': len(ordered_paths)},
        'coverage': {'graph_status': architecture.status, 'truncated': bool(reasons),
            'limit_reasons': sorted(reasons), 'visited_nodes': traversal.visited_nodes,
            'examined_edges': traversal.examined_edges, 'path_search_edges': searched,
            'path_expansions': expansions, 'path_policy': 'bounded_shortest_import_paths_only'}}
