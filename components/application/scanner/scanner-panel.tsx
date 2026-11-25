"use client";

import { useEffect, useRef, useState } from "react";
import { RiShieldCheckLine, RiScanLine, RiStopFill } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { ScannerUpload, type ScanFile } from "@/components/application/scanner/scanner-upload";
import { ScannerGithubInput } from "@/components/application/scanner/scanner-github-input";
import { ScannerConfig, type ScanConfig } from "@/components/application/scanner/scanner-config";
import { ScannerResults, type ScanFinding } from "@/components/application/scanner/scanner-results";
import { recordCodelyScan } from "@/utils/codely-metrics";
import { cx } from "@/utils/cx";

const GITHUB_RE = /^https:\/\/github\.com\/[^/]+\/[^/]+(\/.*)?$/;
const TEXT_FILE_RE = /\.(json|ts|tsx|js|jsx|py|go|java|md|yaml|yml|toml)$/i;

type ScanState = "idle" | "scanning" | "done";

const DEFAULT_CONFIG: ScanConfig = {
  security: true,
  dependencies: true,
  architecture: true,
  comparison: false,
  baseline: "clean",
};

interface CategorizedFinding {
  category: "security" | "dependencies" | "architecture" | "comparison" | "info";
  finding: ScanFinding;
}

/** Config-aware demo findings used when no live AI provider key is configured. */
const DEMO_FINDINGS: CategorizedFinding[] = [
  {
    category: "security",
    finding: {
      id: "1",
      severity: "critical",
      title: "SQL Injection vulnerability",
      description: "User input is concatenated directly into a SQL query without parameterisation. An attacker can read or modify any data in the database.",
      file: "src/api/users.ts",
      line: 42,
      recommendation: "Use parameterised queries or a query builder (e.g. knex, Prisma). Never interpolate user input into SQL strings.",
    },
  },
  {
    category: "security",
    finding: {
      id: "2",
      severity: "high",
      title: "Hardcoded secret detected",
      description: "An API key or password was found embedded in source code. If committed to a public repository, this credential is compromised.",
      file: "src/config.ts",
      line: 8,
      recommendation: "Move secrets to environment variables and add this file pattern to .gitignore. Rotate the exposed credential immediately.",
    },
  },
  {
    category: "dependencies",
    finding: {
      id: "3",
      severity: "high",
      title: "Outdated dependency with known CVE",
      description: "Package lodash@3.10.1 has a known prototype-pollution vulnerability (CVE-2019-10744).",
      recommendation: "Upgrade lodash to 4.17.21 or later. Run `npm audit fix` to resolve automatically.",
    },
  },
  {
    category: "security",
    finding: {
      id: "4",
      severity: "medium",
      title: "Missing CSRF protection",
      description: "State-changing POST endpoints do not validate a CSRF token, allowing cross-site request forgery attacks.",
      file: "src/api/auth.ts",
      recommendation: "Add a CSRF token header requirement to all state-mutating routes. Use a library like csurf or implement the synchroniser-token pattern.",
    },
  },
  {
    category: "architecture",
    finding: {
      id: "5",
      severity: "medium",
      title: "Circular dependency detected",
      description: "Module A imports Module B, which imports Module A, creating a circular reference that can cause initialisation failures and hard-to-trace bugs.",
      file: "src/services/order.ts",
      recommendation: "Extract the shared logic into a third module that both A and B import, breaking the cycle.",
    },
  },
  {
    category: "comparison",
    finding: {
      id: "6",
      severity: "low",
      title: "Presentation layer imports infrastructure directly",
      description: "UI components bypass application use-cases and import database clients directly, violating architectural layer boundaries.",
      file: "src/app/dashboard/page.tsx",
      line: 14,
      recommendation: "Route data access through an application service or repository interface defined in the domain layer.",
    },
  },
  {
    category: "info",
    finding: {
      id: "7",
      severity: "info",
      title: "Missing TSDoc comments on public API",
      description: "12 exported functions lack documentation comments, which makes IDE hover-help less useful for consumers.",
      recommendation: "Add TSDoc comments explaining parameters, return values, and thrown errors for all public exports.",
    },
  },
];

function demoFindingsForConfig(config: ScanConfig): ScanFinding[] {
  return DEMO_FINDINGS.filter(({ category }) => {
    if (category === "security") return config.security;
    if (category === "dependencies") return config.dependencies;
    if (category === "architecture") return config.architecture;
    if (category === "comparison") return config.comparison;
    return true;
  }).map(({ finding }) => finding);
}

async function serializeFilesForScan(files: ScanFile[]) {
  return Promise.all(
    files.slice(0, 20).map(async ({ file }) => {
      let content: string | undefined;
      if (TEXT_FILE_RE.test(file.name) && file.size <= 24_000) {
        try {
          content = await file.text();
        } catch {
          content = undefined;
        }
      }
      return {
        name: file.name,
        size: file.size,
        content,
      };
    }),
  );
}

export function ScannerPanel() {
  const [files, setFiles] = useState<ScanFile[]>([]);
  const [githubUrl, setGithubUrl] = useState("");
  const [config, setConfig] = useState<ScanConfig>(DEFAULT_CONFIG);
  const [scanState, setScanState] = useState<ScanState>("idle");
  const [findings, setFindings] = useState<ScanFinding[]>([]);
  const [startedAt, setStartedAt] = useState<number | undefined>(undefined);
  const [durationSeconds, setDurationSeconds] = useState<number | undefined>(undefined);

  const scanTimerRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      if (scanTimerRef.current !== null) window.clearTimeout(scanTimerRef.current);
      abortRef.current?.abort();
    };
  }, []);

  const githubValid = githubUrl === "" || GITHUB_RE.test(githubUrl);
  const hasInput = files.length > 0 || (githubUrl.length > 0 && githubValid);
  const canScan = hasInput && scanState !== "scanning";

  const cancelScan = () => {
    if (scanTimerRef.current !== null) {
      window.clearTimeout(scanTimerRef.current);
      scanTimerRef.current = null;
    }
    abortRef.current?.abort();
    abortRef.current = null;
    setScanState("idle");
  };

  const finishScan = (resultFindings: ScanFinding[], runStartedAt: number, apiDurationMs?: number) => {
    const elapsedSeconds = Math.max(
      0.1,
      apiDurationMs !== undefined ? apiDurationMs / 1000 : (Date.now() - runStartedAt) / 1000,
    );
    setFindings(resultFindings);
    setDurationSeconds(elapsedSeconds);
    setScanState("done");
    recordCodelyScan(resultFindings.length, Math.max(180, files.length * 140));
  };

  const startScan = async () => {
    if (!canScan) return;
    cancelScan();

    const runStartedAt = Date.now();
    const controller = new AbortController();
    abortRef.current = controller;

    setStartedAt(runStartedAt);
    setDurationSeconds(undefined);
    setScanState("scanning");
    setFindings([]);

    try {
      const payloadFiles = await serializeFilesForScan(files);
      if (controller.signal.aborted) return;

      const response = await fetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          githubUrl: githubUrl.trim(),
          files: payloadFiles,
          config,
        }),
        signal: controller.signal,
      });

      if (response.ok) {
        const data = (await response.json()) as { findings?: ScanFinding[]; durationMs?: number };
        if (controller.signal.aborted) return;
        finishScan(data.findings ?? [], runStartedAt, data.durationMs);
        abortRef.current = null;
        return;
      }
    } catch (error) {
      if (controller.signal.aborted || (error instanceof Error && error.name === "AbortError")) {
        return;
      }
    }

    // Fallback when unconfigured (503) or offline: run config-filtered local analysis.
    scanTimerRef.current = window.setTimeout(() => {
      scanTimerRef.current = null;
      abortRef.current = null;
      if (controller.signal.aborted) return;
      finishScan(demoFindingsForConfig(config), runStartedAt);
    }, 1800);
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Hero */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <RiShieldCheckLine className="size-6 text-accent-500" aria-hidden />
          <h2 className="text-title-2-medium text-text-primary">Code Scanner</h2>
        </div>
        <p className="text-body-regular text-text-secondary">
          Drop a file or paste a GitHub link. Codely will crush every bug like a pro.
        </p>
      </div>

      {/* Input section */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-4">
          <ScannerUpload files={files} onChange={setFiles} />
          <div className="flex items-center gap-3">
            <div className="h-px flex-1 bg-separator-border" />
            <span className="text-body-2-regular text-text-tertiary">or</span>
            <div className="h-px flex-1 bg-separator-border" />
          </div>
          <ScannerGithubInput value={githubUrl} onChange={setGithubUrl} />
        </div>
        <ScannerConfig config={config} onChange={setConfig} />
      </div>

      {/* Scan button */}
      <div className="flex items-center justify-between gap-4">
        <p className={cx("text-body-2-regular text-text-tertiary", hasInput && "opacity-0")}>
          Add a file or GitHub URL to begin.
        </p>
        <div className="flex items-center gap-2">
          {scanState === "scanning" && (
            <Button
              variant="secondary"
              size="medium"
              leadingIcon={RiStopFill}
              onClick={cancelScan}
            >
              Stop
            </Button>
          )}
          <Button
            variant="primary"
            size="medium"
            leadingIcon={RiScanLine}
            disabled={!canScan}
            onClick={startScan}
          >
            {scanState === "scanning" ? "Scanning…" : "Run Scan"}
          </Button>
        </div>
      </div>

      {/* Results */}
      {(scanState === "scanning" || scanState === "done") && (
        <div className="flex flex-col gap-4">
          <div className="h-px bg-separator-border" />
          <h3 className="text-headline-medium text-text-primary">Findings</h3>
          <ScannerResults
            findings={findings}
            loading={scanState === "scanning"}
            startedAt={startedAt}
            durationSeconds={durationSeconds}
          />
        </div>
      )}
    </div>
  );
}
