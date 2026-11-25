# Codely M4 · AI and context intelligence

M4 takes a scanner finding and a repository snapshot, retrieves source evidence, and returns an explanation and optional proposed diff. The scanner result stays in `scanner_finding`. M2 can call this package directly from its backend worker. The CLI runs independently for development and demos.

## Quick start

From the repository root, enter `m4/`. Python 3.12 was used for verification.

```sh
cd m4
python3 -m venv .venv
cp .env.example .env
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v

python -m ai_intelligence index /path/to/repository --project example
python -m ai_intelligence context /path/to/repository src/app.py 4 4
python -m ai_intelligence review /path/to/repository /path/to/normalized-findings.json
```

Review defaults to the labeled offline mock. Install `requirements-parsers.txt` for Java, JS and TS parsing and `requirements-semantic.txt` for in-memory FAISS. Install both to run all tests. Use `requirements-local.txt` to install Sentence Transformers and FAISS together for local inference.

Set `M4_PROVIDER=groq` and provide `GROQ_API_KEY` in the environment or workspace `.env` to use `openai/gpt-oss-120b`. A review can override the environment with `--provider groq`, `--provider gemini`, or `--provider mock`. Groq sends selected source excerpts to its API, so use it only for repositories approved for external processing. Groq uses strict JSON Schema output, followed by local Pydantic and source validation. `GROQ_TIMEOUT_SECONDS` defaults to 30. API failures are reported with the scanner finding and the review stays in the selected provider mode. [Groq Structured Outputs](https://console.groq.com/docs/structured-outputs)

Run `PYTHONPATH=. python docs/demo/groq_synthetic.py` to check live review and architecture advice with synthetic files.

Pass `--semantic-local /path/to/all-MiniLM-L6-v2` to `index`, `context`, or `review` after obtaining the public model files. The flag alone uses the model from the local Hugging Face cache. Indexing and query encoding run locally on CPU. If the model or FAISS is unavailable, retrieval still uses source ranges, symbols, and lexical matching. [MiniLM model files](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)

For live fields, provide `GEMINI_API_KEY` in the environment using your secret manager, or place it in a `.env` file at or above the module directory. `python-dotenv` loads it automatically without printing values. `GOOGLE_API_KEY` is accepted as a fallback. `GEMINI_MODEL` defaults to `gemini-2.5-flash`, `GEMINI_EMBEDDING_MODEL` to `gemini-embedding-001`, and `GEMINI_TIMEOUT_SECONDS` to 30. `python -m ai_intelligence check-gemini` checks metadata availability for both models without sending repository source. Pass `--gemini` to `review` to send selected evidence for generation, or `--semantic-gemini` to embed eligible chunks. These flags transmit source to Gemini. Use them only on repos approved for external processing. `.env` and virtual environments are ignored by Git. [Gemini generation API](https://ai.google.dev/api/generate-content) · [Gemini embeddings API](https://ai.google.dev/api/embeddings)

## Deliverables

- [M2 and M3 integration contracts](docs/INTEGRATION.md)
- [M4 development diary and remaining checklist](docs/DEV_DIARY_M4.md)

CodeRAG informed the chunk/embedding/index flow. The new implementation uses Python AST and optional Tree-sitter, keeps source metadata in memory, distinguishes indexed document from query embeddings, validates citations, and constructs a patch from snapshot lines. It indexes files locally by default. Model-generated statements and diffs are review candidates.
