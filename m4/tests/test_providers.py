import json
import os
from contextlib import nullcontext
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import groq
import httpx
import numpy as np

from ai_intelligence.context import RepositoryContext
from ai_intelligence.contracts import Contract, Finding
from ai_intelligence.embeddings import LocalEmbedder
from ai_intelligence.gemini import MockGenerator, ProviderError
from ai_intelligence.groq import GroqGenerator
from ai_intelligence.integration import review_for_m2, review_normalized
from ai_intelligence.providers import create_generator
from ai_intelligence.review import explain


class Sample(Contract):
    message: str


class GroqTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("ai_intelligence.groq.load_dotenv"))
        self.enterContext(patch.dict(os.environ, {"GROQ_API_KEY": "fixture-secret"}))
        self.provider = GroqGenerator()
        self.addCleanup(self.provider.close)
        self.create = self.enterContext(patch.object(self.provider._client.chat.completions, "create"))

    def test_strict_schema_and_validated_output(self):
        self.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content='{"message":"fixture"}')
        )])
        self.assertEqual(self.provider.generate("Review", {"fixture": True}, Sample).message, "fixture")
        request = self.create.call_args.kwargs
        self.assertEqual(request["model"], "openai/gpt-oss-120b")
        self.assertEqual(request["response_format"], {"type": "json_schema", "json_schema": {
            "name": "Sample", "strict": True, "schema": Sample.model_json_schema(),
        }})
        self.assertEqual(json.loads(request["messages"][1]["content"]), {"fixture": True})

    def test_failures_are_sanitized_and_not_retried(self):
        request = httpx.Request("POST", "https://api.groq.com", headers={"Authorization": "fixture-secret"})
        for failure, expected in (
            (groq.AuthenticationError("fixture-secret", response=httpx.Response(401, request=request), body={}), "401"),
            (groq.RateLimitError("fixture-secret", response=httpx.Response(429, request=request), body={}), "429"),
            (groq.APITimeoutError(request), "timed out"),
            (groq.APIConnectionError(message="fixture-secret", request=request), "connection failed"),
            (groq.APIStatusError("fixture-secret", response=httpx.Response(503, request=request), body={}), "503"),
        ):
            with self.subTest(expected=expected):
                self.create.reset_mock(side_effect=True)
                self.create.side_effect = failure
                with self.assertRaisesRegex(ProviderError, expected) as caught:
                    self.provider.generate("fixture", {}, Sample)
                self.assertNotIn("fixture-secret", str(caught.exception))
                self.create.assert_called_once()

    def test_truncated_and_schema_invalid_data_are_rejected(self):
        for finish, content in (
            ("length", '{"message":"ok"}'),
            ("stop", '{not JSON'),
            ("stop", '{"extra":"unexpected"}'),
            ("stop", '{"message":"fixture-secret"}'),
        ):
            with self.subTest(finish=finish):
                self.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
                    finish_reason=finish, message=SimpleNamespace(content=content)
                )])
                with self.assertRaisesRegex(ProviderError, "schema-invalid") as caught:
                    self.provider.generate("fixture", {}, Sample)
                self.assertNotIn("fixture-secret", str(caught.exception))

    def test_environment_selection_requires_configured_credentials(self):
        with patch("ai_intelligence.providers.load_dotenv"), patch.dict(os.environ, {"M4_PROVIDER": "groq"}):
            selected = create_generator()
            self.addCleanup(selected.close)
            self.assertEqual(selected.mode, "groq")
            self.assertIsInstance(create_generator("mock"), MockGenerator)
            with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
                with self.assertRaisesRegex(ProviderError, "GROQ_API_KEY"):
                    create_generator()


class LocalEmbeddingTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "one"
        self.project.mkdir()
        (self.project / "app.py").write_text("from inventory import record\n\nrecord(1)\n")
        (self.project / "inventory.py").write_text("def record(count):\n    return count\n")
        (self.project / "orchard.py").write_text("# Fruit trees in an orchard\n")
        self.finding = Finding(id="fixture", rule_id="fixture", severity="INFO", path="app.py",
                               start_line=3, end_line=3, message="Review integer inventory")

    def test_local_embeddings_rank_cross_file_context_and_isolate_projects(self):
        model = Mock()
        model.encode.side_effect = lambda texts, **_: np.array(
            [[1., 0.] if "orchard" in text else [0., 1.] for text in texts]
        )
        loader = Mock(return_value=model)
        with (patch.dict(sys.modules, {"sentence_transformers": SimpleNamespace(SentenceTransformer=loader)}),
              patch("ai_intelligence.embeddings._encoding_threads", return_value=nullcontext())):
            embedder = LocalEmbedder()
            index = RepositoryContext("one", self.project, embedder=embedder)
            self.assertEqual(index.semantic_status, "ready")
            result = index.retrieve(self.finding, "orchard")
            self.assertEqual(result[0].reason, "affected")
            self.assertTrue(any(entry.path == "inventory.py" and entry.reason == "symbol" for entry in result))
            self.assertTrue(any(entry.path == "orchard.py" and entry.reason == "semantic" for entry in result))
            other_path = self.root / "two"
            other_path.mkdir()
            (other_path / "app.py").write_text("count = 1\n")
            other = RepositoryContext("two", other_path, embedder=embedder)
            self.assertEqual(other.semantic_status, "ready")
            query = self.finding.model_copy(update={"start_line": 1, "end_line": 1})
            self.assertTrue(all(entry.path == "app.py" for entry in other.retrieve(query, "orchard")))
        loader.assert_called_once_with("sentence-transformers/all-MiniLM-L6-v2", device="cpu",
                                       local_files_only=True, trust_remote_code=False, token=False)

    def test_missing_model_keeps_structural_retrieval_available(self):
        loader = Mock(side_effect=OSError("private cache path"))
        with patch.dict(sys.modules, {"sentence_transformers": SimpleNamespace(SentenceTransformer=loader)}):
            index = RepositoryContext("one", self.project, embedder=LocalEmbedder())
        self.assertEqual(index.semantic_status, "unavailable")
        result = index.retrieve(self.finding)
        self.assertTrue(any(entry.path == "inventory.py" and entry.reason == "symbol" for entry in result))

    def test_adapter_preserves_normalized_input_and_frontend_shape(self):
        index = RepositoryContext("one", self.project)
        provider = MockGenerator()
        result = review_normalized(index, self.finding.model_dump(), provider)
        self.assertEqual(result, explain(index, self.finding, provider).model_dump(mode="json"))

    def test_team_finding_maps_to_existing_m2_explanation(self):
        index = RepositoryContext("one", self.project)
        team_finding = self.finding.model_dump(exclude={"path", "cwe"}) | {
            "file": "app.py", "cwe": ["CWE-20", "CWE-116"], "source": "semgrep",
            "title": "Fixture finding", "evidence": {"raw": "ignored"},
        }
        provider = MockGenerator()
        review = review_normalized(index, team_finding, provider)
        self.assertEqual(review["scanner_finding"]["cwe"], "CWE-20, CWE-116")
        self.assertEqual(review["scanner_finding"]["path"], "app.py")
        response = review_for_m2(index, team_finding, provider)
        self.assertEqual(response["finding_id"], team_finding["id"])
        self.assertTrue(response["explanation"].startswith("Offline mock. "))
        self.assertTrue(response["requires_developer_review"])
        self.assertIsNone(response["suggested_code"])
