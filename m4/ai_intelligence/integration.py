from .context import RepositoryContext
from .contracts import Finding
from .gemini import Generator
from .review import explain


def review_normalized(
    index: RepositoryContext, normalized_finding: dict, generator: Generator,
) -> dict:
    """Run in an M2 worker with an authorized snapshot and injected provider."""
    if "file" in normalized_finding and "path" not in normalized_finding:
        normalized_finding = {
            key: value for key, value in normalized_finding.items()
            if key in Finding.model_fields
        } | {"path": normalized_finding["file"]}
        cwe = normalized_finding.get("cwe")
        if isinstance(cwe, list) and all(isinstance(item, str) for item in cwe):
            normalized_finding["cwe"] = ", ".join(cwe) or None
    finding = Finding.model_validate(normalized_finding)
    return explain(index, finding, generator).model_dump(mode="json")


def review_for_m2(
    index: RepositoryContext, normalized_finding: dict, generator: Generator,
) -> dict:
    """Project a grounded review onto M2's existing Explanation response."""
    review = review_normalized(index, normalized_finding, generator)
    draft = review["interpretation"]
    explanation = draft["explanation"]
    if review["mode"] == "mock":
        explanation = f"Offline mock. {explanation}"
    edits = review["edits"]
    return {
        "finding_id": review["finding_id"],
        "status": "completed",
        "explanation": explanation,
        "potential_impact": draft["potential_impact"],
        "recommendation": draft["recommended_remediation"],
        "suggested_code": edits[0]["suggested_code"] if len(edits) == 1 else None,
        "requires_developer_review": True,
    }
