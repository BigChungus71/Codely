"use client";

import { useDirection } from "@/components/foundations/direction/direction";
import { useTemplateCopy } from "@/components/foundations/template-copy/template-copy";

import { useChat } from "@ai-sdk/react";
import { RiCloseLine, RiMenuLine } from "@remixicon/react";
import { DefaultChatTransport, type UIMessage } from "ai";

import { DemoTransport, SwitchingTransport } from "@/components/application/agent-chat/demo-transport";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AgentChatActions } from "@/components/application/agent-chat/agent-chat-actions";
import {
  SidebarChatHistory,
  type ChatThreadSummary,
} from "@/components/application/agent-chat/agent-chat-history";
import { AgentMessage } from "@/components/application/agent-chat/agent-chat-message";
import { AgentComposer } from "@/components/application/agent-chat/agent-composer";
import { AgentThinking } from "@/components/application/agent-thinking/agent-thinking";
import { starterNav, useStarterBase } from "@/components/application/app-shell/app-shell";
import { DashboardSidebar } from "@/components/application/dashboard/dashboard-sidebar";
import { IconButton } from "@/components/base/buttons/icon-button";
import { Logo } from "@/components/foundations/brand/logo";
import { cx } from "@/utils/cx";

/**
 * Codely — AI-powered code security scanner and architecture reviewer.
 * "crush every bug like a pro."
 *
 * Layout: left sidebar (260 px) + full-width chat surface. No right column.
 * The chat surface is the entire product canvas.
 */

const ENDPOINT = "/api/chat";
const STORAGE_KEY = "codely:agent-chat-threads";
/** Enough history to be useful without letting localStorage grow unbounded. */
const MAX_THREADS = 30;

interface StoredThread extends ChatThreadSummary {
  messages: UIMessage[];
  /** Message id -> when it arrived, so a restored chat shows real times
   *  rather than reporting every message as having just landed. */
  messageAt: Record<string, number>;
}

export function AgentChat({
  className,
  contained = false,
}: {
  className?: string;
  /** Docs preview mode: fill the preview frame's height instead of the
   *  viewport, and keep the phone nav drawer inside the frame. */
  contained?: boolean;
}) {
  const localize = useTemplateCopy();
  const direction = useDirection();
  const [input, setInput] = useState("");
  const [navOpen, setNavOpen] = useState(false);
  const starterBase = useStarterBase();
  const navItems = starterNav(starterBase);
  const [threads, setThreads] = useState<StoredThread[]>([]);
  const [activeId, setActiveId] = useState("");
  const [activeUpdatedAt, setActiveUpdatedAt] = useState(0);
  const [activeTitle, setActiveTitle] = useState<string | null>(null);
  const [activeUnread, setActiveUnread] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLSpanElement>(null);
  const columnRef = useRef<HTMLDivElement>(null);
  const taglineTimerRef = useRef<number | null>(null);
  const [messageAt, setMessageAt] = useState<Record<string, number>>({});
  const [scrollTop, setScrollTop] = useState(0);
  const [canClash, setCanClash] = useState(false);
  const [restored, setRestored] = useState(false);
  /** True when no live provider key is present so queries stream via DemoTransport. */
  const [demoMode, setDemoMode] = useState(true);
  const [providerInfo, setProviderInfo] = useState<{
    model: string | null;
    providerLabel: string | null;
  }>({ model: null, providerLabel: null });
  /** Index into WELCOME_TAGLINES; increments every time New Chat is clicked. */
  const [taglineIndex, setTaglineIndex] = useState(0);
  /** Brief shimmer across the middle tagline when New Chat is clicked. */
  const [taglineShimmer, setTaglineShimmer] = useState(false);

  /** Codely routes live when configured, with transparent DemoTransport fallback. */
  const [transport] = useState(
    () => new SwitchingTransport(new DefaultChatTransport({ api: ENDPOINT }), new DemoTransport()),
  );

  // Silent probe: if `/api/chat` has a configured key, use live streaming; otherwise stay in local stream mode.
  useEffect(() => {
    let cancelled = false;
    fetch(ENDPOINT, { method: "GET" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { configured?: boolean; model?: string | null; providerLabel?: string | null } | null) => {
        if (!cancelled && data && data.configured === true) {
          setDemoMode(false);
          setProviderInfo({
            model: data.model ?? null,
            providerLabel: data.providerLabel ?? null,
          });
        }
      })
      .catch(() => {
        // Keep local stream mode on probe failure.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    return () => {
      if (taglineTimerRef.current !== null) {
        window.clearTimeout(taglineTimerRef.current);
      }
    };
  }, []);

  const { messages, sendMessage, setMessages, status, stop, error } = useChat({
    transport,
  });

  const busy = status === "submitted" || status === "streaming";

  const hasAssistantOutput = useMemo(() => {
    const last = messages[messages.length - 1];
    if (!last || last.role !== "assistant") return false;
    return last.parts.some(
      (part) =>
        (part.type === "text" && part.text.trim().length > 0) ||
        (part.type === "reasoning" && part.text.trim().length > 0) ||
        part.type === "data-research",
    );
  }, [messages]);
  const showThinking = busy && !hasAssistantOutput;

  const transcript = useMemo(
    () =>
      messages
        .map((message) => `${message.role === "user" ? "You" : "Codely"}: ${messageText(message)}`)
        .filter((line) => !line.endsWith(": "))
        .join("\n\n"),
    [messages],
  );

  // Restore history after mount.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- restoring from localStorage after mount; there is no render-time source for it
    setActiveId(newThreadId());
    setThreads(orderThreads(readThreads()));
    setRestored(true);
  }, []);

  const liveThread: StoredThread | null = useMemo(
    () =>
      activeId && messages.length > 0
        ? {
            id: activeId,
            title: activeTitle ?? deriveTitle(messages),
            updatedAt: activeUpdatedAt,
            unread: activeUnread,
            messages,
            messageAt,
          }
        : null,
    [activeId, messages, activeUpdatedAt, activeUnread, messageAt, activeTitle],
  );

  const allThreads = useMemo(() => {
    const rest = threads.filter((thread) => thread.id !== activeId);
    return orderThreads(liveThread ? [liveThread, ...rest] : rest);
  }, [liveThread, threads, activeId]);

  useEffect(() => {
    if (!restored || busy) return;
    writeThreads(allThreads);
  }, [restored, busy, allThreads]);

  useEffect(() => {
    const unseen = messages.filter((message) => messageAt[message.id] === undefined);
    if (unseen.length === 0) return;
    const now = Date.now();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- arrival time is an external event, not derivable from render state
    setMessageAt((prev) => {
      const next = { ...prev };
      for (const message of unseen) next[message.id] = now;
      return next;
    });
  }, [messages, messageAt]);

  // Measure whether the floating title overlaps the message column.
  useEffect(() => {
    const measure = () => {
      const title = titleRef.current?.getBoundingClientRect();
      const column = columnRef.current?.getBoundingClientRect();
      if (!title || !column) return;
      setCanClash(direction === "rtl" ? title.left - 16 < column.right : title.right + 16 > column.left);
    };
    measure();
    const observer = new ResizeObserver(measure);
    if (scrollRef.current) observer.observe(scrollRef.current);
    return () => observer.disconnect();
  }, [messages.length, activeId, activeTitle, direction]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  const submit = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setActiveUpdatedAt(Date.now());
    setActiveUnread(false);
    sendMessage({ text: trimmed }, { body: { demo: demoMode } });
    setInput("");
  };

  const keepLiveThread = useCallback(() => {
    if (!liveThread) return;
    setThreads((prev) =>
      orderThreads([liveThread, ...prev.filter((thread) => thread.id !== liveThread.id)]),
    );
  }, [liveThread]);

  const startNewChat = useCallback(() => {
    if (busy) return;
    keepLiveThread();
    setActiveId(newThreadId());
    setActiveUpdatedAt(0);
    setActiveTitle(null);
    setActiveUnread(false);
    setScrollTop(0);
    setMessageAt({});
    setMessages([]);
    setInput("");
    setTaglineIndex((prev) => (prev + 1) % WELCOME_TAGLINES.length);
    setTaglineShimmer(true);
    if (taglineTimerRef.current !== null) window.clearTimeout(taglineTimerRef.current);
    taglineTimerRef.current = window.setTimeout(() => {
      taglineTimerRef.current = null;
      setTaglineShimmer(false);
    }, 1100);
  }, [busy, keepLiveThread, setMessages]);

  const renameThread = useCallback(
    (id: string, title: string) => {
      if (id === activeId) setActiveTitle(title);
      setThreads((prev) =>
        prev.map((thread) => (thread.id === id ? { ...thread, title } : thread)),
      );
    },
    [activeId],
  );

  const toggleUnread = useCallback(
    (id: string) => {
      if (id === activeId) {
        setActiveUnread((prev) => !prev);
      }
      setThreads((prev) =>
        prev.map((thread) => (thread.id === id ? { ...thread, unread: !thread.unread } : thread)),
      );
    },
    [activeId],
  );

  const deleteThread = useCallback(
    (id: string) => {
      const remaining = threads.filter((thread) => thread.id !== id);
      setThreads(remaining);
      if (id === activeId) {
        setActiveId(newThreadId());
        setActiveUpdatedAt(0);
        setActiveTitle(null);
        setActiveUnread(false);
        setScrollTop(0);
        setMessageAt({});
        setMessages([]);
        setInput("");
      }
    },
    [threads, activeId, setMessages],
  );

  const exportThreads = useCallback(() => {
    if (allThreads.length === 0) return;
    const blob = new Blob([JSON.stringify(allThreads, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "codely-chats.json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }, [allThreads]);

  const selectThread = useCallback(
    (id: string) => {
      if (busy || id === activeId) return;
      const thread = allThreads.find((candidate) => candidate.id === id);
      if (!thread) return;
      keepLiveThread();
      if (thread.unread) {
        setThreads((prev) =>
          prev.map((candidate) => (candidate.id === id ? { ...candidate, unread: false } : candidate)),
        );
      }
      setActiveId(id);
      setActiveUpdatedAt(thread.updatedAt);
      setActiveTitle(thread.title);
      setActiveUnread(false);
      setScrollTop(0);
      setMessageAt(thread.messageAt ?? {});
      setMessages(thread.messages);
      setInput("");
    },
    [busy, activeId, allThreads, keepLiveThread, setMessages],
  );

  const scrolledUnder = scrollTop > 0;
  const scrollFadeOpacity = Math.min(1, scrollTop / 24);

  const chatSidebarSlot = (
    <SidebarChatHistory
      threads={allThreads}
      activeId={activeId}
      onSelect={(id) => {
        selectThread(id);
        setNavOpen(false);
      }}
      onNewChat={() => {
        startNewChat();
        setNavOpen(false);
      }}
      onRename={renameThread}
      onToggleUnread={toggleUnread}
      onDelete={deleteThread}
      onExport={exportThreads}
      disabled={busy}
    />
  );

  return localize((
    <div
      className={cx(
        "relative flex w-full gap-4 overflow-hidden bg-background-full p-3",
        contained ? "h-[var(--template-preview-height)]" : "h-dvh",
        className,
      )}
    >
      <DashboardSidebar
        items={navItems}
        selected="chat"
        onNewChat={() => {
          startNewChat();
          setNavOpen(false);
        }}
        newChatBusy={busy}
        sidebarSlot={chatSidebarSlot}
        className="hidden lg:flex"
      />

      {/* Mobile nav drawer */}
      {navOpen && (
        <div className={cx(contained ? "absolute" : "fixed", "inset-0 z-50 flex lg:hidden")}>
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setNavOpen(false)}
            className="absolute inset-0 cursor-pointer bg-background-full/70 backdrop-blur-xs"
          />
          <div className="relative flex h-full p-3">
            <DashboardSidebar
              mobile
              items={navItems}
              selected="chat"
              onNewChat={() => {
                startNewChat();
                setNavOpen(false);
              }}
              newChatBusy={busy}
              sidebarSlot={chatSidebarSlot}
              onClose={() => setNavOpen(false)}
              className="flex"
            />
          </div>
        </div>
      )}

      {/* Full-width chatbot surface — chat history is in the left sidebar */}
      <div className="relative flex min-h-0 min-w-0 flex-1 overflow-hidden">
        <div className="relative flex h-full min-w-0 flex-1 flex-col overflow-hidden rounded-3xl bg-background-secondary-default">
          {/* Codely chatbot header */}
          <header
            className={cx(
              "absolute inset-x-0 top-0 z-20 flex h-12 items-center gap-2 border-b px-4 pt-[7px] transition-colors",
              scrolledUnder && canClash
                ? "border-separator-border bg-background-secondary-default/80 backdrop-blur-[20px]"
                : "border-transparent",
            )}
          >
            <IconButton
              icon={navOpen ? RiCloseLine : RiMenuLine}
              size="small"
              aria-label={navOpen ? "Close navigation" : "Open navigation"}
              aria-expanded={navOpen}
              onClick={() => setNavOpen((open) => !open)}
              className="lg:hidden"
            />
            {/* Title */}
            <span
              ref={titleRef}
              className="min-w-0 shrink truncate text-headline-medium text-text-primary"
            >
              {messages.length > 0 ? headerTitle(allThreads, activeId) : "Codely"}
            </span>
            <span className="hidden shrink-0 text-caption-1-regular text-text-tertiary md:block">
              crush every bug like a pro
            </span>

            <div className="ms-auto flex items-center gap-1">
              <AgentChatActions
                transcript={transcript}
                onExport={exportThreads}
                onToggleUnread={() => toggleUnread(activeId)}
                onDelete={() => deleteThread(activeId)}
                disabled={messages.length === 0}
              />
            </div>
          </header>

          {/* Transcript + composer */}
          {messages.length === 0 ? (
            <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-4">
              <div className="flex w-full max-w-2xl flex-col items-center gap-6">
                <h2
                  key={taglineIndex}
                  className={cx(
                    "text-center text-title-2-medium transition-opacity duration-300",
                    taglineShimmer ? "agent-progress-loading-text" : "text-text-primary",
                  )}
                >
                  {WELCOME_TAGLINES[taglineIndex]}
                </h2>

                <AgentComposer
                  value={input}
                  onValueChange={setInput}
                  onSubmit={() => submit(input)}
                  onStop={stop}
                  busy={busy}
                  model={providerInfo.model}
                  provider={providerInfo.providerLabel}
                  messageCount={messages.length}
                />

                <div className="flex w-full flex-col gap-1 px-2">
                  {PRESET_QUESTIONS.map((question) => (
                    <button
                      key={question}
                      type="button"
                      onClick={() => submit(question)}
                      className="flex w-full cursor-pointer items-start gap-2 rounded-lg px-2 py-1.5 text-start text-body-regular text-text-secondary transition-colors hover:bg-background-primary-hover hover:text-text-primary"
                    >
                      <span aria-hidden className="shrink-0 text-text-tertiary">→</span>
                      <span>{question}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <>
              <div className="relative min-h-0 flex-1">
                <div
                  ref={scrollRef}
                  onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
                  className="h-full overflow-y-auto scroll-smooth"
                >
                  <div
                    ref={columnRef}
                    className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 pt-[72px] pb-6"
                  >
                    {messages.map((message, index) => {
                      const prevUserPrompt =
                        message.role === "assistant"
                          ? [...messages.slice(0, index)]
                              .reverse()
                              .find((m) => m.role === "user")
                          : undefined;
                      const isLast = index === messages.length - 1;
                      return (
                        <AgentMessage
                          key={message.id}
                          role={message.role}
                          text={messageText(message)}
                          parts={message.parts}
                          metadata={message.metadata}
                          userPrompt={prevUserPrompt ? messageText(prevUserPrompt) : undefined}
                          streaming={busy && isLast}
                          hasError={Boolean(error) && isLast}
                          at={messageAt[message.id]}
                        />
                      );
                    })}

                    {showThinking && (
                      <div className="flex items-center gap-2.5 px-1">
                        <Logo size={24} />
                        <AgentThinking variant="wave" tone="accent" label="Codely is thinking…" active />
                      </div>
                    )}

                    {error && (
                      <p role="alert" className="px-1 text-body-regular text-text-error-primary">
                        Something went wrong. Check the server logs, then try again.
                      </p>
                    )}
                  </div>
                </div>

                {/* Soft progressive blur + fade along top scroll edge (BoardUI scroll rule) */}
                <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 z-10 h-14">
                  <div
                    className="absolute inset-x-0 top-0 h-6 backdrop-blur-[1px]"
                    style={{
                      opacity: scrollFadeOpacity,
                      maskImage: "linear-gradient(to bottom, #000, transparent)",
                      WebkitMaskImage: "linear-gradient(to bottom, #000, transparent)",
                    }}
                  />
                  <div
                    className="absolute inset-x-0 top-0 h-4 backdrop-blur-[4px]"
                    style={{
                      opacity: scrollFadeOpacity,
                      maskImage: "linear-gradient(to bottom, #000, transparent)",
                      WebkitMaskImage: "linear-gradient(to bottom, #000, transparent)",
                    }}
                  />
                  <div
                    className="absolute inset-0 bg-linear-to-b from-background-secondary-default to-transparent"
                    style={{ opacity: scrollFadeOpacity }}
                  />
                </div>
              </div>

              <div className="shrink-0 px-3 pb-3">
                <div className="mx-auto w-full max-w-3xl">
                  <AgentComposer
                    value={input}
                    onValueChange={setInput}
                    onSubmit={() => submit(input)}
                    onStop={stop}
                    busy={busy}
                    model={providerInfo.model}
                    provider={providerInfo.providerLabel}
                    messageCount={messages.length}
                  />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  ));
}

const WELCOME_TAGLINES = [
  "What’s on the agenda today?",
  "Ready to crush every bug like a pro?",
  "Drop a repo, let’s hunt some vulnerabilities.",
  "What are we building — or hardening — today?",
  "Clean code starts with a sharp scan.",
  "Got a tricky architecture puzzle? Let’s unpack it.",
];

const PRESET_QUESTIONS = [
  "How does Codely show structured thinking while a scan is running?",
  "How does Codely present multi-step security audits and architectural comparisons?",
  "How can developers showcase their Codely usage and security impact on the dashboard?",
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function orderThreads(threads: StoredThread[]) {
  return [...threads].sort((a, b) => b.updatedAt - a.updatedAt).slice(0, MAX_THREADS);
}

function messageText(message: UIMessage) {
  return message.parts
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("");
}

function newThreadId() {
  return globalThis.crypto?.randomUUID?.() ?? `t-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function deriveTitle(messages: UIMessage[]) {
  const firstUser = messages.find((message) => message.role === "user");
  const text = firstUser?.parts
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("")
    .trim();
  if (!text) return "New chat";
  return text.length > 48 ? `${text.slice(0, 48)}...` : text;
}

function headerTitle(threads: ChatThreadSummary[], activeId: string) {
  return threads.find((thread) => thread.id === activeId)?.title ?? "New chat";
}

function readThreads(): StoredThread[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (thread): thread is StoredThread =>
        typeof thread === "object" &&
        thread !== null &&
        typeof (thread as StoredThread).id === "string" &&
        Array.isArray((thread as StoredThread).messages),
    );
  } catch {
    return [];
  }
}

function writeThreads(threads: StoredThread[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(threads));
  } catch {
    // Quota or blocked storage: history is best-effort, the chat still works.
  }
}
