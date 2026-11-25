import {
  convertToModelMessages,
  createUIMessageStream,
  createUIMessageStreamResponse,
  safeValidateUIMessages,
  smoothStream,
  streamText,
  toUIMessageStream,
  type ToolSet,
  type UIMessage,
  type UIMessageChunk,
} from "ai";

import { resolveProvider, type Provider } from "@/app/api/_lib/ai-provider";
import {
  classifyApiResearchPrompt,
  type ChatMessageMetadata,
  type ResearchLogPartData,
  type ResearchStatus,
  type ResearchStep,
} from "@/components/application/agent-chat/codely-research-plan";

/** Bumped when the contract below changes in a way templates can depend on. */
const RUNTIME_CONTRACT = 1;

/** Streaming replies outlive the default budget on longer answers. */
export const maxDuration = 30;

type CodelyUIDataTypes = {
  research: ResearchLogPartData;
};

type CodelyUIMessage = UIMessage<ChatMessageMetadata, CodelyUIDataTypes>;
type CodelyChunk = UIMessageChunk<ChatMessageMetadata, CodelyUIDataTypes>;

function lastUserPrompt(messages: UIMessage[]): string {
  const lastUser = [...messages].reverse().find((message) => message.role === "user");
  if (!lastUser) return "";
  return lastUser.parts
    .filter((part): part is { type: "text"; text: string } => part.type === "text")
    .map((part) => part.text)
    .join("\n")
    .trim();
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function summarizeReasoning(reasoning: string): ResearchStep | null {
  const trimmed = reasoning.trim();
  if (!trimmed) return null;
  const lines = trimmed
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  const lastLine = lines[lines.length - 1] ?? trimmed;
  const excerpt = lastLine.length > 160 ? `${lastLine.slice(0, 157)}…` : lastLine;
  return {
    title: "Model reasoning trace",
    detail: excerpt,
  };
}

/**
 * Facts about Codely so live API answers stay grounded in what exists in the app.
 */
function systemPrompt(provider: Provider) {
  return [
    "You are Codely — an AI-powered code security scanner and architecture reviewer (\"crush every bug like a pro\").",
    "",
    "What this app provides, for when you are asked:",
    `- Live AI streaming powered by the configured provider key (${provider.label}, model ${provider.modelId}) via the /api/chat Next.js App Router endpoint and Vercel AI SDK.`,
    "- Structured Thinking (`AgentThinking`, `ComposerLoader`) and Deep Research (`AgentLog` / `CodelyResearchLog`) trails that stream progress steps and stop animating/timing as soon as analysis or research completes.",
    "- Code Scanner (`/scanner`) browses configured local workspaces and runs deterministic Python Semgrep with source-linked findings.",
    "- Dashboard (`/dashboard`) displays illustrative analytics.",
    "- Components & Blocks catalogue (`/components`) built with BoardUI source-owned components, React, and Tailwind CSS v4, with browser-local chat history.",
    "",
    "Answer concisely in clear, practical engineering language. When asked to audit, scan, compare architectures, or perform deep research, provide structured, actionable findings. Use markdown only when it genuinely helps.",
  ].join("\n");
}

/**
 * Config probe. The UI calls this on mount so a deployment with no key yet can
 * stream cleanly in local demo mode instead of failing on submit.
 */
export async function GET() {
  const { provider, reason } = resolveProvider();
  return Response.json({
    configured: provider !== null,
    provider: provider?.id ?? null,
    providerLabel: provider?.label ?? null,
    model: provider?.modelId ?? null,
    reason: reason ?? null,
    contract: RUNTIME_CONTRACT,
  });
}

export async function POST(req: Request) {
  const badBody = Response.json(
    { error: "invalid_body", message: "Expected JSON with a messages array." },
    { status: 400 },
  );

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return badBody;
  }

  const submitted = (body as { messages?: unknown } | null)?.messages;
  if (!Array.isArray(submitted)) return badBody;

  const validated = await safeValidateUIMessages({ messages: submitted });
  if (!validated.success) {
    return Response.json(
      { error: "invalid_messages", message: validated.error.message },
      { status: 400 },
    );
  }

  const project = (body as { project?: unknown } | null)?.project;
  if (typeof project === "string" && project.length > 0) {
    const question = validated.data.findLast((message) => message.role === "user")?.parts
      .flatMap((part) => part.type === "text" ? [part.text] : []).join("\n") ?? "";
    if (!question.trim() || question.length > 4000) {
      return Response.json({ message: "Enter a repository question of up to 4,000 characters." }, { status: 400 });
    }
    const base = process.env.CODELY_BACKEND_URL ?? "http://127.0.0.1:8000";
    try {
      const response = await fetch(new URL(`/api/projects/${encodeURIComponent(project)}/design-question`, base), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, constraints: asRecord(body).constraints ?? "", architecture_advice: asRecord(body).architecture_advice === true }),
        signal: AbortSignal.any([req.signal, AbortSignal.timeout(120_000)]),
      });
      const result = await response.json();
      if (!response.ok) {
        const message = typeof result.detail === "string" ? result.detail : "Repository AI request failed.";
        return Response.json({ message }, { status: response.status });
      }
      const sources = result.sources.map((source: { file: string; start_line: number; end_line: number }) =>
        `- ${source.file}:${source.start_line}–${source.end_line}`).join("\n");
      const text = `${result.answer}\n\nSources\n${sources}`;
      const stream = createUIMessageStream({
        execute({ writer }) {
          const id = "repository-answer";
          writer.write({ type: "start" });
          writer.write({ type: "text-start", id });
          writer.write({ type: "text-delta", id, delta: text });
          writer.write({ type: "text-end", id });
          writer.write({ type: "finish" });
        },
      });
      return createUIMessageStreamResponse({ stream });
    } catch {
      return Response.json({ message: "The repository AI backend could not be reached." }, { status: 502 });
    }
  }

  const { provider, reason } = resolveProvider();

  if (!provider) {
    return Response.json({ error: "missing_api_key", message: reason }, { status: 503 });
  }

  const promptText = lastUserPrompt(validated.data);
  const initialPlan = classifyApiResearchPrompt(promptText);
  const startedAt = Date.now();
  const researchId = `research-${startedAt}`;

  const result = streamText({
    model: provider.model,
    system: systemPrompt(provider),
    messages: await convertToModelMessages(validated.data),
    experimental_transform: smoothStream({ delayInMs: 18, chunking: "word" }),
    abortSignal: req.signal,
  });

  const baseStream = toUIMessageStream<ToolSet, CodelyUIMessage>({
    stream: result.stream,
    sendReasoning: true,
  });

  let researchActive = initialPlan !== null;
  let planMode = initialPlan?.mode ?? "thinking";
  let planHeadline = initialPlan?.headline ?? "Structured thinking";
  let planWorkingLabel = initialPlan?.workingLabel ?? "Thinking…";
  let reasoningBuffer = "";
  let lastReasoningEmitAt = 0;
  let phase: "thinking" | "synthesizing" | "done" = "thinking";
  let hasTerminalChunk = false;

  const buildSteps = (currentPhase: "thinking" | "synthesizing" | "done"): ResearchStep[] => {
    const baseSteps = initialPlan?.steps ?? [];
    const reasoningStep = summarizeReasoning(reasoningBuffer);

    let steps: ResearchStep[];
    if (baseSteps.length > 0) {
      if (currentPhase === "thinking") {
        steps = baseSteps.slice(0, 1).map((step) => ({ ...step, status: "running" as const }));
      } else if (currentPhase === "synthesizing") {
        steps = baseSteps.map((step, index) => ({
          ...step,
          status: index < baseSteps.length - 1 ? ("done" as const) : ("running" as const),
        }));
      } else {
        steps = baseSteps.map((step) => ({ ...step, status: "done" as const }));
      }
    } else {
      steps = [];
    }

    if (reasoningStep) {
      steps.push({
        ...reasoningStep,
        status: currentPhase === "done" ? "done" : "running",
      });
    }

    return steps;
  };

  const buildResearchPayload = (
    status: ResearchStatus,
    currentPhase: "thinking" | "synthesizing" | "done",
    completedAt?: number,
  ): CodelyChunk => ({
    type: "data-research",
    id: researchId,
    data: {
      mode: planMode,
      headline: planHeadline,
      workingLabel:
        currentPhase === "synthesizing"
          ? planMode === "research"
            ? "Synthesizing research findings…"
            : "Composing response…"
          : planWorkingLabel,
      status,
      steps: buildSteps(currentPhase),
      startedAt,
      ...(completedAt !== undefined
        ? { completedAt, durationMs: Math.max(0, completedAt - startedAt) }
        : {}),
    },
  });

  const instrumentedStream = baseStream.pipeThrough(
    new TransformStream<CodelyChunk, CodelyChunk>({
      transform(chunk, controller) {
        if (chunk.type === "start") {
          controller.enqueue({
            ...chunk,
            messageMetadata: {
              ...asRecord(chunk.messageMetadata),
              startedAt,
              status: "streaming",
            },
          });
          if (researchActive) {
            controller.enqueue(buildResearchPayload("running", "thinking"));
          }
          return;
        }

        if (chunk.type === "reasoning-start") {
          researchActive = true;
          controller.enqueue(buildResearchPayload("running", "thinking"));
          controller.enqueue(chunk);
          return;
        }

        if (chunk.type === "reasoning-delta") {
          reasoningBuffer += chunk.delta;
          const now = Date.now();
          if (now - lastReasoningEmitAt >= 150) {
            lastReasoningEmitAt = now;
            controller.enqueue(buildResearchPayload("running", phase));
          }
          controller.enqueue(chunk);
          return;
        }

        if (chunk.type === "reasoning-end") {
          if (researchActive) {
            controller.enqueue(buildResearchPayload("running", phase));
          }
          controller.enqueue(chunk);
          return;
        }

        if (chunk.type === "text-start") {
          phase = "synthesizing";
          if (researchActive) {
            controller.enqueue(buildResearchPayload("running", "synthesizing"));
          }
          controller.enqueue(chunk);
          return;
        }

        if (chunk.type === "finish") {
          hasTerminalChunk = true;
          phase = "done";
          const completedAt = Date.now();
          const durationMs = Math.max(0, completedAt - startedAt);
          if (researchActive) {
            controller.enqueue(buildResearchPayload("complete", "done", completedAt));
          }
          controller.enqueue({
            ...chunk,
            messageMetadata: {
              ...asRecord(chunk.messageMetadata),
              startedAt,
              completedAt,
              durationMs,
              status: "complete",
            },
          });
          return;
        }

        if (chunk.type === "abort" || chunk.type === "error") {
          hasTerminalChunk = true;
          phase = "done";
          const terminalStatus = chunk.type === "abort" ? "aborted" : "error";
          const completedAt = Date.now();
          const durationMs = Math.max(0, completedAt - startedAt);
          if (researchActive) {
            controller.enqueue(buildResearchPayload(terminalStatus, "done", completedAt));
          }
          controller.enqueue({
            type: "message-metadata",
            messageMetadata: {
              startedAt,
              completedAt,
              durationMs,
              status: terminalStatus,
            },
          });
          controller.enqueue(chunk);
          return;
        }

        controller.enqueue(chunk);
      },
      flush(controller) {
        if (hasTerminalChunk) return;
        const completedAt = Date.now();
        const durationMs = Math.max(0, completedAt - startedAt);
        const terminalStatus = req.signal.aborted ? "aborted" : "complete";
        if (researchActive) {
          controller.enqueue(buildResearchPayload(terminalStatus, "done", completedAt));
        }
        controller.enqueue({
          type: "message-metadata",
          messageMetadata: {
            startedAt,
            completedAt,
            durationMs,
            status: terminalStatus,
          },
        });
      },
    }),
  );

  return createUIMessageStreamResponse({
    stream: instrumentedStream,
  });
}
