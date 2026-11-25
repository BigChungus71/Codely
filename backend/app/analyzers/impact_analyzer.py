"""Architectural Security Impact Mapping: evidence relevance, not exploit propagation."""
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
import json
import re

from .architecture_graph import ArchitectureGraph, relative_file
from .architecture_traversal import TraversalLimits
from .impact_paths import dependency_analysis
from .semgrep_adapter import ScanResult
from .structure_analyzer import RepositoryStructure, enclosing_symbols
from .structure_extractor import stable_id


LIMITATIONS = [
    'Static import reachability indicates potential relevance, not confirmed exploit propagation or runtime calls.',
    'Severity and CWE belong only to the original finding; dependent modules are not assigned that vulnerability.',
    'The caller must supply scan, structure and graph from the same immutable repository version.',
    'Cross-input references are checked, but these existing contracts do not prove repository snapshot identity.',
    'Unknown, ambiguous, conditional, dynamic and omitted external dependencies limit coverage.',
    'Only bounded shortest observed import paths are returned; longer alternate paths are not enumerated.',
    'Unparsed source cannot be mapped to a trusted symbol; unmapped findings remain explicit.',
    'Source text, finding title/message, literal values and raw diagnostics are omitted from this evidence package.',
]


@dataclass(frozen=True)
class ImpactOptions:
    traversal: TraversalLimits = field(default_factory=TraversalLimits)
    max_findings: int = 1000
    max_modules: int = 128
    max_path_search_edges: int = 10000
    max_path_expansions: int = 10000
    max_evidence_per_edge: int = 32
    max_evidence_records: int = 10000
    max_diagnostics: int = 100

    def validate(self):
        self.traversal.validate()
        for name in ('max_findings','max_modules','max_path_search_edges','max_path_expansions',
                     'max_evidence_per_edge','max_evidence_records','max_diagnostics'):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError('Impact budgets must be positive integers')


@dataclass
class SecurityImpactResult:
    schema_version: str
    status: str
    scope: dict
    summary: dict
    finding_impacts: list[dict]
    module_impacts: list[dict]
    node_contexts: list[dict]
    evidence_edges: list[dict]
    diagnostics: list[dict]
    coverage: dict

    def to_dict(self):
        return asdict(self)

    def evidence_for_result(self, result_id):
        finding = next((item for item in self.finding_impacts if item['id'] == result_id), None)
        if finding is None:
            raise KeyError('Unknown impact result')
        analysis = next((item for item in self.module_impacts if item['id'] == finding['module_impact_id']), None)
        ids = {finding['vulnerable_node_id']} if finding['vulnerable_node_id'] else set()
        if analysis:
            ids.update(analysis['direct_dependent_node_ids'] + analysis['transitive_dependent_node_ids'])
        edge_ids = set(analysis['relevant_edge_ids']) if analysis else set()
        return deepcopy({'finding_impact': finding, 'dependency_analysis': analysis,
            'node_contexts': [node for node in self.node_contexts if node['id'] in ids],
            'evidence_edges': [edge for edge in self.evidence_edges if edge['id'] in edge_ids],
            'coverage': self.coverage, 'interpretation': LIMITATIONS[0]})

    def evidence_for_finding(self, finding_id):
        matches = [item for item in self.finding_impacts if item['finding_id'] == finding_id]
        if not matches:
            raise KeyError('Unknown finding')
        if len(matches) != 1:
            raise ValueError('Duplicate finding ID; select an impact result ID')
        return self.evidence_for_result(matches[0]['id'])


def _token(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,256}', value) is not None


def _metadata(raw):
    raw = raw if isinstance(raw, dict) else {}
    meta = {key: raw.get(key) if _token(raw.get(key)) else None for key in ('id','rule_id','source')}
    severity = raw.get('severity')
    meta['severity'] = severity if isinstance(severity,str) and severity in {'CRITICAL','HIGH','MEDIUM','LOW'} else None
    cwe = raw.get('cwe')
    cwe_valid = isinstance(cwe, list) and all(isinstance(value, str) and re.fullmatch(r'CWE-\d+', value) for value in cwe)
    meta['cwe'] = sorted(set(cwe)) if cwe_valid else []
    reason = None
    try:
        meta['file'] = relative_file(raw.get('file'))
    except ValueError:
        meta['file'] = None
        reason = 'invalid_finding_path'
    for key in ('start_line','end_line'):
        value = raw.get(key)
        meta[key] = value if type(value) is int and value > 0 else None
    if (any(meta[key] is None for key in ('id','rule_id','source','severity','start_line','end_line'))
            or not cwe_valid or not isinstance(raw.get('title'), str) or not isinstance(raw.get('message'), str)
            or (meta['start_line'] and meta['end_line'] and meta['end_line'] < meta['start_line'])):
        reason = reason or 'invalid_finding_metadata'
    return meta, reason


def _scan_data(scan):
    if isinstance(scan, ScanResult):
        payload = scan.to_dict()
    elif isinstance(scan, dict):
        payload = scan
    else:
        raise TypeError('Expected ScanResult or scanner envelope dictionary')
    findings = payload.get('findings')
    diagnostics = payload.get('diagnostics')
    status = payload.get('status')
    valid = isinstance(findings, list) and isinstance(diagnostics, list) and all(isinstance(d, dict) for d in diagnostics)
    status = status if isinstance(status,str) and status in {'complete','partial','error'} and valid else 'invalid'
    process_ok = valid and any(d.get('code') == 'scanner_exit' and d.get('exit_code') == 0 for d in diagnostics)
    incomplete = valid and any(d.get('code') in {'scanner_error','scanner_skipped_file','scanner_timeout',
                               'invalid_scanner_output','coverage_limit','python_syntax_error'} for d in diagnostics)
    complete = status == 'complete' and process_ok and not incomplete and not payload.get('errors')
    return findings if isinstance(findings, list) else [], status, complete, diagnostics if valid else []


def _consistent(structure, architecture):
    if architecture.coverage.get('structure_modules') != len(structure.modules):
        return False
    modules = {module['id']: module for module in structure.modules}
    relationships = {(dep['source_module_id'],dep['target_module_id'],dep['import_id'],
                      dep['file'],dep['start_line'],dep['end_line']) for dep in structure.internal_dependencies}
    for identifier, node in architecture._graph.nodes(data=True):
        module = modules.get(identifier)
        if module is None or relative_file(module['file']) != node['file'] or bool(module['parsed']) != node['parsed']:
            return False
    for source, target, edge in architecture._graph.edges(data=True):
        for proof in edge['evidence']:
            if (source,target,proof['import_id'],proof['file'],proof['start_line'],proof['end_line']) not in relationships:
                return False
    return True


def _symbol(symbol):
    if symbol is None:
        return None
    result = {key: symbol[key] for key in ('id','module_id','parent_id','name','qualified_name','kind',
        'is_async','file','start_line','end_line','extent_start_line') if key in symbol}
    result.setdefault('kind','class' if 'bases' in symbol else 'function')
    return result


def _diagnostics(items, source):
    result=[]
    for item in items:
        if not isinstance(item,dict):
            continue
        row={'source':source,'code':item['code'] if _token(item.get('code')) else 'analysis_diagnostic'}
        try:
            if item.get('file'):
                row['file']=relative_file(item['file'])
        except ValueError:
            pass
        if type(item.get('start_line')) is int and item['start_line']>0:
            row['start_line']=item['start_line']
        if type(item.get('exit_code')) is int:
            row['exit_code']=item['exit_code']
        result.append(row)
    return result


def analyze_security_impact(scan, structure: RepositoryStructure, architecture: ArchitectureGraph, *,
                            finding_id: str | None = None, options: ImpactOptions | None = None) -> SecurityImpactResult:
    """Reuse pipeline results. No scanner, AST parser or graph builder is invoked."""
    if not isinstance(structure, RepositoryStructure) or not isinstance(architecture, ArchitectureGraph):
        raise TypeError('Expected RepositoryStructure and ArchitectureGraph')
    if finding_id is not None and not _token(finding_id):
        raise ValueError('Invalid finding selection')
    options = options or ImpactOptions()
    options.validate()
    incoming, scanner_status, scanner_complete, scan_diagnostics = _scan_data(scan)
    diagnostics = []
    try:
        consistent = _consistent(structure, architecture)
    except (ValueError, KeyError, TypeError):
        consistent = False
    if not consistent:
        diagnostics.append({'code':'graph_structure_mismatch'})
    dependency_gaps = {
        'unresolved_imports':sum(item.get('resolution')=='unresolved' for item in structure.imports),
        'ambiguous_imports':sum(item.get('resolution')=='ambiguous' for item in structure.imports),
        'namespace_imports_without_file':sum(item.get('reason')=='namespace_package_without_source_file' for item in structure.imports),
        'unparsed_modules':sum(not module.get('parsed') for module in structure.modules)}
    if dependency_gaps['unresolved_imports'] or dependency_gaps['ambiguous_imports']:
        diagnostics.append({'code':'dependency_resolution_incomplete'})
    prepared = [_metadata(raw) for raw in incoming]
    id_counts = Counter(meta['id'] for meta, _ in prepared if meta['id'] is not None)
    selected = [(meta,reason) for meta,reason in prepared if finding_id is None or meta['id'] == finding_id]
    selected.sort(key=lambda pair: json.dumps(pair,sort_keys=True))
    if finding_id is not None and not selected:
        diagnostics.append({'code':'finding_id_not_found'})
    files = {item['file']: item for item in structure.files}
    modules = {item['file']: item for item in structure.modules}
    functions, classes = defaultdict(list), defaultdict(list)
    for item in structure.functions:
        functions[item['file']].append(item)
    for item in structure.classes:
        classes[item['file']].append(item)
    views, analyses, records, ordinals = {}, {}, [], Counter()
    edge_index = {(source,target): edge for source,target,edge in architecture._graph.edges(data=True)}
    all_edges = {edge['id']: edge for edge in edge_index.values()}
    for index, (meta, reason) in enumerate(selected):
        canonical = json.dumps(meta,sort_keys=True)
        ordinal = ordinals[canonical]
        ordinals[canonical] += 1
        record = {'id':stable_id('impact',canonical,ordinal), 'finding_id':meta['id'], 'finding':meta,
            'mapping_status':'unmapped', 'mapping_reason':None, 'vulnerable_node_id':None,
            'enclosing_symbol':None, 'enclosing_function':None, 'enclosing_class':None,
            'module_impact_id':None, 'direct_dependent_node_ids':[], 'transitive_dependent_node_ids':[],
            'relevant_edge_ids':[], 'evidence_path_ids':[],
            'source_references':[], 'coverage':{'truncated':False,'diagnostics':[]}}
        if meta['file'] and meta['start_line'] and meta['end_line'] and meta['start_line']<=meta['end_line']:
            record['source_references'].append({'file':meta['file'], 'start_line':meta['start_line'],
                'end_line':meta['end_line'], 'kind':'original_finding_location'})
        if not reason and id_counts[meta['id']] > 1:
            reason = 'duplicate_finding_id'
        if not reason and index >= options.max_findings:
            reason = 'max_findings'
            record['coverage']['truncated'] = True
        if not reason and not consistent:
            reason = 'graph_structure_mismatch'
        file, module = files.get(meta['file']), modules.get(meta['file'])
        if not reason and (file is None or module is None):
            reason = 'source_file_not_in_structure'
        if not reason and (not module['parsed'] or file.get('status') != 'parsed'):
            reason = 'source_not_parsed'
        if not reason and (type(file.get('line_count')) is not int or meta['end_line'] > file['line_count']):
            reason = 'source_location_out_of_range'
        node = architecture.module_for_file(meta['file']) if not reason else None
        if not reason and node is None:
            reason = 'architecture_node_not_found'
        if reason:
            record['mapping_reason'] = reason
            record['coverage']['diagnostics'].append({'code':reason})
            records.append(record)
            continue
        if meta['file'] not in views:
            views[meta['file']] = replace(structure, modules=[module], functions=functions[meta['file']], classes=classes[meta['file']])
        enclosing = enclosing_symbols(views[meta['file']],meta['file'],meta['start_line'])
        function = next((item for item in enclosing['functions'] if item['end_line'] >= meta['end_line']),None)
        cls = next((item for item in enclosing['classes'] if item['end_line'] >= meta['end_line']),None)
        record.update(mapping_status='mapped',mapping_reason='parsed_file_and_graph_node',vulnerable_node_id=node['id'],
            enclosing_function=_symbol(function),enclosing_class=_symbol(cls))
        record['enclosing_symbol'] = _symbol(function or cls) or {
            'id':module['id'],'kind':'module','file':meta['file'],'start_line':module.get('start_line'),
            'end_line':module.get('end_line')}
        for kind, symbol in [('enclosing_function',function),('enclosing_class',cls)]:
            if symbol:
                record['source_references'].append({'file':meta['file'],
                    'start_line':symbol['extent_start_line'],'end_line':symbol['end_line'],'kind':kind})
        if node['id'] not in analyses and len(analyses) < options.max_modules:
            analysis = dependency_analysis(architecture,node['id'],options,edge_index)
            sem_edges = [
                edge for edge in architecture.edges
                if edge.get('relationship') != 'imports'
                and edge.get('target') in ({node['id']} | set(analysis['direct_dependent_node_ids']) | set(analysis['transitive_dependent_node_ids']))
                and edge.get('source') != node['id']
            ]
            if sem_edges:
                analysis['inferred_relationships'] = [
                    {
                        'node_id': edge['source'],
                        'target_node_id': edge['target'],
                        'relationship': edge['relationship'],
                        'confidence': edge.get('confidence', 'inferred'),
                        'edge_id': edge['id'],
                    }
                    for edge in sorted(sem_edges, key=lambda e: (e['relationship'], e['source'], e['target']))
                ]
            analyses[node['id']] = analysis
        analysis = analyses.get(node['id'])
        if analysis:
            record.update(module_impact_id=analysis['id'],
                direct_dependent_node_ids=analysis['direct_dependent_node_ids'],
                transitive_dependent_node_ids=analysis['transitive_dependent_node_ids'],
                relevant_edge_ids=analysis['relevant_edge_ids'], evidence_path_ids=[path['id'] for path in analysis['paths']])
            record['coverage']['truncated'] = analysis['coverage']['truncated']
            record['coverage']['diagnostics'] += [{'code':code} for code in analysis['coverage']['limit_reasons']]
        else:
            record['coverage']['truncated'] = True
            record['coverage']['diagnostics'].append({'code':'max_modules'})
        records.append(record)
    selected_edges = sorted({edge for analysis in analyses.values() for edge in analysis['relevant_edge_ids']})
    evidence_edges = []
    used = 0
    evidence_truncated = False
    for identifier in selected_edges:
        edge = all_edges[identifier]
        count = min(options.max_evidence_per_edge, max(0,options.max_evidence_records-used))
        proof = edge['evidence'][:count]
        used += len(proof)
        truncated = len(proof) != len(edge['evidence'])
        evidence_truncated |= truncated
        evidence_edges.append({'id':identifier,'source':edge['source'],'target':edge['target'],
            'relationship':'imports','evidence':deepcopy(proof),
            'evidence_count':len(edge['evidence']),'provided_evidence_count':len(proof),'evidence_truncated':truncated})
    if evidence_truncated:
        diagnostics.append({'code':'impact_evidence_limit'})
        affected_edges={edge['id'] for edge in evidence_edges if edge['evidence_truncated']}
        for analysis in analyses.values():
            if affected_edges.intersection(analysis['relevant_edge_ids']):
                analysis['coverage']['truncated']=True
                analysis['coverage']['limit_reasons']=sorted(set(analysis['coverage']['limit_reasons'])|{'impact_evidence_limit'})
        for record in records:
            if affected_edges.intersection(record['relevant_edge_ids']):
                record['coverage']['truncated']=True
                record['coverage']['diagnostics'].append({'code':'impact_evidence_limit'})
    blocking_diagnostics = bool(diagnostics)
    source_diagnostics = (_diagnostics(scan_diagnostics,'scanner')
        + _diagnostics(structure.diagnostics,'structure') + _diagnostics(architecture.diagnostics,'architecture'))
    source_diagnostics.sort(key=lambda item:(item['source'],item['code'],item.get('file',''),item.get('start_line',0)))
    diagnostics_truncated = len(source_diagnostics)>options.max_diagnostics
    diagnostics += source_diagnostics[:options.max_diagnostics]
    if not scanner_complete:
        diagnostics.append({'code':'scanner_incomplete','source':'scanner'})
    node_ids = {row['vulnerable_node_id'] for row in records if row['vulnerable_node_id']}
    node_ids.update(node for analysis in analyses.values() for node in (
        analysis['direct_dependent_node_ids']+analysis['transitive_dependent_node_ids']
        +[rel['node_id'] for rel in analysis.get('inferred_relationships',[])]))
    node_contexts = [{key:deepcopy(architecture._graph.nodes[identifier][key]) for key in (
        'id','label','type','file','parsed','classification_confidence','classifications')}
        for identifier in sorted(node_ids)]
    mapped = sum(record['mapping_status']=='mapped' for record in records)
    truncated = any(record['coverage']['truncated'] for record in records) or evidence_truncated or diagnostics_truncated
    complete = (scanner_complete and structure.status=='complete' and architecture.status=='complete'
                and consistent and mapped==len(records) and not truncated and not blocking_diagnostics)
    status = 'complete' if complete else 'partial'
    if (scanner_status=='invalid' or not consistent or structure.status=='error' or architecture.status=='error'
            or (scanner_status=='error' and not records) or (finding_id is not None and not selected)):
        status = 'error'
    summary = {'findings_received':len(incoming),'findings_selected':len(records),'mapped_findings':mapped,
        'unmapped_findings':len(records)-mapped,'vulnerable_modules':len({r['vulnerable_node_id'] for r in records if r['vulnerable_node_id']}),
        'analyzed_modules':len(analyses),
        'unique_direct_dependents':len({node for a in analyses.values() for node in a['direct_dependent_node_ids']}),
        'unique_transitive_dependents':len({node for a in analyses.values() for node in a['transitive_dependent_node_ids']})}
    coverage = {'scanner_status':scanner_status,'scanner_complete':bool(scanner_complete),
        'structure_status':structure.status,'graph_status':architecture.status,
        'graph_structure_consistent':consistent,'snapshot_identity':'caller_required',
        'dependency_scope':'resolved_internal_imports_only','dependency_gaps':dependency_gaps,
        'diagnostics_truncated':diagnostics_truncated,
        'truncated':truncated,'limits':asdict(options),'limitations':LIMITATIONS}
    return SecurityImpactResult('1.0.0',status,{'type':'finding' if finding_id else 'repository','finding_id':finding_id},
        summary,records,sorted(analyses.values(),key=lambda item:item['vulnerable_node_id']),node_contexts,
        evidence_edges,diagnostics,coverage)


def analyze_finding_impact(finding_id, scan, structure, architecture, *, options=None):
    return analyze_security_impact(scan,structure,architecture,finding_id=finding_id,options=options)
