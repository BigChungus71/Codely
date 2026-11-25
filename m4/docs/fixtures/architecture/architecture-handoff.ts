// M4 advice handoff. The existing M2 graph response remains a separate contract.
export interface SourceRange {
  path: string;
  start_line: number;
  end_line: number;
}

export interface Node {
  id: string;
  label: string;
}

export interface Edge {
  id: string;
  source: string;
  target: string;
  label: string;
}

export interface Evidence extends SourceRange {
  id: string;
  text: string;
  reason: string;
  redacted: boolean;
  similarity?: number | null;
}

export interface Recommendation {
  concern: string;
  evidence_ids: string[];
  principle: string;
  guideline_ids: string[];
  proposed_modification: string;
  expected_benefits: string[];
  trade_offs: string[];
  complexity: "low" | "medium" | "high";
  affected_components: string[];
  validation_requirements: string[];
  assumptions_and_limitations: string[];
}

export interface Advice {
  recommendations: Recommendation[];
  proposed_nodes: Node[];
  proposed_edges: Edge[];
  limitations: string[];
}

interface GuidelineSource {
  title: string;
  url: string;
}

interface Guideline {
  id: string;
  title: string;
  description: string;
  applicability: string;
  limitations: string;
  source: GuidelineSource;
  benefits: string[];
  trade_offs: string[];
  registry_version: string;
  signals: string[];
  requirement_terms: string[];
  checklist_references: { id: string; source: GuidelineSource }[];
}

interface ArchitectureBase {
  project_id: string;
  revision: string;
  observed_graph: {
    nodes: (Node & { location: SourceRange })[];
    edges: (Edge & { location: SourceRange })[];
  };
  structure_status: "complete" | "partial";
  coverage: Record<string, unknown>;
  diagnostics: ({ code?: string } & Record<string, unknown>)[];
  unresolved_references: Record<string, unknown>[];
  omitted_nodes: { id: string; reason: string }[];
  omitted_edges: { id: string; reason: string }[];
  requires_developer_review: true;
}

export type ArchitectureHandoff = ArchitectureBase & (
  | {
      provider: { status: "ready"; mode: "mock" | "groq" | "gemini"; code: null };
      advice: Advice;
      registry_version: string;
      source_evidence: Evidence[];
      selected_guidelines: {
        guideline: Guideline;
        policy: "advisory" | "mandatory";
        matched_by: string[];
      }[];
    }
  | {
      provider:
        | { status: "not_requested"; mode: null; code: null }
        | { status: "unavailable"; mode: "groq" | "gemini"; code: "provider_unavailable" };
      advice: null;
      registry_version: null;
      source_evidence: [];
      selected_guidelines: [];
    }
);

// A bounded M4 view can use the demo branch's existing Graph viewer with this mapping.
export function toObservedGraphDto(input: ArchitectureHandoff) {
  const { nodes, edges } = input.observed_graph;
  return {
    project_id: input.project_id,
    status: input.structure_status,
    diagnostics: input.diagnostics,
    coverage: input.coverage,
    nodes: nodes.map(({ id, label, location }) => ({
      id, label, file: location.path, type: "module", parsed: true,
      fan_in: edges.filter((edge) => edge.target === id).length,
      fan_out: edges.filter((edge) => edge.source === id).length,
    })),
    edges: edges.map(({ id, source, target, label, location }) => ({
      id, source, target, relationship: label, file: location.path,
      start_line: location.start_line, end_line: location.end_line,
      evidence: [{ file: location.path, start_line: location.start_line, end_line: location.end_line }],
    })),
  };
}
