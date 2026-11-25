"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/base/buttons/button";
import { Select, SelectItem } from "@/components/base/select/select";
import { ScannerResults } from "./scanner-results";
import {
  completedFindings, createCodelyClient, type Explanation, type FindingsResponse,
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
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState("");
  const [explanation, setExplanation] = useState<Explanation>();
  const [reviewStatus, setReviewStatus] = useState("");
  const reviewRequest = useRef(0);
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
    setScanning(true);
    setResult(undefined);
    setScanError("");
    ++reviewRequest.current;
    setExplanation(undefined);
    setReviewStatus("");
    try {
      setResult(await api.scan(project));
    } catch (failure) {
      setScanError(message(failure));
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

  async function loadGraph() {
    setLoadingGraph(true);
    setGraph(undefined);
    setGraphStatus("Analyzing Python structure…");
    try {
      setGraph(await api.architecture(project));
      setGraphStatus("");
    } catch (failure) {
      setGraphStatus(message(failure));
    } finally {
      setLoadingGraph(false);
    }
  }

  const coverage = result?.diagnostics?.find((entry) => entry.code === "coverage");
  const nodes = new Map(graph?.nodes.map((node) => [node.id, node]));
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
        <div><Button variant="primary" disabled={scanning} onClick={scan}>Run Python security scan</Button></div>
        {scanError && <p role="alert" className="text-text-error-primary">{scanError}</p>}
        {result && <p role="status">{result.cached ? "Cached scan" : "Scan completed"}{coverage ? ` · ${coverage.snapshot_files} Python files analyzed` : ""}</p>}
        {(scanning || result?.status === "completed") && (
          <ScannerResults findings={result ? completedFindings(result) : []} loading={scanning}
            onOpen={openFile} onExplain={explain} />
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
        <div><Button variant="secondary" disabled={loadingGraph} onClick={loadGraph}>Load Python architecture</Button></div>
        {graphStatus && <p role="status">{graphStatus}</p>}
        {graph && (
          <>
            <h2 className="text-headline-medium">Observed modules and imports</h2>
            {graph.status === "partial" && <p>Partial analysis. Some files could not be parsed.</p>}
            <ul className="flex flex-wrap gap-2">
              {graph.nodes.map((node) => <li key={node.id}><Button variant="secondary" size="small" onClick={() => openFile(node.file)}>{node.label}</Button></li>)}
            </ul>
            {graph.edges.length === 0 && <p>No internal imports were resolved.</p>}
            <ul className="flex flex-col gap-2">
              {graph.edges.map((edge, index) => (
                <li key={index} className="flex flex-wrap items-center gap-2">
                  <span>{nodes.get(edge.source)?.label}</span><span>→ {edge.relationship} →</span>
                  <span>{nodes.get(edge.target)?.label}</span>
                  {edge.file && <Button variant="ghost" size="small" onClick={() => openFile(edge.file!, edge.start_line ?? undefined)}>Open import</Button>}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
      <Link href={{ pathname: "/", query: { project } }} className="text-body-medium text-accent-700 underline">
        Ask a system-design question about this repository
      </Link>
    </>
  );
}
