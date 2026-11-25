"use client";

import {
  RiAlertFill,
  RiErrorWarningFill,
  RiInformationFill,
  RiCheckboxCircleFill,
  RiArrowDownSLine,
  RiArrowUpSLine,
  RiShieldCheckLine,
} from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { useState } from "react";
import { cx } from "@/utils/cx";

export type Severity = "critical" | "high" | "medium" | "low" | "info";

export interface ScanFinding {
  id: string;
  severity: Severity;
  title: string;
  description: string;
  file?: string;
  line?: number;
  recommendation?: string;
}

interface ScannerResultsProps {
  findings: ScanFinding[];
  /** True while the scan is in progress. */
  loading?: boolean;
  onOpen?: (path: string, line?: number) => void;
  onExplain?: (id: string) => void;
}

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];

const SEVERITY_META: Record<
  Severity,
  { label: string; icon: typeof RiAlertFill; chipClass: string; dotClass: string }
> = {
  critical: {
    label: "Critical",
    icon: RiAlertFill,
    chipClass: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
    dotClass: "bg-red-500",
  },
  high: {
    label: "High",
    icon: RiErrorWarningFill,
    chipClass: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300",
    dotClass: "bg-orange-500",
  },
  medium: {
    label: "Medium",
    icon: RiInformationFill,
    chipClass: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
    dotClass: "bg-amber-400",
  },
  low: {
    label: "Low",
    icon: RiInformationFill,
    chipClass: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
    dotClass: "bg-blue-400",
  },
  info: {
    label: "Info",
    icon: RiCheckboxCircleFill,
    chipClass: "bg-background-tertiary-default text-text-secondary",
    dotClass: "bg-border-button-default",
  },
};

export function ScannerResults({ findings, loading = false, onOpen, onExplain }: ScannerResultsProps) {
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-3xl border border-border-button-default bg-background-secondary-default py-16">
        <RiShieldCheckLine className="size-10 animate-pulse text-accent-500" aria-hidden />
        <p className="text-body-regular text-text-secondary">Scanning for bugs to crush…</p>
      </div>
    );
  }

  if (findings.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-3xl border border-border-button-default bg-background-secondary-default py-16">
        <RiCheckboxCircleFill className="size-10 text-lime-500" aria-hidden />
        <p className="text-headline-medium text-text-primary">No issues found</p>
        <p className="text-body-regular text-text-secondary">The configured rules returned zero findings for the files they scanned.</p>
      </div>
    );
  }

  const grouped = SEVERITY_ORDER.map((severity) => ({
    severity,
    items: findings.filter((f) => f.severity === severity),
  })).filter(({ items }) => items.length > 0);

  return (
    <div className="flex flex-col gap-4">
      {/* Summary row */}
      <div className="flex flex-wrap gap-2">
        {grouped.map(({ severity, items }) => {
          const meta = SEVERITY_META[severity];
          return (
            <span
              key={severity}
              className={cx("inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-body-2-medium", meta.chipClass)}
            >
              <span className={cx("size-1.5 rounded-full", meta.dotClass)} aria-hidden />
              {items.length} {meta.label}
            </span>
          );
        })}
      </div>

      {/* Finding rows */}
      {grouped.map(({ severity, items }) => (
        <div key={severity} className="flex flex-col gap-2">
          <h3 className="text-body-medium text-text-secondary">{SEVERITY_META[severity].label}</h3>
          {items.map((finding) => (
            <FindingRow key={finding.id} finding={finding} onOpen={onOpen} onExplain={onExplain} />
          ))}
        </div>
      ))}
    </div>
  );
}

function FindingRow({ finding, onOpen, onExplain }: Pick<ScannerResultsProps, "onOpen" | "onExplain"> & { finding: ScanFinding }) {
  const [expanded, setExpanded] = useState(false);
  const meta = SEVERITY_META[finding.severity];
  const Icon = meta.icon;

  return (
    <div className="rounded-xl border border-border-button-default bg-background-primary-default">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="flex w-full cursor-pointer items-start gap-3 px-4 py-3 text-start"
      >
        <Icon className={cx("mt-0.5 size-4 shrink-0", meta.chipClass.split(" ").find((c) => c.startsWith("text-")))} aria-hidden />
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-body-medium text-text-primary">{finding.title}</span>
          {finding.file && (
            <span className="text-body-2-regular text-text-tertiary">
              {finding.file}{finding.line != null ? `:${finding.line}` : ""}
            </span>
          )}
        </div>
        {expanded ? (
          <RiArrowUpSLine className="mt-0.5 size-4 shrink-0 text-foreground-icon-secondary" aria-hidden />
        ) : (
          <RiArrowDownSLine className="mt-0.5 size-4 shrink-0 text-foreground-icon-secondary" aria-hidden />
        )}
      </button>

      {expanded && (
        <div className="flex flex-col gap-3 border-t border-separator-border px-4 pb-4 pt-3">
          <p className="text-body-regular text-text-secondary">{finding.description}</p>
          <div className="flex flex-wrap gap-2">
            {onOpen && finding.file && <Button variant="secondary" size="small" onClick={() => onOpen(finding.file!, finding.line)}>Open source</Button>}
            {onExplain && <Button variant="secondary" size="small" onClick={() => onExplain(finding.id)}>Explain finding</Button>}
          </div>
          {finding.recommendation && (
            <div className="rounded-lg bg-background-secondary-default px-3 py-2">
              <p className="text-body-2-medium text-text-primary">Recommendation</p>
              <p className="mt-0.5 text-body-2-regular text-text-secondary">{finding.recommendation}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
