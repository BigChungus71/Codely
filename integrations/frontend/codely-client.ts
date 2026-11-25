/** Backend contracts and display mapping for feat/frontend-workspace.
 * No fixtures or simulated responses. Pass NEXT_PUBLIC_CODELY_API_URL at the call site.
 */
export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO" | "UNKNOWN";
export interface Finding {
  id: string; rule_id: string; source: string; severity: Severity; title: string;
  file: string; start_line: number; end_line: number; message: string;
  cwe: string[]; evidence: Record<string, unknown>;
}
export interface FindingsResponse {
  project_id: string; status: "completed" | "not_scanned" | "stale";
  repository_version: string; cached: boolean; scanned_at: string | null; findings: Finding[];
}
export interface Project { project_id: string; name: string; status: "ready"; languages: string[] }
export interface TreeNode { name: string; path: string; type: "file" | "directory"; children?: TreeNode[] }
export interface SourceFile { project_id: string; path: string; language: string; content: string }
export interface Explanation {
  finding_id: string; status: "completed"; explanation: string; potential_impact: string;
  recommendation: string; suggested_code: string | null; requires_developer_review: true;
}
export interface Graph {
  project_id: string;
  nodes: { id: string; label: string; type: string; file: string }[];
  edges: { source: string; target: string; relationship: string }[];
}
/** Structurally assignable to the frontend's existing ScanFinding. */
export interface DisplayFinding {
  id: string; severity: "critical" | "high" | "medium" | "low" | "info";
  title: string; description: string; file: string; line: number;
  recommendation?: string; scannerSeverity: Severity;
}
export function toDisplayFinding(finding: Finding): DisplayFinding {
  const severity = finding.severity === "UNKNOWN" ? "info" : finding.severity.toLowerCase() as DisplayFinding["severity"];
  return {
    id: finding.id, severity, scannerSeverity: finding.severity, title: finding.title,
    description: finding.severity === "UNKNOWN" ? `[Scanner severity: UNKNOWN] ${finding.message}` : finding.message,
    file: finding.file, line: finding.start_line,
  };
}
/** Prevent a stale/unscanned result from becoming a false "No issues found" UI. */
export function completedFindings(result: FindingsResponse): DisplayFinding[] {
  if (result.status !== "completed") throw new Error(`Scan is ${result.status}; run a successful scan first.`);
  return result.findings.map(toDisplayFinding);
}
export class CodelyApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.name = "CodelyApiError"; this.status = status; }
}
export function createCodelyClient(baseUrl: string, fetcher: typeof fetch = fetch) {
  const base = baseUrl.replace(/\/+$/, "");
  async function request<T>(path: string, method = "GET"): Promise<T> {
    const response = await fetcher(`${base}/api${path}`, { method, cache: "no-store", signal: AbortSignal.timeout(100_000) });
    const body = await response.json();
    if (!response.ok) throw new CodelyApiError(response.status, typeof body.detail === "string" ? body.detail : `Backend returned HTTP ${response.status}`);
    return body as T;
  }
  const projectPath = (id: string) => `/projects/${encodeURIComponent(id)}`;
  return {
    projects: () => request<{ projects: Project[] }>("/projects"),
    tree: (id: string) => request<{ project_id: string; tree: TreeNode[] }>(`${projectPath(id)}/tree`),
    file: (id: string, path: string) => request<SourceFile>(`${projectPath(id)}/files?${new URLSearchParams({ path })}`),
    scan: (id: string) => request<FindingsResponse>(`${projectPath(id)}/scan`, "POST"),
    findings: (id: string) => request<FindingsResponse>(`${projectPath(id)}/findings`),
    explain: (id: string, findingId: string) => request<Explanation>(`${projectPath(id)}/findings/${encodeURIComponent(findingId)}/explain`, "POST"),
    architecture: (id: string) => request<Graph>(`${projectPath(id)}/architecture`),
  };
}
