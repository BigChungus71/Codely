"use client";

import { useEffect, useRef, useState } from "react";
import { RiShieldCheckLine, RiScanLine, RiStopFill } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { ScannerUpload, type ScanFile } from "@/components/application/scanner/scanner-upload";
import { ScannerConfig, type ScanConfig } from "@/components/application/scanner/scanner-config";
import { ScannerResults, type ScanFinding } from "@/components/application/scanner/scanner-results";
import { cx } from "@/utils/cx";

const TEXT_FILE_RE = /\.(json|ts|tsx|js|jsx|py|go|java|md|yaml|yml|toml)$/i;

type ScanState = "idle" | "scanning" | "done";

const DEFAULT_CONFIG: ScanConfig = {
  security: true,
  dependencies: true,
  architecture: true,
  comparison: false,
  baseline: "clean",
};

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
  const [error, setError] = useState("");
  const [config, setConfig] = useState<ScanConfig>(DEFAULT_CONFIG);
  const [scanState, setScanState] = useState<ScanState>("idle");
  const [findings, setFindings] = useState<ScanFinding[]>([]);
  const [startedAt, setStartedAt] = useState<number | undefined>(undefined);
  const [durationSeconds, setDurationSeconds] = useState<number | undefined>(undefined);

  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const hasInput = files.length > 0;
  const canScan = hasInput && scanState !== "scanning";

  const cancelScan = () => {
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
  };

  const startScan = async () => {
    if (!canScan) return;
    cancelScan();
    setError("");

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
      const failure = await response.json().catch(() => null);
      throw new Error(failure?.message ?? `AI review returned HTTP ${response.status}`);
    } catch (failure) {
      if (controller.signal.aborted) return;
      abortRef.current = null;
      setScanState("idle");
      setError(failure instanceof Error ? failure.message : "AI review failed");
    }

  };

  return (
    <div className="flex flex-col gap-6">
      {/* Hero */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <RiShieldCheckLine className="size-6 text-accent-500" aria-hidden />
          <h2 className="text-title-2-medium text-text-primary">AI snippet review</h2>
        </div>
        <p className="text-body-regular text-text-secondary">
          Submit text snippets for suggestions from the configured AI provider.
        </p>
      </div>

      {/* Input section */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-4">
          <ScannerUpload files={files} onChange={setFiles} />

        </div>
        <ScannerConfig config={config} onChange={setConfig} />
      </div>

      {/* Scan button */}
      <div className="flex items-center justify-between gap-4">
        <p className={cx("text-body-2-regular text-text-tertiary", hasInput && "opacity-0")}>
          Add a supported text file to begin.
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
            {scanState === "scanning" ? "Scanning…" : "Review snippets"}
          </Button>
        </div>
      </div>

      {error && <p role="alert" className="text-text-error-primary">{error}</p>}

      {/* Results */}
      {(scanState === "scanning" || scanState === "done") && (
        <div className="flex flex-col gap-4">
          <div className="h-px bg-separator-border" />
          <h3 className="text-headline-medium text-text-primary">AI review suggestions</h3>
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
