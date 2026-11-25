from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class Finding(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    rule_id: str
    source: str
    severity: Literal['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO', 'UNKNOWN']
    title: str
    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    message: str
    cwe: list[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)

class ScanCoverage(BaseModel):
    status: Literal['complete', 'partial', 'error', 'unsupported', 'timeout']
    detected_languages: list[str] = Field(default_factory=list)
    analyzed_languages: list[str] = Field(default_factory=list)
    unsupported_languages: list[str] = Field(default_factory=list)
    rule_sets: list[str] = Field(default_factory=list)
    scanned_files: int = Field(default=0, ge=0)
    excluded_files: int = Field(default=0, ge=0)
    excluded_directory_count: int = Field(default=0, ge=0)
    unscanned_supported_files: int = Field(default=0, ge=0)

class ScanResult(BaseModel):
    coverage: ScanCoverage | None = None
    diagnostics: list[dict] = Field(default_factory=list)
    findings: list[Finding]
    # A partial scanner result must not masquerade as a completed clean scan.
    errors: list[dict] = Field(default_factory=list)

class FindingsResponse(BaseModel):
    coverage: ScanCoverage | None = None
    diagnostics: list[dict] = Field(default_factory=list)
    project_id: str
    status: Literal['completed', 'not_scanned', 'stale']
    repository_version: str
    cached: bool
    scanned_at: str | None = None
    findings: list[Finding]

class Explanation(BaseModel):
    finding_id: str
    status: Literal['completed'] = 'completed'
    explanation: str = Field(min_length=1)
    potential_impact: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    suggested_code: str | None = None
    requires_developer_review: Literal[True] = True
    assumptions_and_limitations: list[str] = Field(default_factory=list)

class GraphSource(BaseModel):
    model_config = ConfigDict(extra='allow')
    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

class Node(BaseModel):
    model_config = ConfigDict(extra='allow')
    files: list[str] = Field(default_factory=list)
    evidence: list[GraphSource] = Field(default_factory=list)
    id: str
    label: str
    type: str
    file: str

class Edge(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str | None = None
    confidence: Literal['confirmed', 'inferred'] | None = None
    evidence: list[GraphSource] = Field(default_factory=list)
    file: str | None = None
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    source: str
    target: str
    relationship: str

class Graph(BaseModel):
    model_config = ConfigDict(extra='allow')
    graph_type: Literal['dependencies', 'system'] = 'dependencies'
    status: Literal['complete', 'partial', 'unsupported', 'error'] = 'complete'
    diagnostics: list[dict] = Field(default_factory=list)
    coverage: dict = Field(default_factory=dict)
    project_id: str
    nodes: list[Node]
    edges: list[Edge]

class Project(BaseModel):
    project_id: str
    name: str
    status: Literal['ready']
    languages: list[str]

class ProjectsResponse(BaseModel):
    projects: list[Project]

class TreeNode(BaseModel):
    name: str
    path: str
    type: Literal['file', 'directory']
    children: list['TreeNode'] | None = None

class TreeResponse(BaseModel):
    project_id: str
    tree: list[TreeNode]

class FileResponse(BaseModel):
    project_id: str
    path: str
    language: str
    content: str
