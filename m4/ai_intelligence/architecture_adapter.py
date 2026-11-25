"""Project trusted M3 structure reports into M4's source-grounded advice input."""
from collections.abc import Collection, Mapping
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from .architecture import ArchitectureResult, ObservedEdge, ObservedGraph, ObservedNode, advise
from .context import ContextError, RepositoryContext
from .contracts import Contract, Evidence, SourceRange
from .gemini import Generator


# Leave room for advise() to retrieve a repeated anchor even after all unique
# excerpts have been charged to its 16,000-character evidence budget.
_EVIDENCE_BUDGET = 12_000
_MAX_EXCERPT = 4_000


class _M3Record(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)


class _Module(_M3Record):
    id: str = Field(min_length=1, max_length=150)
    file: str
    names: list[str]
    parsed: bool
    is_package: bool
    start_line: int | None = None
    end_line: int | None = None


class _Located(_M3Record):
    file: str
    start_line: int
    end_line: int

    def location(self) -> SourceRange:
        return SourceRange(path=self.file, start_line=self.start_line, end_line=self.end_line)


class _Import(_Located):
    id: str = Field(min_length=1)
    module_id: str
    resolution: Literal["internal", "external", "stdlib", "unresolved", "ambiguous"]
    candidate_module_ids: list[str]


class _Dependency(_Located):
    id: str | None = Field(default=None, min_length=1, max_length=150)
    source_module_id: str
    target_module_id: str
    relationship: Literal["imports"]
    import_id: str
    target_parsed: bool

    def edge_id(self) -> str:
        if self.id is not None:
            return self.id
        identity = json.dumps([self.import_id, self.source_module_id, self.target_module_id,
                               self.file, self.start_line, self.end_line])
        return "dependency_" + sha256(identity.encode()).hexdigest()


class _Structure(_M3Record):
    schema_version: Literal["1.0.0"]
    status: Literal["complete", "partial", "error"]
    modules: list[_Module]
    imports: list[_Import]
    internal_dependencies: list[_Dependency]
    coverage: dict[str, JsonValue]
    diagnostics: list[dict[str, JsonValue]]
    unresolved_references: list[dict[str, JsonValue]]


class Omission(Contract):
    id: str
    reason: Literal["unparsed_module", "unanchored_module", "unconfirmed_import",
                    "endpoint_omitted", "node_limit", "edge_limit", "evidence_budget"]


class ArchitectureProjection(Contract):
    project_id: str
    revision: str
    graph: ObservedGraph
    structure_status: Literal["complete", "partial", "error"]
    coverage: dict[str, JsonValue]
    diagnostics: list[dict[str, JsonValue]]
    unresolved_references: list[dict[str, JsonValue]]
    omitted_nodes: list[Omission]
    omitted_edges: list[Omission]
    source_evidence: list[Evidence]


def _unique(records, identifier):
    result = {}
    for record in records:
        key = identifier(record)
        if key in result:
            raise ContextError("Duplicate identifier in M3 structure report")
        result[key] = record
    return result


def _source_anchor(index: RepositoryContext, location: SourceRange) -> Evidence:
    source = index.files.get(location.path)
    if source is None or location.end_line > len(source.lines):
        raise ContextError("M3 source evidence is outside the authorized snapshot")
    # The exact range was checked above, so failure here means the excerpt is
    # too large for advice. The caller records that omission.
    return index.retrieve(location, budget=32_000, include_related=False)[0]


def _evidence_cost(item: Evidence) -> int:
    return len(item.text) + 2 * len(item.path) + 180


def project_structure(
    index: RepositoryContext, structure: Mapping[str, object], *, project_id: str, revision: str,
) -> ArchitectureProjection:
    """Project a report labelled by the trusted caller with its checkout identity."""
    if not revision or (project_id, revision) != (index.project_id, index.revision):
        raise ContextError("M3 report identity does not match the authorized snapshot")
    report = _Structure.model_validate(structure)
    if report.status == "error":
        raise ContextError("M3 reported an unsuccessful structural analysis")

    modules = _unique(report.modules, lambda module: module.id)
    if len({module.file for module in modules.values()}) != len(modules):
        raise ContextError("Duplicate module path in M3 structure report")
    imports = _unique(report.imports, lambda entry: entry.id)
    dependencies = _unique(report.internal_dependencies, _Dependency.edge_id)
    if len({entry.import_id for entry in dependencies.values()}) != len(dependencies):
        raise ContextError("Duplicate dependency for an M3 import")
    unresolved_imports = {row["reference_id"] for row in report.unresolved_references
                          if row.get("kind") == "import" and isinstance(row.get("reference_id"), str)}
    nodes = {}
    edges = []
    node_evidence = {}
    omitted_nodes = {}
    omitted_edges = {}

    for module in sorted(modules.values(), key=lambda row: (row.file, row.id)):
        start, end = module.start_line, module.end_line
        span = SourceRange(path=module.file, start_line=1 if start is None else start,
                           end_line=1 if end is None else end)
        if (start is None) != (end is None):
            raise ContextError("Incomplete M3 module location")
        if not module.parsed:
            omitted_nodes[module.id] = "unparsed_module"
            continue
        if start is None:
            omitted_nodes[module.id] = "unanchored_module"
            continue
        source = index.files.get(span.path)
        if source is None or span.end_line > len(source.lines):
            raise ContextError("M3 module range is outside the authorized snapshot")
        anchor_line = next((number for number in range(span.start_line, span.end_line + 1)
                            if source.lines[number - 1].strip()), None)
        if anchor_line is None:
            omitted_nodes[module.id] = "unanchored_module"
            continue
        label = min(filter(None, module.names), key=lambda name: (len(name), name), default=module.file)
        anchor = SourceRange(path=span.path, start_line=anchor_line, end_line=anchor_line)
        nodes[module.id] = ObservedNode(id=module.id, label=label[:150], location=anchor)
        try:
            node_evidence[module.id] = _source_anchor(index, anchor)
        except ContextError:
            omitted_nodes[module.id] = "evidence_budget"

    for edge_id, dependency in sorted(dependencies.items(), key=lambda pair: (
        pair[1].file, pair[1].start_line, pair[1].end_line, pair[0],
    )):
        location = dependency.location()
        source_id, target_id = dependency.source_module_id, dependency.target_module_id
        if source_id not in modules or target_id not in modules:
            raise ContextError("Dangling M3 dependency endpoint")
        linked_import = imports.get(dependency.import_id)
        if linked_import is None:
            raise ContextError("M3 dependency has no linked import")
        if (linked_import.module_id != source_id or modules[source_id].file != location.path
                or linked_import.location() != location):
            raise ContextError("M3 dependency and import source locations disagree")
        if (linked_import.resolution != "internal" or len(linked_import.candidate_module_ids) != 1
                or linked_import.id in unresolved_imports):
            omitted_edges[edge_id] = "unconfirmed_import"
            continue
        if linked_import.candidate_module_ids[0] != target_id:
            raise ContextError("M3 dependency disagrees with its resolved import target")
        if dependency.target_parsed != modules[target_id].parsed:
            raise ContextError("M3 dependency disagrees with its target parse status")
        if source_id in omitted_nodes or target_id in omitted_nodes:
            omitted_edges[edge_id] = "endpoint_omitted"
            continue
        source = index.files[location.path]
        if location.end_line > len(source.lines):
            raise ContextError("M3 import range is outside the authorized snapshot")
        try:
            evidence = _source_anchor(index, location)
        except ContextError:
            omitted_edges[edge_id] = "evidence_budget"
            continue
        if not evidence.text.strip():
            raise ContextError("M3 import range has no source evidence")
        edges.append((ObservedEdge(id=edge_id, source=source_id, target=target_id,
                                   label=dependency.relationship, location=location), evidence))

    selected_nodes = {}
    selected_edges = []
    evidence_by_id = {}
    remaining = _EVIDENCE_BUDGET

    def include(anchors):
        nonlocal remaining
        pending = {item.id: item for item in anchors if item.id not in evidence_by_id}
        cost = sum(map(_evidence_cost, pending.values()))
        if cost > remaining or any(_evidence_cost(item) > _MAX_EXCERPT for item in pending.values()):
            return False
        evidence_by_id.update(pending)
        remaining -= cost
        return True

    # Prefer connected nodes, ordered by canonical source location. Fill any
    # remaining node slots with standalone modules in canonical file order.
    for edge, evidence in edges:
        endpoints = dict.fromkeys((edge.source, edge.target))
        new_nodes = [node_id for node_id in endpoints if node_id not in selected_nodes]
        if len(selected_edges) == 20:
            omitted_edges[edge.id] = "edge_limit"
        elif len(selected_nodes) + len(new_nodes) > 15:
            omitted_edges[edge.id] = "node_limit"
        elif include([evidence, *(node_evidence[node_id] for node_id in new_nodes)]):
            selected_nodes.update((node_id, nodes[node_id]) for node_id in new_nodes)
            selected_edges.append(edge)
        else:
            omitted_edges[edge.id] = "evidence_budget"

    for node_id, node in nodes.items():
        if node_id in selected_nodes or node_id in omitted_nodes:
            continue
        if len(selected_nodes) == 15:
            omitted_nodes[node_id] = "node_limit"
        elif include([node_evidence[node_id]]):
            selected_nodes[node_id] = node
        else:
            omitted_nodes[node_id] = "evidence_budget"

    if not selected_nodes:
        raise ContextError("M3 report has no modules with usable source evidence")
    graph = ObservedGraph(nodes=list(selected_nodes.values()), edges=selected_edges)
    return ArchitectureProjection(
        project_id=project_id, revision=revision, graph=graph, structure_status=report.status,
        coverage=report.coverage, diagnostics=report.diagnostics,
        unresolved_references=report.unresolved_references,
        omitted_nodes=[Omission(id=key, reason=value) for key, value in sorted(omitted_nodes.items())],
        omitted_edges=[Omission(id=key, reason=value) for key, value in sorted(omitted_edges.items())],
        source_evidence=list(evidence_by_id.values()),
    )


def advise_from_structure(
    index: RepositoryContext, structure: Mapping[str, object], requirements: str, generator: Generator,
    *, project_id: str, revision: str, mandatory_guideline_ids: Collection[str] = (),
) -> tuple[ArchitectureProjection, ArchitectureResult]:
    projection = project_structure(index, structure, project_id=project_id, revision=revision)
    return projection, advise(index, projection.graph, requirements, generator,
                              mandatory_guideline_ids=mandatory_guideline_ids)
