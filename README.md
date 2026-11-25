# Codely

Codely is a repository-aware security review and architecture demo. Use the scanner to browse configured checkouts, run native Semgrep, inspect source-linked findings, or switch between the Python dependency graph and the Java/React system view. Repository chat can use retrieved evidence and user constraints.

## Run locally

Follow the [demo runbook](docs/DEMO_RUNBOOK.md) to start Next.js, FastAPI and the separate Semgrep tool environment. The security checks, merge scope and remaining scanner dependency advisories are in the [release report](docs/MAIN_RELEASE_SECURITY.md).

The original CodeRAG backend and extension archives remain available as historical inputs. Use the maintained application and runbook for the demo.

## Stack

- [Next.js](https://nextjs.org) 16
- [BoardUI](https://www.boardui.com) — React design system (source-owned components under `components/`)
- [Vercel AI SDK](https://sdk.vercel.ai) — streaming chat, model routing
- Tailwind CSS v4

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `AI_API_KEY` | For live chat | Model provider key (OpenAI, Anthropic, Google, OpenRouter, Groq, xAI, Vercel AI Gateway) |
| `CHAT_MODEL` | No | Override the default model for your provider |
| `AI_PROVIDER` | No | Name the provider when the key has no recognisable shape (e.g. `mistral`) |
| `AI_BASE_URL` | No | Any OpenAI-compatible server (Ollama, LM Studio, vLLM) |

The provider is auto-detected from the key prefix. Set `CHAT_MODEL` to override.

## License

[MIT](LICENSE).
