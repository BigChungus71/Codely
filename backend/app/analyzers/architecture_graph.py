"""Observed file-backed import graph. No parsing, target execution or runtime-call claims."""
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath
import re

import networkx as nx

from .structure_analyzer import RepositoryStructure
from .structure_extractor import stable_id


ROLES = {'api_application': 'application_entry_point', 'router': 'router', 'controller': 'controller',
         'service': 'service', 'data_access': 'data_access', 'database_model': 'database_model',
         'authentication': 'authentication', 'configuration': 'configuration', 'utility': 'utility',
         'test': 'test'}
PRIORITY = ['application_entry_point', 'router', 'controller', 'service', 'data_access',
            'database_model', 'authentication', 'configuration', 'utility', 'test', 'unclassified']
LIMITATIONS = [
    'Edges represent resolved file-backed static imports: importer -> imported module, not runtime calls.',
    'Unknown, ambiguous, namespace-only, external and stdlib imports do not create internal edges.',
    'Unparsed modules and unresolved imports can hide dependencies; isolation and metrics concern only observed edges.',
    'Confirmed roles mean explicit static evidence; inferred roles are naming heuristics, not enforced layers.',
    'Cycles are detected by strongly connected components with one witness each; not every simple cycle is enumerated.',
    'Graph metrics alone do not establish architecture quality, exploitability or vulnerability impact.',
]


def relative_file(value):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('Expected repository-relative file')
    windows = PureWindowsPath(value)
    if windows.drive or windows.root or '..' in windows.parts:
        raise ValueError('Expected repository-relative file')
    path = PurePosixPath(value.replace('\\', '/'))
    if path.is_absolute() or path.as_posix() == '.':
        raise ValueError('Expected repository-relative file')
    return path.as_posix()


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,256}', value) is not None


def _position(item):
    start, end = item.get('start_line'), item.get('end_line')
    return type(start) is int and type(end) is int and 1 <= start <= end


@dataclass(frozen=True)
class GraphOptions:
    max_nodes: int = 10000
    max_edges: int = 100000
    max_evidence_records: int = 200000

    def validate(self):
        for value in (self.max_nodes, self.max_edges, self.max_evidence_records):
            if type(value) is not int or value < 1:
                raise ValueError('Graph limits must be positive integers')


@dataclass
class ArchitectureGraph:
    schema_version: str
    status: str
    nodes: list[dict]
    edges: list[dict]
    statistics: dict
    diagnostics: list[dict]
    coverage: dict
    _graph: nx.DiGraph = field(repr=False)
    _file_ids: dict = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        self._file_ids = {node['file']: node['id'] for node in self.nodes}

    def to_dict(self):
        return deepcopy({name: getattr(self, name) for name in (
            'schema_version', 'status', 'nodes', 'edges', 'statistics', 'diagnostics', 'coverage')})

    @property
    def networkx_graph(self):
        """Return a detached frozen copy; callers cannot change internal traversal state."""
        return nx.freeze(deepcopy(self._graph))

    def module_for_file(self, file):
        canonical = relative_file(file)
        identifier = self._file_ids.get(canonical)
        return deepcopy(self._graph.nodes[identifier]) if identifier is not None else None

    def _require(self, module_id):
        if module_id not in self._graph:
            raise KeyError('Unknown graph node')

    def direct_dependencies(self, module_id):
        self._require(module_id)
        return sorted(self._graph.successors(module_id))

    def direct_dependents(self, module_id):
        self._require(module_id)
        return sorted(self._graph.predecessors(module_id))

    def transitive_dependencies(self, module_id, *, limits=None):
        from .architecture_traversal import traverse_dependencies
        return traverse_dependencies(self, module_id, direction='outgoing', limits=limits)

    def reverse_dependencies(self, module_id, *, limits=None):
        from .architecture_traversal import traverse_dependencies
        return traverse_dependencies(self, module_id, direction='incoming', limits=limits)


def _roles(structure, modules):
    result = {identifier: [] for identifier in modules}
    for entry in structure.classifications:
        identifier = entry.get('module_id')
        component = ROLES.get(entry.get('component'))
        confidence = entry.get('confidence')
        if identifier not in modules or component is None or confidence not in {'confirmed', 'inferred'}:
            continue
        evidence = entry.get('evidence', {})
        try:
            if relative_file(evidence.get('file')) != modules[identifier]['file']:
                continue
        except ValueError:
            continue
        safe_evidence = {'file': modules[identifier]['file']}
        if _position(evidence):
            safe_evidence.update(start_line=evidence['start_line'], end_line=evidence['end_line'])
        reason = entry.get('reason', '')
        result[identifier].append({'type': component, 'confidence': confidence,
            'reason': reason if _identifier(reason) else 'structure_classification', 'evidence': safe_evidence})
    for identifier, module in modules.items():
        entries = result[identifier]
        if not entries and PurePosixPath(module['file']).name in {'__main__.py', 'main.py', 'app.py', 'wsgi.py', 'asgi.py'}:
            entries.append({'type': 'application_entry_point', 'confidence': 'inferred',
                'reason': 'entry_point_filename_heuristic', 'evidence': {'file': module['file']}})
        # Prefer explicit evidence for a component; keep all evidence of the selected confidence.
        confirmed = {item['type'] for item in entries if item['confidence'] == 'confirmed'}
        entries = [item for item in entries if item['confidence'] == 'confirmed' or item['type'] not in confirmed]
        unique = {(item['type'], item['confidence'], item['reason'], tuple(item['evidence'].items())): item
                  for item in entries}
        result[identifier] = sorted(unique.values(), key=lambda item: (
            item['confidence'] != 'confirmed', PRIORITY.index(item['type']),
            item['evidence'].get('start_line', 0), item['evidence'].get('end_line', 0), item['reason']))
    return result


def _statistics(graph):
    strong = sorted((sorted(component) for component in nx.strongly_connected_components(graph)), key=tuple)
    weak = sorted((sorted(component) for component in nx.weakly_connected_components(graph)), key=tuple)
    cyclic = []
    strong_rows = []
    for members in strong:
        identifier = stable_id('scc', *members)
        is_cycle = len(members) > 1 or graph.has_edge(members[0], members[0])
        strong_rows.append({'id': identifier, 'node_ids': members, 'size': len(members), 'cyclic': is_cycle})
        if is_cycle:
            found = nx.find_cycle(graph.subgraph(members), source=members[0])
            cycle = [source for source, _target in found]
            offset = min(range(len(cycle)), key=lambda index: cycle[index])
            cycle = cycle[offset:] + cycle[:offset]
            cycle.append(cycle[0])
            cyclic.append({'component_id': identifier, 'node_ids': members,
                'witness': {'node_ids': cycle,
                    'edge_ids': [graph.edges[source, target]['id'] for source, target in zip(cycle, cycle[1:])]}})
    weak_index = {node: index for index, members in enumerate(weak) for node in members}
    edge_counts = [0] * len(weak)
    for source, _target in graph.edges:
        edge_counts[weak_index[source]] += 1
    isolated = sorted(nx.isolates(graph))
    return {'node_count': graph.number_of_nodes(), 'edge_count': graph.number_of_edges(),
        'import_evidence_count': sum(len(data['evidence']) for _, _, data in graph.edges(data=True)),
        'is_acyclic': not cyclic, 'self_import_count': nx.number_of_selfloops(graph),
        'isolated_modules': isolated, 'isolated_module_count': len(isolated),
        'max_fan_in': max((degree for _, degree in graph.in_degree), default=0),
        'max_fan_out': max((degree for _, degree in graph.out_degree), default=0),
        'strong_component_count': len(strong), 'strong_components': strong_rows,
        'cyclic_component_count': len(cyclic), 'cyclic_components': cyclic,
        'weak_component_count': len(weak), 'weak_components': [
            {'id': stable_id('wcc', *members), 'node_ids': members, 'size': len(members), 'edge_count': edge_counts[index]}
            for index, members in enumerate(weak)]}


def build_architecture_graph(structure: RepositoryStructure, *, options: GraphOptions | None = None) -> ArchitectureGraph:
    """Consume existing AST evidence without reading a repository or parsing again."""
    if not isinstance(structure, RepositoryStructure):
        raise TypeError('Expected RepositoryStructure, not a path or arbitrary JSON')
    options = options or GraphOptions()
    options.validate()
    diagnostics = []
    modules, files = {}, set()
    duplicate_modules = 0
    for module in sorted(structure.modules, key=lambda item: (str(item.get('id', '')), str(item.get('file', '')),
            bool(item.get('parsed')), tuple(sorted(str(name) for name in (item.get('names') or []))))):
        try:
            identifier, file = module['id'], relative_file(module['file'])
            if not _identifier(identifier):
                raise ValueError('invalid')
            if not isinstance(module.get('names', []), list):
                raise ValueError('invalid')
            names = sorted({name for name in module.get('names', []) if isinstance(name, str)
                            and all(part.isidentifier() for part in name.split('.'))}, key=lambda name: (len(name), name))
        except (ValueError, KeyError):
            diagnostics.append({'code': 'invalid_module_skipped'})
            continue
        if identifier in modules or file in files:
            previous = modules.get(identifier)
            if (previous and previous['file'] == file and previous['parsed'] == bool(module.get('parsed'))
                    and previous['module_names'] == names):
                duplicate_modules += 1
                continue
            diagnostics.append({'code': 'conflicting_module_skipped'})
            continue
        if len(modules) >= options.max_nodes:
            diagnostics.append({'code': 'graph_node_limit'})
            break
        modules[identifier] = {'id': identifier, 'file': file, 'parsed': bool(module.get('parsed')),
                               'module_names': names}
        files.add(file)
    roles = _roles(structure, modules)
    graph = nx.DiGraph()
    for identifier, module in sorted(modules.items()):
        entries = roles[identifier]
        graph.add_node(identifier, **module,
            label=next(iter(module['module_names']), PurePosixPath(module['file']).stem),
            type=entries[0]['type'] if entries else 'unclassified', classifications=entries,
            classification_confidence=entries[0]['confidence'] if entries else 'unclassified')
    imports, conflicts = {}, set()
    for item in structure.imports:
        if item['id'] in imports and imports[item['id']] != item:
            conflicts.add(item['id'])
        imports[item['id']] = item
    for identifier in sorted(conflicts):
        del imports[identifier]
        diagnostics.append({'code': 'conflicting_import_record_skipped'})
    grouped = {}
    seen_evidence = set()
    evidence_count = duplicates = 0
    for dependency in sorted(structure.internal_dependencies, key=lambda item: (
            str(item.get('source_module_id', '')), str(item.get('target_module_id', '')), str(item.get('import_id', '')))):
        try:
            source, target = dependency['source_module_id'], dependency['target_module_id']
            imported = imports[dependency['import_id']]
            if (source not in modules or target not in modules or dependency['relationship'] != 'imports'
                    or imported['resolution'] != 'internal' or imported['candidate_module_ids'] != [target]
                    or imported['module_id'] != source or not _identifier(imported['id'])
                    or relative_file(dependency['file']) != modules[source]['file']
                    or relative_file(imported['file']) != modules[source]['file']
                    or not _position(imported) or not _position(dependency)
                    or (dependency['start_line'], dependency['end_line']) != (imported['start_line'], imported['end_line'])):
                raise ValueError('Invalid resolved import evidence')
        except (ValueError, KeyError, TypeError):
            diagnostics.append({'code': 'invalid_or_dangling_dependency_skipped'})
            continue
        key = source, target
        if imported['id'] in seen_evidence:
            duplicates += 1
            continue
        if key not in grouped and len(grouped) >= options.max_edges:
            diagnostics.append({'code': 'graph_edge_limit'})
            break
        if evidence_count >= options.max_evidence_records:
            diagnostics.append({'code': 'graph_evidence_limit'})
            break
        seen_evidence.add(imported['id'])
        evidence = {'import_id': imported['id'], 'file': modules[source]['file'],
            'start_line': imported['start_line'], 'end_line': imported['end_line'],
            'resolution': 'internal', 'conditional': bool(imported.get('conditional')),
            'target_parsed': modules[target]['parsed']}
        if _identifier(imported.get('scope_id')):
            evidence['scope_id'] = imported['scope_id']
        grouped.setdefault(key, []).append(evidence)
        evidence_count += 1
    for (source, target), evidence in sorted(grouped.items()):
        graph.add_edge(source, target, id=stable_id('edge', source, target, 'imports'),
                       source=source, target=target, relationship='imports', evidence=evidence,
                       evidence_count=len(evidence))
    for identifier in graph:
        graph.nodes[identifier]['fan_in'] = graph.in_degree(identifier)
        graph.nodes[identifier]['fan_out'] = graph.out_degree(identifier)
    statistics = _statistics(graph)
    status = structure.status if structure.status in {'complete', 'partial', 'error'} else 'error'
    if (diagnostics or structure.diagnostics or any(not module['parsed'] for module in modules.values())) and status == 'complete':
        status = 'partial'
    source_diagnostics = []
    for item in structure.diagnostics:
        row = {'code': item['code'] if _identifier(item.get('code')) else 'structure_diagnostic', 'source': 'structure'}
        try:
            if 'file' in item:
                row['file'] = relative_file(item['file'])
        except ValueError:
            pass
        source_diagnostics.append(row)
    coverage = {'structure_status': structure.status, 'relationship_scope': 'resolved_internal_imports_only',
        'structure_modules': len(structure.modules), 'graph_modules': len(modules),
        'parsed_modules': sum(module['parsed'] for module in modules.values()),
        'unparsed_modules': sum(not module['parsed'] for module in modules.values()),
        'unresolved_imports': sum(item.get('resolution') == 'unresolved' for item in structure.imports),
        'ambiguous_imports': sum(item.get('resolution') == 'ambiguous' for item in structure.imports),
        'namespace_imports_without_file': sum(item.get('reason') == 'namespace_package_without_source_file' for item in structure.imports),
        'duplicate_dependency_records_removed': duplicates,
        'duplicate_module_records_removed': duplicate_modules,
        'limits': {'max_nodes': options.max_nodes, 'max_edges': options.max_edges, 'max_evidence_records': options.max_evidence_records},
        'limitations': LIMITATIONS}
    nodes = [deepcopy(data) for _, data in graph.nodes(data=True)]
    edges = [deepcopy(data) for _, _, data in graph.edges(data=True)]
    return ArchitectureGraph('1.0.0', status, nodes, edges, statistics,
        sorted(diagnostics + source_diagnostics, key=lambda item: (item['code'], item.get('file', ''))),
        coverage, nx.freeze(graph))
