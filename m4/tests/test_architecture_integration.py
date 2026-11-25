import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pydantic import ValidationError

from ai_intelligence.architecture_integration import (
    ArchitectureAdviceResponse, ArchitecturePolicy, SnapshotIdentity, review_architecture,
)
from ai_intelligence.architecture_adapter import project_structure
from ai_intelligence.context import ContextError, RepositoryContext
from ai_intelligence.gemini import ProviderError
from test_architecture_adapter import FIXTURE, IDENTITY
from test_guidelines import GuidelineMock


class ArchitectureIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = RepositoryContext(root=FIXTURE / "checkout", **IDENTITY)
        self.report = json.loads((FIXTURE / "report.json").read_text())
        self.provider = GuidelineMock("arch.avoid-circular-dependencies")
        self.binding = SnapshotIdentity(**IDENTITY)

    def review(self, **overrides):
        options = IDENTITY | {"report_binding": self.binding} | overrides
        return review_architecture(self.snapshot, self.report, self.provider, **options)

    def test_bound_report_returns_json_ready_grounded_advice_and_coverage(self):
        policy = ArchitecturePolicy(mandatory_guideline_ids=("arch.avoid-circular-dependencies",))
        result = self.review(requirements="Review this dependency boundary.", policy=policy)
        self.assertEqual((result.project_id, result.revision), tuple(IDENTITY.values()))
        self.assertEqual(result.mode, "mock")
        self.assertEqual(len(result.observed_graph.nodes), 12)
        self.assertEqual(len(result.observed_graph.edges), 7)
        self.assertEqual(result.coverage, self.report["coverage"])
        self.assertEqual(result.unresolved_references, self.report["unresolved_references"])
        self.assertEqual(len(result.omitted_nodes), 1)
        self.assertTrue(result.requires_developer_review)
        proposal = result.advice.recommendations[0]
        self.assertEqual(proposal.guideline_ids, ["arch.avoid-circular-dependencies"])
        self.assertEqual(set(proposal.evidence_ids), {item.id for item in result.source_evidence})
        selected = next(item for item in result.selected_guidelines if item.guideline.id == proposal.guideline_ids[0])
        self.assertEqual(selected.policy, "mandatory")
        self.assertEqual(ArchitectureAdviceResponse.model_validate_json(result.model_dump_json()), result)

    def test_stale_or_cross_project_report_is_rejected_before_provider(self):
        for different in ({"revision": "old-revision"}, {"project_id": "different-project"}):
            with self.subTest(different=different):
                self.binding = SnapshotIdentity(**(IDENTITY | different))
                with self.assertRaisesRegex(ContextError, "report binding is stale"):
                    self.review()
                self.assertFalse(hasattr(self.provider, "payload"))

    def test_unauthorized_snapshot_cannot_be_used_with_valid_report_binding(self):
        for different in ({"revision": "stale"}, {"project_id": "different-project"}):
            with self.subTest(different=different):
                self.snapshot = RepositoryContext(root=FIXTURE / "checkout", **(IDENTITY | different))
                with self.assertRaisesRegex(ContextError, "snapshot does not match"):
                    self.review()
                self.assertFalse(hasattr(self.provider, "payload"))

    def test_missing_or_blank_trusted_identity_is_rejected(self):
        for invalid in ("", "  ", None):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                self.review(revision=invalid)
        with self.assertRaisesRegex(ContextError, "report binding is stale"):
            self.review(report_binding=None)
        self.assertFalse(hasattr(self.provider, "payload"))

    def test_report_paths_cannot_escape_or_read_symlink_targets(self):
        module = self.report["modules"][0]
        for path in ("../outside.py", "/outside.py", "src\\outside.py"):
            with self.subTest(path=path), self.assertRaises(ValidationError):
                module["file"] = path
                self.review()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / "checkout"
            checkout.mkdir()
            outside = root / "outside.py"
            outside.write_text("value = 1\n")
            (checkout / "linked.py").symlink_to(outside)
            self.snapshot = RepositoryContext(root=checkout, **IDENTITY)
            self.report["modules"] = [module | {"file": "linked.py", "end_line": 1}]
            self.report["internal_dependencies"] = []
            with self.assertRaisesRegex(ContextError, "outside the authorized snapshot"):
                self.review()
        self.assertFalse(hasattr(self.provider, "payload"))

    def test_unknown_policy_and_bad_provider_citations_fail(self):
        with self.assertRaisesRegex(ValueError, "Unknown mandatory"):
            self.review(policy=ArchitecturePolicy(mandatory_guideline_ids=("arch.unknown",)))
        self.assertFalse(hasattr(self.provider, "payload"))
        self.provider.reference = "arch.unknown"
        with self.assertRaisesRegex(ProviderError, "unselected guideline"):
            self.review()

    def test_generation_failure_does_not_replace_or_change_observed_graph(self):
        before = project_structure(self.snapshot, self.report, **IDENTITY)

        class Unavailable:
            mode = "groq"
            calls = 0

            def generate(self, instruction, payload, schema):
                self.calls += 1
                raise ProviderError("Groq request timed out")

        self.provider = Unavailable()
        with self.assertRaisesRegex(ProviderError, "timed out"):
            self.review()
        self.assertEqual(self.provider.calls, 1)
        self.assertEqual(project_structure(self.snapshot, self.report, **IDENTITY), before)

    def test_unknown_citation_and_dangling_proposal_are_rejected(self):
        class InvalidAdvice(GuidelineMock):
            change = "citation"

            def generate(self, instruction, payload, schema):
                result = super().generate(instruction, payload, schema).model_dump()
                if self.change == "citation":
                    result["recommendations"][0]["evidence_ids"] = ["fabricated.py:1-1"]
                else:
                    result["proposed_edges"] = [{
                        "id": "proposed-edge", "source": payload["observed"]["nodes"][0]["id"],
                        "target": "absent", "label": "imports",
                    }]
                return schema.model_validate(result)

        self.provider = InvalidAdvice("arch.avoid-circular-dependencies")
        with self.assertRaisesRegex(ProviderError, "unknown source"):
            self.review()
        self.provider.change = "endpoint"
        with self.assertRaisesRegex(ProviderError, "unknown endpoint"):
            self.review()
