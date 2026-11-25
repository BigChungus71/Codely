import type { ChatTransport, UIMessage, UIMessageChunk } from "ai";

import { pickDemoAnswer } from "@/components/application/agent-chat/demo-answers";

/** A beat before the first word, so the thinking indicator & rim loader read clearly. */
const THINK_MS = 1050;
/** Per word. Smooth streaming pace. */
const WORD_MS = 26;

const wait = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    });
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
 * Local scripted transport so the three Q&A sets and chat prompts stream
 * seamlessly even when no external model key is configured.
 */
export class DemoTransport implements ChatTransport<UIMessage> {
  async sendMessages({
    messages,
    abortSignal,
  }: {
    messages: UIMessage[];
    abortSignal: AbortSignal | undefined;
  }): Promise<ReadableStream<UIMessageChunk>> {
    const reply = pickDemoAnswer(lastUserText(messages));
    const id = `codely-${Date.now()}`;
    return new ReadableStream<UIMessageChunk>({
      async start(controller) {
        try {
          controller.enqueue({ type: "start" });
          controller.enqueue({ type: "start-step" });
          await wait(THINK_MS, abortSignal);
          controller.enqueue({ type: "text-start", id });
          const words = reply.split(/(?<=\s)/);
          for (const word of words) {
            await wait(WORD_MS, abortSignal);
            controller.enqueue({ type: "text-delta", id, delta: word });
          }
          controller.enqueue({ type: "text-end", id });
          controller.enqueue({ type: "finish-step" });
          controller.enqueue({ type: "finish" });
        } catch {
          controller.enqueue({ type: "abort" });
        } finally {
          controller.close();
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
 * endpoint fails (e.g. unconfigured key), so queries never hit an error wall.
 */
export class SwitchingTransport implements ChatTransport<UIMessage> {
  constructor(
    private readonly live: ChatTransport<UIMessage>,
    private readonly canned: ChatTransport<UIMessage>,
  ) {}

  sendMessages: ChatTransport<UIMessage>["sendMessages"] = async (options) => {
    const demo = Boolean((options.body as { demo?: boolean } | undefined)?.demo);
    if (demo) {
      return this.canned.sendMessages(options);
    }
    try {
      return await this.live.sendMessages(options);
    } catch {
      return this.canned.sendMessages(options);
    }
  };

  reconnectToStream: ChatTransport<UIMessage>["reconnectToStream"] = (options) =>
    this.live.reconnectToStream(options);
}
