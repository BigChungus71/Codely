"""FastAPI worker boundary for architecture advice on an authorized snapshot."""

from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import JsonValue, StringConstraints, model_validator

from .architecture import ArchitectureResult
from .architecture_adapter import Omission, advise_from_structure
from .context import ContextError, RepositoryContext
from .contracts import Contract
from .gemini import Generator


Identifier = Annotated[str, StringConstraints(strict=True, min_length=1, pattern=r"\S")]


class SnapshotIdentity(Contract):
    """Identity supplied by M2 from its authorization and snapshot lifecycle."""

    project_id: Identifier
    revision: Identifier


class ArchitecturePolicy(Contract):
    """Server-side configuration supplied by M2, separate from user requirements."""

    mandatory_guideline_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def unique_guidelines(self):
        if len(set(self.mandatory_guideline_ids)) != len(self.mandatory_guideline_ids):
            raise ValueError("Duplicate mandatory architecture guideline ID")
        return self


class ArchitectureAdviceResponse(ArchitectureResult):
    project_id: str
    revision: str
    structure_status: Literal["complete", "partial", "error"]
    coverage: dict[str, JsonValue]
    diagnostics: list[dict[str, JsonValue]]
    unresolved_references: list[dict[str, JsonValue]]
    omitted_nodes: list[Omission]
    omitted_edges: list[Omission]
    requires_developer_review: Literal[True] = True


def review_architecture(
    snapshot: RepositoryContext,
    structure_report: Mapping[str, object],
    provider: Generator,
    *,
    project_id: str,
    revision: str,
    report_binding: SnapshotIdentity,
    requirements: str = "",
    policy: ArchitecturePolicy | None = None,
) -> ArchitectureAdviceResponse:
    """Review M3 output bound by M2 to the same authorized, captured snapshot.

    M2 supplies the current authorized identity and the binding recorded when
    this report was produced. Validate both before reading evidence or calling
    the provider. An identity match checks consistency of trusted metadata.
    """
    authorized = SnapshotIdentity(project_id=project_id, revision=revision)
    if (snapshot.project_id, snapshot.revision) != (authorized.project_id, authorized.revision):
        raise ContextError("Architecture snapshot does not match the authorized project and revision")
    if not isinstance(report_binding, SnapshotIdentity) or report_binding != authorized:
        raise ContextError("Architecture report binding is stale or belongs to another project")

    projection, result = advise_from_structure(
        snapshot, structure_report, requirements, provider,
        project_id=authorized.project_id, revision=authorized.revision,
        mandatory_guideline_ids=policy.mandatory_guideline_ids if policy else (),
    )
    return ArchitectureAdviceResponse(
        **result.model_dump(),
        **projection.model_dump(exclude={"graph", "source_evidence"}),
    )
