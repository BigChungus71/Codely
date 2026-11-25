import type { ChatTransport, UIMessage, UIMessageChunk } from "ai";

import {
  classifyApiResearchPrompt,
  type ChatMessageMetadata,
  type ResearchLogPartData,
  type ResearchStep,
} from "@/components/application/agent-chat/codely-research-plan";
import { pickDemoAnswer } from "@/components/application/agent-chat/demo-answers";

type DemoUIDataTypes = {
  research: ResearchLogPartData;
};

type DemoChunk = UIMessageChunk<ChatMessageMetadata, DemoUIDataTypes>;

/** Initial beat before first text when no multi-step research plan runs. */
const THINK_MS = 1050;
/** Delay between research steps in demo mode. */
const STEP_MS = 460;
/** Per word. Smooth streaming pace. */
const WORD_MS = 26;

const wait = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });

function lastUserText(messages: UIMessage[]): string {
  const last = [...messages].reverse().find((message) => message.role === "user");
  return (
    last?.parts
      .filter((part): part is { type: "text"; text: string } => part.type === "text")
      .map((part) => part.text)
      .join("\n") ?? ""
  );
}

/**
 * Local scripted transport so the Q&A sets and chat prompts stream seamlessly
 * even when no external model key is configured, emitting the exact same
 * `data-research` and `messageMetadata` completion contract as `/api/chat`.
 */
export class DemoTransport implements ChatTransport<UIMessage> {
  async sendMessages({
    messages,
    abortSignal,
  }: {
    messages: UIMessage[];
    abortSignal: AbortSignal | undefined;
  }): Promise<ReadableStream<UIMessageChunk>> {
    const prompt = lastUserText(messages);
    const reply = pickDemoAnswer(prompt);
    const plan = classifyApiResearchPrompt(prompt);
    const startedAt = Date.now();
    const id = `codely-${startedAt}`;
    const researchId = `research-${startedAt}`;

    return new ReadableStream<UIMessageChunk>({
      async start(controller) {
        const safeEnqueue = (chunk: DemoChunk) => {
          try {
            controller.enqueue(chunk as UIMessageChunk);
          } catch {
            // Stream was already cancelled/closed by the consumer.
          }
        };
        const safeClose = () => {
          try {
            controller.close();
          } catch {
            // Stream was already closed/cancelled.
          }
        };

        const revealedSteps: ResearchStep[] = [];
        let researchStarted = false;

        const emitResearch = (
          status: ResearchLogPartData["status"],
          steps: ResearchStep[],
          completedAt?: number,
        ) => {
          if (!plan) return;
          researchStarted = true;
          safeEnqueue({
            type: "data-research",
            id: researchId,
            data: {
              mode: plan.mode,
              headline: plan.headline,
              workingLabel: plan.workingLabel,
              status,
              steps,
              startedAt,
              ...(completedAt !== undefined
                ? { completedAt, durationMs: Math.max(0, completedAt - startedAt) }
                : {}),
            },
          });
        };

        try {
          safeEnqueue({
            type: "start",
            messageMetadata: { startedAt, status: "streaming" },
          });
          safeEnqueue({ type: "start-step" });

          if (plan) {
            emitResearch("running", []);
            await wait(160, abortSignal);
            for (const step of plan.steps) {
              revealedSteps.push({ ...step, status: "running" });
              for (let i = 0; i < revealedSteps.length - 1; i++) {
                revealedSteps[i] = { ...revealedSteps[i], status: "done" };
              }
              emitResearch("running", [...revealedSteps]);
              await wait(STEP_MS, abortSignal);
            }
          } else {
            await wait(THINK_MS, abortSignal);
          }

          safeEnqueue({ type: "text-start", id });
          const words = reply.split(/(?<=\s)/);
          for (const word of words) {
            await wait(WORD_MS, abortSignal);
            safeEnqueue({ type: "text-delta", id, delta: word });
          }
          safeEnqueue({ type: "text-end", id });

          const completedAt = Date.now();
          const durationMs = Math.max(0, completedAt - startedAt);
          if (plan) {
            emitResearch(
              "complete",
              plan.steps.map((step) => ({ ...step, status: "done" as const })),
              completedAt,
            );
          }

          safeEnqueue({ type: "finish-step" });
          safeEnqueue({
            type: "finish",
            messageMetadata: {
              startedAt,
              completedAt,
              durationMs,
              status: "complete",
            },
          });
        } catch {
          const completedAt = Date.now();
          const durationMs = Math.max(0, completedAt - startedAt);
          if (plan && researchStarted) {
            emitResearch(
              "aborted",
              revealedSteps.map((step) => ({ ...step, status: "done" as const })),
              completedAt,
            );
          }
          safeEnqueue({
            type: "message-metadata",
            messageMetadata: {
              startedAt,
              completedAt,
              durationMs,
              status: "aborted",
            },
          });
          safeEnqueue({ type: "abort" });
        } finally {
          safeClose();
        }
      },
    });
  }

  async reconnectToStream(): Promise<ReadableStream<UIMessageChunk> | null> {
    return null;
  }
}

/**
 * Routes to the live `/api/chat` transport when configured, and falls back
 * transparently to `DemoTransport` whenever `body.demo` is true OR the live
 * endpoint is unavailable (never swallowing explicit user aborts).
 */
export class SwitchingTransport implements ChatTransport<UIMessage> {
  constructor(
    private readonly live: ChatTransport<UIMessage>,
    private readonly canned: ChatTransport<UIMessage>,
  ) {}

  sendMessages: ChatTransport<UIMessage>["sendMessages"] = async (options) => {
    if (options.abortSignal?.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }
    const body = options.body as { demo?: boolean; project?: string } | undefined;
    if (body?.project) return this.live.sendMessages(options);
    const demo = Boolean(body?.demo);
    if (demo) {
      return this.canned.sendMessages(options);
    }
    try {
      return await this.live.sendMessages(options);
    } catch (error) {
      if (
        options.abortSignal?.aborted ||
        (error instanceof Error && error.name === "AbortError")
      ) {
        throw error;
      }
      return this.canned.sendMessages(options);
    }
  };

  reconnectToStream: ChatTransport<UIMessage>["reconnectToStream"] = (options) =>
    this.live.reconnectToStream(options);
}
