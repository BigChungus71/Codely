import json
import logging
from typing import Literal
from pathlib import Path
from datetime import datetime, timezone
from threading import Lock
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query
from . import adapters
from .repository import PROJECTS, root_for, tree, source, files, version, LANGUAGES
from .schemas import ScanResult, FindingsResponse, Explanation, Graph, ProjectsResponse, TreeResponse, FileResponse

router = APIRouter(prefix='/api', tags=['Codely'])
cache: dict = {}
scan_lock = Lock()
logger = logging.getLogger(__name__)


def invoke(service, *args):
    try:
        return service(*args)
    except HTTPException:
        raise
    except Exception as error:
        if getattr(error, "status_code", None) == 429:
            raise HTTPException(429, "AI provider rate limit reached. Retry shortly.") from None
        # Do not expose provider payloads, source code or credentials in HTTP errors.
        logger.warning('Analysis service failed: %s', service.__name__)
        raise HTTPException(502, 'Analysis service failed or returned an invalid response')


@router.get('/projects', response_model=ProjectsResponse)
def projects():
    available = []
    for project_id, (name, _, _) in PROJECTS.items():
        try:
            root = root_for(project_id)
        except HTTPException:
            continue
        languages = sorted({LANGUAGES[Path(path).suffix.lower()] for path in files(root)})
        available.append({'project_id': project_id, 'name': name, 'status': 'ready', 'languages': languages})
    if not available:
        raise HTTPException(503, 'No configured repository is available')
    return {'projects': available}


@router.get('/health')
def health():
    return {'status': 'ok'}


@router.get('/projects/{project_id}/tree', response_model=TreeResponse, response_model_exclude_none=True)
def repository_tree(project_id: str):
    return {'project_id': project_id, 'tree': tree(root_for(project_id))}


@router.get('/projects/{project_id}/files', response_model=FileResponse)
def repository_file(project_id: str, path: str = Query(min_length=1)):
    file, content = source(root_for(project_id), path)
    return {'project_id': project_id, 'path': file.relative_to(root_for(project_id)).as_posix(), 'language': LANGUAGES[file.suffix.lower()], 'content': content}


def validated_scan(root):
    result = ScanResult.model_validate(adapters.scan_repository(str(root)))
    seen = set()
    for finding in result.findings:
        _, text = source(root, finding.file)
        if finding.id in seen or finding.end_line < finding.start_line or finding.end_line > len(text.splitlines()):
            raise ValueError('Invalid finding location or duplicate ID')
        seen.add(finding.id)
    cover = result.coverage
    if result.errors or (cover and cover.status != 'complete'):
        status = {'unsupported': 422, 'timeout': 504}.get(cover.status if cover else None, 502)
        raise HTTPException(status, {
            'message': 'Scanner reported incomplete analysis; no completed result cached',
            'coverage': cover.model_dump() if cover else None,
            'diagnostics': result.diagnostics,
            'findings': [finding.model_dump() for finding in result.findings],
        })
    return result


@router.post('/projects/{project_id}/scan', response_model=FindingsResponse)
def scan(project_id: str):
    root = root_for(project_id)
    # One bounded process at a time, avoid duplicate demo scans.
    if not scan_lock.acquire(blocking=False):
        raise HTTPException(409, 'Another scan is running; retry shortly')
    try:
        current = version(root)
        previous = cache.get((project_id, root))
        if previous and previous['repository_version'] == current:
            return {**previous, 'cached': True}
        result = invoke(validated_scan, root)
        if version(root) != current:
            raise HTTPException(409, 'Repository changed during scan; retry')
        response = {'project_id': project_id, 'status': 'completed', 'repository_version': current, 'cached': False, 'coverage': result.coverage, 'diagnostics': result.diagnostics, 'scanned_at': datetime.now(timezone.utc).isoformat(), 'findings': [f.model_dump() for f in result.findings]}
        cache[(project_id, root)] = response
        return response
    finally:
        scan_lock.release()


@router.get('/projects/{project_id}/findings', response_model=FindingsResponse)
def findings(project_id: str):
    root = root_for(project_id)
    current = version(root)
    previous = cache.get((project_id, root))
    if previous and previous['repository_version'] == current:
        return {**previous, 'cached': True}
    return {'project_id': project_id, 'status': 'stale' if previous else 'not_scanned', 'repository_version': current, 'cached': False, 'findings': []}


def validated_explanation(finding, context):
    result = Explanation.model_validate(adapters.explain(finding, context))
    if result.finding_id != finding['id']: raise ValueError('Finding ID mismatch')
    return result


@router.post('/projects/{project_id}/findings/{finding_id}/explain', response_model=Explanation)
def explanation(project_id: str, finding_id: str):
    result = findings(project_id)
    if result['status'] != 'completed':
        raise HTTPException(409, 'Run a current successful scan before requesting an explanation')
    finding = next((f for f in result['findings'] if f['id'] == finding_id), None)
    if not finding: raise HTTPException(404, 'Finding not found')
    root = root_for(project_id)
    _, text = source(root, finding['file'])
    start = max(1, finding['start_line'] - 12)
    end = min(finding['end_line'] + 12, start + 100)
    context = {'project_id': project_id, 'root': root, 'file': finding['file'], 'start_line': start, 'content': '\n'.join(text.splitlines()[start-1:end])[:16000]}
    # Exclude potentially large raw scanner output from the LLM request.
    evidence = {k: v for k, v in finding.items() if k != 'evidence'}
    output = invoke(validated_explanation, evidence, context)
    if version(root) != result['repository_version']:
        raise HTTPException(409, 'Repository changed during explanation; scan again')
    return output


@router.get('/projects/{project_id}/findings/{finding_id}/impact')
def finding_impact(project_id: str, finding_id: str):
    from .teammate_services import build_project_graph
    from backend.app.analyzers.impact_analyzer import analyze_finding_impact

    scan = findings(project_id)
    if scan['status'] != 'completed':
        raise HTTPException(409, 'Run a current successful scan before reviewing impact')
    target = next((finding for finding in scan['findings'] if finding['id'] == finding_id), None)
    if target is None:
        raise HTTPException(404, 'Finding not found')
    if Path(target['file']).suffix.lower() != '.py':
        raise HTTPException(422, 'Static impact is available for Python findings only')
    if not any(item.get('code') == 'coverage' and item.get('rule_set') == 'python-security-v2'
               for item in scan['diagnostics']):
        raise HTTPException(503, 'Impact mapping requires the bundled Python scanner')
    root = root_for(project_id)
    structure, graph = invoke(build_project_graph, str(root))
    envelope = {**scan, 'status': 'complete'}
    result = invoke(analyze_finding_impact, finding_id, envelope, structure, graph)
    if version(root) != scan['repository_version']:
        raise HTTPException(409, 'Repository changed during impact mapping; scan again')
    return {'status': result.status, **result.evidence_for_finding(finding_id)}


def validated_graph(project_id, root, view):
    analyzer = adapters.system_architecture if view == 'system' else adapters.architecture
    raw = analyzer(str(root))
    graph = Graph.model_validate({'graph_type': view, **raw, 'project_id': project_id})
    if graph.graph_type != view:
        raise ValueError('Analyzer returned the wrong graph view')
    if graph.status in {'unsupported', 'error'}:
        raise HTTPException(422 if graph.status == 'unsupported' else 502, {
            'message': f'Architecture analysis is {graph.status}',
            'diagnostics': graph.diagnostics,
            'coverage': graph.coverage,
        })

    ids = {node.id for node in graph.nodes}
    if len(ids) != len(graph.nodes):
        raise ValueError('Duplicate node ID')
    edge_ids = [edge.id for edge in graph.edges if edge.id is not None]
    if len(edge_ids) != len(set(edge_ids)):
        raise ValueError('Duplicate edge ID')
    source_lines = {}

    def validate_source(file, start=None, end=None):
        if file not in source_lines:
            try:
                _, text = source(root, file)
            except HTTPException as error:
                raise ValueError('Invalid graph source') from error
            source_lines[file] = len(text.splitlines())
        if start is not None and not 1 <= start <= (end or start) <= source_lines[file]:
            raise ValueError('Invalid graph source range')

    for node in graph.nodes:
        for file in {node.file, *node.files}:
            validate_source(file)
        for anchor in node.evidence:
            validate_source(anchor.file, anchor.start_line, anchor.end_line)
    for edge in graph.edges:
        if edge.source not in ids or edge.target not in ids:
            raise ValueError('Dangling edge')
        if view == 'system' and (not edge.id or not edge.evidence or not edge.confidence):
            raise ValueError('Missing system relationship evidence')
        if edge.file:
            validate_source(edge.file, edge.start_line, edge.end_line)
        for anchor in edge.evidence:
            validate_source(anchor.file, anchor.start_line, anchor.end_line)
    return graph


@router.get('/projects/{project_id}/architecture', response_model=Graph)
def architecture(project_id: str, view: Literal['dependencies', 'system'] = 'dependencies'):
    root = root_for(project_id)
    current = version(root)
    result = invoke(validated_graph, project_id, root, view)
    if version(root) != current:
        raise HTTPException(409, 'Repository changed during analysis; retry')
    return result


class DesignQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    constraints: str | dict[str, str | int | float] = ''
    architecture_advice: bool = False


@router.post('/projects/{project_id}/design-question')
def design_question(project_id: str, request: DesignQuestion):
    from .teammate_services import answer_design, advise_design

    root = root_for(project_id)
    current = version(root)
    constraints = request.constraints
    if isinstance(constraints, dict):
        constraints = json.dumps(constraints, ensure_ascii=False, sort_keys=True)
    if len(constraints) > 4000:
        raise HTTPException(422, 'Constraints must fit within 4,000 characters')
    if request.architecture_advice:
        answer = invoke(advise_design, project_id, root, current, request.question, constraints)
    else:
        answer = invoke(answer_design, project_id, root, request.question, constraints)
    if current != version(root):
        raise HTTPException(409, 'Repository changed during retrieval; retry')
    return answer
