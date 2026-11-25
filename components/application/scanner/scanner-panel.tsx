"use client";

import { useState } from "react";
import { RiShieldCheckLine, RiScanLine } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { ScannerUpload, type ScanFile } from "@/components/application/scanner/scanner-upload";
import { ScannerGithubInput } from "@/components/application/scanner/scanner-github-input";
import { ScannerConfig, type ScanConfig } from "@/components/application/scanner/scanner-config";
import { ScannerResults, type ScanFinding } from "@/components/application/scanner/scanner-results";
import { recordCodelyScan } from "@/utils/codely-metrics";
import { cx } from "@/utils/cx";

const GITHUB_RE = /^https:\/\/github\.com\/[^/]+\/[^/]+(\/.*)?$/;

type ScanState = "idle" | "scanning" | "done";

const DEFAULT_CONFIG: ScanConfig = {
  security: true,
  dependencies: true,
  architecture: true,
  comparison: false,
  baseline: "clean",
};

/** Demo findings shown when no real backend is wired. */
const DEMO_FINDINGS: ScanFinding[] = [
  {
    id: "1",
    severity: "critical",
    title: "SQL Injection vulnerability",
    description: "User input is concatenated directly into a SQL query without parameterisation. An attacker can read or modify any data in the database.",
    file: "src/api/users.ts",
    line: 42,
    recommendation: "Use parameterised queries or a query builder (e.g. knex, Prisma). Never interpolate user input into SQL strings.",
  },
  {
    id: "2",
    severity: "high",
    title: "Hardcoded secret detected",
    description: "An API key or password was found embedded in source code. If committed to a public repository, this credential is compromised.",
    file: "src/config.ts",
    line: 8,
    recommendation: "Move secrets to environment variables and add this file pattern to .gitignore. Rotate the exposed credential immediately.",
  },
  {
    id: "3",
    severity: "high",
    title: "Outdated dependency with known CVE",
    description: "Package lodash@3.10.1 has a known prototype-pollution vulnerability (CVE-2019-10744).",
    recommendation: "Upgrade lodash to 4.17.21 or later. Run `npm audit fix` to resolve automatically.",
  },
  {
    id: "4",
    severity: "medium",
    title: "Missing CSRF protection",
    description: "State-changing POST endpoints do not validate a CSRF token, allowing cross-site request forgery attacks.",
    file: "src/api/auth.ts",
    recommendation: "Add a CSRF token header requirement to all state-mutating routes. Use a library like csurf or implement the synchroniser-token pattern.",
  },
  {
    id: "5",
    severity: "medium",
    title: "Circular dependency detected",
    description: "Module A imports Module B, which imports Module A, creating a circular reference that can cause initialisation failures and hard-to-trace bugs.",
    file: "src/services/order.ts",
    recommendation: "Extract the shared logic into a third module that both A and B import, breaking the cycle.",
  },
  {
    id: "6",
    severity: "low",
    title: "Unused exported function",
    description: "The function `calculateDiscount` is exported but never imported elsewhere in the project.",
    file: "src/utils/pricing.ts",
    line: 56,
    recommendation: "Remove the export or the function if it is dead code. If it is intended for future use, add a TODO comment.",
  },
  {
    id: "7",
    severity: "info",
    title: "Missing TSDoc comments on public API",
    description: "12 exported functions lack documentation comments, which makes IDE hover-help less useful for consumers.",
    recommendation: "Add TSDoc comments explaining parameters, return values, and thrown errors for all public exports.",
  },
];

export function ScannerPanel() {
  const [files, setFiles] = useState<ScanFile[]>([]);
  const [githubUrl, setGithubUrl] = useState("");
  const [config, setConfig] = useState<ScanConfig>(DEFAULT_CONFIG);
  const [scanState, setScanState] = useState<ScanState>("idle");
  const [findings, setFindings] = useState<ScanFinding[]>([]);

  const githubValid = githubUrl === "" || GITHUB_RE.test(githubUrl);
  const hasInput = files.length > 0 || (githubUrl.length > 0 && githubValid);
  const canScan = hasInput && scanState !== "scanning";

  const startScan = () => {
    if (!canScan) return;
    setScanState("scanning");
    setFindings([]);
    // Simulate a scan — replace with a real API call when the backend is ready.
    setTimeout(() => {
      setFindings(DEMO_FINDINGS);
      setScanState("done");
      recordCodelyScan(DEMO_FINDINGS.length, Math.max(180, files.length * 140));
    }, 2200);
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

      {/* Results */}
      {(scanState === "scanning" || scanState === "done") && (
        <div className="flex flex-col gap-4">
          <div className="h-px bg-separator-border" />
          <h3 className="text-headline-medium text-text-primary">Findings</h3>
          <ScannerResults findings={findings} loading={scanState === "scanning"} />
        </div>
      )}
    </div>
  );
}
