"use client";

import { useState } from "react";
import { RiArrowDownSLine, RiCheckLine, RiSearchLine, RiSparklingLine } from "@remixicon/react";
import {
  LogRow,
  ShimmerText,
  WorkingRow,
  useLogMotion,
  useRevealTicker,
} from "@/components/application/agent-log/agent-log";
import { AgentThinking } from "@/components/application/agent-thinking/agent-thinking";
import { cx } from "@/utils/cx";

export interface ResearchStep {
  title: string;
  detail: string;
}

export interface ResearchPlan {
  mode: "thinking" | "research" | "building";
  headline: string;
  workingLabel: string;
  steps: ResearchStep[];
}

const PRESET_PLANS: { match: RegExp; plan: ResearchPlan }[] = [
  {
    match: /structured thinking|thinking while a scan|composer.?loader|agent.?thinking/i,
    plan: {
      mode: "thinking",
      headline: "Structured thinking pipeline",
      workingLabel: "Evaluating thinking components…",
      steps: [
        {
          title: "ComposerLoader rim light activated",
          detail: "4-stop iridescent sweep orbiting the pill rim at 450ms fade-in",
        },
        {
          title: "AgentThinking wave matrix synced",
          detail: "3×3 dot wavefront + shimmering status label and elapsed timer",
        },
        {
          title: "Reduced-motion & token check passed",
          detail: "Semantic foreground tones verified across light and dark modes",
        },
      ],
    },
  },
  {
    match: /multi-step security audits|architectural comparisons|agent.?log|scanner/i,
    plan: {
      mode: "research",
      headline: "Deep research & audit trail",
      workingLabel: "Researching security & architecture rules…",
      steps: [
        {
          title: "Indexed repository & dependency manifest",
          detail: "Mapped source modules, imports, and lockfile CVE advisories",
        },
        {
          title: "Evaluated OWASP Top 10 security vectors",
          detail: "Checked injection sinks, secret patterns, and CSRF guards",
        },
        {
          title: "Compared boundaries against Clean Architecture",
          detail: "Detected circular imports and cross-layer coupling hotspots",
        },
        {
          title: "Compiled AgentLog tree & severity findings",
          detail: "Paced row reveal via useRevealTicker + curved RowConnector guide",
        },
      ],
    },
  },
  {
    match: /showcase their codely usage|dashboard|vulnerabilities edited|bugs crushed|line changes/i,
    plan: {
      mode: "building",
      headline: "Dashboard telemetry synthesis",
      workingLabel: "Aggregating security flex metrics…",
      steps: [
        {
          title: "Read live codely:metrics store",
          detail: "Synced vulnerabilities edited & fixed, bugs crushed, and line counts",
        },
        {
          title: "Built KPI StatCards with delta chips",
          detail: "Mapped 142 fixed CVEs, 389 bugs crushed, and 48,920 line changes",
        },
        {
          title: "Configured Lines Hardened & Bugs Crushed charts",
          detail: "Rendered 12-month comparisons via RevenueChartCard & OrdersChartCard",
        },
      ],
    },
  },
];

export function matchResearchPlan(prompt: string | undefined): ResearchPlan | null {
  if (!prompt) return null;
  return PRESET_PLANS.find((entry) => entry.match.test(prompt))?.plan ?? null;
}

/**
 * Renders Codely's structured Thinking & Deep Research trail inside an assistant
 * message using the `AgentLog` (`LogRow`, `WorkingRow`, `ShimmerText`,
 * `useRevealTicker`) and `AgentThinking` components.
 */
export function CodelyResearchLog({
  plan,
  streaming = false,
}: {
  plan: ResearchPlan;
  streaming?: boolean;
}) {
  const reduce = useLogMotion();
  const [open, setOpen] = useState(true);
  const revealed = useRevealTicker({
    total: plan.steps.length,
    stepInterval: 480,
    startDelay: 120,
  });

  const finished = revealed >= plan.steps.length && !streaming;
  const visibleCount = Math.min(revealed, plan.steps.length);
  const ModeIcon = plan.mode === "research" ? RiSearchLine : RiSparklingLine;

  return (
    <div className="mb-2 rounded-2xl border border-border-button-default bg-background-secondary-default/70 px-3.5 py-2.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full cursor-pointer items-center justify-between gap-2 text-start"
      >
        <span className="flex items-center gap-2">
          {finished ? (
            <RiCheckLine className="size-4 shrink-0 text-lime-600 dark:text-lime-400" aria-hidden />
          ) : (
            <ModeIcon className="size-4 shrink-0 text-accent-500" aria-hidden />
          )}
          <span className="text-body-2-medium text-text-primary">
            {finished ? (
              `${plan.headline} • ${plan.steps.length} steps`
            ) : (
              <ShimmerText>{plan.headline}</ShimmerText>
            )}
          </span>
        </span>
        <RiArrowDownSLine
          className={cx(
            "size-4 shrink-0 text-foreground-icon-secondary transition-transform duration-150",
            open && "rotate-180",
          )}
          aria-hidden
        />
      </button>

      {open && (
        <div className="mt-2.5 flex flex-col gap-1">
          {visibleCount > 0 && (
            <ul className="flex flex-col">
              {plan.steps.slice(0, visibleCount).map((step, index) => (
                <LogRow
                  key={step.title}
                  first={index === 0}
                  last={index === visibleCount - 1 && finished}
                  reduce={reduce}
                  className="py-1"
                >
                  <div className="flex flex-col gap-0.5">
                    <span className="text-body-2-medium text-text-primary">{step.title}</span>
                    <span className="text-caption-1-regular text-text-tertiary">{step.detail}</span>
                  </div>
                </LogRow>
              ))}
            </ul>
          )}

          {!finished && (
            <WorkingRow label={plan.workingLabel} reduce={reduce} />
          )}

          {finished && (
            <div className="mt-1 flex items-center gap-2 border-t border-separator-border pt-2">
              <AgentThinking
                variant={plan.mode === "research" ? "infinity" : "stars"}
                tone="accent"
                label={plan.mode === "research" ? "Deep research complete" : "Thinking complete"}
                shimmer={false}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
