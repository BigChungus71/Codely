"use client";

import { useEffect, useRef, useState } from "react";
import {
  RiArrowDownSLine,
  RiCheckLine,
  RiCloseLine,
  RiErrorWarningLine,
  RiSearchLine,
  RiSparklingLine,
} from "@remixicon/react";
import {
  LogRow,
  ShimmerText,
  WorkingRow,
  useLogMotion,
  useRevealTicker,
} from "@/components/application/agent-log/agent-log";
import { AgentThinking } from "@/components/application/agent-thinking/agent-thinking";
import {
  matchResearchPlan,
  type ResearchLogPartData,
  type ResearchMode,
  type ResearchPlan,
  type ResearchStatus,
  type ResearchStep,
} from "@/components/application/agent-chat/codely-research-plan";
import { cx } from "@/utils/cx";

export {
  matchResearchPlan,
  type ResearchLogPartData,
  type ResearchMode,
  type ResearchPlan,
  type ResearchStatus,
  type ResearchStep,
};

function completeLabelFor(mode: ResearchMode, status: ResearchStatus): string {
  if (status === "error") {
    if (mode === "research") return "Deep research interrupted";
    if (mode === "building") return "Analysis interrupted";
    return "Thinking interrupted";
  }
  if (status === "aborted") {
    if (mode === "research") return "Deep research stopped";
    if (mode === "building") return "Analysis stopped";
    return "Thinking stopped";
  }
  if (mode === "research") return "Deep research complete";
  if (mode === "building") return "Analysis complete";
  return "Thinking complete";
}

/**
 * Renders Codely's structured Thinking & Deep Research trail inside an assistant
 * message using the `AgentLog` (`LogRow`, `WorkingRow`, `ShimmerText`,
 * `useRevealTicker`) and `AgentThinking` components.
 *
 * Accepts either live/persisted stream state (`data` from `data-research` chunks
 * produced by `/api/chat` and `DemoTransport`) or a static legacy `plan`.
 * In both cases, all animations and elapsed timers stop immediately when
 * analysis or research completes, stops, or errors.
 */
export function CodelyResearchLog({
  data,
  plan,
  streaming = false,
  hasError = false,
  startedAt,
  durationMs,
}: {
  data?: ResearchLogPartData;
  plan?: ResearchPlan;
  streaming?: boolean;
  hasError?: boolean;
  startedAt?: number;
  durationMs?: number;
}) {
  const reduce = useLogMotion();
  const [open, setOpen] = useState(true);

  const mode: ResearchMode = data?.mode ?? plan?.mode ?? "thinking";
  const headline = data?.headline ?? plan?.headline ?? "Structured thinking";
  const workingLabel = data?.workingLabel ?? plan?.workingLabel ?? "Thinking…";
  const allSteps = data?.steps ?? plan?.steps ?? [];

  // Fallback ticker only runs when rendered from a static `plan` while actively
  // streaming without stream-driven `data-research` chunks. Restored historical
  // messages mount already revealed (`initialRevealed: allSteps.length`).
  const isStreamDriven = data !== undefined;
  const legacyRevealed = useRevealTicker({
    total: allSteps.length,
    run: !isStreamDriven && streaming && !hasError,
    stepInterval: 480,
    startDelay: 120,
    initialRevealed: !isStreamDriven && streaming ? 0 : allSteps.length,
  });

  let status: ResearchStatus;
  if (isStreamDriven) {
    if (data.status === "running" && !streaming) {
      status = hasError ? "error" : "aborted";
    } else {
      status = data.status;
    }
  } else if (hasError) {
    status = "error";
  } else if (streaming) {
    status = "running";
  } else {
    status = "complete";
  }

  const isRunning = status === "running";
  const isComplete = status === "complete";
  const visibleSteps = isStreamDriven
    ? allSteps
    : isRunning
      ? allSteps.slice(0, legacyRevealed)
      : allSteps;

  const effectiveStartedAt = data?.startedAt ?? startedAt;
  const explicitDurationMs = data?.durationMs ?? durationMs;

  const startEpochRef = useRef<number | null>(effectiveStartedAt ?? null);
  const wasRunningRef = useRef(isRunning);
  const [fallbackDurationSeconds, setFallbackDurationSeconds] = useState<number | undefined>(() =>
    explicitDurationMs !== undefined ? Math.max(0, explicitDurationMs / 1000) : undefined,
  );

  useEffect(() => {
    if (effectiveStartedAt !== undefined) {
      startEpochRef.current = effectiveStartedAt;
    } else if (isRunning && startEpochRef.current === null) {
      startEpochRef.current = Date.now();
    }
  }, [effectiveStartedAt, isRunning]);

  useEffect(() => {
    if (explicitDurationMs !== undefined) {
      wasRunningRef.current = isRunning;
      return;
    }
    if (wasRunningRef.current && !isRunning) {
      const origin = startEpochRef.current ?? Date.now();
      const computed = Math.max(0.1, (Date.now() - origin) / 1000);
      wasRunningRef.current = false;
      const frame = window.requestAnimationFrame(() => setFallbackDurationSeconds(computed));
      return () => window.cancelAnimationFrame(frame);
    }
    wasRunningRef.current = isRunning;
  }, [isRunning, explicitDurationMs]);

  const durationSeconds =
    explicitDurationMs !== undefined
      ? Math.max(0, explicitDurationMs / 1000)
      : fallbackDurationSeconds;

  const thinkingVariant = mode === "research" ? "infinity" : "stars";
  const ModeIcon = mode === "research" ? RiSearchLine : RiSparklingLine;

  const headerSuffix = isComplete
    ? visibleSteps.length > 0
      ? `${headline} • ${visibleSteps.length} ${visibleSteps.length === 1 ? "step" : "steps"}`
      : headline
    : status === "error"
      ? `${headline} • Interrupted`
      : `${headline} • Stopped`;

  return (
    <div className="mb-2 rounded-2xl border border-border-button-default bg-background-secondary-default/70 px-3.5 py-2.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full cursor-pointer items-center justify-between gap-2 text-start"
      >
        <span className="flex items-center gap-2">
          {isComplete ? (
            <RiCheckLine className="size-4 shrink-0 text-status-lime-text" aria-hidden />
          ) : status === "error" ? (
            <RiErrorWarningLine className="size-4 shrink-0 text-text-error-primary" aria-hidden />
          ) : status === "aborted" ? (
            <RiCloseLine className="size-4 shrink-0 text-text-tertiary" aria-hidden />
          ) : (
            <ModeIcon className="size-4 shrink-0 text-accent-500" aria-hidden />
          )}
          <span className="text-body-2-medium text-text-primary">
            {isRunning ? <ShimmerText>{headline}</ShimmerText> : headerSuffix}
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
          {visibleSteps.length > 0 && (
            <ul className="flex flex-col">
              {visibleSteps.map((step, index) => (
                <LogRow
                  key={`${index}-${step.title}`}
                  first={index === 0}
                  last={index === visibleSteps.length - 1 && !isRunning}
                  reduce={reduce}
                  className="py-1"
                >
                  <div className="flex flex-col gap-0.5">
                    <span className="text-body-2-medium text-text-primary">{step.title}</span>
                    {step.detail && (
                      <span className="text-caption-1-regular text-text-tertiary">{step.detail}</span>
                    )}
                  </div>
                </LogRow>
              ))}
            </ul>
          )}

          {isRunning && (
            <WorkingRow
              label={workingLabel}
              variant={thinkingVariant}
              tone="accent"
              reduce={reduce}
              active
              startedAt={effectiveStartedAt}
            />
          )}

          {!isRunning && (
            <div className="mt-1 flex items-center gap-2 border-t border-separator-border pt-2">
              <AgentThinking
                variant={thinkingVariant}
                tone={isComplete ? "accent" : "subtle"}
                label={completeLabelFor(mode, status)}
                active={false}
                shimmer={false}
                showTimer={durationSeconds !== undefined}
                durationSeconds={durationSeconds}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
