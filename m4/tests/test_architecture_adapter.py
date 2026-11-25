from copy import deepcopy
import json
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
import unittest

from pydantic import ValidationError

from ai_intelligence.architecture import ArchitectureDraft
from ai_intelligence.architecture_adapter import advise_from_structure, project_structure
from ai_intelligence.context import ContextError, RepositoryContext


FIXTURE = Path(__file__).parent / "fixtures" / "m3_structure"
IDENTITY = {"project_id": "fixture-project", "revision": "fixture-v1"}


class MockArchitecture:
    mode = "mock"

    def generate(self, instruction, payload, schema):
        if schema is not ArchitectureDraft:
            raise AssertionError("Expected the architecture draft contract")
        self.payload = payload
        edge = payload["observed"]["edges"][0]
        return schema.model_validate({
            "recommendations": [{
                "concern": "Offline mock: review the selected dependency boundary.",
                "evidence_ids": [edge["evidence_id"]],
                "principle": "Separation of concerns",
                "proposed_modification": "Introduce a narrow interface.",
                "expected_benefits": ["Supports isolated tests."],
                "trade_offs": ["Adds another interface."],
                "complexity": "low",
                "affected_components": [edge["source"], edge["target"]],
                "validation_requirements": ["Exercise both implementations."],
            }],
            "proposed_nodes": [{"id": "mock-interface", "label": "Mock interface"}],
            "proposed_edges": [{"id": "mock-link", "source": edge["source"],
                                "target": "mock-interface", "label": "uses"}],
            "limitations": ["Offline mock. No provider API was called."],
        })


class ArchitectureAdapterTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((FIXTURE / "report.json").read_text())
        self.index = RepositoryContext(root=FIXTURE / "checkout", **IDENTITY)

    def project(self):
        return project_structure(self.index, self.report, **IDENTITY)

    def test_committed_example_maps_modules_imports_and_evidence(self):
        result = self.project()
        self.assertEqual(result.structure_status, "partial")
        self.assertEqual(result.coverage, self.report["coverage"])
        self.assertEqual(result.diagnostics, self.report["diagnostics"])
        self.assertEqual({item.id for item in result.graph.nodes},
                         {item["id"] for item in self.report["modules"] if item["parsed"]})
        self.assertEqual(len(result.graph.nodes), 12)
        self.assertEqual(len(result.graph.edges), 7)
        source = next(item for item in self.report["internal_dependencies"] if item["file"] == "src/demo/api.py")
        edge = next(item for item in result.graph.edges if item.id == source["id"])
        self.assertEqual((edge.source, edge.target, edge.label),
                         (source["source_module_id"], source["target_module_id"], "imports"))
        self.assertEqual(edge.location.model_dump(), {
            "path": source["file"], "start_line": source["start_line"], "end_line": source["end_line"],
        })
        self.assertEqual([row.reason for row in result.omitted_nodes], ["unparsed_module"])
        self.assertIn(self.index.retrieve(edge.location, include_related=False)[0], result.source_evidence)

    def test_circular_dependencies_are_preserved(self):
        pairs = {(item.source, item.target) for item in self.project().graph.edges}
        module_ids = {row["file"]: row["id"] for row in self.report["modules"]}
        service = module_ids["src/demo/services.py"]
        helper = module_ids["src/demo/nested/helpers.py"]
        self.assertTrue({(service, helper), (helper, service)} <= pairs)

    def test_unresolved_references_stay_separate_and_contradictory_edges_are_omitted(self):
        dependency = self.report["internal_dependencies"][0]
        linked = next(row for row in self.report["imports"] if row["id"] == dependency["import_id"])
        linked["resolution"] = "ambiguous"
        result = self.project()
        self.assertNotIn(dependency["id"], {edge.id for edge in result.graph.edges})
        self.assertEqual(result.omitted_edges[0].reason, "unconfirmed_import")
        self.assertEqual(result.unresolved_references, self.report["unresolved_references"])
        self.assertTrue(any(row["kind"] == "call" for row in result.unresolved_references))

    def test_missing_source_and_invalid_locations_are_rejected(self):
        root = TemporaryDirectory()
        self.addCleanup(root.cleanup)
        missing = RepositoryContext(root=Path(root.name), **IDENTITY)
        with self.assertRaisesRegex(ContextError, "outside the authorized snapshot"):
            project_structure(missing, self.report, **IDENTITY)
        module = self.report["modules"][0]
        module["end_line"] = 10_000
        with self.assertRaisesRegex(ContextError, "outside the authorized snapshot"):
            self.project()
        module["file"] = "../outside.py"
        with self.assertRaises(ValidationError):
            self.project()

    def test_malformed_and_duplicate_reports_are_rejected(self):
        baseline = deepcopy(self.report)
        for field in ("modules", "imports", "internal_dependencies"):
            with self.subTest(field=field):
                self.report = deepcopy(baseline)
                self.report[field].append(self.report[field][0])
                with self.assertRaisesRegex(ContextError, "Duplicate identifier"):
                    self.project()
        self.report = deepcopy(baseline)
        self.report["modules"][0]["parsed"] = "yes"
        with self.assertRaises(ValidationError):
            self.project()

    def test_dangling_and_inconsistent_dependencies_are_rejected(self):
        dependency = self.report["internal_dependencies"][0]
        target = dependency["target_module_id"]
        dependency["target_module_id"] = "unknown"
        with self.assertRaisesRegex(ContextError, "Dangling"):
            self.project()
        dependency["target_module_id"] = target
        dependency["start_line"] = 1
        with self.assertRaisesRegex(ContextError, "locations disagree"):
            self.project()
        dependency["start_line"] = dependency["end_line"]
        dependency["import_id"] = "unknown-import"
        with self.assertRaisesRegex(ContextError, "no linked import"):
            self.project()

    def test_determinism_including_generated_edge_id(self):
        self.report["internal_dependencies"][0].pop("id")
        first = self.project()
        self.assertTrue(any(len(edge.id) == len("dependency_") + 64 for edge in first.graph.edges))
        for field in ("modules", "imports", "internal_dependencies"):
            self.report[field].reverse()
        for module in self.report["modules"]:
            module["names"].reverse()
        self.assertEqual(first, self.project())

    def test_graph_and_evidence_limits(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.report.update(modules=[], imports=[], internal_dependencies=[], unresolved_references=[])
            for number in range(19):
                file = f"module{number:02}.py"
                lines = ["# module", *(["import module01"] * 24 if number == 0 else [])]
                (root / file).write_text("\n".join(lines) + "\n")
                self.report["modules"].append({
                    "id": file, "file": file, "names": [file], "parsed": True,
                    "is_package": False, "start_line": 1, "end_line": len(lines),
                })
            for line in range(2, 26):
                location = {"file": "module00.py", "start_line": line, "end_line": line}
                self.report["imports"].append(location | {
                    "id": f"import-{line}", "module_id": "module00.py",
                    "resolution": "internal", "candidate_module_ids": ["module01.py"],
                })
                self.report["internal_dependencies"].append(location | {
                    "id": f"dependency-{line}", "source_module_id": "module00.py",
                    "target_module_id": "module01.py", "relationship": "imports",
                    "import_id": f"import-{line}", "target_parsed": True,
                })
            self.index = RepositoryContext(root=root, **IDENTITY)
            result = self.project()
            self.assertEqual(len(result.graph.nodes), 15)
            self.assertEqual(len(result.graph.edges), 20)
            self.assertEqual([row.reason for row in result.omitted_nodes], ["node_limit"] * 4)
            self.assertEqual([row.reason for row in result.omitted_edges], ["edge_limit"] * 4)

            # Large valid anchors can exhaust the evidence budget before the edge limit.
            (root / "module00.py").write_text("# module\n" + ("import module01 #" + "a" * 2900 + "\n") * 24)
            self.index = RepositoryContext(root=root, **IDENTITY)
            bounded, review = advise_from_structure(
                self.index, self.report, "Review dependency boundaries.", MockArchitecture(), **IDENTITY,
            )
            self.assertIn("evidence_budget", {row.reason for row in bounded.omitted_edges})
            self.assertEqual(review.mode, "mock")

    def test_project_and_revision_isolation(self):
        for identity in (IDENTITY | {"project_id": "other"}, IDENTITY | {"revision": "other"}):
            with self.subTest(identity=identity):
                other = RepositoryContext(root=FIXTURE / "checkout", **identity)
                with self.assertRaisesRegex(ContextError, "identity does not match"):
                    project_structure(other, self.report, **IDENTITY)
        without_revision = RepositoryContext(IDENTITY["project_id"], FIXTURE / "checkout")
        with self.assertRaisesRegex(ContextError, "identity does not match"):
            project_structure(without_revision, self.report, **IDENTITY)

    def test_projection_reads_the_snapshot_after_checkout_changes(self):
        with TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            copytree(FIXTURE / "checkout", checkout)
            self.index = RepositoryContext(root=checkout, **IDENTITY)
            before = self.project()
            target = checkout / "src/demo/__init__.py"
            target.write_text("# changed after snapshot capture\n")
            self.assertEqual(self.project(), before)

    def test_advice_uses_observed_graph_and_explicit_mock_output(self):
        mock = MockArchitecture()
        projection, result = advise_from_structure(
            self.index, self.report, "Review dependency boundaries.", mock, **IDENTITY,
        )
        self.assertEqual(result.mode, "mock")
        self.assertEqual(result.observed_graph, projection.graph)
        self.assertEqual(result.advice.recommendations[0].trade_offs, ["Adds another interface."])
        self.assertEqual(result.advice.proposed_nodes[0].id, "mock-interface")
        self.assertIn(result.source_evidence[0], projection.source_evidence)
        self.assertNotIn("unresolved_references", mock.payload)
