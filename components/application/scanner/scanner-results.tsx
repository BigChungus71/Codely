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
import { useState } from "react";
import { AgentThinking } from "@/components/application/agent-thinking/agent-thinking";
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
  /** Epoch-ms timestamp when the scan started. */
  startedAt?: number;
  /** Elapsed duration in seconds once the scan finishes. */
  durationSeconds?: number;
}

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];

const SEVERITY_META: Record<
  Severity,
  {
    label: string;
    icon: typeof RiAlertFill;
    chipClass: string;
    iconClass: string;
    dotClass: string;
  }
> = {
  critical: {
    label: "Critical",
    icon: RiAlertFill,
    chipClass: "bg-status-rose-background text-status-rose-text",
    iconClass: "text-status-rose-text",
    dotClass: "bg-status-rose-text",
  },
  high: {
    label: "High",
    icon: RiErrorWarningFill,
    chipClass: "bg-status-orange-background text-status-orange-text",
    iconClass: "text-status-orange-text",
    dotClass: "bg-status-orange-text",
  },
  medium: {
    label: "Medium",
    icon: RiInformationFill,
    chipClass: "bg-status-yellow-background text-status-yellow-text",
    iconClass: "text-status-yellow-text",
    dotClass: "bg-status-yellow-text",
  },
  low: {
    label: "Low",
    icon: RiInformationFill,
    chipClass: "bg-status-blue-background text-status-blue-text",
    iconClass: "text-status-blue-text",
    dotClass: "bg-status-blue-text",
  },
  info: {
    label: "Info",
    icon: RiCheckboxCircleFill,
    chipClass: "bg-background-tertiary-default text-text-secondary",
    iconClass: "text-foreground-icon-secondary",
    dotClass: "bg-foreground-icon-tertiary",
  },
};

export function ScannerResults({
  findings,
  loading = false,
  startedAt,
  durationSeconds,
}: ScannerResultsProps) {
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-3xl border border-border-button-default bg-background-secondary-default py-16">
        <RiShieldCheckLine className="size-10 text-accent-500" aria-hidden />
        <AgentThinking
          variant="wave"
          tone="accent"
          label="Analyzing codebase…"
          active
          startedAt={startedAt}
        />
      </div>
    );
  }

  if (findings.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-3xl border border-border-button-default bg-background-secondary-default py-16">
        <RiCheckboxCircleFill className="size-10 text-status-lime-text" aria-hidden />
        <p className="text-headline-medium text-text-primary">No issues found</p>
        <p className="text-body-regular text-text-secondary">Your codebase looks clean. Well done!</p>
        {durationSeconds !== undefined && (
          <AgentThinking
            variant="stars"
            tone="accent"
            label="Analysis complete"
            active={false}
            shimmer={false}
            durationSeconds={durationSeconds}
          />
        )}
      </div>
    );
  }

  const grouped = SEVERITY_ORDER.map((severity) => ({
    severity,
    items: findings.filter((f) => f.severity === severity),
  })).filter(({ items }) => items.length > 0);

  return (
    <div className="flex flex-col gap-4">
      {/* Completion banner + Summary row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
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

        <AgentThinking
          variant="stars"
          tone="accent"
          label="Analysis complete"
          active={false}
          shimmer={false}
          showTimer={durationSeconds !== undefined}
          durationSeconds={durationSeconds}
        />
      </div>

      {/* Finding rows */}
      {grouped.map(({ severity, items }) => (
        <div key={severity} className="flex flex-col gap-2">
          <h3 className="text-body-medium text-text-secondary">{SEVERITY_META[severity].label}</h3>
          {items.map((finding) => (
            <FindingRow key={finding.id} finding={finding} />
          ))}
        </div>
      ))}
    </div>
  );
}

function FindingRow({ finding }: { finding: ScanFinding }) {
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
        <Icon className={cx("mt-0.5 size-4 shrink-0", meta.iconClass)} aria-hidden />
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
