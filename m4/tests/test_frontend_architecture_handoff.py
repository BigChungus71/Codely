import json
from pathlib import Path
import unittest

from ai_intelligence.architecture import ObservedGraph
from ai_intelligence.architecture_integration import ArchitectureAdviceResponse
from ai_intelligence.contracts import SourceRange


FIXTURES = Path(__file__).resolve().parents[1] / "docs" / "fixtures" / "architecture"


class FrontendArchitectureHandoffTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = {path.stem: json.loads(path.read_text()) for path in FIXTURES.glob("*.json")}

    def test_graphs_and_ready_advice_validate_against_m4_contracts(self):
        self.assertEqual(len(self.fixtures), 5)
        for name, payload in self.fixtures.items():
            with self.subTest(name=name):
                graph = ObservedGraph.model_validate(payload["observed_graph"])
                self.assertTrue(payload["requires_developer_review"])
                body = dict(payload)
                provider = body.pop("provider")
                if provider["status"] == "ready":
                    self.assertEqual(provider["mode"], "mock")
                    advice = ArchitectureAdviceResponse.model_validate(body | {"mode": provider["mode"]})
                    observed_ids = {node.id for node in graph.nodes}
                    proposed_ids = {node.id for node in advice.advice.proposed_nodes}
                    self.assertFalse(observed_ids & proposed_ids)
                    for edge in advice.advice.proposed_edges:
                        self.assertTrue({edge.source, edge.target} <= observed_ids | proposed_ids)
                    for item in advice.source_evidence:
                        self.assertEqual(item.id, f"{item.path}:{item.start_line}-{item.end_line}")
                        SourceRange(path=item.path, start_line=item.start_line, end_line=item.end_line)
                else:
                    self.assertIsNone(body["advice"])
                    self.assertEqual(body["source_evidence"], [])

    def test_mock_and_unavailable_examples_preserve_the_current_graph(self):
        current = self.fixtures["a-current-cycle"]
        for name in ("b-mock-proposal", "e-advice-unavailable"):
            scenario = self.fixtures[name]
            for field in ("project_id", "revision", "observed_graph"):
                self.assertEqual(scenario[field], current[field])
        self.assertEqual(self.fixtures["e-advice-unavailable"]["provider"]["status"], "unavailable")
        edges = {(edge["source"], edge["target"]) for edge in current["observed_graph"]["edges"]}
        self.assertEqual(len(edges), 2)
        self.assertEqual(edges, {(target, source) for source, target in edges})

    def test_small_and_partial_scenarios_have_distinct_states(self):
        small = self.fixtures["c-small-app"]
        partial = self.fixtures["d-partial-analysis"]
        self.assertEqual(small["advice"]["recommendations"], [])
        self.assertEqual(small["advice"]["proposed_nodes"], [])
        self.assertEqual(small["structure_status"], "complete")
        self.assertEqual(partial["structure_status"], "partial")
        self.assertTrue(partial["unresolved_references"])
        self.assertTrue(partial["omitted_nodes"])
        self.assertEqual(partial["observed_graph"]["edges"], [])
