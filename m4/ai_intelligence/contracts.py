from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class SourceRange(Contract):
    path: str = Field(min_length=1, max_length=1024)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    @field_validator("path")
    @classmethod
    def relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (path.is_absolute() or ".." in path.parts or path.as_posix() != value
                or value == "." or any(ord(c) < 32 or c in "\\:" for c in value)):
            raise ValueError("Use a canonical repository-relative POSIX path")
        return value

    @model_validator(mode="after")
    def ordered(self):
        if self.end_line < self.start_line:
            raise ValueError("end_line precedes start_line")
        return self


class Finding(SourceRange):
    id: str = Field(min_length=1, max_length=200)
    rule_id: str = Field(min_length=1, max_length=300)
    severity: str = Field(min_length=1, max_length=40)
    message: str = Field(min_length=1, max_length=4000)
    cwe: str | None = Field(default=None, max_length=200)


class Evidence(SourceRange):
    id: str
    text: str
    reason: Literal["affected", "containing", "imports", "symbol", "keyword", "semantic"]
    similarity: float | None = None
    redacted: bool = False


class EditDraft(Contract):
    evidence_id: str
    replacement: str = Field(max_length=10000)
    explanation: str = Field(min_length=1, max_length=1600)


class ReviewDraft(Contract):
    explanation: str = Field(min_length=1, max_length=2500)
    root_cause: str = Field(min_length=1, max_length=1600)
    potential_impact: str = Field(min_length=1, max_length=1600)
    preconditions: list[str] = Field(max_length=10)
    evidence_ids: list[str] = Field(min_length=1, max_length=12)
    affected_components: list[str] = Field(max_length=12)
    recommended_remediation: str = Field(min_length=1, max_length=2500)
    assumptions_and_limitations: list[str] = Field(max_length=12)
    contextual_concerns: list[str] = Field(max_length=8)
    edits: list[EditDraft] = Field(max_length=4)
    verification_steps: list[str] = Field(max_length=12)


class CodeEdit(SourceRange):
    original_code: str
    suggested_code: str
    explanation: str


class ReviewResult(Contract):
    finding_id: str
    scanner_finding: Finding
    mode: Literal["gemini", "groq", "mock"]
    interpretation: ReviewDraft
    source_evidence: list[Evidence]
    affected_files: list[str]
    edits: list[CodeEdit]
    proposed_diff: str
