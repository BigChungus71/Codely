"""Live Groq contract and source-grounding checks using synthetic source only."""
import ast
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_intelligence.architecture import ObservedGraph, advise
from ai_intelligence.context import RepositoryContext
from ai_intelligence.contracts import Finding
from ai_intelligence.gemini import ProviderError
from ai_intelligence.integration import review_normalized
from ai_intelligence.providers import create_generator


def vulnerability_review(index, generator, source):
    finding = Finding(
        id="synthetic-count-review", rule_id="fixture.numeric-parser", severity="ERROR",
        path="counts.py", start_line=7, end_line=7, cwe="CWE-95",
        message="The decimal inventory count parser evaluates untrusted text as Python code.",
    )
    result = review_normalized(index, finding.model_dump(), generator)
    assert result["mode"] == "groq" and result["scanner_finding"] == finding.model_dump()
    draft = result["interpretation"]
    for field in ("explanation", "root_cause", "potential_impact", "recommended_remediation"):
        assert draft[field].strip()
    print("Live review fields and citation IDs validated", flush=True)
    for field in ("explanation", "root_cause", "potential_impact", "recommended_remediation"):
        print(f"{field}: {draft[field]}", flush=True)
    print("Citations:", ", ".join(item["id"] for item in result["source_evidence"]), flush=True)
    assert result["edits"] and result["proposed_diff"]
    lines = source.splitlines()
    for edit in sorted(result["edits"], key=lambda edit: edit["start_line"], reverse=True):
        assert edit["path"] == finding.path
        lines[edit["start_line"] - 1:edit["end_line"]] = edit["suggested_code"].splitlines()
    parsed = ast.parse("\n".join(lines))
    parser = next(node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name == "parse_count")
    calls = {node.func.id for node in ast.walk(parser) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "eval" not in calls and "int" in calls
    print("Grounded proposed diff parsed and replaces eval with integer conversion", flush=True)


def architecture_review(index, generator):
    graph = ObservedGraph.model_validate({
        "nodes": [
            {"id": "parser", "label": "Inventory count parser", "location": {
                "path": "counts.py", "start_line": 5, "end_line": 7,
            }},
            {"id": "storage", "label": "Inventory recording", "location": {
                "path": "inventory.py", "start_line": 1, "end_line": 2,
            }},
        ],
        "edges": [
            {"id": "records", "source": "parser", "target": "storage", "label": "calls record_count",
             "location": {"path": "counts.py", "start_line": 7, "end_line": 7}},
        ],
    })
    result = advise(index, graph, "Keep parsing separate from recording and explain the testing trade-offs.", generator)
    assert result.mode == "groq" and result.observed_graph == graph
    assert result.advice.recommendations and result.source_evidence
    print(f"Live architecture review validated {len(result.advice.recommendations)} recommendations and "
          f"{len(result.source_evidence)} evidence citations", flush=True)


def main():
    try:
        generator = create_generator("groq")
    except ProviderError as error:
        raise SystemExit(str(error)) from None
    try:
        with TemporaryDirectory(prefix="codely-groq-synthetic-") as directory:
            root = Path(directory)
            source = ('"""Count intake for a fictional orchard."""\n'
                      'from inventory import record_count\n\n\n'
                      'def parse_count(raw):\n'
                      '    """Parse and record a base-10 integer count."""\n'
                      '    return record_count(eval(raw))\n')
            (root / "counts.py").write_text(source)
            (root / "inventory.py").write_text("def record_count(count: int):\n    return count\n")
            index = RepositoryContext("synthetic-groq", root)
            failures = 0
            for label, probe, args in (
                ("vulnerability review", vulnerability_review, (index, generator, source)),
                ("architecture review", architecture_review, (index, generator)),
            ):
                try:
                    probe(*args)
                except ProviderError as error:
                    failures += 1
                    print(f"{label} failed: {error}", flush=True)
                except (AssertionError, SyntaxError, StopIteration):
                    failures += 1
                    print(f"{label} failed its defensive verification", flush=True)
            return int(bool(failures))
    finally:
        generator.close()


if __name__ == "__main__":
    sys.exit(main())
