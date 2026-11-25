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

class ScanResult(BaseModel):
    findings: list[Finding]
    # A partial scanner result must not masquerade as a completed clean scan.
    diagnostics: list[dict] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)

class FindingsResponse(BaseModel):
    project_id: str
    status: Literal['completed', 'not_scanned', 'stale']
    repository_version: str
    cached: bool
    diagnostics: list[dict] = Field(default_factory=list)
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

class Node(BaseModel):
    id: str
    label: str
    type: str
    file: str

class Edge(BaseModel):
    source: str
    target: str
    relationship: str
    file: str | None = None
    start_line: int | None = None
    end_line: int | None = None

class Graph(BaseModel):
    status: Literal['complete', 'partial'] = 'complete'
    diagnostics: list[dict] = Field(default_factory=list)
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
