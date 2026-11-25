<div align="center">

# CodeRAG (Enterprise Edition)
### Repository-Aware Intelligence for GitHub Copilot
#### Powered by Azure OpenAI & FAISS

CodeRAG integrates deep repository-level context into the GitHub Copilot experience. By indexing your entire source code into a high-dimensional vector space using **Azure OpenAI text-embedding-3-small**, it enables Copilot to provide responses grounded in your specific implementation patterns and architectural decisions.

[Install Extension](#installation) · [View Backend](https://github.com/ssundxr/coderag-backend) · [Quick Start](#quick-start) · [Technical Overview](#technical-overview)

---

</div>

## Core Capabilities

| Capability | Description |
|---|---|
| **Semantic Code Search** | Provides contextually relevant code snippets from the repository using vector similarity. |
| **#coderag Context Injection** | Use the `#codeRagSearch` reference to automatically inject retrieved context into Copilot Chat. |
| **@coderag Participant** | Dedicated chat participant for repository-specific inquiries and architectural analysis. |
| **Azure OpenAI Engine** | Utilizes `text-embedding-3-small` with an 8,192 token context window for accurate code understanding. |
| **FAISS Vector Index** | High-performance local retrieval powered by Facebook AI Similarity Search. |
| **MNC-Level Security** | Keep your code context within your private Azure tenant for enterprise compliance. |

## Technical Architecture

The system follows a **Local-First Indexing** strategy with a cloud-assisted embedding pipeline:

1. **Indexing Workflow:** 
   - The VS Code extension performs a recursive scan of the workspace.
   - Files are intelligently chunked and filtered (ignoring binaries/minified files).
   - Chunks are transmitted to the **Azure App Service** backend.
   - Backend performs embedding using **Azure OpenAI Service**.
   - Vectors are stored in a local **FAISS** index for millisecond-latency retrieval.

2. **Retrieval Workflow:** 
   - User queries via `#coderag` or `@coderag` are embedded on-the-fly.
   - The system performs a similarity search against the FAISS index.
   - The most relevant code "knowledge" is injected into the LLM prompt.

## Requirements

- **CodeRAG Backend:** Active FastAPI instance (locally or on Azure).
- **GitHub Copilot Chat:** Active subscription and extension installed.
- **VS Code v1.95.0+**: Support for the latest Language Model Tool APIs.

## Installation

### Marketplace
Search for **CodeRAG** in the VS Code Extensions tab and select Install.

### Backend Setup
Configure your Azure App Service with:
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT`

## Quick Start Guide

### 1. Configure Backend URL
Update the `BACKEND_URL` in the extension settings to point to your Azure endpoint.

### 2. Index Workspace
Open the Command Palette (`Ctrl+Shift+P`) and execute:
`CodeRAG: Index Workspace`

### 3. Invoke Context
- `How is the routing handled in this project? #codeRagSearch`
- `@coderag Explain the interaction between the indexer and retriever.`

## Security and Privacy
CodeRAG processes your code through your own secure infrastructure. Communications occur between the VS Code client and your designated backend. No source code is transmitted to external providers outside your Azure tenant.

---

<div align="center">

**Developed by**
### Shyam Sunder
*B.Tech Computer Science & Engineering (AI & ML)*
*Alliance University, Bangalore*

*"Grounding AI in the reality of your code."*

</div>
