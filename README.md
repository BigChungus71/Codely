# Codely

> **crush every bug like a pro.**

Codely is an AI-powered code security scanner and architecture reviewer. Drop a file, paste a GitHub repository link, or ask a question — Codely scans for vulnerabilities, dependency risks, and architectural flaws and walks you through the findings conversationally.

## Features

- **Code Scanner** — upload files or paste a GitHub URL; get findings mapped to OWASP Top 10, known CVEs, and architecture patterns
- **Conversational analysis** — findings are injected into the Codely chatbot so you can ask follow-up questions and get fix suggestions
- **Architecture comparison** — compare your project against Clean Architecture, Hexagonal, MVC, and more
- **Developer Mode** — toggle raw scan output and verbose logs in Settings

## Run locally

```bash
npm install
cp .env.example .env.local   # add your model key to AI_API_KEY
npm run dev
```

## Stack

- [Next.js](https://nextjs.org) 16
- [BoardUI](https://www.boardui.com) — React design system (source-owned components under `components/`)
- [Vercel AI SDK](https://sdk.vercel.ai) — streaming chat, model routing
- Tailwind CSS v4

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `AI_API_KEY` | Yes | Model provider key (OpenAI, Anthropic, Google, OpenRouter, Groq, xAI, Vercel AI Gateway) |
| `CHAT_MODEL` | No | Override the default model for your provider |
| `AI_PROVIDER` | No | Name the provider when the key has no recognisable shape (e.g. `mistral`) |
| `AI_BASE_URL` | No | Any OpenAI-compatible server (Ollama, LM Studio, vLLM) |

The provider is auto-detected from the key prefix. Set `CHAT_MODEL` to override.

## License

[MIT](LICENSE).
