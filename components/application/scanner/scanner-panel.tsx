"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/base/buttons/button";
import { Select, SelectItem } from "@/components/base/select/select";
import { ScannerResults } from "./scanner-results";
import {
  CodelyApiError, completedFindings, createCodelyClient, toDisplayFinding,
  type Explanation, type Finding, type FindingImpact, type FindingsResponse, type GraphView, type ScanCoverage,
  type Graph, type Project, type SourceFile, type TreeNode,
} from "@/integrations/frontend/codely-client";
import { cx } from "@/utils/cx";

const api = createCodelyClient(process.env.NEXT_PUBLIC_CODELY_API_URL ?? "http://127.0.0.1:8000");
const message = (error: unknown) => error instanceof Error ? error.message : "Request failed";

function RepositoryTree({ nodes, onOpen }: { nodes: TreeNode[]; onOpen: (path: string) => void }) {
  return (
    <ul className="flex flex-col gap-1">
      {nodes.map((node) => (
        <li key={node.path}>
          {node.type === "directory" ? (
            <details>
              <summary className="cursor-pointer py-1 text-body-2-medium text-text-primary">{node.name}</summary>
              <div className="ps-4"><RepositoryTree nodes={node.children ?? []} onOpen={onOpen} /></div>
            </details>
          ) : (
            <Button variant="ghost" size="small" onClick={() => onOpen(node.path)}>{node.name}</Button>
          )}
        </li>
      ))}
    </ul>
  );
}

export function ScannerPanel() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [project, setProject] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api.projects().then(({ projects }) => {
      if (!active) return;
      setProjects(projects);
      setProject(projects[0]?.project_id ?? "");
    }).catch((failure: unknown) => { if (active) setError(message(failure)); });
    return () => { active = false; };
  }, []);
  return (
    <div className="flex flex-col gap-6">
      {error && <p role="alert" className="text-text-error-primary">{error}</p>}
      {!projects && !error && <p role="status">Loading repositories…</p>}
      {projects && (
        <Select aria-label="Repository" selectedKey={project} onSelectionChange={(key) => setProject(String(key))}>
          {projects.map((item) => <SelectItem key={item.project_id} id={item.project_id}>{item.name}</SelectItem>)}
        </Select>
      )}
      {project && <RepositoryWorkspace key={project} project={project} />}
    </div>
  );
}

function RepositoryWorkspace({ project }: { project: string }) {
  const [tree, setTree] = useState<TreeNode[] | null>(null);
  const [treeError, setTreeError] = useState("");
  const [file, setFile] = useState<SourceFile>();
  const [fileStatus, setFileStatus] = useState("");
  const [line, setLine] = useState<number>();
  const markedLine = useRef<HTMLSpanElement>(null);
  const fileRequest = useRef(0);
  const [result, setResult] = useState<FindingsResponse>();
  const [scanStarted, setScanStarted] = useState<number>();
  const [scanDuration, setScanDuration] = useState<number>();
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState("");
  const [explanation, setExplanation] = useState<Explanation>();
  const [reviewStatus, setReviewStatus] = useState("");
  const reviewRequest = useRef(0);
  const [partialCoverage, setPartialCoverage] = useState<ScanCoverage>();
  const [partialFindings, setPartialFindings] = useState<Finding[]>([]);
  const [view, setView] = useState<GraphView>("system");
  const impactRequest = useRef(0);
  const [impact, setImpact] = useState<FindingImpact>();
  const [impactStatus, setImpactStatus] = useState("");
  const [graph, setGraph] = useState<Graph>();
  const [graphStatus, setGraphStatus] = useState("");
  const [loadingGraph, setLoadingGraph] = useState(false);

  useEffect(() => {
    let active = true;
    api.tree(project).then((response) => { if (active) setTree(response.tree); })
      .catch((failure: unknown) => { if (active) setTreeError(message(failure)); });
    return () => { active = false; };
  }, [project]);

  useEffect(() => { markedLine.current?.scrollIntoView({ block: "nearest" }); }, [file, line]);

  async function openFile(path: string, sourceLine?: number) {
    const request = ++fileRequest.current;
    setFileStatus("Opening source…");
    try {
      const next = await api.file(project, path);
      if (request !== fileRequest.current) return;
      setFile(next);
      setLine(sourceLine);
      setFileStatus("");
    } catch (failure) {
      if (request === fileRequest.current) setFileStatus(message(failure));
    }
  }

  async function scan() {
    const started = Date.now();
    setScanStarted(started);
    setScanDuration(undefined);
    setScanning(true);
    setResult(undefined);
    setScanError("");
    ++reviewRequest.current;
    setPartialCoverage(undefined);
    setPartialFindings([]);
    ++impactRequest.current;
    setImpact(undefined);
    setImpactStatus("");
    setExplanation(undefined);
    setReviewStatus("");
    try {
      setResult(await api.scan(project));
      setScanDuration((Date.now() - started) / 1000);
    } catch (failure) {
      setScanError(message(failure));
      if (failure instanceof CodelyApiError) {
        setPartialCoverage(failure.coverage);
        setPartialFindings(failure.findings);
      }
    } finally {
      setScanning(false);
    }
  }

  async function explain(id: string) {
    const request = ++reviewRequest.current;
    setExplanation(undefined);
    setReviewStatus("Requesting explanation…");
    try {
      const next = await api.explain(project, id);
      if (request !== reviewRequest.current) return;
      setExplanation(next);
      setReviewStatus("");
    } catch (failure) {
      if (request === reviewRequest.current) setReviewStatus(message(failure));
    }
  }

  async function reviewImpact(id: string) {
    const request = ++impactRequest.current;
    setImpact(undefined);
    setImpactStatus("Mapping static dependents…");
    try {
      const payload = await api.impact(project, id);
      if (request !== impactRequest.current) return;
      setImpact(payload);
      setImpactStatus("");
    } catch (failure) {
      if (request === impactRequest.current) setImpactStatus(message(failure));
    }
  }

  async function loadGraph() {
    setLoadingGraph(true);
    setGraph(undefined);
    setGraphStatus("Analyzing repository structure…");
    try {
      setGraph(await api.architecture(project, view));
      setGraphStatus("");
    } catch (failure) {
      setGraphStatus(message(failure));
    } finally {
      setLoadingGraph(false);
    }
  }

  const priorCoverage = result?.diagnostics?.find((entry) => entry.code === "coverage");
  const coverage = result?.coverage ?? partialCoverage;
  return (
    <>
      <section className="flex flex-col gap-4 rounded-3xl border border-border-button-default p-4">
        <h2 className="text-headline-medium">Repository source</h2>
        {treeError && <p role="alert" className="text-text-error-primary">{treeError}</p>}
        {!tree && !treeError && <p role="status">Loading files…</p>}
        {tree && <RepositoryTree nodes={tree} onOpen={openFile} />}
        {fileStatus && <p role="status">{fileStatus}</p>}
        {file && (
          <div>
            <h3 className="text-body-medium">{file.path}</h3>
            <pre dir="ltr" className="whitespace-pre-wrap break-all rounded-xl bg-background-secondary-default p-4 text-start">
              {file.content.split("\n").map((text, index) => (
                <span key={index} ref={line === index + 1 ? markedLine : undefined}
                  className={cx("block", line === index + 1 && "bg-background-tertiary-default text-text-primary")}>
                  <span className="me-4 text-text-tertiary" aria-hidden>{index + 1}</span>{text}
                </span>
              ))}
            </pre>
          </div>
        )}
      </section>
      <section className="flex flex-col gap-4">
        <div><Button variant="primary" disabled={scanning} onClick={scan}>Run repository security scan</Button></div>
        {scanError && <p role="alert" className="text-text-error-primary">{scanError}</p>}
        {result && <p role="status">{result.cached ? "Cached scan" : "Scan completed"}{!coverage && priorCoverage ? ` · ${priorCoverage.snapshot_files} files in scanner snapshot` : ""}</p>}
        {coverage && (
          <section aria-label="Scan coverage" className="flex flex-col gap-1 rounded-xl bg-background-secondary-default p-4">
            <h3 className="text-headline-medium">Scan coverage</h3>
            <p>Detected: {coverage.detected_languages.join(", ") || "None"}</p>
            <p>Analyzed: {coverage.analyzed_languages.join(", ") || "None"}</p>
            <p>Unsupported: {coverage.unsupported_languages.join(", ") || "None detected"}</p>
            <p>{coverage.scanned_files} scanned · {coverage.excluded_files} observed files excluded · {coverage.excluded_directory_count} directories pruned</p>
            {coverage.unscanned_supported_files > 0 && <p>{coverage.unscanned_supported_files} staged files were unscanned.</p>}
          </section>
        )}
        {partialFindings.length > 0 && (
          <section aria-label="Partial findings">
            <h3 className="text-headline-medium">Partial findings</h3>
            <ScannerResults findings={partialFindings.map(toDisplayFinding)} onOpen={openFile} />
          </section>
        )}
        {(scanning || result?.status === "completed") && (
          <ScannerResults findings={result ? completedFindings(result) : []} loading={scanning}
            onOpen={openFile} onExplain={explain} onImpact={reviewImpact} startedAt={scanStarted} durationSeconds={scanDuration} />
        )}
        {impactStatus && <p role="status">{impactStatus}</p>}
        {impact && (
          <section className="flex flex-col gap-2 rounded-xl bg-background-secondary-default p-4">
            <h3 className="text-headline-medium">Static finding impact</h3>
            <p>{impact.interpretation}</p>
            <p>Analysis {impact.status} · Finding {impact.finding_impact.mapping_status}</p>
            {(["direct", "transitive"] as const).map((kind) => (
              <div key={kind}>
                <h4 className="text-body-medium">{kind === "direct" ? "Direct dependents" : "Transitive dependents"}</h4>
                <ul className="flex flex-wrap gap-1">
                  {impact.node_contexts.filter((node) => impact.finding_impact[`${kind}_dependent_node_ids`].includes(node.id))
                    .map((node) => <li key={node.id}><Button variant="ghost" size="small" onClick={() => openFile(node.file)}>{node.file}</Button></li>)}
                </ul>
              </div>
            ))}
          </section>
        )}
        {reviewStatus && <p role="status">{reviewStatus}</p>}
        {explanation && (
          <div className="flex flex-col gap-2 rounded-xl bg-background-secondary-default p-4">
            <h3 className="text-headline-medium">Finding explanation</h3>
            <p>{explanation.explanation}</p><p>{explanation.potential_impact}</p><p>{explanation.recommendation}</p>
            {explanation.suggested_code && <pre className="whitespace-pre-wrap" dir="ltr">{explanation.suggested_code}</pre>}
            {explanation.assumptions_and_limitations?.map((limit, index) => <p key={index}>{limit}</p>)}
            <p className="text-body-2-regular text-text-secondary">Developer review required.</p>
          </div>
        )}
      </section>
      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end gap-2">
          <Select aria-label="Architecture view" selectedKey={view} isDisabled={loadingGraph} onSelectionChange={(key) => {
            if (key === "dependencies" || key === "system") { setView(key); setGraph(undefined); setGraphStatus(""); }
          }}>
            <SelectItem id="system">System Architecture</SelectItem>
            <SelectItem id="dependencies">Code Dependencies</SelectItem>
          </Select>
          <Button variant="secondary" disabled={loadingGraph} onClick={loadGraph}>Load architecture</Button>
        </div>
        {graphStatus && <p role="status">{graphStatus}</p>}
        {graph && <ArchitectureViewer graph={graph} onOpen={openFile} />}
      </section>
      <Link href={{ pathname: "/", query: { project } }} className="text-body-medium text-accent-700 underline">
        Ask a system-design question about this repository
      </Link>
    </>
  );
}

function ArchitectureViewer({ graph, onOpen }: {
  graph: Graph; onOpen: (path: string, line?: number) => void;
}) {
  const [focus, setFocus] = useState("all");
  const [page, setPage] = useState(0);
  const [zoom, setZoom] = useState(100);
  const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
  const edges = focus === "all" ? graph.edges : graph.edges.filter((edge) => edge.source === focus || edge.target === focus);
  const pageSize = 16;
  const pages = Math.max(1, Math.ceil(edges.length / pageSize));
  const focused = nodes.get(focus);
  const system = graph.graph_type === "system";
  const groups = [...new Set(graph.nodes.map((node) => node.type))].sort();

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <h2 className="text-headline-medium">{system ? "Observed system architecture" : "Observed code dependencies"}</h2>
      <p className="text-body-2-regular text-text-secondary">
        {graph.nodes.length} {system ? "components" : "modules"} · {graph.edges.length} directed relationships
        {graph.status === "partial" && " · Partial coverage"}
      </p>
      {system && <p className="text-body-2-regular text-text-secondary">
        {groups.map((type) => `${type.replaceAll("_", " ")}: ${graph.nodes.filter((node) => node.type === type).length}`).join(" · ")}
      </p>}
      {graph.diagnostics.length > 0 && <p className="text-body-2-regular text-text-secondary">
        {Array.from(new Set(graph.diagnostics.flatMap((item) => item.code ? [item.code.replaceAll("_", " ")] : []))).join(" · ")}
      </p>}
      <div className="flex flex-wrap items-center gap-2">
        <Select aria-label="Focus architecture module" selectedKey={focus} onSelectionChange={(key) => {
          setFocus(String(key)); setPage(0);
        }}>
          <SelectItem id="all">All modules</SelectItem>
          {graph.nodes.map((node) => <SelectItem key={node.id} id={node.id}>{node.label} · {node.file}</SelectItem>)}
        </Select>
        {focused && <Button variant="secondary" size="small" onClick={() => onOpen(focused.file)}>Open module source</Button>}
        <Button variant="ghost" size="small" disabled={zoom <= 75} onClick={() => setZoom(zoom - 25)}>Zoom out</Button>
        <Button variant="ghost" size="small" disabled={zoom >= 175} onClick={() => setZoom(zoom + 25)}>Zoom in</Button>
        <span aria-live="polite">{zoom}%</span>
      </div>
      {edges.length === 0 && <p>No directed relationships were observed for this selection.</p>}
      {edges.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-border-button-default bg-background-secondary-default p-3 focus-visible:ring-2 focus-visible:ring-border-focus-ring"
          role="region" aria-label="Directed architecture graph, scroll horizontally to pan" tabIndex={0}>
          <ul className="flex w-max min-w-full flex-col gap-2" style={{ zoom: zoom / 100 }}>
            {edges.slice(page * pageSize, (page + 1) * pageSize).map((edge) => {
              const from = nodes.get(edge.source);
              const to = nodes.get(edge.target);
              return (
                <li key={edge.id ?? `${edge.source}:${edge.target}`} className="flex items-center gap-2">
                  {from && <Button variant="secondary" size="small" onClick={() => onOpen(from.file)}>{from.label}</Button>}
                  <span className="text-body-2-regular text-text-secondary">{edge.relationship.replaceAll("_", " ")} {edge.confidence === "inferred" ? "(inferred)" : ""} →</span>
                  {to && <Button variant="secondary" size="small" onClick={() => onOpen(to.file)}>{to.label}</Button>}
                  {edge.evidence?.length ? (
                    <details className="text-body-2-regular text-text-secondary">
                      <summary className="cursor-pointer">Evidence</summary>
                      {edge.evidence.map((anchor) => (
                        <Button key={`${anchor.file}:${anchor.start_line}`} variant="ghost" size="small"
                          onClick={() => onOpen(anchor.file, anchor.start_line)}>{anchor.file}:{anchor.start_line}</Button>
                      ))}
                    </details>
                  ) : edge.file && <Button variant="ghost" size="small" onClick={() => onOpen(edge.file!, edge.start_line ?? undefined)}>Open source</Button>}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {pages > 1 && <div className="flex items-center gap-2">
        <Button variant="ghost" size="small" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous edges</Button>
        <span>{page + 1} of {pages}</span>
        <Button variant="ghost" size="small" disabled={page + 1 === pages} onClick={() => setPage(page + 1)}>Next edges</Button>
      </div>}
    </div>
  );
}
