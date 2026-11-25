# Task 10 · M1 architecture frontend handoff

## What to reuse

| Branch and inspected tip | Existing implementation | Handoff |
| --- | --- | --- |
| M1 `feat/frontend-workspace` · `b899602` | Scanner architecture and comparison settings, a findings panel, and a Next.js scan route. The scan route returns findings. [Scanner controls](https://github.com/BigChungus71/Codely/blob/b899602/components/application/scanner/scanner-config.tsx#L59-L90) · [Scan route](https://github.com/BigChungus71/Codely/blob/b899602/app/api/scan/route.ts#L51-L137) | Keep the controls and findings UI. Use the project graph client for the observed architecture view. |
| M2 `feature/backend-core` · `ada47e4` | Existing observed graph endpoint and typed `architecture(projectId)` client. [Endpoint](https://github.com/BigChungus71/Codely/blob/ada47e4/backend/codely/api.py#L115-L132) · [Client](https://github.com/BigChungus71/Codely/blob/ada47e4/integrations/frontend/codely-client.ts#L17-L25) | Preserve the existing graph route and response. |
| Demo `integration/codely-demo` · `2bf4e68` | Observed graph client and viewer with module focus, directed import rows, zoom, paging and source links. Also has design chat and static impact. [Viewer](https://github.com/BigChungus71/Codely/blob/2bf4e68/components/application/scanner/scanner-panel.tsx#L245-L303) · [Client](https://github.com/BigChungus71/Codely/blob/2bf4e68/integrations/frontend/codely-client.ts#L27-L33) | Extend this viewer for advice and an optional proposed overlay. Keep observed graph, impact, and free-form chat as separate results. |
| M3 `security-analysis` · `3a87132` | Deterministic structure, dependency graph, cycle witnesses and impact mapping. [Cycle computation](https://github.com/BigChungus71/Codely/blob/3a87132/backend/app/analyzers/architecture_graph.py#L148-L165) | Reuse M3 cycle witnesses when the graph endpoint exposes them. |
| M4 `feature/architecture-graph` · `750b26b` plus local Phase 4 | Bounded graph projection, guidelines and advice worker tied to an authorized snapshot. [M4 integration guide](INTEGRATION.md) | Use the fixtures below to review UI handling. An M2 advice route still needs to publish this shape. |

## Response contract

[TypeScript contract and viewer adapter](fixtures/architecture/architecture-handoff.ts) defines the handoff envelope. Its successful payload reuses `ArchitectureAdviceResponse` fields and wraps the worker's `mode` in `provider`. The unavailable response is a proposed M2 presentation contract. The M4 worker continues to propagate provider failures, and M2 supplies already validated observed data when assembling an unavailable response.

| Field | Meaning |
| --- | --- |
| `project_id`, `revision` | Identity of the authorized source snapshot. Keep both with selection and advice state. Discard stale responses after either changes. |
| `observed_graph.nodes`, `observed_graph.edges` | Source-backed modules and relationships. Each has a stable `id` and exact `location`. Edge direction is `source` to `target`. |
| `advice` | Validated recommendations and optional proposed nodes and edges. `null` means no advice result. An empty `recommendations` array means a review returned no supported changes. |
| `advice.proposed_nodes`, `advice.proposed_edges` | Suggestions with IDs separate from observed IDs. Proposed edges can reference observed or proposed nodes. Proposed elements carry no direct source location and do not represent repository edits. |
| `affected_components`, `evidence_ids`, `guideline_ids` | Join recommendation components to observed node IDs, citations to `source_evidence[].id`, and guidelines to `selected_guidelines[].guideline.id`. Show advisory or configured mandatory status from the registry selection. |
| `location`, `source_evidence` | Canonical repository-relative path and one-based inclusive line range. Call the existing project file API with the authorized project and URL-encoded path. Highlight the range only if the returned source is for the same revision. Render source and model text as text. |
| `structure_status`, `coverage`, `diagnostics`, `unresolved_references`, `omitted_*` | Structural completeness and projection limits. Omitted elements describe scope or evidence availability. Unresolved references stay outside the observed edges. |
| `provider`, `requires_developer_review` | The provider state describes advice. Developer review is required for all suggested changes. No provider error body is exposed. |

The viewer adapter flattens observed locations to M2's `file`, `start_line` and `end_line` and preserves IDs and direction. Its fan counts measure the displayed M4 projection. Keep the full M2 observed graph when it is already loaded, and annotate the bounded subset reviewed by M4.

## UI states and visualization

- **Loading.** Load observed architecture independently of advice. Keep a same-revision graph visible while advice loads. Reset focus and selection when the project or revision changes.
- **Observed graph.** Reuse the existing import rows and module focus. For a canvas, draw arrowheads from importer to imported module, keep keyboard-accessible rows, and use stable IDs for selection. Open the observed node anchor or the specific edge's import location.
- **Cycles.** Highlight the observed edges in an M3 cycle witness when available. If computing from the displayed subgraph, label the result as a cycle in the visible graph. A partial graph cannot rule out other cycles. A proposed edge cannot establish an observed cycle.
- **Proposed overlay.** Make the overlay optional and label additions as proposed. Use a distinct line style or badge as well as color. Keep observed edges intact when showing proposals. The current draft represents additions and does not encode removals. Selecting a proposal opens its recommendation and citations where available, with no fabricated source link.
- **Recommendation cards.** Group or filter by affected component. Display the concern, proposed improvement, cited source, guideline links, expected benefits, trade-offs, complexity, assumptions, validation steps, and developer review status. Keep benefits qualitative and distinguish policy labels from proven violations.
- **Empty state.** Zero resolved edges can be valid for a single-file app. For a completed review with no recommendations, show that the review suggested no changes. For `not_requested`, show the graph without implying a review ran.
- **Partial coverage.** Show the coverage state, unresolved reference count, and omitted nodes or edges alongside the graph. Explain that missing relationships may be outside the captured or resolved scope.
- **Errors and status.** Treat structural errors as graph errors. For `provider.status: "unavailable"`, keep the graph and show an advice-specific error. Badge `mode: "mock"` as **Mock advice**. Badge a successful `groq` or `gemini` result as **Live advice** only when the server says `status: "ready"`. Fixture E's simulated failure is never a live success. Use centered empty states and preserve meaningful text for accessibility.

## Offline fixture pack

| Fixture | Use to verify |
| --- | --- |
| [A · Current cycle](fixtures/architecture/a-current-cycle.json) | Two observed modules and reciprocal import edges, with advice unrequested. |
| [B · Mock proposal](fixtures/architecture/b-mock-proposal.json) | Same graph and revision as A, one mock recommendation with both import citations, and an explicitly optional proposed overlay. |
| [C · Small app](fixtures/architecture/c-small-app.json) | Single FastAPI module and a completed mock review with no changes proposed. |
| [D · Partial analysis](fixtures/architecture/d-partial-analysis.json) | Unresolved reference and unparsed module omission alongside valid observed structure. |
| [E · Advice unavailable](fixtures/architecture/e-advice-unavailable.json) | Same graph and revision as A. Simulated failure retains that graph and returns no advice. |

The fixture builder uses M3's pinned structural analyzer, the M4 projection, and the M4 architecture worker. Mocks and simulated failure are explicit. It never executes the fixture source or calls a provider. For reproduction, use Python 3.12 and the M4 environment. Run from the repository root.

```sh
M3_DIR=$(mktemp -d)
git archive 3a87132d51d46b00bdc44ae3e5ce0a4391304f58 backend/app | tar -xf - -C "$M3_DIR"
cd m4
PYTHONPATH=".:$M3_DIR" python docs/demo/build_architecture_handoff.py docs/fixtures/architecture --check
```

Omit `--check` to regenerate the files. Live provider verification is deferred. [Historical report](LIVE_ARCHITECTURE_VERIFICATION.md)
