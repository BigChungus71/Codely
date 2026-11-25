"use client";

import { useTemplateCopy } from "@/components/foundations/template-copy/template-copy";

import { useChat } from "@ai-sdk/react";
import { RiAddLine, RiCloseLine, RiMenuLine, RiScanLine, RiShieldCheckLine } from "@remixicon/react";
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
import { CODELY_SUGGESTIONS, pickSuggestions } from "@/components/application/agent-chat/codely-suggestions";
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
  const [input, setInput] = useState("");
  const [navOpen, setNavOpen] = useState(false);
  const starterBase = useStarterBase();
  const navItems = starterNav(starterBase);
  const [threads, setThreads] = useState<StoredThread[]>([]);
  const [activeId, setActiveId] = useState("");
  const [activeUpdatedAt, setActiveUpdatedAt] = useState(0);
  const [activeTitle, setActiveTitle] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLSpanElement>(null);
  const columnRef = useRef<HTMLDivElement>(null);
  const [messageAt, setMessageAt] = useState<Record<string, number>>({});
  const [scrolledUnder, setScrolledUnder] = useState(false);
  const [canClash, setCanClash] = useState(false);
  const [restored, setRestored] = useState(false);

  /** Codely always starts in live mode; demo transport is a silent fallback. */
  const [transport] = useState(
    () => new SwitchingTransport(new DefaultChatTransport({ api: ENDPOINT }), new DemoTransport()),
  );

  const { messages, sendMessage, setMessages, status, stop, error } = useChat({
    transport,
  });

  const busy = status === "submitted" || status === "streaming";

  const streamedText = useMemo(() => {
    const last = messages[messages.length - 1];
    if (!last || last.role !== "assistant") return "";
    return last.parts
      .filter((part) => part.type === "text")
      .map((part) => part.text)
      .join("");
  }, [messages]);
  const showThinking = busy && streamedText.length === 0;

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
            messages,
            messageAt,
          }
        : null,
    [activeId, messages, activeUpdatedAt, messageAt, activeTitle],
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
      setCanClash(title.right + 16 > column.left);
    };
    measure();
    const observer = new ResizeObserver(measure);
    if (scrollRef.current) observer.observe(scrollRef.current);
    return () => observer.disconnect();
  }, [messages.length, activeId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  const submit = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setActiveUpdatedAt(Date.now());
    sendMessage({ text: trimmed }, { body: { demo: false } });
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
    setMessageAt({});
    setMessages([]);
    setInput("");
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

  const toggleUnread = useCallback((id: string) => {
    setThreads((prev) =>
      prev.map((thread) => (thread.id === id ? { ...thread, unread: !thread.unread } : thread)),
    );
  }, []);

  const deleteThread = useCallback(
    (id: string) => {
      const remaining = threads.filter((thread) => thread.id !== id);
      setThreads(remaining);
      if (id === activeId) {
        setActiveId(newThreadId());
        setActiveUpdatedAt(0);
        setActiveTitle(null);
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
      if (thread.unread) toggleUnread(id);
      setActiveId(id);
      setActiveUpdatedAt(thread.updatedAt);
      setActiveTitle(thread.title);
      setMessageAt(thread.messageAt ?? {});
      setMessages(thread.messages);
      setInput("");
    },
    [busy, activeId, allThreads, keepLiveThread, toggleUnread, setMessages],
  );

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
            className="absolute inset-0 cursor-pointer bg-black/40"
          />
          <div className="relative flex h-full p-3">
            <DashboardSidebar
              mobile
              items={navItems}
              selected="chat"
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
              "absolute inset-x-0 top-0 z-10 flex h-12 items-center gap-2 border-b px-4 pt-[7px] transition-colors",
              scrolledUnder && canClash
                ? "border-separator-border bg-white/20 backdrop-blur-[20px] dark:bg-black/20"
                : "border-transparent",
            )}
          >
            <IconButton
              icon={navOpen ? RiCloseLine : RiMenuLine}
              size="small"
              aria-label="Open navigation"
              onClick={() => setNavOpen((open) => !open)}
              className="lg:hidden"
            />
            {/* Codely bot identity */}
            <div className="flex min-w-0 items-center gap-2">
              <Logo size={28} className="rounded-lg" />
              <span
                ref={titleRef}
                className="min-w-0 shrink truncate text-headline-medium text-text-primary"
              >
                {messages.length > 0 ? headerTitle(allThreads, activeId) : "Codely Assistant"}
              </span>
              <span className="hidden items-center gap-1 rounded-full bg-background-primary-default px-2 py-0.5 text-[11px] font-medium text-text-secondary shadow-xs sm:inline-flex">
                <span className="size-1.5 rounded-full bg-lime-500" aria-hidden />
                Online
              </span>
            </div>
            {/* Slogan — hidden when header is narrow */}
            <span className="hidden shrink-0 text-caption-1-regular text-text-tertiary md:block">
              crush every bug like a pro
            </span>

            <div className="ms-auto flex items-center gap-1">
              <button
                type="button"
                onClick={startNewChat}
                disabled={busy || messages.length === 0}
                aria-label="New chat"
                title="New chat"
                className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-md px-2 text-body-2-medium text-text-secondary transition-colors hover:bg-background-primary-hover hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
              >
                <RiAddLine className="size-4 shrink-0" aria-hidden />
                <span className="hidden sm:inline">New chat</span>
              </button>

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
          <>
            <div
              ref={scrollRef}
              onScroll={(event) => setScrolledUnder(event.currentTarget.scrollTop > 0)}
              className="min-h-0 flex-1 overflow-y-auto scroll-smooth"
            >
              <div
                ref={columnRef}
                className={cx(
                  "mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 pt-[72px] pb-6",
                  messages.length === 0 && "min-h-full justify-center",
                )}
              >
                {messages.length === 0 ? (
                  <EmptyState onPick={submit} base={starterBase} />
                ) : (
                  messages.map((message, index) => (
                    <AgentMessage
                      key={message.id}
                      role={message.role}
                      text={messageText(message)}
                      streaming={busy && index === messages.length - 1}
                      at={messageAt[message.id]}
                    />
                  ))
                )}

                {showThinking && (
                  <div className="flex items-center gap-2.5 px-1">
                    <Logo size={28} className="rounded-lg" />
                    <AgentThinking variant="wave" label="Codely is thinking…" />
                  </div>
                )}

                {error && (
                  <p role="alert" className="px-1 text-body-regular text-text-tertiary">
                    Something went wrong. Check the server logs, then try again.
                  </p>
                )}
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
                  model={null}
                  provider="Codely AI • Online"
                  messageCount={messages.length}
                />
              </div>
            </div>
          </>
        </div>
      </div>
    </div>
  ));
}

/** Codely chatbot empty state — bot greeting, slogan, scanner shortcut, and shuffled starter pills. */
function EmptyState({ onPick, base = "" }: { onPick: (text: string) => void; base?: string }) {
  const localize = useTemplateCopy();
  // Shuffle once per mount so each new thread shows a fresh set.
  const [suggestions] = useState(() => pickSuggestions(5));

  return localize((
    <div className="flex flex-col items-center gap-5 text-center">
      <Logo size={56} className="rounded-2xl shadow-xs" />
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-center gap-2">
          <RiShieldCheckLine className="size-5 text-accent-500" aria-hidden />
          <h2 className="text-title-2-medium text-text-primary">Hey! I&apos;m Codely — crush every bug like a pro.</h2>
        </div>
        <p className="text-body-regular text-text-secondary">
          Ask me to review code, find vulnerabilities, compare architectures, or run a live scan.
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        <a
          href={`${base}/scanner`}
          className="inline-flex cursor-pointer items-center gap-1.5 rounded-full bg-accent-500 px-4 py-2 text-body-medium text-white shadow-xs transition-opacity hover:opacity-90"
        >
          <RiScanLine className="size-4 shrink-0" aria-hidden />
          Open Code Scanner
        </a>
        {suggestions.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            onClick={() => onPick(suggestion)}
            className="cursor-pointer rounded-full bg-background-primary-default px-3.5 py-2 text-body-regular text-text-secondary shadow-xs transition-colors hover:bg-background-primary-hover"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  ));
}

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
