"""Versioned architecture guidance and deterministic applicability checks."""

import re
from collections.abc import Collection, Iterable
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from .contracts import Contract, Evidence


_REGISTRY = Path(__file__).with_name("architecture_guidelines.json")
_ID_PATTERN = r"^arch\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
_VERSION_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+$"
Signal = Literal["small_scope", "mixed_concerns", "infrastructure_dependency", "shared_dependency",
                 "dependency_cycle", "authorization_boundary", "deployment_configuration",
                 "test_boundary", "fastapi", "spring_boot"]


class GuidelineSource(Contract):
    title: str = Field(min_length=1)
    url: HttpUrl

    @model_validator(mode="after")
    def public_https(self):
        if self.url.scheme != "https" or self.url.username or self.url.password:
            raise ValueError("Guideline source must be an HTTPS reference without credentials")
        return self


class ChecklistReference(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
    source: GuidelineSource


class Guideline(Contract):
    id: str = Field(pattern=_ID_PATTERN)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    applicability: str = Field(min_length=1)
    limitations: str = Field(min_length=1)
    source: GuidelineSource
    benefits: tuple[str, ...] = Field(min_length=1)
    trade_offs: tuple[str, ...] = Field(min_length=1)
    registry_version: str = Field(pattern=_VERSION_PATTERN)
    signals: tuple[Signal, ...] = Field(min_length=1)
    requirement_terms: tuple[str, ...] = ()
    checklist_references: tuple[ChecklistReference, ...] = ()


class GuidelineRegistry(Contract):
    version: str = Field(pattern=_VERSION_PATTERN)
    guidelines: tuple[Guideline, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_catalog(self):
        if len({guideline.id for guideline in self.guidelines}) != len(self.guidelines):
            raise ValueError("Duplicate architecture guideline ID")
        if any(guideline.registry_version != self.version for guideline in self.guidelines):
            raise ValueError("Guideline version must match the registry version")
        return self


class SelectedGuideline(Contract):
    guideline: Guideline
    policy: Literal["advisory", "mandatory"]
    matched_by: tuple[str, ...]


def load_registry(path: Path = _REGISTRY) -> GuidelineRegistry:
    return GuidelineRegistry.model_validate_json(path.read_bytes())


def _dependency_cycle(adjacency: dict[str, set[str]]) -> bool:
    for origin, targets in adjacency.items():
        pending = list(targets)
        visited = set()
        while pending:
            target = pending.pop()
            if target == origin:
                return True
            if target not in visited:
                visited.add(target)
                pending.extend(adjacency.get(target, ()))
    return False


def _observations(graph: dict, evidence: Iterable[Evidence]) -> set[str]:
    signals = set()
    code = "\n".join(item.text for item in evidence if not item.redacted).lower()
    if re.search(r"(?m)^\s*(?:from|import)\s+fastapi\b", code):
        signals.add("fastapi")
    if re.search(r"(?m)^\s*(?:import\s+org\.springframework\.boot\.|@springbootapplication\b)", code):
        signals.add("spring_boot")

    roles = {}
    patterns = {
        "web": r"routers?|routes?|controllers?|views?|endpoints?",
        "domain": r"domain|services?|use.?cases?|business",
        "infrastructure": r"repositories|repository|database|persistence|infrastructure|clients?|adapters?",
    }
    for node in graph["nodes"]:
        tokens = re.sub(r"[^a-z0-9]", " ", f'{node["label"]} {node["location"]["path"]}'.lower())
        roles[node["id"]] = {role for role, pattern in patterns.items()
                             if re.search(rf"\b(?:{pattern})\b", tokens)}

    adjacency = {}
    incoming = {}
    for edge in graph["edges"]:
        if edge["label"].strip().lower() not in {"imports", "depends on", "depends_on", "calls", "uses"}:
            continue
        source, target = edge["source"], edge["target"]
        adjacency.setdefault(source, set()).add(target)
        incoming.setdefault(target, set()).add(source)
        if "domain" in roles[source] and "infrastructure" in roles[target]:
            signals.update(("infrastructure_dependency", "test_boundary"))
        if roles[source] and roles[target] and roles[source] != roles[target]:
            signals.add("mixed_concerns")
    if _dependency_cycle(adjacency):
        signals.add("dependency_cycle")
    if any(len(sources) >= 3 for sources in incoming.values()):
        signals.add("shared_dependency")
    if len(roles) <= 3 and len(graph["edges"]) <= 2:
        signals.add("small_scope")
    if re.search(r"\b(?:authorize|authorization|permission|current_user|require_role|tenant_id)\b", code):
        signals.add("authorization_boundary")
    if re.search(r"\b(?:os\.getenv|os\.environ|process\.env|basesettings|configurationproperties)\b", code):
        signals.add("deployment_configuration")
    return signals


def select_guidelines(
    registry: GuidelineRegistry, graph: dict, evidence: Iterable[Evidence], requirements: str = "",
    *, mandatory_guideline_ids: Collection[str] = (),
) -> tuple[SelectedGuideline, ...]:
    mandatory = frozenset(mandatory_guideline_ids)
    if mandatory.difference(guideline.id for guideline in registry.guidelines):
        raise ValueError("Unknown mandatory architecture guideline ID")

    signals = _observations(graph, evidence)
    requirements = requirements.casefold()
    selected = []
    for guideline in sorted(registry.guidelines, key=lambda item: item.id):
        matches = sorted(signals.intersection(guideline.signals))
        if any(re.search(rf"\b{re.escape(term.casefold())}\b", requirements)
               for term in guideline.requirement_terms):
            matches.append("project_requirements")
        is_mandatory = guideline.id in mandatory
        if is_mandatory:
            matches.append("configured_policy")
        if matches:
            selected.append(SelectedGuideline(guideline=guideline, matched_by=tuple(matches),
                                               policy="mandatory" if is_mandatory else "advisory"))
    return tuple(selected)
