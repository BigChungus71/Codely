"use client";

import { useTemplateCopy } from "@/components/foundations/template-copy/template-copy";

import { RiCheckLine, RiFileCopyLine, RiVolumeMuteLine, RiVolumeUpLine } from "@remixicon/react";
import type { UIMessage } from "ai";
import { motion, useReducedMotion } from "motion/react";
import { memo, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import {
  CodelyResearchLog,
  matchResearchPlan,
  type ResearchLogPartData,
  type ResearchStep,
} from "@/components/application/agent-chat/codely-research-log";
import type { ChatMessageMetadata } from "@/components/application/agent-chat/codely-research-plan";
import { Logo } from "@/components/foundations/brand/logo";
import { cx } from "@/utils/cx";

/**
 * One turn in the transcript.
 *
 * Assistant replies arrive a paragraph at a time, each softening in out of a
 * blur as it first appears and then only growing, so nothing already on screen
 * ever re-animates.
 *
 * The action row is deliberately mounted at all times and revealed on hover or
 * focus. Rendering it only on hover would make it unreachable by keyboard and
 * would shift the layout as the pointer moves across the transcript.
 */

export interface AgentMessageProps {
  role: string;
  text: string;
  /** Full AI SDK parts array, carrying live/persisted `data-research` and `reasoning` parts. */
  parts?: UIMessage["parts"];
  /** Optional message metadata emitted by `/api/chat` or `DemoTransport`. */
  metadata?: unknown;
  /** The user prompt this assistant message answers, used as fallback for legacy threads. */
  userPrompt?: string;
  /** True while this message is still being streamed. */
  streaming?: boolean;
  /** True if the request terminated with an error. */
  hasError?: boolean;
  /** When the message first appeared, for the hover timestamp. */
  at?: number;
}

function isResearchData(value: unknown): value is ResearchLogPartData {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<ResearchLogPartData>;
  return (
    typeof candidate.mode === "string" &&
    typeof candidate.headline === "string" &&
    typeof candidate.status === "string" &&
    Array.isArray(candidate.steps)
  );
}

function findResearchPartData(parts: UIMessage["parts"] | undefined): ResearchLogPartData | undefined {
  if (!parts) return undefined;
  for (let i = parts.length - 1; i >= 0; i--) {
    const part = parts[i];
    if (part.type === "data-research" && "data" in part && isResearchData(part.data)) {
      return part.data;
    }
  }
  return undefined;
}

function parseMetadata(metadata: unknown): ChatMessageMetadata | undefined {
  if (typeof metadata !== "object" || metadata === null) return undefined;
  return metadata as ChatMessageMetadata;
}

function reasoningStepsFromText(reasoning: string): ResearchStep[] {
  const chunks = reasoning
    .split(/\n{2,}/)
    .map((chunk) => chunk.trim())
    .filter(Boolean)
    .slice(-4);
  if (chunks.length === 0) return [];
  return chunks.map((chunk, index) => {
    const firstBreak = chunk.indexOf("\n");
    const firstLine = (firstBreak === -1 ? chunk : chunk.slice(0, firstBreak)).trim();
    const rest = firstBreak === -1 ? "" : chunk.slice(firstBreak + 1).trim();
    const title =
      firstLine.length > 72 ? `Thinking step ${index + 1}` : firstLine || `Thinking step ${index + 1}`;
    const detailSource = rest || (firstLine.length > 72 ? firstLine : "");
    const detail = detailSource.length > 180 ? `${detailSource.slice(0, 177)}…` : detailSource;
    return { title, detail };
  });
}

export function AgentMessage({
  role,
  text,
  parts,
  metadata: rawMetadata,
  userPrompt,
  streaming = false,
  hasError = false,
  at,
}: AgentMessageProps) {
  const localize = useTemplateCopy();
  const metadata = useMemo(() => parseMetadata(rawMetadata), [rawMetadata]);
  const streamedResearch = useMemo(() => findResearchPartData(parts), [parts]);

  const reasoningInfo = useMemo(() => {
    if (!parts) return { text: "", active: false };
    const reasoningParts = parts.filter(
      (part): part is Extract<UIMessage["parts"][number], { type: "reasoning" }> =>
        part.type === "reasoning",
    );
    return {
      text: reasoningParts.map((part) => part.text).join("\n\n").trim(),
      active: reasoningParts.some((part) => part.state === "streaming"),
    };
  }, [parts]);

  const legacyPlan = useMemo(
    () => (role === "assistant" && !streamedResearch && !reasoningInfo.text ? matchResearchPlan(userPrompt) : null),
    [role, streamedResearch, reasoningInfo.text, userPrompt],
  );

  const reasoningData: ResearchLogPartData | undefined = useMemo(() => {
    if (streamedResearch || !reasoningInfo.text) return undefined;
    const status = hasError
      ? "error"
      : streaming || reasoningInfo.active
        ? "running"
        : metadata?.status === "aborted"
          ? "aborted"
          : "complete";
    return {
      mode: "thinking",
      headline: "Model thinking",
      workingLabel: "Thinking…",
      status,
      steps: reasoningStepsFromText(reasoningInfo.text),
      startedAt: metadata?.startedAt ?? at ?? 0,
      completedAt: metadata?.completedAt,
      durationMs: metadata?.durationMs,
    };
  }, [streamedResearch, reasoningInfo.text, reasoningInfo.active, hasError, streaming, metadata, at]);

  const researchData = streamedResearch ?? reasoningData;

  if (role === "user") {
    if (!text) return null;
    return localize((
      <div className="ms-auto flex max-w-[78%] flex-col items-end gap-1">
        <span className="px-1 text-caption-1-medium text-text-tertiary">You</span>
        <p className="w-fit rounded-2xl rounded-se-sm bg-accent-500 px-3.5 py-2.5 text-start text-body-regular break-words whitespace-pre-wrap text-white shadow-xs">
          {text}
        </p>
      </div>
    ));
  }

  if (!text && !researchData && !legacyPlan) return null;

  return localize((
    <div className="group/message flex items-start gap-2.5 px-1">
      <Logo size={24} className="mt-1" />
      <div className="flex min-w-0 max-w-[85%] flex-col gap-1.5">
        <div className="flex items-center gap-1.5">
          <span className="text-caption-1-semibold text-text-primary">Codely</span>
        </div>
        {(researchData || legacyPlan) && (
          <CodelyResearchLog
            data={researchData}
            plan={legacyPlan ?? undefined}
            streaming={streaming}
            hasError={hasError}
            startedAt={metadata?.startedAt ?? at}
            durationMs={metadata?.durationMs}
          />
        )}
        {text && (
          <div className="rounded-2xl rounded-ss-sm border border-border-button-default bg-background-primary-default px-4 py-3 shadow-xs">
            <StreamedText text={text} />
          </div>
        )}
        {text && <MessageActions text={text} at={at} hidden={streaming} />}
      </div>
    </div>
  ));
}

/**
 * Paragraphs, each softening in once as it first appears.
 */
export function StreamedText({ text, paragraphs = false }: { text: string; paragraphs?: boolean }) {
  const localize = useTemplateCopy();
  const reduceMotion = useReducedMotion();
  const lines = useMemo(
    () => text.split(paragraphs ? /\n\s*\n/ : "\n").filter((line) => line.trim() !== ""),
    [text, paragraphs],
  );

  return localize((
    <div className="flex flex-col gap-3">
      {lines.map((line, index) => (
        <Line key={index} text={line} animate={!reduceMotion} />
      ))}
    </div>
  ));
}

const LINE_HIDDEN = { opacity: 0, filter: "blur(5px)", y: 4 };
const LINE_SHOWN = { opacity: 1, filter: "blur(0px)", y: 0 };
const LINE_TRANSITION = { duration: 0.42, ease: [0.22, 0.61, 0.36, 1] } as const;

const Line = memo(function Line({ text, animate }: { text: string; animate: boolean }) {
  return (
    <motion.p
      initial={animate ? LINE_HIDDEN : false}
      animate={LINE_SHOWN}
      transition={LINE_TRANSITION}
      className="text-body-regular break-words text-text-primary"
    >
      {text}
    </motion.p>
  );
});

function MessageActions({ text, at, hidden }: { text: string; at?: number; hidden: boolean }) {
  const localize = useTemplateCopy();
  const [copied, setCopied] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const speakingRef = useRef(false);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(timer);
  }, [copied]);

  // Only cancel speech on unmount if this message instance started speaking.
  useEffect(() => {
    return () => {
      if (speakingRef.current && typeof window !== "undefined") {
        window.speechSynthesis?.cancel();
        speakingRef.current = false;
      }
    };
  }, []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      // Clipboard access can be refused (insecure origin, denied permission).
    }
  };

  const toggleSpeech = () => {
    const synth = typeof window === "undefined" ? undefined : window.speechSynthesis;
    if (!synth) return;
    if (speaking) {
      synth.cancel();
      speakingRef.current = false;
      setSpeaking(false);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onend = () => {
      speakingRef.current = false;
      setSpeaking(false);
    };
    utterance.onerror = () => {
      speakingRef.current = false;
      setSpeaking(false);
    };
    synth.cancel();
    synth.speak(utterance);
    speakingRef.current = true;
    setSpeaking(true);
  };

  return localize((
    <div
      className={cx(
        "flex items-center gap-1 transition-opacity duration-150",
        hidden
          ? "pointer-events-none opacity-0"
          : "opacity-0 group-hover/message:opacity-100 focus-within:opacity-100",
      )}
    >
      <ActionButton label={copied ? "Copied" : "Copy message"} onClick={copy}>
        {copied ? <RiCheckLine className="size-4" aria-hidden /> : <RiFileCopyLine className="size-4" aria-hidden />}
      </ActionButton>

      <ActionButton label={speaking ? "Stop reading aloud" : "Read aloud"} onClick={toggleSpeech}>
        {speaking ? (
          <RiVolumeMuteLine className="size-4" aria-hidden />
        ) : (
          <RiVolumeUpLine className="size-4" aria-hidden />
        )}
      </ActionButton>

      {at ? (
        <time dateTime={new Date(at).toISOString()} className="ms-1 text-caption-1-regular text-text-tertiary">
          {formatAgo(at)}
        </time>
      ) : null}
    </div>
  ));
}

function ActionButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  const localize = useTemplateCopy();
  return localize((
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="flex size-7 cursor-pointer items-center justify-center rounded-md text-foreground-icon-tertiary transition-colors hover:bg-background-primary-default hover:text-foreground-icon-secondary focus-visible:ring-2 focus-visible:ring-border-focus-ring focus-visible:outline-none"
    >
      {children}
    </button>
  ));
}

/** "just now", "3 minutes ago", "2 hours ago" — matching how the rail reads. */
function formatAgo(at: number) {
  const seconds = Math.max(0, Math.round((Date.now() - at) / 1000));
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}
