# Phase 5 live Groq verification

## Run on 2026-11-25

The existing Groq provider loaded the credential from the ignored local `m4/.env` and configured `openai/gpt-oss-120b` on Groq's documented chat completions endpoint. The credential was never displayed. The provider used strict JSON Schema, existing local Pydantic validation, and zero SDK retries. Groq documents strict schema support for this model. [Groq Structured Outputs](https://console.groq.com/docs/structured-outputs)

The harness generated four synthetic fixtures. It used M3's structural analyzer from `662ddaa83f21bae2369184ffb1fec2719c47845c`, then the existing M4 projection, guideline selection and architecture worker. The fourth fixture used the existing vulnerability review engine. Fixture source was parsed and never executed. No private source was sent.

| Fixture | Local preparation and expectation | Live result | Request latency |
| --- | --- | --- | --- |
| A · Circular imports and shared responsibilities | Five observed import edges, including reciprocal imports. Check for evidence-grounded cycle advice and proportionate remediation. | HTTP 404 | 1.134 s |
| B · Minimal FastAPI health endpoint | One module and no edges. Check whether advice avoids unnecessary layers. | HTTP 404 | 0.279 s |
| C · Separated transport, service, and domain | Two observed import edges. Check whether advice avoids inventing a problem. | HTTP 404 | 0.298 s |
| Vulnerability · Decimal count parser | Synthetic finding at `counts.py:3`. Check explanation, impact, safe integer parsing, citations, and developer review. | HTTP 404 | 0.268 s |

The initial sandboxed attempt for fixture A stopped at connection failure after 0.055 s. After network access was granted, all four generation attempts returned the statuses above. One authenticated model-catalog request without source also returned HTTP 404. The cause and remote acceptance of the credential remain unconfirmed. There were no successful completions or returned token-usage records.

## Evidence and quality assessment

The observed graphs remained intact across all three provider failures. Local payload inspection produced these guideline selections:

- **A** selected `arch.avoid-circular-dependencies` and `arch.coupling-and-cohesion`.
- **B** selected `arch.fastapi-boundaries` and `arch.keep-it-simple`.
- **C** selected `arch.keep-it-simple`, `arch.separation-of-concerns`, and `arch.single-responsibility`.

These are local applicability signals. Groq returned no recommendations, citations, benefits, trade-offs, proposed graph additions, or vulnerability explanation and fix to assess. Live schema conformance and semantic quality remain unverified. No failed live response was replaced with a mock.

## Regression and failure coverage

All 49 offline tests passed with zero skips, including the previous 47. Coverage includes missing credentials, simulated HTTP 401 and 429, timeout, invalid JSON, unknown guideline IDs, unsupported source citations, dangling proposal endpoints, and preservation of the observed graph on provider failure.

## Current status

Live provider verification is deferred. The dedicated live probes were removed from the active workflow. This report retains the historical results.
