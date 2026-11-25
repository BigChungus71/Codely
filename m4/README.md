# Codely M4 · AI and context intelligence

M4 takes a scanner finding and a repository snapshot, retrieves source evidence, and returns an explanation and optional proposed diff. The scanner result stays in `scanner_finding`. M2 can call this package directly from its backend worker. The CLI runs independently for development and demos.

## Architecture Intelligence

Task 10 turns M3's Python structure report into a bounded, source-backed architecture graph. It selects relevant engineering guidance and validates recommendations, trade-offs, citations, and proposed graph additions. Observed dependencies and proposed changes remain separate.

| Module | Responsibility |
| --- | --- |
| `context.py` | Capture source for the authorized snapshot and resolve exact evidence ranges. |
| `architecture_adapter.py` | Project M3 modules and resolved imports into M4 nodes and edges. Preserve coverage and omission reasons. |
| `guidelines.py` and `architecture_guidelines.json` | Select from 11 versioned guidelines and distinguish advisory guidance from configured policy. |
| `architecture.py` | Build the provider request and validate advice, citations, guideline IDs, and graph endpoints. |
| `architecture_integration.py` | Provide the synchronous M2 worker and validate snapshot and report bindings. |

The workflow is M3 structure report → M4 graph projection → guideline selection → advice worker → validated response → M1 handoff. M2 supplies the authorized project, revision, snapshot, and separately recorded report identity. See the [M2 integration guide](docs/INTEGRATION.md).

For an offline demo, open the five [frontend fixtures](docs/fixtures/architecture) or follow the regeneration instructions in the [M1 handoff](docs/FRONTEND_ARCHITECTURE_HANDOFF.md). The examples cover a cycle, a mock proposal, a small app, partial analysis, and unavailable advice. Mock recommendations are explicitly labeled. They are authored fixtures, and live AI generation was never successfully verified.

The projection covers supported Python modules and resolved imports with a maximum of 15 nodes and 20 edges. Guidelines are selected heuristically from the available evidence. M3 v1 has no independent revision attestation. The actual M2 advice route and M1 proposal overlay still need team integration.

## Quick start

From the repository root, enter `m4/`. Python 3.12 was used for verification.

```sh
cd m4
python3 -m venv .venv
# Copy .env.example to .env only if needed for local configuration.
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v

python -m ai_intelligence index /path/to/repository --project example
python -m ai_intelligence context /path/to/repository src/app.py 4 4
python -m ai_intelligence review /path/to/repository /path/to/normalized-findings.json
```

Review defaults to the labeled offline mock. Install `requirements-parsers.txt` for Java, JS and TS parsing and `requirements-semantic.txt` for in-memory FAISS. Install both to run all tests. Use `requirements-local.txt` to install Sentence Transformers and FAISS together for local inference.

```sh
python -m pip install -r requirements-parsers.txt -r requirements-semantic.txt
python -m unittest discover -s tests -v
```

Set `M4_PROVIDER=groq` and provide `GROQ_API_KEY` in the environment or workspace `.env` to use `openai/gpt-oss-120b`. A review can override the environment with `--provider groq`, `--provider gemini`, or `--provider mock`. Groq sends selected source excerpts to its API, so use it only for repositories approved for external processing. Groq uses strict JSON Schema output, followed by local Pydantic and source validation. `GROQ_TIMEOUT_SECONDS` defaults to 30. API failures are reported with the scanner finding and the review stays in the selected provider mode. [Groq Structured Outputs](https://console.groq.com/docs/structured-outputs)

Live provider verification is deferred. The frontend handoff includes offline architecture fixtures and a record of the earlier live verification attempt.

Pass `--semantic-local /path/to/all-MiniLM-L6-v2` to `index`, `context`, or `review` after obtaining the public model files. The flag alone uses the model from the local Hugging Face cache. Indexing and query encoding run locally on CPU. If the model or FAISS is unavailable, retrieval still uses source ranges, symbols, and lexical matching. [MiniLM model files](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)

For live fields, provide `GEMINI_API_KEY` in the environment using your secret manager, or place it in a `.env` file at or above the module directory. `python-dotenv` loads it automatically without printing values. `GOOGLE_API_KEY` is accepted as a fallback. `GEMINI_MODEL` defaults to `gemini-2.5-flash`, `GEMINI_EMBEDDING_MODEL` to `gemini-embedding-001`, and `GEMINI_TIMEOUT_SECONDS` to 30. `python -m ai_intelligence check-gemini` checks metadata availability for both models without sending repository source. Pass `--gemini` to `review` to send selected evidence for generation, or `--semantic-gemini` to embed eligible chunks. These flags transmit source to Gemini. Use them only on repos approved for external processing. `.env` and virtual environments are ignored by Git. [Gemini generation API](https://ai.google.dev/api/generate-content) · [Gemini embeddings API](https://ai.google.dev/api/embeddings)

## Deliverables

- [M1 architecture frontend handoff](docs/FRONTEND_ARCHITECTURE_HANDOFF.md)
- [Task 10 implementation summary](docs/ARCHITECTURE_IMPLEMENTATION_SUMMARY.md)
- [M2 and M3 integration contracts](docs/INTEGRATION.md)
- [M4 development diary and remaining checklist](docs/DEV_DIARY_M4.md)

CodeRAG informed the chunk/embedding/index flow. The new implementation uses Python AST and optional Tree-sitter, keeps source metadata in memory, distinguishes indexed document from query embeddings, validates citations, and constructs a patch from snapshot lines. It indexes files locally by default. Model-generated statements and diffs are review candidates.
