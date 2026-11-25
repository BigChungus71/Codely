import json
from io import BytesIO
import os
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from dotenv import load_dotenv
from pydantic import ValidationError

from ai_intelligence.context import ContextError, RepositoryContext
from ai_intelligence.contracts import Finding, ReviewDraft
from ai_intelligence.gemini import Gemini, MockGenerator, ProviderError
from ai_intelligence.review import explain, semgrep_findings


class FixtureFix(MockGenerator):
    def generate(self, instruction, payload, schema):
        draft = super().generate(instruction, payload, schema).model_dump()
        draft["edits"] = [{
            "evidence_id": draft["evidence_ids"][0],
            "replacement": '    return int(value)',
            "explanation": "Accept a decimal integer using the language's numeric parser.",
        }]
        return schema.model_validate(draft)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "app.py").write_text("from helper import record\n\ndef parse(value):\n    return eval(value)\n")
        (self.root / "helper.py").write_text("def record(value):\n    return value\n")
        (self.root / ".env").write_text("API_KEY=synthetic")
        (self.root / "application.properties").write_text("service.api-key=synthetic\n")
        (self.root / "alias.py").symlink_to(self.root / "app.py")
        self.index = RepositoryContext("fixture", self.root)
        self.finding = Finding(id="fixture-1", rule_id="fixture.unsafe-eval", severity="ERROR",
                               path="app.py", start_line=4, end_line=4, message="Review eval")

    def test_context_sensitive_files_and_exact_first(self):
        evidence = self.index.retrieve(self.finding)
        self.assertEqual(evidence[0].text, "    return eval(value)")
        self.assertEqual(evidence[0].reason, "affected")
        self.assertTrue(any(item.path == "helper.py" and item.reason == "symbol" for item in evidence))
        self.assertTrue(any(item.start_line == 3 and item.reason == "containing" for item in evidence))
        self.assertNotIn(".env", self.index.files)
        self.assertNotIn("alias.py", self.index.files)
        self.assertNotIn("synthetic", str(self.index.files["application.properties"].lines))
        with self.assertRaises(ContextError):
            self.index.retrieve(self.finding, budget=10)

    def test_fixture_review_and_patch(self):
        review = explain(self.index, self.finding, FixtureFix())
        self.assertEqual(review.mode, "mock")
        self.assertEqual(review.scanner_finding, self.finding)
        self.assertEqual(review.affected_files, ["app.py"])
        self.assertIn("+    return int(value)", review.proposed_diff)
        self.assertIn("eval", (self.root / "app.py").read_text())
        self.assertEqual(ReviewDraft.model_validate_json(review.interpretation.model_dump_json()),
                         review.interpretation)

    def test_bad_citation_rejected(self):
        class InvalidCitation(MockGenerator):
            def generate(self, instruction, payload, schema):
                draft = super().generate(instruction, payload, schema).model_dump()
                draft["evidence_ids"].append("other.py:2-2")
                return schema.model_validate(draft)

        with self.assertRaises(ProviderError):
            explain(self.index, self.finding, InvalidCitation())

    def test_invalid_source_and_project_isolation(self):
        with self.assertRaises(ValidationError):
            Finding.model_validate({**self.finding.model_dump(), "path": "../app.py"})
        with self.assertRaises(ContextError):
            self.index.retrieve(self.finding.model_copy(update={"start_line": 8, "end_line": 8}))
        with tempfile.TemporaryDirectory() as directory:
            other = RepositoryContext("other", Path(directory))
            with self.assertRaises(ContextError):
                other.retrieve(self.finding)

    def test_semgrep_import_is_deterministic(self):
        raw = {"results": [{"check_id": "fixture.rule", "path": "app.py",
                            "start": {"line": 4, "col": 1}, "end": {"line": 4, "col": 10},
                            "extra": {"severity": "ERROR", "message": "Fixture",
                                      "metadata": {"cwe": ["CWE-95"]}}}]}
        result = semgrep_findings(raw)
        self.assertEqual(result, semgrep_findings(raw))
        self.assertEqual(result[0].cwe, "CWE-95")

    def test_gemini_json_and_embedding_task_contract(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            gemini = Gemini()
        valid = explain(self.index, self.finding, MockGenerator()).interpretation
        response = {"candidates": [{"finishReason": "STOP", "content": {
            "parts": [{"text": valid.model_dump_json()}]}}]}
        with patch.object(gemini, "_request", return_value=response) as request:
            self.assertEqual(gemini.generate("fixture", {}, ReviewDraft), valid)
            self.assertIn("responseJsonSchema", request.call_args.args[1]["generationConfig"])
        with patch.object(gemini, "_request", return_value={"embeddings": [{"values": [1, 2]}]}) as request:
            self.assertEqual(gemini.embed_documents(["source"]), [[1, 2]])
            self.assertEqual(request.call_args.args[1]["requests"][0]["taskType"], "RETRIEVAL_DOCUMENT")
        with patch.object(gemini, "_request", return_value={"embedding": {"values": [1, 2]}}) as request:
            self.assertEqual(gemini.embed_query("query"), [1, 2])
            self.assertEqual(request.call_args.args[1]["taskType"], "RETRIEVAL_QUERY")
        with patch.object(gemini, "_request", return_value=json.loads('{}')):
            with self.assertRaises(ProviderError):
                gemini.generate("fixture", {}, ReviewDraft)

    def test_dotenv_is_loaded_and_model_availability_checks_both_models(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "GEMINI_API_KEY=synthetic-test-key\n"
                "GEMINI_MODEL=fixture-generation\n"
                "GEMINI_EMBEDDING_MODEL=fixture-embedding\n"
            )
            with patch.dict(os.environ, {}, clear=True):
                with patch("ai_intelligence.gemini.load_dotenv",
                           side_effect=lambda: load_dotenv(env_file, override=True)) as loader:
                    gemini = Gemini()
                self.assertEqual(gemini.model, "fixture-generation")
                self.assertEqual(gemini.embedding_model, "fixture-embedding")
                loader.assert_called_once_with()
            with patch.object(gemini, "_request", side_effect=[
                {"name": "models/fixture-generation"},
                {"name": "models/fixture-embedding"},
            ]) as request:
                status = gemini.check()
            self.assertTrue(status["reachable"])
            self.assertEqual(status["model"], "models/fixture-generation")
            self.assertEqual(status["embedding_model"], "models/fixture-embedding")
            self.assertEqual([call.args[0] for call in request.call_args_list],
                             ["fixture-generation", "fixture-embedding"])

    def test_provider_errors_do_not_expose_credentials_or_response_bodies(self):
        credential = "AIza" + "A" * 35
        with patch.dict(os.environ, {"GEMINI_API_KEY": credential}):
            gemini = Gemini()
        response_body = f'{{"error":"billing issue","debug":"{credential}"}}'.encode()
        error = HTTPError(
            "https://generativelanguage.googleapis.com/", 402, "Payment Required", {},
            BytesIO(response_body),
        )
        with patch.object(gemini._opener, "open", side_effect=error):
            with self.assertRaises(ProviderError) as raised:
                gemini._request("fixture")
        self.assertNotIn(credential, str(raised.exception))
        self.assertNotIn("billing issue", str(raised.exception))


    def test_faiss_uses_per_snapshot_vectors_and_falls_back_on_query_failure(self):
        try:
            import faiss  # noqa: F401
        except ImportError:
            self.skipTest("Install optional FAISS dependencies")

        class FixtureEmbedder:
            failed = False

            def embed_documents(self, texts):
                return [[1, 0] if "helper.py" in text else [0, 1] for text in texts]

            def embed_query(self, text):
                if self.failed:
                    raise ProviderError("Offline fixture")
                return [1, 0]

        embedder = FixtureEmbedder()
        context = RepositoryContext("semantic-project", self.root, embedder=embedder)
        self.assertEqual(context.semantic_status, "ready")
        ranking = context.semantic.search("fixture query", 1)
        self.assertEqual(context.chunks[ranking[0][0]].path, "helper.py")
        self.assertAlmostEqual(ranking[0][1], 1.0)
        embedder.failed = True
        evidence = context.retrieve(self.finding)
        self.assertEqual(evidence[0].reason, "affected")
        self.assertTrue(any(item.reason == "symbol" for item in evidence))

    def test_native_parser_spans(self):
        from ai_intelligence.context import _language, parsed_spans
        if _language(".java") is None or _language(".tsx") is None or _language(".js") is None:
            self.skipTest("Install optional language parsers")
        java = "class Example {\n  int size() {\n    return 1;\n  }\n}\n"
        javascript = "export function run() {\n  return 1;\n}\n"
        tsx = "export const App = () => {\n  return <div />;\n};\n"
        self.assertIn((2, 4), parsed_spans("Example.java", java))
        self.assertIn((1, 3), parsed_spans("run.js", javascript))
        self.assertIn((1, 3), parsed_spans("App.tsx", tsx))

    def test_architecture_rejects_invented_edges_and_preserves_observed_graph(self):
        from ai_intelligence.architecture import ObservedGraph, advise

        graph = ObservedGraph.model_validate({"nodes": [{
            "id": "app", "label": "Application",
            "location": {"path": "app.py", "start_line": 3, "end_line": 3},
        }], "edges": []})

        class ArchitectureFixture(MockGenerator):
            broken = False

            def generate(self, instruction, payload, schema):
                reference = payload["evidence"][0]["id"]
                return schema.model_validate({"recommendations": [{
                    "concern": "Fixture concern", "evidence_ids": [reference],
                    "principle": "Separation of concerns", "proposed_modification": "Add a parser",
                    "expected_benefits": ["Simpler tests"], "trade_offs": ["One more class"],
                    "complexity": "low", "affected_components": ["app"],
                    "validation_requirements": ["Exercise the parse method"],
                }], "proposed_nodes": [{"id": "parser", "label": "Parser"}],
                    "proposed_edges": [{"id": "uses", "source": "app",
                                        "target": "missing" if self.broken else "parser", "label": "uses"}],
                    "limitations": ["Mock fixture"]})

        generator = ArchitectureFixture()
        result = advise(self.index, graph, "Testable code", generator)
        self.assertEqual(result.observed_graph, graph)
        self.assertEqual(result.advice.proposed_edges[0].target, "parser")
        generator.broken = True
        with self.assertRaises(ProviderError):
            advise(self.index, graph, "Testable code", generator)


if __name__ == "__main__":
    unittest.main()
