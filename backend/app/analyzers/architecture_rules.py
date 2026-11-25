"""Deterministic architecture evaluation and recommendation engine.

Consumes existing RepositoryStructure and ArchitectureGraph results without
re-parsing source files, invoking a scanner, executing target code or calling an LLM.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass, field
import re

from .architecture_graph import ArchitectureGraph, relative_file
from .architecture_policy import (
    ArchitecturePolicy,
    ArchitectureThresholds,
    coerce_policy,
)
from .structure_analyzer import RepositoryStructure
from .structure_extractor import stable_id


PRIORITY_ORDER = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}

INTERNAL_UNRESOLVED_REASONS = {
    'local_module_not_found',
    'relative_import_beyond_source_root',
    'imported_attribute_not_statically_identified',
    'parent_module_is_not_uniquely_a_package',
}

RESPONSIBILITY_GROUPS = {
    'application_entry_point': 'transport_interface',
    'router': 'transport_interface',
    'controller': 'transport_interface',
    'service': 'service_domain',
    'data_access': 'persistence',
    'database_model': 'persistence',
    'authentication': 'authentication',
    'configuration': 'configuration',
}

EXTERNAL_BASE_ROOTS = {'object', 'builtins.object', 'Exception', 'BaseException'}

LIMITATIONS = [
    'Architecture observations are static structural indicators and heuristic guidelines, not runtime defects or security vulnerabilities.',
    'Edges reflect observed static internal imports only; dynamic imports, reflection, runtime hooks and unknown external dependencies are not fully captured.',
    'Inferred module roles rely on filename/path heuristics rather than confirmed framework or database bindings.',
    'Size, coupling, inheritance and responsibility thresholds are configurable heuristics and do not produce an overall architecture quality score.',
    'Recommendations are advisory, context-dependent and require human engineering review; source files are never automatically rewritten.',
    'No runtime latency, throughput, scalability improvement or exploitability probability is claimed without runtime measurement.',
]


def _token(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,256}', value) is not None


@dataclass(frozen=True)
class ArchitectureEvaluationOptions:
    max_observations: int = 500
    max_affected_modules_per_observation: int = 100
    max_source_locations_per_observation: int = 64
    max_evidence_edges: int = 100
    max_dependency_paths: int = 64
    max_diagnostics: int = 100

    def validate(self) -> None:
        for name in (
            'max_observations',
            'max_affected_modules_per_observation',
            'max_source_locations_per_observation',
            'max_evidence_edges',
            'max_dependency_paths',
            'max_diagnostics',
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f'Evaluation budget {name} must be a positive integer')


@dataclass
class ArchitectureEvaluationResult:
    schema_version: str
    status: str
    policy: dict
    summary: dict
    observations: list[dict]
    supporting_metrics: dict
    diagnostics: list[dict]
    coverage: dict
    _module_catalog: dict = field(default_factory=dict, repr=False)
    _symbol_catalog: dict = field(default_factory=dict, repr=False)
    _path_catalog: dict = field(default_factory=dict, repr=False)
    _edge_catalog: dict = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict:
        return deepcopy(
            {
                'schema_version': self.schema_version,
                'status': self.status,
                'policy': self.policy,
                'summary': self.summary,
                'observations': self.observations,
                'supporting_metrics': self.supporting_metrics,
                'diagnostics': self.diagnostics,
                'coverage': self.coverage,
            }
        )

    def gemini_evidence_package(self, observation_id: str | None = None) -> dict:
        """Build a nontext, deterministic evidence package for downstream Gemini explanations."""
        if observation_id is not None:
            selected = [obs for obs in self.observations if obs['id'] == observation_id]
            if not selected:
                raise KeyError(f'Unknown observation ID: {observation_id}')
        else:
            selected = list(self.observations)

        module_ids: set[str] = set()
        symbol_ids: set[str] = set()
        path_ids: set[str] = set()
        edge_ids: set[str] = set()
        compact_observations = []
        for obs in selected:
            obs_module_ids = [m['module_id'] for m in obs['affected_modules']]
            obs_symbol_ids = [s['id'] for s in obs['affected_symbols']]
            obs_path_ids = [p['id'] for p in obs['supporting_graph_evidence']['dependency_paths']]
            obs_edge_ids = list(obs['supporting_graph_evidence']['edge_ids'])
            module_ids.update(obs_module_ids)
            module_ids.update(obs['supporting_graph_evidence']['node_ids'])
            symbol_ids.update(obs_symbol_ids)
            path_ids.update(obs_path_ids)
            edge_ids.update(obs_edge_ids)
            compact_observations.append(
                {
                    'id': obs['id'],
                    'rule_id': obs['rule_id'],
                    'category': obs['category'],
                    'priority': obs['priority'],
                    'title': obs['title'],
                    'explanation': obs['explanation'],
                    'evidence_classification': obs['evidence_classification'],
                    'confidence': obs['confidence'],
                    'observed_metric': deepcopy(obs['observed_metric']),
                    'configured_threshold': deepcopy(obs['configured_threshold']),
                    'suggested_improvement': obs['suggested_improvement'],
                    'trade_offs': list(obs['trade_offs']),
                    'validation_method': obs['validation_method'],
                    'known_limitations': list(obs['known_limitations']),
                    'affected_module_ids': obs_module_ids,
                    'affected_symbol_ids': obs_symbol_ids,
                    'source_locations': deepcopy(obs['source_locations']),
                    'dependency_path_ids': obs_path_ids,
                    'relevant_edge_ids': obs_edge_ids,
                    'advisory_only': obs['advisory_only'],
                }
            )

        return deepcopy(
            {
                'schema_version': '1.0.0',
                'status': self.status,
                'scope': {
                    'type': 'observation' if observation_id else 'repository',
                    'observation_id': observation_id,
                },
                'user_constraints': self.policy,
                'supporting_metrics': self.supporting_metrics,
                'observations': compact_observations,
                'relevant_modules': [
                    self._module_catalog[mid] for mid in sorted(module_ids) if mid in self._module_catalog
                ],
                'relevant_symbols': [
                    self._symbol_catalog[sid] for sid in sorted(symbol_ids) if sid in self._symbol_catalog
                ],
                'relevant_edges': [
                    self._edge_catalog[eid] for eid in sorted(edge_ids) if eid in self._edge_catalog
                ],
                'dependency_paths': [
                    self._path_catalog[pid] for pid in sorted(path_ids) if pid in self._path_catalog
                ],
                'analysis_limitations': list(LIMITATIONS),
                'interpretation_guidance': (
                    'Use these deterministic observations, metrics, constraints and dependency paths to explain '
                    'structural trade-offs in context. Treat heuristics and inferred roles as review candidates, '
                    'do not invent runtime performance gains or quality scores, and keep all recommendations advisory.'
                ),
            }
        )


def _consistent(structure: RepositoryStructure, architecture: ArchitectureGraph) -> bool:
    if architecture.coverage.get('structure_modules') != len(structure.modules):
        return False
    modules = {module['id']: module for module in structure.modules}
    relationships = {
        (
            dep['source_module_id'],
            dep['target_module_id'],
            dep['import_id'],
            dep['file'],
            dep['start_line'],
            dep['end_line'],
        )
        for dep in structure.internal_dependencies
    }
    for identifier, node in architecture._graph.nodes(data=True):
        module = modules.get(identifier)
        if module is None or relative_file(module['file']) != node['file'] or bool(module['parsed']) != node['parsed']:
            return False
    for source, target, edge in architecture._graph.edges(data=True):
        for proof in edge['evidence']:
            if (
                source,
                target,
                proof['import_id'],
                proof['file'],
                proof['start_line'],
                proof['end_line'],
            ) not in relationships:
                return False
    return True


def _sanitize_diagnostics(items: list[dict], source: str) -> list[dict]:
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = {
            'source': source,
            'code': item['code'] if _token(item.get('code')) else 'analysis_diagnostic',
        }
        try:
            if item.get('file'):
                row['file'] = relative_file(item['file'])
        except ValueError:
            pass
        if type(item.get('start_line')) is int and item['start_line'] > 0:
            row['start_line'] = item['start_line']
        result.append(row)
    return result


def _module_descriptor(node: dict) -> dict:
    return {
        'module_id': node['id'],
        'file': node['file'],
        'label': node['label'],
        'role': node['type'],
        'classification_confidence': node['classification_confidence'],
    }


def _symbol_descriptor(symbol: dict) -> dict:
    kind = symbol.get('kind') or ('class' if 'bases' in symbol else 'function')
    return {
        'id': symbol['id'],
        'module_id': symbol['module_id'],
        'name': symbol['name'],
        'qualified_name': symbol['qualified_name'],
        'kind': kind,
        'file': symbol['file'],
        'start_line': symbol['start_line'],
        'end_line': symbol['end_line'],
    }


def _effective_parameter_count(func: dict) -> tuple[int, int]:
    params = func.get('parameters') or []
    total = len(params)
    if func.get('kind') != 'method' or not params:
        return total, total
    first_name = params[0].get('name')
    decorator_names = {
        str(d.get('name', '')).split('.')[-1] for d in (func.get('decorators') or []) if isinstance(d, dict)
    }
    if first_name == 'self':
        return max(0, total - 1), total
    if first_name == 'cls' and 'staticmethod' not in decorator_names:
        return max(0, total - 1), total
    return total, total


def _is_test_node(node: dict) -> bool:
    return node.get('type') == 'test' or any(
        entry.get('type') == 'test' for entry in (node.get('classifications') or [])
    )


def _node_line_count(module: dict | None, file_rec: dict | None) -> int | None:
    if isinstance(file_rec, dict) and type(file_rec.get('line_count')) is int:
        return file_rec['line_count']
    if isinstance(module, dict) and type(module.get('end_line')) is int:
        return module['end_line']
    return None


def _build_inheritance_index(
    structure: RepositoryStructure,
) -> tuple[dict[str, dict], dict[str, dict]]:
    classes_by_id = {cls['id']: cls for cls in structure.classes}
    module_top_classes: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for cls in structure.classes:
        if cls.get('parent_id') == cls.get('module_id'):
            module_top_classes[(cls['module_id'], cls['name'])].append(cls)

    modules_by_name: dict[str, list[str]] = defaultdict(list)
    for mod in structure.modules:
        for name in mod.get('names') or []:
            modules_by_name[name].append(mod['id'])

    # Map (module_id, binding) -> (target_module_id, exported_symbol_name | None)
    import_bindings: dict[tuple[str, str], tuple[str, str | None]] = {}
    for imp in structure.imports:
        if imp.get('resolution') != 'internal':
            continue
        candidates = imp.get('candidate_module_ids') or []
        if len(candidates) != 1:
            continue
        target_mod_id = candidates[0]
        binding = imp.get('binding')
        if not binding:
            continue
        if imp.get('kind') == 'from' and imp.get('name') and imp.get('name') != '*':
            import_bindings[(imp['module_id'], binding)] = (target_mod_id, imp['name'])
        else:
            import_bindings[(imp['module_id'], binding)] = (target_mod_id, None)

    def resolve_base(cls: dict, base: dict) -> tuple[dict | None, bool]:
        target_id = base.get('target_symbol_id')
        if target_id and target_id in classes_by_id:
            return classes_by_id[target_id], True
        if base.get('is_dynamic'):
            return None, False
        name = base.get('name') or ''
        if not name:
            return None, False
        first, _, tail = name.partition('.')
        binding_hit = import_bindings.get((cls['module_id'], first))
        if binding_hit:
            target_mod_id, imported_symbol = binding_hit
            if imported_symbol and not tail:
                hits = module_top_classes.get((target_mod_id, imported_symbol), [])
                if len(hits) == 1:
                    return hits[0], True
            elif not imported_symbol and tail and '.' not in tail:
                hits = module_top_classes.get((target_mod_id, tail), [])
                if len(hits) == 1:
                    return hits[0], True
        qual = base.get('import_qualified_name')
        if qual and '.' in qual:
            mod_part, _, attr_part = qual.rpartition('.')
            mod_hits = modules_by_name.get(mod_part, [])
            if len(mod_hits) == 1:
                hits = module_top_classes.get((mod_hits[0], attr_part), [])
                if len(hits) == 1:
                    return hits[0], True
        return None, False

    memo: dict[str, dict] = {}
    visiting: set[str] = set()

    def compute(class_id: str) -> dict:
        if class_id in memo:
            return memo[class_id]
        if class_id in visiting:
            return {
                'depth': 1,
                'chain_ids': [class_id],
                'chain_names': [classes_by_id[class_id]['qualified_name']],
                'fully_resolved': False,
                'cyclic_inheritance': True,
            }
        visiting.add(class_id)
        cls = classes_by_id[class_id]
        bases = cls.get('bases') or []
        best_depth = 1
        best_chain_ids = [class_id]
        best_chain_names = [cls['qualified_name']]
        fully_resolved = True
        cyclic = False

        for base in bases:
            base_name = base.get('name') or '<dynamic>'
            base_qual = base.get('import_qualified_name') or base_name
            if base_name in EXTERNAL_BASE_ROOTS or base_qual in EXTERNAL_BASE_ROOTS:
                continue
            parent_cls, resolved = resolve_base(cls, base)
            if parent_cls is not None:
                parent_info = compute(parent_cls['id'])
                candidate_depth = 1 + parent_info['depth']
                if candidate_depth > best_depth:
                    best_depth = candidate_depth
                    best_chain_ids = [class_id] + parent_info['chain_ids']
                    best_chain_names = [cls['qualified_name']] + parent_info['chain_names']
                fully_resolved = fully_resolved and parent_info['fully_resolved']
                cyclic = cyclic or parent_info['cyclic_inheritance']
            else:
                # Non-builtin external or unresolved base adds 1 hierarchy level above this class.
                candidate_depth = 2
                if candidate_depth > best_depth:
                    best_depth = candidate_depth
                    best_chain_ids = [class_id]
                    best_chain_names = [cls['qualified_name'], base_qual]
                if base.get('is_dynamic') or base.get('import_qualified_name') is None:
                    fully_resolved = False

        visiting.remove(class_id)
        result = {
            'depth': best_depth,
            'chain_ids': best_chain_ids,
            'chain_names': best_chain_names,
            'fully_resolved': fully_resolved,
            'cyclic_inheritance': cyclic,
        }
        memo[class_id] = result
        return result

    for class_id in sorted(classes_by_id):
        compute(class_id)
    return classes_by_id, memo


def _threshold_meta(thresholds: ArchitectureThresholds, name: str, unit: str) -> dict:
    return {
        'name': name,
        'value': getattr(thresholds, name),
        'unit': unit,
        'source': thresholds.threshold_source(name),
    }


def evaluate_architecture(
    structure: RepositoryStructure,
    architecture: ArchitectureGraph,
    policy: ArchitecturePolicy | dict | None = None,
    *,
    options: ArchitectureEvaluationOptions | None = None,
) -> ArchitectureEvaluationResult:
    """Evaluate structural and policy rules on existing AST and graph outputs."""
    if not isinstance(structure, RepositoryStructure) or not isinstance(architecture, ArchitectureGraph):
        raise TypeError('Expected RepositoryStructure and ArchitectureGraph')
    active_policy, policy_supplied = coerce_policy(policy)
    options = options or ArchitectureEvaluationOptions()
    options.validate()
    thresholds = active_policy.thresholds

    diagnostics: list[dict] = []
    try:
        consistent = _consistent(structure, architecture)
    except (ValueError, KeyError, TypeError):
        consistent = False
    if not consistent:
        diagnostics.append({'code': 'graph_structure_mismatch', 'source': 'evaluator'})

    source_diags = _sanitize_diagnostics(structure.diagnostics, 'structure') + _sanitize_diagnostics(
        architecture.diagnostics, 'architecture'
    )
    source_diags.sort(key=lambda d: (d['source'], d['code'], d.get('file', ''), d.get('start_line', 0)))
    diagnostics_truncated = len(source_diags) > options.max_diagnostics
    diagnostics.extend(source_diags[: options.max_diagnostics])

    nodes_by_id = {node['id']: node for node in architecture.nodes}
    modules_by_id = {mod['id']: mod for mod in structure.modules}
    files_by_path = {f['file']: f for f in structure.files}
    edges_by_pair = {(edge['source'], edge['target']): edge for edge in architecture.edges}
    edges_by_id = {edge['id']: edge for edge in architecture.edges}

    functions_by_module: dict[str, list[dict]] = defaultdict(list)
    for func in structure.functions:
        functions_by_module[func['module_id']].append(func)
    classes_by_module: dict[str, list[dict]] = defaultdict(list)
    methods_by_class: dict[str, list[dict]] = defaultdict(list)
    for cls in structure.classes:
        classes_by_module[cls['module_id']].append(cls)
    for func in structure.functions:
        if func.get('kind') == 'method' and func.get('parent_id'):
            methods_by_class[func['parent_id']].append(func)

    internal_unresolved_imports: dict[str, list[dict]] = defaultdict(list)
    unclassified_external_count = 0
    for imp in structure.imports:
        res = imp.get('resolution')
        reason = imp.get('reason')
        if res == 'ambiguous' or (
            res == 'unresolved' and (reason in INTERNAL_UNRESOLVED_REASONS or imp.get('level', 0) > 0)
        ):
            internal_unresolved_imports[imp['module_id']].append(imp)
        elif res == 'unresolved' and reason == 'not_local_stdlib_or_known_external':
            unclassified_external_count += 1

    edge_catalog: dict[str, dict] = {
        edge['id']: {
            'id': edge['id'],
            'source': edge['source'],
            'target': edge['target'],
            'relationship': edge['relationship'],
            'evidence_count': edge['evidence_count'],
            'locations': [
                {
                    'file': ev['file'],
                    'start_line': ev['start_line'],
                    'end_line': ev['end_line'],
                    'conditional': ev['conditional'],
                }
                for ev in edge['evidence'][:8]
            ],
        }
        for edge in architecture.edges
    }

    module_catalog: dict[str, dict] = {}
    for mod_id, node in sorted(nodes_by_id.items()):
        mod = modules_by_id.get(mod_id)
        file_rec = files_by_path.get(node['file'])
        module_catalog[mod_id] = {
            'id': node['id'],
            'file': node['file'],
            'label': node['label'],
            'type': node['type'],
            'classification_confidence': node['classification_confidence'],
            'parsed': node['parsed'],
            'fan_in': node['fan_in'],
            'fan_out': node['fan_out'],
            'line_count': _node_line_count(mod, file_rec),
            'function_count': len(functions_by_module[mod_id]),
            'class_count': len(classes_by_module[mod_id]),
        }

    symbol_catalog: dict[str, dict] = {}
    for func in structure.functions:
        eff, raw = _effective_parameter_count(func)
        symbol_catalog[func['id']] = {
            **_symbol_descriptor(func),
            'line_count': func['end_line'] - func['start_line'] + 1,
            'effective_parameters_count': eff,
            'total_parameters_count': raw,
        }
    for cls in structure.classes:
        symbol_catalog[cls['id']] = {
            **_symbol_descriptor(cls),
            'line_count': cls['end_line'] - cls['start_line'] + 1,
            'method_count': len(methods_by_class[cls['id']]),
            'bases': [b.get('import_qualified_name') or b.get('name') or '<dynamic>' for b in (cls.get('bases') or [])],
        }

    path_catalog: dict[str, dict] = {}
    observations: list[dict] = []

    def register_path(kind: str, node_ids: list[str], edge_ids: list[str]) -> dict:
        pid = stable_id('arch_path', kind, *node_ids)
        evidence_slice = []
        for eid in edge_ids[: options.max_evidence_edges]:
            edge = edges_by_id.get(eid)
            if edge:
                evidence_slice.append(
                    {
                        'edge_id': eid,
                        'source': edge['source'],
                        'target': edge['target'],
                        'evidence_count': edge['evidence_count'],
                        'locations': [
                            {
                                'file': ev['file'],
                                'start_line': ev['start_line'],
                                'end_line': ev['end_line'],
                                'conditional': ev['conditional'],
                            }
                            for ev in edge['evidence'][:8]
                        ],
                    }
                )
        path_obj = {
            'id': pid,
            'kind': kind,
            'node_ids': list(node_ids),
            'edge_ids': list(edge_ids),
            'import_evidence': evidence_slice,
        }
        path_catalog[pid] = path_obj
        return {'id': pid, 'kind': kind, 'node_ids': list(node_ids), 'edge_ids': list(edge_ids)}

    def add_observation(
        *,
        rule_id: str,
        key_parts: tuple[str, ...],
        category: str,
        priority: str,
        title: str,
        explanation: str,
        module_ids: list[str],
        symbols: list[dict],
        source_locations: list[dict],
        edge_ids: list[str],
        dependency_paths: list[dict],
        component_ids: list[str],
        observed_metric: dict | None,
        configured_threshold: dict | None,
        suggested_improvement: str,
        trade_offs: list[str],
        validation_method: str,
        confidence: str,
        evidence_classification: str,
        known_limitations: list[str],
    ) -> None:
        if not active_policy.is_rule_enabled(rule_id):
            return
        dedup_mods = []
        seen_m = set()
        for mid in module_ids:
            if mid in nodes_by_id and mid not in seen_m:
                seen_m.add(mid)
                dedup_mods.append(_module_descriptor(nodes_by_id[mid]))
        affected_modules = dedup_mods[: options.max_affected_modules_per_observation]

        seen_s = set()
        dedup_syms = []
        for sym in symbols:
            if sym['id'] not in seen_s:
                seen_s.add(sym['id'])
                dedup_syms.append(_symbol_descriptor(sym))

        seen_loc = set()
        dedup_locs = []
        for loc in source_locations:
            loc_key = (loc['file'], loc.get('start_line'), loc.get('end_line'), loc['kind'])
            if loc_key not in seen_loc:
                seen_loc.add(loc_key)
                dedup_locs.append(loc)
                if len(dedup_locs) >= options.max_source_locations_per_observation:
                    break

        bounded_edges = sorted(set(edge_ids))[: options.max_evidence_edges]
        import_evidence = []
        for eid in bounded_edges:
            edge = edges_by_id.get(eid)
            if edge:
                for ev in edge['evidence'][:8]:
                    import_evidence.append(
                        {
                            'edge_id': eid,
                            'import_id': ev['import_id'],
                            'file': ev['file'],
                            'start_line': ev['start_line'],
                            'end_line': ev['end_line'],
                            'conditional': ev['conditional'],
                        }
                    )

        observations.append(
            {
                'id': stable_id('arch_obs', rule_id, *key_parts),
                'rule_id': rule_id,
                'category': category,
                'priority': priority,
                'title': title,
                'explanation': explanation,
                'affected_modules': affected_modules,
                'affected_symbols': dedup_syms,
                'source_locations': dedup_locs,
                'supporting_graph_evidence': {
                    'node_ids': [m['module_id'] for m in affected_modules],
                    'edge_ids': bounded_edges,
                    'dependency_paths': dependency_paths[: options.max_dependency_paths],
                    'component_ids': sorted(set(component_ids)),
                    'import_evidence': import_evidence,
                },
                'observed_metric': observed_metric,
                'configured_threshold': configured_threshold,
                'suggested_improvement': suggested_improvement,
                'trade_offs': trade_offs,
                'validation_method': validation_method,
                'confidence': confidence,
                'evidence_classification': evidence_classification,
                'known_limitations': known_limitations,
                'advisory_only': True,
            }
        )

    cannot_evaluate = (
        not consistent
        or structure.status == 'error'
        or architecture.status == 'error'
        or len(architecture.nodes) == 0
    )

    if not cannot_evaluate:
        # 1. CODELY-ARCH-001: Circular dependencies
        for comp in architecture.statistics.get('cyclic_components', []):
            members = comp['node_ids']
            witness = comp['witness']
            w_nodes = witness['node_ids']
            w_edges = witness['edge_ids']
            all_conditional = bool(w_edges) and all(
                all(
                    bool(ev.get('conditional'))
                    or (bool(ev.get('scope_id')) and ev.get('scope_id') != edges_by_id[eid]['source'])
                    for ev in edges_by_id[eid]['evidence']
                )
                for eid in w_edges
                if eid in edges_by_id
            )
            locs = []
            for eid in w_edges:
                edge = edges_by_id.get(eid)
                if edge:
                    for ev in edge['evidence']:
                        locs.append(
                            {
                                'file': ev['file'],
                                'start_line': ev['start_line'],
                                'end_line': ev['end_line'],
                                'kind': 'cycle_import_edge',
                            }
                        )
            path_ref = register_path('cycle_witness', w_nodes, w_edges)
            is_self_loop = len(members) == 1
            priority = 'MEDIUM' if (is_self_loop or all_conditional) else 'HIGH'
            cond_note = ' All witness imports occur inside conditional or function-local blocks.' if all_conditional else ''
            add_observation(
                rule_id='CODELY-ARCH-001',
                key_parts=(comp['component_id'],),
                category='dependency_cycle',
                priority=priority,
                title='Self-import dependency detected' if is_self_loop else 'Circular module dependency detected',
                explanation=(
                    f'Strongly connected component {comp["component_id"]} involves {len(members)} module(s) '
                    f'with a static import cycle ({ " -> ".join(nodes_by_id[n]["file"] for n in w_nodes) }).'
                    f'{cond_note}'
                ),
                module_ids=members,
                symbols=[],
                source_locations=locs,
                edge_ids=w_edges,
                dependency_paths=[path_ref],
                component_ids=[comp['component_id']],
                observed_metric={
                    'name': 'cycle_component_size',
                    'value': len(members),
                    'unit': 'modules',
                    'details': {'is_self_import': is_self_loop, 'all_witness_imports_conditional': all_conditional},
                },
                configured_threshold={'name': 'max_cycle_size', 'value': 1, 'unit': 'modules', 'source': 'default'},
                suggested_improvement=(
                    'Extract shared abstractions, types or contracts into an acyclic module, '
                    'reconsider dependency direction using dependency inversion/protocols, or merge artificially split modules.'
                ),
                trade_offs=[
                    'Extracting an abstraction module adds indirection and small files.',
                    'Merging cyclic modules reduces file separation.',
                    'Deferring imports into functions avoids import-time failure but preserves architectural coupling.',
                ],
                validation_method=(
                    'Re-run AST structure and architecture graph analysis to verify cyclic_component_count decreases '
                    'and execute the project test suite.'
                ),
                confidence='confirmed',
                evidence_classification='confirmed_structural',
                known_limitations=[
                    'Reflects static import syntax only; conditional or function-local imports may not fail at import time.',
                    'Each strongly connected component reports one deterministic witness cycle rather than enumerating all simple cycles.',
                ],
            )

        # 2 & 3. CODELY-ARCH-002 (Layer violations) and CODELY-ARCH-003 (Controller -> data-access)
        def _eligible_roles(node: dict, include_inferred: bool) -> list[tuple[str, str]]:
            by_role: dict[str, str] = {}
            entries = node.get('classifications') or []
            if not entries and node.get('type') not in (None, 'unclassified'):
                entries = [{'type': node['type'], 'confidence': node.get('classification_confidence', 'inferred')}]
            for entry in entries:
                role = entry.get('type')
                conf = entry.get('confidence', 'inferred')
                if role in (None, 'unclassified'):
                    continue
                if not include_inferred and conf != 'confirmed':
                    continue
                if by_role.get(role) != 'confirmed':
                    by_role[role] = conf
            return sorted(by_role.items(), key=lambda pair: (pair[1] != 'confirmed', pair[0]))

        layers = active_policy.layers
        if layers is not None and layers.has_explicit_rules():
            prohibited_map: dict[tuple[str, str], str] = {
                (item.source, item.target): item.reason for item in layers.prohibited_dependencies
            }
            allowed = layers.allowed_dependencies or {}
            policy_mentions_test = (
                'test' in allowed
                or any('test' in targets for targets in allowed.values())
                or any('test' in (k[0], k[1]) for k in prohibited_map)
            )
            for edge in architecture.edges:
                src_node = nodes_by_id[edge['source']]
                tgt_node = nodes_by_id[edge['target']]
                if src_node['id'] == tgt_node['id']:
                    continue
                if (_is_test_node(src_node) or _is_test_node(tgt_node)) and not policy_mentions_test:
                    continue
                src_roles = _eligible_roles(src_node, layers.include_inferred_roles)
                tgt_roles = _eligible_roles(tgt_node, layers.include_inferred_roles)
                if not src_roles or not tgt_roles:
                    continue

                locs = [
                    {
                        'file': ev['file'],
                        'start_line': ev['start_line'],
                        'end_line': ev['end_line'],
                        'kind': 'policy_dependency_edge',
                    }
                    for ev in edge['evidence']
                ]
                path_ref = register_path('layer_edge', [src_node['id'], tgt_node['id']], [edge['id']])

                emitted_ctrl_data = False
                for src_role, src_conf in src_roles:
                    for tgt_role, tgt_conf in tgt_roles:
                        if src_role == tgt_role and layers.allow_same_layer and (src_role, tgt_role) not in prohibited_map:
                            continue
                        both_confirmed = src_conf == 'confirmed' and tgt_conf == 'confirmed'
                        obs_conf = 'confirmed' if both_confirmed else 'inferred'
                        ev_class = 'confirmed_structural' if both_confirmed else 'heuristic_maintainability'
                        obs_priority = 'HIGH' if both_confirmed else 'MEDIUM'

                        is_ctrl_to_data = (
                            src_role in {'controller', 'router'}
                            and tgt_role == 'data_access'
                            and (
                                layers.prohibit_controller_to_data_access is True
                                or (src_role, tgt_role) in prohibited_map
                                or (
                                    layers.allowed_dependencies is not None
                                    and src_role in allowed
                                    and tgt_role not in allowed[src_role]
                                    and layers.prohibit_controller_to_data_access is not False
                                )
                            )
                        )
                        if is_ctrl_to_data and not emitted_ctrl_data:
                            emitted_ctrl_data = True
                            reason_detail = prohibited_map.get(
                                (src_role, tgt_role),
                                f'Configured policy prohibits direct {src_role} -> data_access dependencies.',
                            )
                            add_observation(
                                rule_id='CODELY-ARCH-003',
                                key_parts=(edge['id'], src_role, tgt_role),
                                category='layer_boundary',
                                priority=obs_priority,
                                title=f'Direct {src_role} dependency on data-access module',
                                explanation=(
                                    f'{src_node["file"]} (role: {src_role}, {src_conf}) directly imports '
                                    f'{tgt_node["file"]} (role: data_access, {tgt_conf}). {reason_detail}'
                                ),
                                module_ids=[src_node['id'], tgt_node['id']],
                                symbols=[],
                                source_locations=locs,
                                edge_ids=[edge['id']],
                                dependency_paths=[path_ref],
                                component_ids=[],
                                observed_metric={
                                    'name': 'direct_layer_violation_edges',
                                    'value': 1,
                                    'unit': 'edges',
                                    'details': {
                                        'source_role': src_role,
                                        'target_role': tgt_role,
                                        'source_confidence': src_conf,
                                        'target_confidence': tgt_conf,
                                    },
                                },
                                configured_threshold=None,
                                suggested_improvement=(
                                    'Route persistence calls through a service or domain abstraction so HTTP handlers '
                                    'remain decoupled from data-access details.'
                                ),
                                trade_offs=[
                                    'Adding a service or facade introduces extra boilerplate for simple CRUD operations.',
                                    'If direct access is intentional for this endpoint, record an explicit policy exception.',
                                ],
                                validation_method=(
                                    'Re-run architecture evaluation to confirm the direct edge is removed while preserving '
                                    'route integration tests.'
                                ),
                                confidence=obs_conf,
                                evidence_classification=ev_class,
                                known_limitations=[
                                    'Role classification relies on confirmed framework/DB indicators or filename heuristics as recorded per module.',
                                    'Direct import evidence does not confirm which functions are executed at runtime.',
                                ],
                            )
                            continue

                        if is_ctrl_to_data:
                            continue

                        explicit_prohibited = prohibited_map.get((src_role, tgt_role))
                        disallowed_by_allowlist = (
                            layers.allowed_dependencies is not None
                            and src_role in allowed
                            and tgt_role not in allowed[src_role]
                            and not (layers.allow_same_layer and src_role == tgt_role)
                        )
                        if explicit_prohibited or disallowed_by_allowlist:
                            detail = explicit_prohibited or (
                                f'Role {src_role} is only allowed to depend on {list(allowed[src_role])}.'
                            )
                            add_observation(
                                rule_id='CODELY-ARCH-002',
                                key_parts=(edge['id'], src_role, tgt_role),
                                category='layer_boundary',
                                priority=obs_priority,
                                title=f'Layer boundary violation: {src_role} -> {tgt_role}',
                                explanation=(
                                    f'{src_node["file"]} (role: {src_role}, {src_conf}) imports '
                                    f'{tgt_node["file"]} (role: {tgt_role}, {tgt_conf}). {detail}'
                                ),
                                module_ids=[src_node['id'], tgt_node['id']],
                                symbols=[],
                                source_locations=locs,
                                edge_ids=[edge['id']],
                                dependency_paths=[path_ref],
                                component_ids=[],
                                observed_metric={
                                    'name': 'layer_violation_edges',
                                    'value': 1,
                                    'unit': 'edges',
                                    'details': {
                                        'source_role': src_role,
                                        'target_role': tgt_role,
                                        'source_confidence': src_conf,
                                        'target_confidence': tgt_conf,
                                    },
                                },
                                configured_threshold=None,
                                suggested_improvement=(
                                    f'Route the dependency from {src_role} through an allowed intermediate abstraction '
                                    f'or adjust the policy if {src_role} -> {tgt_role} is intentional.'
                                ),
                                trade_offs=[
                                    'Introducing intermediate interfaces increases indirection and boilerplate.',
                                    'Overly strict layer rules can hinder pragmatic shared utilities.',
                                ],
                                validation_method=(
                                    'Re-evaluate architecture rules after refactoring imports and verify behavior via tests.'
                                ),
                                confidence=obs_conf,
                                evidence_classification=ev_class,
                                known_limitations=[
                                    'Inferred filename roles are heuristic and should be verified against actual module responsibilities.',
                                    'Layer policies apply only to observed internal imports.',
                                ],
                            )

        # Inheritance index computed once across parsed classes
        classes_by_id, inheritance_info = _build_inheritance_index(structure)

        # Module-level rules (004, 005, 006, 007, 011, 012)
        for mod_id, node in sorted(nodes_by_id.items()):
            mod = modules_by_id[mod_id]
            file_rec = files_by_path.get(node['file'])
            is_test = _is_test_node(node)
            skip_heuristics = is_test and not thresholds.include_tests_in_heuristics

            fan_in = node['fan_in']
            fan_out = node['fan_out']
            total_coupling = fan_in + fan_out
            in_edges = [
                edges_by_pair[(src, mod_id)]
                for src in architecture.direct_dependents(mod_id)
                if (src, mod_id) in edges_by_pair
            ]
            out_edges = [
                edges_by_pair[(mod_id, tgt)]
                for tgt in architecture.direct_dependencies(mod_id)
                if (mod_id, tgt) in edges_by_pair
            ]
            mod_locs = (
                [
                    {
                        'file': node['file'],
                        'start_line': mod['start_line'],
                        'end_line': mod['end_line'],
                        'kind': 'module',
                    }
                ]
                if type(mod.get('start_line')) is int and type(mod.get('end_line')) is int
                else []
            )

            if not skip_heuristics:
                # CODELY-ARCH-004: Excessive total coupling
                if total_coupling > thresholds.max_total_coupling:
                    eids = [e['id'] for e in in_edges + out_edges]
                    add_observation(
                        rule_id='CODELY-ARCH-004',
                        key_parts=(mod_id,),
                        category='coupling',
                        priority='MEDIUM',
                        title='Excessive module coupling',
                        explanation=(
                            f'{node["file"]} has {total_coupling} total internal neighbor connections '
                            f'(fan_in={fan_in}, fan_out={fan_out}), exceeding threshold {thresholds.max_total_coupling}.'
                        ),
                        module_ids=[mod_id],
                        symbols=[],
                        source_locations=mod_locs,
                        edge_ids=eids,
                        dependency_paths=[],
                        component_ids=[],
                        observed_metric={
                            'name': 'total_module_coupling',
                            'value': total_coupling,
                            'unit': 'connections',
                            'details': {'fan_in': fan_in, 'fan_out': fan_out},
                        },
                        configured_threshold=_threshold_meta(thresholds, 'max_total_coupling', 'connections'),
                        suggested_improvement=(
                            'Review module responsibilities and dependency boundaries; consider separating unrelated '
                            'capabilities or narrowing exported interfaces.'
                        ),
                        trade_offs=[
                            'Splitting a central module creates additional files and import hops.',
                            'Shared coordinators or domain facades can legitimately connect multiple modules.',
                        ],
                        validation_method=(
                            'Check updated fan_in/fan_out metrics in the architecture graph and run unit/integration tests.'
                        ),
                        confidence='heuristic',
                        evidence_classification='heuristic_maintainability',
                        known_limitations=[
                            'Counts unique internal Python module neighbors only; external libraries and runtime calls are excluded.',
                            'High connectivity on intentional shared foundations or entry points is not automatically a defect.',
                        ],
                    )

                # CODELY-ARCH-005: High fan-in
                if fan_in > thresholds.max_fan_in:
                    shared_foundation = node['type'] in {'utility', 'configuration', 'database_model'} or mod.get('is_package')
                    add_observation(
                        rule_id='CODELY-ARCH-005',
                        key_parts=(mod_id,),
                        category='coupling',
                        priority='LOW' if shared_foundation else 'MEDIUM',
                        title='High module fan-in',
                        explanation=(
                            f'{node["file"]} (role: {node["type"]}) is imported by {fan_in} distinct internal modules, '
                            f'exceeding threshold {thresholds.max_fan_in}.'
                            + (
                                ' Shared utility, configuration or model modules often attract high fan-in intentionally.'
                                if shared_foundation
                                else ''
                            )
                        ),
                        module_ids=[mod_id],
                        symbols=[],
                        source_locations=mod_locs,
                        edge_ids=[e['id'] for e in in_edges],
                        dependency_paths=[],
                        component_ids=[],
                        observed_metric={'name': 'module_fan_in', 'value': fan_in, 'unit': 'dependents'},
                        configured_threshold=_threshold_meta(thresholds, 'max_fan_in', 'dependents'),
                        suggested_improvement=(
                            'Verify that the module exposes a stable, cohesive interface; split unrelated exports only '
                            'if callers are coupled to volatile details they do not use.'
                        ),
                        trade_offs=[
                            'Splitting a stable shared module can add unnecessary import churn across dependents.',
                            'Leaving unrelated responsibilities together increases blast radius when changes occur.',
                        ],
                        validation_method=(
                            'Review incoming dependencies and confirm public interfaces remain minimal and well tested.'
                        ),
                        confidence='heuristic',
                        evidence_classification='heuristic_maintainability',
                        known_limitations=[
                            'High fan-in often indicates healthy reuse rather than a design flaw.',
                            'Reflects observed internal imports only.',
                        ],
                    )

                # CODELY-ARCH-006: High fan-out
                if fan_out > thresholds.max_fan_out:
                    is_entry = node['type'] == 'application_entry_point'
                    add_observation(
                        rule_id='CODELY-ARCH-006',
                        key_parts=(mod_id,),
                        category='coupling',
                        priority='LOW' if is_entry else 'MEDIUM',
                        title='High module fan-out',
                        explanation=(
                            f'{node["file"]} (role: {node["type"]}) imports {fan_out} distinct internal modules, '
                            f'exceeding threshold {thresholds.max_fan_out}.'
                            + (
                                ' Application entry points and composition roots often wire many modules together by design.'
                                if is_entry
                                else ''
                            )
                        ),
                        module_ids=[mod_id],
                        symbols=[],
                        source_locations=mod_locs,
                        edge_ids=[e['id'] for e in out_edges],
                        dependency_paths=[],
                        component_ids=[],
                        observed_metric={'name': 'module_fan_out', 'value': fan_out, 'unit': 'dependencies'},
                        configured_threshold=_threshold_meta(thresholds, 'max_fan_out', 'dependencies'),
                        suggested_improvement=(
                            'Review whether the module coordinates too many distinct collaborators; group cohesive '
                            'dependencies behind focused service or facade boundaries.'
                        ),
                        trade_offs=[
                            'Introducing intermediate facades adds indirection.',
                            'Composition roots intentionally import multiple routers, services or adapters.',
                        ],
                        validation_method=(
                            'Verify reduced outgoing dependencies in the architecture graph without breaking integration tests.'
                        ),
                        confidence='heuristic',
                        evidence_classification='heuristic_maintainability',
                        known_limitations=[
                            'Counts observed internal imports only; external package imports are counted separately.',
                        ],
                    )

                # CODELY-ARCH-007: Oversized module
                if node['parsed']:
                    line_count = _node_line_count(mod, file_rec)
                    func_count = len(functions_by_module[mod_id])
                    class_count = len(classes_by_module[mod_id])
                    exceeded = []
                    if line_count is not None and line_count > thresholds.max_module_lines:
                        exceeded.append(('module_lines', line_count, 'max_module_lines', 'lines'))
                    if func_count > thresholds.max_module_functions:
                        exceeded.append(('module_functions', func_count, 'max_module_functions', 'functions'))
                    if class_count > thresholds.max_module_classes:
                        exceeded.append(('module_classes', class_count, 'max_module_classes', 'classes'))
                    if exceeded:
                        m_name, m_val, t_name, unit = exceeded[0]
                        add_observation(
                            rule_id='CODELY-ARCH-007',
                            key_parts=(mod_id,),
                            category='size_complexity',
                            priority='MEDIUM' if len(exceeded) > 1 or node['type'] not in {'database_model'} else 'LOW',
                            title='Oversized module',
                            explanation=(
                                f'{node["file"]} exceeds configured module size thresholds '
                                f'({m_name}={m_val} > {getattr(thresholds, t_name)}).'
                            ),
                            module_ids=[mod_id],
                            symbols=[],
                            source_locations=mod_locs,
                            edge_ids=[],
                            dependency_paths=[],
                            component_ids=[],
                            observed_metric={
                                'name': m_name,
                                'value': m_val,
                                'unit': unit,
                                'details': {
                                    'line_count': line_count,
                                    'function_count': func_count,
                                    'class_count': class_count,
                                    'exceeded_indicators': [item[0] for item in exceeded],
                                },
                            },
                            configured_threshold=_threshold_meta(thresholds, t_name, unit),
                            suggested_improvement=(
                                'Inspect the module for cohesive sub-responsibilities that could be separated into '
                                'focused modules if independent change cadence or readability warrants it.'
                            ),
                            trade_offs=[
                                'Splitting a cohesive module can scatter closely related logic across extra files.',
                                'Large schema or model definition files may already be cohesively organized.',
                            ],
                            validation_method=(
                                'Re-run AST structure analysis to verify module metrics and run the test suite.'
                            ),
                            confidence='heuristic',
                            evidence_classification='heuristic_maintainability',
                            known_limitations=[
                                'Line and declaration counts do not measure cohesion; large files can still be well structured.',
                            ],
                        )

                    # CODELY-ARCH-011 (module-level mixed confirmed responsibilities)
                    confirmed_groups: dict[str, list[str]] = defaultdict(list)
                    conf_locs = []
                    for entry in node.get('classifications') or []:
                        if entry.get('confidence') == 'confirmed':
                            group = RESPONSIBILITY_GROUPS.get(entry['type'])
                            if group:
                                confirmed_groups[group].append(entry['type'])
                                ev = entry.get('evidence') or {}
                                if type(ev.get('start_line')) is int and type(ev.get('end_line')) is int:
                                    conf_locs.append(
                                        {
                                            'file': ev['file'],
                                            'start_line': ev['start_line'],
                                            'end_line': ev['end_line'],
                                            'kind': f'confirmed_{entry["type"]}',
                                        }
                                    )
                    if len(confirmed_groups) >= thresholds.max_responsibility_groups_per_module:
                        groups_sorted = sorted(confirmed_groups)
                        add_observation(
                            rule_id='CODELY-ARCH-011',
                            key_parts=(mod_id, 'mixed_responsibilities'),
                            category='responsibility_concentration',
                            priority='MEDIUM',
                            title='Potential concentration of responsibilities in module',
                            explanation=(
                                f'{node["file"]} combines {len(groups_sorted)} distinct confirmed responsibility groups '
                                f'({", ".join(groups_sorted)}).'
                            ),
                            module_ids=[mod_id],
                            symbols=[],
                            source_locations=conf_locs or mod_locs,
                            edge_ids=[],
                            dependency_paths=[],
                            component_ids=[],
                            observed_metric={
                                'name': 'confirmed_responsibility_groups',
                                'value': len(groups_sorted),
                                'unit': 'groups',
                                'details': {'groups': groups_sorted},
                            },
                            configured_threshold=_threshold_meta(
                                thresholds, 'max_responsibility_groups_per_module', 'groups'
                            ),
                            suggested_improvement=(
                                'Review whether HTTP routing, persistence, authentication and configuration logic in this '
                                'module should be separated into dedicated modules along change boundaries.'
                            ),
                            trade_offs=[
                                'Small self-contained microservices or scripts may intentionally keep endpoints and helpers together.',
                                'Separating responsibilities increases module count and wiring.',
                            ],
                            validation_method=(
                                'Confirm separated modules retain single-responsibility classifications and pass integration tests.'
                            ),
                            confidence='heuristic',
                            evidence_classification='heuristic_maintainability',
                            known_limitations=[
                                'Only explicitly recognized framework, database, auth and environment APIs contribute to confirmed responsibility groups.',
                            ],
                        )

            # CODELY-ARCH-012: Unresolved internal dependency references (applies to all modules)
            unresolved_list = internal_unresolved_imports.get(mod_id, [])
            if unresolved_list:
                locs = [
                    {
                        'file': imp['file'],
                        'start_line': imp['start_line'],
                        'end_line': imp['end_line'],
                        'kind': f'import_{imp["resolution"]}',
                    }
                    for imp in unresolved_list
                ]
                names = sorted({imp.get('resolved_name') or imp.get('module') or '<relative>' for imp in unresolved_list})
                reasons = sorted({imp.get('reason') or imp.get('resolution') for imp in unresolved_list})
                add_observation(
                    rule_id='CODELY-ARCH-012',
                    key_parts=(mod_id,),
                    category='dependency_integrity',
                    priority='HIGH',
                    title='Unresolved or ambiguous internal dependency reference',
                    explanation=(
                        f'{node["file"]} has {len(unresolved_list)} unresolved or ambiguous internal import(s): '
                        f'{", ".join(names[:5])} ({", ".join(reasons)}).'
                    ),
                    module_ids=[mod_id],
                    symbols=[],
                    source_locations=locs,
                    edge_ids=[],
                    dependency_paths=[],
                    component_ids=[],
                    observed_metric={
                        'name': 'unresolved_internal_imports',
                        'value': len(unresolved_list),
                        'unit': 'imports',
                        'details': {'targets': names, 'reasons': reasons},
                    },
                    configured_threshold={
                        'name': 'max_unresolved_internal_imports',
                        'value': 0,
                        'unit': 'imports',
                        'source': 'default',
                    },
                    suggested_improvement=(
                        'Verify internal module/symbol paths, package __init__.py files, or configure StructureOptions.source_roots '
                        'if the project uses nonstandard Python source roots; disambiguate colliding module/attribute names.'
                    ),
                    trade_offs=[
                        'If imports depend on runtime sys.path mutation or code generation, adjusting analyzer source_roots '
                        'may be preferable to changing application imports.',
                    ],
                    validation_method=(
                        'Re-run AST structure analysis and confirm unresolved internal import counts drop to zero.'
                    ),
                    confidence='confirmed',
                    evidence_classification='confirmed_structural',
                    known_limitations=[
                        'Static import resolution does not execute import hooks, dynamic sys.path changes or wildcard re-exports.',
                    ],
                )

        # Function-level rules (008, 009)
        for func in sorted(structure.functions, key=lambda f: (f['file'], f['start_line'], f['id'])):
            node = nodes_by_id.get(func['module_id'])
            if node is None:
                continue
            if _is_test_node(node) and not thresholds.include_tests_in_heuristics:
                continue
            func_lines = func['end_line'] - func['start_line'] + 1
            func_loc = [
                {
                    'file': func['file'],
                    'start_line': func['extent_start_line'],
                    'end_line': func['end_line'],
                    'kind': func['kind'],
                }
            ]
            if func_lines > thresholds.max_function_lines:
                add_observation(
                    rule_id='CODELY-ARCH-008',
                    key_parts=(func['id'],),
                    category='size_complexity',
                    priority='MEDIUM',
                    title=f'Oversized {func["kind"]}: {func["qualified_name"]}',
                    explanation=(
                        f'{func["qualified_name"]} in {func["file"]} spans {func_lines} lines '
                        f'(lines {func["start_line"]}-{func["end_line"]}), exceeding threshold {thresholds.max_function_lines}.'
                    ),
                    module_ids=[func['module_id']],
                    symbols=[func],
                    source_locations=func_loc,
                    edge_ids=[],
                    dependency_paths=[],
                    component_ids=[],
                    observed_metric={'name': 'function_lines', 'value': func_lines, 'unit': 'lines'},
                    configured_threshold=_threshold_meta(thresholds, 'max_function_lines', 'lines'),
                    suggested_improvement=(
                        'Review opportunities for responsibility-based decomposition into smaller, well-named helper functions.'
                    ),
                    trade_offs=[
                        'Over-fragmentation into trivial single-use helpers can reduce linear readability.',
                    ],
                    validation_method='Re-run structure analysis and verify existing unit tests pass after extraction.',
                    confidence='heuristic',
                    evidence_classification='heuristic_maintainability',
                    known_limitations=[
                        'Line span includes docstrings, comments and multi-line literals inside the function body.',
                    ],
                )

            eff_params, raw_params = _effective_parameter_count(func)
            if eff_params > thresholds.max_function_parameters:
                add_observation(
                    rule_id='CODELY-ARCH-009',
                    key_parts=(func['id'],),
                    category='size_complexity',
                    priority='MEDIUM' if eff_params >= thresholds.max_function_parameters + 3 else 'LOW',
                    title=f'Excessive parameter count: {func["qualified_name"]}',
                    explanation=(
                        f'{func["qualified_name"]} in {func["file"]} accepts {eff_params} effective parameter(s) '
                        f'({raw_params} total including receiver if method), exceeding threshold {thresholds.max_function_parameters}.'
                    ),
                    module_ids=[func['module_id']],
                    symbols=[func],
                    source_locations=func_loc,
                    edge_ids=[],
                    dependency_paths=[],
                    component_ids=[],
                    observed_metric={
                        'name': 'effective_function_parameters',
                        'value': eff_params,
                        'unit': 'parameters',
                        'details': {'total_parameters': raw_params},
                    },
                    configured_threshold=_threshold_meta(thresholds, 'max_function_parameters', 'parameters'),
                    suggested_improvement=(
                        'Consider grouping cohesive parameters into a typed dataclass/configuration object or splitting '
                        'distinct call modes into separate functions.'
                    ),
                    trade_offs=[
                        'Parameter objects add type definitions and indirection for simple internal helpers.',
                    ],
                    validation_method='Update callers, re-run structure analysis and run type/unit checks.',
                    confidence='heuristic',
                    evidence_classification='heuristic_maintainability',
                    known_limitations=[
                        'Does not account for *args/**kwargs unpacking complexity or framework-injected route parameters.',
                    ],
                )

        # Class-level rules (010 deep inheritance, 011 god-class method concentration)
        for cls in sorted(structure.classes, key=lambda c: (c['file'], c['start_line'], c['id'])):
            node = nodes_by_id.get(cls['module_id'])
            if node is None:
                continue
            if _is_test_node(node) and not thresholds.include_tests_in_heuristics:
                continue
            cls_loc = [
                {
                    'file': cls['file'],
                    'start_line': cls['extent_start_line'],
                    'end_line': cls['end_line'],
                    'kind': 'class',
                }
            ]

            inh = inheritance_info[cls['id']]
            if inh['depth'] > thresholds.max_inheritance_depth:
                chain_classes = [classes_by_id[cid] for cid in inh['chain_ids'] if cid in classes_by_id]
                chain_mod_ids = [c['module_id'] for c in chain_classes]
                chain_locs = [
                    {
                        'file': c['file'],
                        'start_line': c['extent_start_line'],
                        'end_line': c['end_line'],
                        'kind': 'inheritance_chain_class',
                    }
                    for c in chain_classes
                ]
                confirmed_inh = inh['fully_resolved'] and not inh['cyclic_inheritance']
                add_observation(
                    rule_id='CODELY-ARCH-010',
                    key_parts=(cls['id'],),
                    category='inheritance',
                    priority='MEDIUM',
                    title=f'Deep inheritance hierarchy: {cls["qualified_name"]}',
                    explanation=(
                        f'Class {cls["qualified_name"]} in {cls["file"]} has inheritance depth {inh["depth"]} '
                        f'({" -> ".join(inh["chain_names"])}), exceeding threshold {thresholds.max_inheritance_depth}.'
                    ),
                    module_ids=chain_mod_ids,
                    symbols=chain_classes,
                    source_locations=chain_locs or cls_loc,
                    edge_ids=[],
                    dependency_paths=[],
                    component_ids=[],
                    observed_metric={
                        'name': 'inheritance_depth',
                        'value': inh['depth'],
                        'unit': 'levels',
                        'details': {
                            'chain': inh['chain_names'],
                            'fully_resolved': inh['fully_resolved'],
                            'cyclic_inheritance': inh['cyclic_inheritance'],
                        },
                    },
                    configured_threshold=_threshold_meta(thresholds, 'max_inheritance_depth', 'levels'),
                    suggested_improvement=(
                        'Evaluate composition, delegation or Python Protocol interfaces where shared behavior does not '
                        'require deep subtype hierarchies.'
                    ),
                    trade_offs=[
                        'Composition requires explicit forwarding or helper injection rather than implicit method inheritance.',
                        'Framework or domain taxonomies sometimes intentionally extend base hierarchies.',
                    ],
                    validation_method=(
                        'Verify inheritance depth drops in structure analysis while maintaining behavioral contract tests.'
                    ),
                    confidence='confirmed' if confirmed_inh else 'heuristic',
                    evidence_classification='confirmed_structural' if confirmed_inh else 'heuristic_maintainability',
                    known_limitations=[
                        'Dynamic base expressions, metaclasses and external multi-level class hierarchies are not deeply traversed.',
                    ],
                )

            method_count = len(methods_by_class[cls['id']])
            if method_count > thresholds.max_class_methods:
                add_observation(
                    rule_id='CODELY-ARCH-011',
                    key_parts=(cls['id'], 'class_methods'),
                    category='responsibility_concentration',
                    priority='MEDIUM',
                    title=f'Potential concentration of responsibilities in class {cls["qualified_name"]}',
                    explanation=(
                        f'Class {cls["qualified_name"]} in {cls["file"]} defines {method_count} direct method(s), '
                        f'exceeding threshold {thresholds.max_class_methods}.'
                    ),
                    module_ids=[cls['module_id']],
                    symbols=[cls],
                    source_locations=cls_loc,
                    edge_ids=[],
                    dependency_paths=[],
                    component_ids=[],
                    observed_metric={'name': 'class_methods', 'value': method_count, 'unit': 'methods'},
                    configured_threshold=_threshold_meta(thresholds, 'max_class_methods', 'methods'),
                    suggested_improvement=(
                        'Inspect whether the class handles multiple independent concerns that can be delegated to '
                        'smaller collaborator classes.'
                    ),
                    trade_offs=[
                        'Extracting collaborator classes adds object wiring and indirection.',
                        'Protocol implementations or rich domain entities may cohesively expose many small methods.',
                    ],
                    validation_method='Re-run structure analysis and verify all class behavioral tests pass.',
                    confidence='heuristic',
                    evidence_classification='heuristic_maintainability',
                    known_limitations=[
                        'Method count alone does not prove low cohesion; small cohesive helper methods can inflate counts.',
                    ],
                )

    observations.sort(
        key=lambda obs: (
            PRIORITY_ORDER[obs['priority']],
            obs['rule_id'],
            obs['affected_modules'][0]['file'] if obs['affected_modules'] else '',
            obs['id'],
        )
    )
    obs_truncated = len(observations) > options.max_observations
    if obs_truncated:
        diagnostics.append({'code': 'max_observations', 'source': 'evaluator'})
        observations = observations[: options.max_observations]

    truncated = obs_truncated or diagnostics_truncated
    unresolved_internal_count = sum(len(v) for v in internal_unresolved_imports.values())
    ambiguous_imports_count = sum(1 for imp in structure.imports if imp.get('resolution') == 'ambiguous')
    unparsed_modules_count = sum(not mod.get('parsed') for mod in structure.modules)

    if cannot_evaluate:
        status = 'error'
    elif (
        structure.status != 'complete'
        or architecture.status != 'complete'
        or truncated
        or unresolved_internal_count > 0
        or ambiguous_imports_count > 0
        or unparsed_modules_count > 0
    ):
        status = 'partial'
    else:
        status = 'complete'

    by_priority = Counter(obs['priority'] for obs in observations)
    by_category = Counter(obs['category'] for obs in observations)
    by_classification = Counter(obs['evidence_classification'] for obs in observations)

    summary = {
        'total_observations': len(observations),
        'by_priority': {level: by_priority.get(level, 0) for level in ('HIGH', 'MEDIUM', 'LOW')},
        'by_category': dict(sorted(by_category.items())),
        'by_evidence_classification': {
            kind: by_classification.get(kind, 0)
            for kind in ('confirmed_structural', 'heuristic_maintainability')
        },
        'evaluated_modules': len(nodes_by_id),
        'evaluated_edges': len(architecture.edges),
        'evaluated_classes': len(structure.classes),
        'evaluated_functions': len(structure.functions),
    }

    supporting_metrics = {
        'graph': deepcopy(architecture.statistics),
        'structure': {
            'modules': len(structure.modules),
            'parsed_modules': sum(bool(mod.get('parsed')) for mod in structure.modules),
            'classes': len(structure.classes),
            'functions': len(structure.functions),
            'imports': len(structure.imports),
            'internal_dependencies': len(structure.internal_dependencies),
            'external_dependencies': len(structure.external_dependencies),
            'unresolved_internal_imports': unresolved_internal_count,
            'ambiguous_imports': ambiguous_imports_count,
            'unclassified_external_imports': unclassified_external_count,
        },
    }

    policy_payload = {
        **active_policy.to_dict(),
        'policy_configured': policy_supplied,
        'layer_rules_active': bool(active_policy.layers is not None and active_policy.layers.has_explicit_rules()),
    }

    coverage = {
        'structure_status': structure.status,
        'graph_status': architecture.status,
        'graph_structure_consistent': consistent,
        'policy_configured': policy_supplied,
        'layer_rules_active': policy_payload['layer_rules_active'],
        'parsed_modules': supporting_metrics['structure']['parsed_modules'],
        'unparsed_modules': unparsed_modules_count,
        'unresolved_internal_imports': unresolved_internal_count,
        'ambiguous_imports': ambiguous_imports_count,
        'unclassified_external_imports': unclassified_external_count,
        'truncated': truncated,
        'diagnostics_truncated': diagnostics_truncated,
        'observations_truncated': obs_truncated,
        'limits': asdict(options),
        'limitations': LIMITATIONS,
    }

    return ArchitectureEvaluationResult(
        schema_version='1.0.0',
        status=status,
        policy=policy_payload,
        summary=summary,
        observations=observations,
        supporting_metrics=supporting_metrics,
        diagnostics=diagnostics,
        coverage=coverage,
        _module_catalog=module_catalog,
        _symbol_catalog=symbol_catalog,
        _path_catalog=path_catalog,
        _edge_catalog=edge_catalog,
    )
