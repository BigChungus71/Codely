"""Generate the offline M1 architecture handoff from synthetic Python source."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_intelligence.architecture_adapter import project_structure
from ai_intelligence.architecture_integration import SnapshotIdentity, review_architecture
from ai_intelligence.context import RepositoryContext
from ai_intelligence.gemini import ProviderError


CYCLE = {
    "orders.py": "from payments import charge\ndef place_order(total):\n    return charge(total)\n",
    "payments.py": "from orders import place_order\ndef charge(total):\n    return total\n",
}
SIMPLE = {"app.py": "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\ndef health():\n    return {'ok': True}\n"}
PARTIAL = {"app.py": "import missing_local_dependency\ndef run():\n    return None\n",
           "broken.py": "def incomplete(:\n"}


class HandoffMock:
    mode = "mock"

    def __init__(self, propose_changes):
        self.propose_changes = propose_changes

    def generate(self, instruction, payload, schema):
        draft = {"recommendations": [], "proposed_nodes": [], "proposed_edges": [],
                 "limitations": ["Offline mock. No provider API was called."]}
        if not self.propose_changes:
            draft["limitations"].append("Preserve the single-module health endpoint. Additional layers have no demonstrated benefit.")
            return schema.model_validate(draft)

        left, right = payload["observed"]["edges"]
        assert (left["source"], left["target"]) == (right["target"], right["source"])
        draft.update(
            recommendations=[{
                "concern": "The observed order and payment modules import each other.",
                "evidence_ids": [left["evidence_id"], right["evidence_id"]],
                "principle": "Avoid circular dependencies",
                "guideline_ids": ["arch.avoid-circular-dependencies"],
                "proposed_modification": "Remove the unused reverse import. Add a shared contract only if both modules later need it.",
                "expected_benefits": ["Clearer dependency direction and simpler module initialization."],
                "trade_offs": ["A shared contract would introduce another module to maintain."],
                "complexity": "low",
                "affected_components": [left["source"], left["target"]],
                "validation_requirements": ["Verify import order and existing checkout behavior."],
                "assumptions_and_limitations": ["The proposed shared contract is an optional overlay example."],
            }],
            proposed_nodes=[{"id": "proposal:payment-contract", "label": "Optional payment contract"}],
            proposed_edges=[{"id": "proposal:orders-contract", "source": left["source"],
                             "target": "proposal:payment-contract", "label": "may use"}],
        )
        return schema.model_validate(draft)


class SimulatedUnavailable:
    mode = "groq"

    def generate(self, instruction, payload, schema):
        raise ProviderError("Simulated provider unavailability")


def build_fixtures(analyze_repository):
    fixtures = {}
    with TemporaryDirectory(prefix="codely-architecture-handoff-") as directory:
        root = Path(directory)
        for name, project, files in (
            ("a-current-cycle", "cycle", CYCLE),
            ("b-mock-proposal", "cycle", CYCLE),
            ("c-small-app", "small", SIMPLE),
            ("d-partial-analysis", "partial", PARTIAL),
            ("e-advice-unavailable", "cycle", CYCLE),
        ):
            checkout = root / name
            checkout.mkdir()
            for path, source in files.items():
                (checkout / path).write_text(source, encoding="utf-8")
            identity = {"project_id": f"synthetic-{project}", "revision": f"synthetic-{project}-v1"}
            snapshot = RepositoryContext(root=checkout, **identity)
            report = analyze_repository(str(checkout)).to_dict()
            projected = project_structure(snapshot, report, **identity)
            payload = projected.model_dump(mode="json", exclude={"graph", "source_evidence"}) | {
                "observed_graph": projected.graph.model_dump(mode="json"),
                "source_evidence": [], "selected_guidelines": [], "registry_version": None,
                "advice": None, "requires_developer_review": True,
                "provider": {"status": "not_requested", "mode": None, "code": None},
            }
            provider = {
                "b-mock-proposal": HandoffMock(True),
                "c-small-app": HandoffMock(False),
                "e-advice-unavailable": SimulatedUnavailable(),
            }.get(name)
            if provider is not None:
                try:
                    reviewed = review_architecture(
                        snapshot, report, provider, report_binding=SnapshotIdentity(**identity),
                        requirements="Keep the design minimal.", **identity,
                    )
                except ProviderError:
                    if not isinstance(provider, SimulatedUnavailable):
                        raise
                    payload["provider"] = {"status": "unavailable", "mode": "groq",
                                           "code": "provider_unavailable"}
                else:
                    assert reviewed.mode == "mock" and reviewed.observed_graph == projected.graph
                    payload.update(reviewed.model_dump(mode="json", exclude={"mode"}))
                    payload["provider"] = {"status": "ready", "mode": "mock", "code": None}
            fixtures[name] = payload
    return fixtures


def main():
    from backend.app.analyzers.structure_analyzer import analyze_repository

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--check", action="store_true", help="Verify that generated JSON matches checked-in fixtures")
    args = parser.parse_args()
    for name, payload in build_fixtures(analyze_repository).items():
        path = args.output / f"{name}.json"
        expected = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        if args.check:
            if path.read_text(encoding="utf-8") != expected:
                raise SystemExit(f"Fixture differs: {path.name}")
        else:
            args.output.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")


if __name__ == "__main__":
    main()
