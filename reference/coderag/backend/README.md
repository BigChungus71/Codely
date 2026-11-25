# CodeRAG Backend v2.0 (FastAPI)
### The Vector Intelligence Layer for CodeRAG

This is the Python-based backend service for the CodeRAG VS Code extension. It provides the high-performance embedding, retrieval, and AI validation pipeline needed to ground GitHub Copilot in your specific codebase.

## 🚀 Key Features

- **Azure OpenAI Integration**: Uses `text-embedding-3-small` for industry-leading code embeddings.
- **Provider Agnostic**: Supports both Azure OpenAI (Enterprise) and standard OpenAI API.
- **Google Gemini LLM**: Powered by Gemini 2.0 Flash for intelligent code generation.
- **Smart Context Visualizer**: Per-chunk relevance scoring with detailed retrieval metadata.
- **Hallucination & Confidence Checker**: Validates generated code against codebase symbols.
- **Document Upload RAG**: Upload PDFs and docs for hybrid code + documentation search.
- **Project Memory**: Persistent query history with confidence tracking.
- **Local FAISS Storage**: Millisecond-latency semantic search using Facebook AI Similarity Search.

## 🛠️ Tech Stack

- **FastAPI**: High-performance web framework.
- **OpenAI SDK**: For Azure/OpenAI embedding calls.
- **Google Gemini**: LLM for code generation and query refinement.
- **FAISS**: Vector similarity search.
- **PyPDF2**: Document parsing for uploaded files.
- **Pydantic**: Robust data validation.

## 📡 API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Service status and feature list |
| `/health` | GET | Health check with feature flags |
| `/embed` | POST | Generate embeddings (Azure/OpenAI) |
| `/index` | POST | Index a repository into FAISS |
| `/query` | POST | Full RAG: Retrieve → Generate → Validate |
| `/retrieve` | POST | Pure RAG retrieval (for Copilot) |
| `/retrieve-detailed` | POST | Detailed retrieval with scores (for Visualizer) |
| `/validate` | POST | Confidence check on generated code |
| `/upload-doc` | POST | Upload document for hybrid RAG |
| `/documents` | GET | List uploaded documents |
| `/documents/{id}` | DELETE | Remove uploaded document |
| `/memory` | GET | Get project query history |
| `/memory/clear` | POST | Clear all project memory |
| `/lint` | POST | Run static analysis on code |

## ⚙️ Configuration

Create a `.env` file or set environment variables in Azure:

### Embeddings (Azure OpenAI - Recommended)
```bash
AZURE_OPENAI_API_KEY=your_key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=text-embedding-3-small
```

### Embeddings (Standard OpenAI - Fallback)
```bash
OPENAI_API_KEY=sk-...
```

### LLM (Google Gemini)
```bash
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-2.0-flash
```

## 📦 Deployment

### Local Development
1. `python -m venv .venv`
2. `source .venv/bin/activate` (or `.venv\Scripts\activate` on Windows)
3. `pip install -r requirements.txt`
4. `uvicorn main:app --reload`

### Azure Deployment
The repository includes a `deploy.bat` script for easy deployment to Azure App Service:
```powershell
.\deploy.bat
```

## 🔒 Security
No source code is stored in the cloud. The backend only uses your Azure tenant for temporary embedding generation. The vector index stays local to your workspace. Uploaded documents are stored in-memory only and cleared on restart.

---

**Developed by Shyam Sunder**
*"Grounding AI in the reality of your code."*
