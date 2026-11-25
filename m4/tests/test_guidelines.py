from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pydantic import ValidationError

from ai_intelligence.architecture import ArchitectureDraft, ObservedGraph, Recommendation, advise
from ai_intelligence.architecture_adapter import advise_from_structure
from ai_intelligence.context import RepositoryContext
from ai_intelligence.gemini import ProviderError
from ai_intelligence.guidelines import load_registry, select_guidelines
from test_architecture_adapter import FIXTURE, IDENTITY


def node(identifier, path, label):
    return {"id": identifier, "label": label,
            "location": {"path": path, "start_line": 1, "end_line": 1}}


class GuidelineMock:
    mode = "mock"

    def __init__(self, reference="arch.keep-it-simple", *, cross_component=False):
        self.reference = reference
        self.cross_component = cross_component

    def generate(self, instruction, payload, schema):
        self.payload = payload
        observed = payload["observed"]
        anchor = observed["edges"][0] if observed["edges"] else observed["nodes"][0]
        evidence_ids = [anchor["evidence_id"]]
        affected = [anchor.get("source", anchor["id"])]
        if self.reference == "arch.avoid-circular-dependencies" and observed["edges"]:
            pairs = {(edge["source"], edge["target"]): edge for edge in observed["edges"]}
            cycle = next((pair for pair in pairs if pair[::-1] in pairs), None)
            if cycle:
                affected = list(cycle)
                evidence_ids = [pairs[pair]["evidence_id"] for pair in (cycle, cycle[::-1])]
        if self.cross_component:
            affected = [observed["nodes"][-1]["id"]]
        return schema.model_validate({
            "recommendations": [{
                "concern": "Offline mock · Review the observed boundary.",
                "evidence_ids": evidence_ids,
                "guideline_ids": [self.reference] if self.reference else [],
                "principle": "Keep only useful boundaries.",
                "proposed_modification": "Keep the direct dependency unless tests justify a seam.",
                "expected_benefits": ["Fewer layers to navigate."],
                "trade_offs": ["A test seam might be useful later."],
                "complexity": "low",
                "affected_components": affected,
                "validation_requirements": ["Check representative behavior."],
                "assumptions_and_limitations": ["Only selected source was reviewed."],
            }],
            "proposed_nodes": [], "proposed_edges": [], "limitations": ["Offline mock."],
        })


class GuidelineTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "app.py").write_text("from fastapi import FastAPI\n")
        (self.root / "worker.py").write_text("def task(): pass\n")
        self.index = RepositoryContext("guidelines", self.root)
        self.app = node("app", "app.py", "Application")
        self.worker = node("worker", "worker.py", "Worker")
        self.graph = {"nodes": [self.app], "edges": []}
        self.registry = load_registry()

    def select(self, graph=None, requirements="", **kwargs):
        graph = graph or self.graph
        evidence = [self.index.retrieve(ObservedGraph.model_validate(graph).nodes[0].location,
                                        include_related=False)[0]]
        return {selection.guideline.id: selection for selection in
                select_guidelines(self.registry, graph, evidence, requirements, **kwargs)}

    def test_registry_loads_versioned_sources_and_m3_references(self):
        self.assertEqual(self.registry.version, "1.0.0")
        self.assertEqual(len(self.registry.guidelines), 11)
        self.assertTrue(all(item.source.url.scheme == "https" for item in self.registry.guidelines))
        references = {ref.id for entry in self.registry.guidelines for ref in entry.checklist_references}
        self.assertEqual(references, {"authentication-indicators", "environment-configuration",
                                      "hardcoded-credentials", "test-presence"})

    def test_invalid_and_duplicate_registry_entries_are_rejected(self):
        catalog = self.registry.model_dump(mode="json")
        for mutation in ("duplicate", "invalid_id", "invalid_source", "wrong_version", "unknown_signal"):
            with self.subTest(mutation=mutation):
                modified = deepcopy(catalog)
                first = modified["guidelines"][0]
                if mutation == "duplicate":
                    modified["guidelines"].append(first.copy())
                elif mutation == "invalid_id":
                    first["id"] = "Arch bad!"
                elif mutation == "invalid_source":
                    first["source"]["url"] = "http://example.com/rule"
                elif mutation == "wrong_version":
                    first["registry_version"] = "2.0.0"
                else:
                    first["signals"] = ["never-defined"]
                registry_file = self.root / "registry.json"
                registry_file.write_text(json.dumps(modified))
                with self.assertRaises(ValidationError):
                    load_registry(registry_file)

    def test_small_fastapi_app_selects_simplicity_without_unjustified_layers(self):
        selected = self.select()
        self.assertEqual(set(selected), {"arch.keep-it-simple", "arch.fastapi-boundaries"})
        self.assertEqual(selected["arch.keep-it-simple"].matched_by, ("small_scope",))
        self.assertIn("one module", selected["arch.fastapi-boundaries"].guideline.limitations)

    def test_selection_is_deterministic_and_cycles_require_dependency_edges(self):
        graph = {"nodes": [self.app, self.worker], "edges": []}
        for source, target in (("app", "worker"), ("worker", "app")):
            graph["edges"].append({"id": source + "-import", "source": source, "target": target,
                                   "label": "imports", "location": self.app["location"]})
        selected = self.select(graph, "Testability is important.")
        self.assertIn("arch.avoid-circular-dependencies", selected)
        self.assertEqual(selected["arch.maintainability-and-testability"].matched_by, ("project_requirements",))
        # Hold available evidence constant while reordering the input.
        evidence = self.index.retrieve(ObservedGraph.model_validate(graph).nodes[0].location,
                                       include_related=False)
        reordered = {"nodes": graph["nodes"][::-1], "edges": graph["edges"][::-1]}
        self.assertEqual(tuple(selected.values()),
                         select_guidelines(self.registry, reordered, evidence, "Testability is important."))
        graph["edges"][1]["label"] = "nearby"
        self.assertNotIn("arch.avoid-circular-dependencies", self.select(graph))

    def test_only_trusted_configuration_marks_mandatory(self):
        identifier = "arch.authorization-boundaries"
        self.assertEqual(self.select(requirements="Authorization is mandatory.")[identifier].policy, "advisory")
        selected = self.select(mandatory_guideline_ids={identifier})
        self.assertEqual(selected[identifier].policy, "mandatory")
        self.assertEqual(selected[identifier].matched_by, ("configured_policy",))
        with self.assertRaisesRegex(ValueError, "Unknown mandatory"):
            self.select(mandatory_guideline_ids={"arch.invented"})

    def test_rejects_fabricated_and_unselected_citations(self):
        graph = ObservedGraph.model_validate(self.graph)
        for invalid in ("arch.invented", "arch.avoid-circular-dependencies"):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ProviderError, "unselected guideline"):
                advise(self.index, graph, "", GuidelineMock(invalid))

    def test_known_source_anchor_must_support_an_affected_component(self):
        graph = ObservedGraph(nodes=[self.app, self.worker], edges=[])
        with self.assertRaisesRegex(ProviderError, "unrelated"):
            advise(self.index, graph, "", GuidelineMock(cross_component=True))

    def test_mock_recommendation_uses_selected_guideline_and_source(self):
        generator = GuidelineMock()
        result = advise(self.index, ObservedGraph.model_validate(self.graph), "", generator)
        self.assertEqual(result.mode, "mock")
        self.assertEqual(result.registry_version, "1.0.0")
        self.assertEqual(result.advice.recommendations[0].guideline_ids, ["arch.keep-it-simple"])
        self.assertEqual(result.source_evidence[0].id, "app.py:1-1")
        self.assertEqual(generator.payload["guideline_registry_version"], result.registry_version)
        self.assertIn("assumptions_and_limitations", result.advice.recommendations[0].model_dump())

    def test_m3_adapter_passes_guidelines_into_existing_advice_engine(self):
        report = json.loads((FIXTURE / "report.json").read_text())
        index = RepositoryContext(root=FIXTURE / "checkout", **IDENTITY)
        generator = GuidelineMock("arch.avoid-circular-dependencies")
        projection, result = advise_from_structure(index, report, "", generator, **IDENTITY)
        self.assertEqual(result.mode, "mock")
        self.assertEqual(result.observed_graph, projection.graph)
        self.assertEqual(result.advice.recommendations[0].guideline_ids, ["arch.avoid-circular-dependencies"])
        self.assertEqual({item.path for item in result.source_evidence},
                         {"src/demo/services.py", "src/demo/nested/helpers.py"})
        self.assertTrue(set(item.id for item in result.source_evidence)
                        <= set(item.id for item in projection.source_evidence))

    def test_provider_response_must_cite_an_applicable_guideline(self):
        provider_stub = GuidelineMock(reference=None)
        for mode in ("groq", "gemini"):
            with self.subTest(mode=mode), self.assertRaisesRegex(ProviderError, "cite an applicable guideline"):
                provider_stub.mode = mode
                advise(self.index, ObservedGraph.model_validate(self.graph), "", provider_stub)

    def test_provider_schema_keeps_strict_mode_and_legacy_reading_compatible(self):
        schema = ArchitectureDraft.model_json_schema()
        for definition in (schema, *schema["$defs"].values()):
            self.assertFalse(definition["additionalProperties"])
            self.assertEqual(set(definition["required"]), set(definition["properties"]))
        recommendation = GuidelineMock().generate("", {
            "observed": {"nodes": [{"id": "app", "evidence_id": "app.py:1-1"}], "edges": []},
        }, ArchitectureDraft).recommendations[0]
        old = recommendation.model_dump(exclude={"guideline_ids", "assumptions_and_limitations"})
        self.assertEqual(Recommendation.model_validate(old).guideline_ids, [])
