"use client";

import { useTemplateCopy } from "@/components/foundations/template-copy/template-copy";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ComponentType,
  type ReactNode,
} from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  RiAsterisk,
  RiBankLine,
  RiCalendarLine,
  RiChatAiLine,
  RiCloseLine,
  RiEditBoxLine,
  RiHomeLine,
  RiImageAiLine,
  RiKanbanView2,
  RiMegaphoneLine,
  RiSearchLine,
  RiSideBarFill,
  RiUserSmileLine,
} from "@remixicon/react";
import { SettingsModal } from "@/components/application/settings/settings-modal";
import { ThemeToggle } from "@/components/application/theme/theme-toggle";
import { Badge } from "@/components/base/badges/badge";
import { CloseButton } from "@/components/base/buttons/close-button";
import { CodelyWordmark, Logo } from "@/components/foundations/brand/logo";
import { cx } from "@/utils/cx";
import { DashboardTeamMenu } from "./dashboard-team-menu";
import { DashboardUserMenu } from "./dashboard-user-menu";

/**
 * Figma sources:
 *   expanded  → Board UI → dashboard 1 → Sidebar (node 3731:2934)
 *   collapsed → Board UI → Sidebar (node 3768:3382)
 *
 * Floating sidebar panel. Expanded: 260px wide, p 12, radius/3xl (24px),
 * white 1px border, "Background/Sidebar Elevation" shadow, bg
 * background/secondary. Collapsed: 60px wide (36px icon items + 12px
 * padding); collapse button sits centered above the workspace avatar, quick
 * search becomes a 36px neutral-200 square, nav items become icon-only
 * squares, the team card reduces to its avatar.
 *
 * The two states morph into each other: the panel width animates while
 * labels / badges / kbd collapse via max-width + opacity.
 */

type IconComponent = ComponentType<{
  className?: string;
  "aria-hidden"?: boolean | "true" | "false";
}>;

/**
 * Collapsible text/badge slot: blurs + fades + shrinks away when the rail
 * closes, and blurs back in on expand. The icons/rows themselves stay pinned in
 * place — only these label/badge slots animate — so nothing jumps to center.
 */
function Collapsible({ collapsed, children, className }: { collapsed: boolean; children: ReactNode; className?: string }) {
  const localize = useTemplateCopy();
  return localize((
    <span
      className={cx(
        "flex min-w-0 items-center overflow-hidden transition-[max-width,opacity,filter] duration-300 ease-in-out",
        // Expanded, the cap is the row itself: a fixed cap (it was 160px)
        // clipped any label wider than it, "Components and Blocks" included.
        collapsed ? "max-w-0 opacity-0 blur-[3px]" : "max-w-full opacity-100 blur-0",
        className,
      )}
    >
      {children}
    </span>
  ));
}

function NavItem({
  icon: Icon,
  label,
  badge,
  isSelected = false,
  collapsed = false,
  href = "#",
  onClick,
}: {
  icon: IconComponent;
  label: string;
  badge?: ReactNode;
  isSelected?: boolean;
  collapsed?: boolean;
  href?: string;
  /** Action rows (e.g. Settings → modal) intercept the navigation. */
  onClick?: () => void;
}) {
  const localize = useTemplateCopy();
  const isInternal = href.startsWith("/") && !onClick;
  const classes = cx(
    "flex items-center justify-between overflow-hidden rounded-2lg p-2",
    "transition-[width,background-color] duration-300 ease-in-out",
    collapsed ? "w-9" : "w-full",
    isSelected
      ? "bg-linear-to-b from-accent-500 to-accent-600 shadow-nav-selected"
      : "hover:bg-background-secondary-hover",
  );
  const content = (
    <>
      <span className="flex min-w-0 items-center gap-2">
        <Icon
          className={cx("size-5 shrink-0", isSelected ? "text-white" : "text-foreground-icon-secondary")}
          aria-hidden
        />
        <Collapsible collapsed={collapsed}>
          <span
            className={cx(
              "text-body-medium whitespace-nowrap",
              isSelected ? "text-white" : "text-text-secondary",
            )}
          >
            {label}
          </span>
        </Collapsible>
      </span>
      {badge && <Collapsible collapsed={collapsed}>{badge}</Collapsible>}
    </>
  );

  if (isInternal) {
    return localize((
      <Link
        href={href}
        aria-current={isSelected ? "page" : undefined}
        aria-label={label}
        title={collapsed ? label : undefined}
        className={classes}
      >
        {content}
      </Link>
    ));
  }

  return localize((
    <a
      href={href}
      onClick={
        onClick
          ? (event) => {
              event.preventDefault();
              onClick();
            }
          : undefined
      }
      aria-current={isSelected ? "page" : undefined}
      aria-label={label}
      title={collapsed ? label : undefined}
      className={classes}
    >
      {content}
    </a>
  ));
}

/** A primary navigation row. Rows without an `href` are decoration only. */
export interface DashboardNavItem {
  key: string;
  label: string;
  icon: IconComponent;
  href?: string;
  badge?: string | number;
}

/** Kept as a name for callers that typed their `selected` prop; any key works. */
export type DashboardNavKey = string;

/** The Pro dashboard's navigation, the default set. */
export const DASHBOARD_NAV: DashboardNavItem[] = [
  { key: "home", label: "Home", icon: RiHomeLine, href: "/templates/dashboard", badge: 152 },
  { key: "project-board", label: "Project board", icon: RiKanbanView2, href: "/templates/project-board" },
  { key: "marketing", label: "Marketing", icon: RiMegaphoneLine, href: "/templates/marketing" },
  { key: "calendar", label: "Calendar", icon: RiCalendarLine, href: "/templates/calendar" },
  { key: "finance", label: "Finance", icon: RiBankLine, href: "/templates/finance" },
  { key: "medical", label: "Medical Report", icon: RiAsterisk, href: "/templates/medical-profile" },
  { key: "ai-chat", label: "AI Chat", icon: RiChatAiLine, href: "/templates/ai-chat" },
  { key: "ai-image", label: "AI Image Generation", icon: RiImageAiLine, href: "/templates/ai-image-generation" },
  { key: "profile", label: "Profile", icon: RiUserSmileLine, href: "/templates/ai-profile" },
];

/**
 * The primary rows. A component of its own so the closures over `collapsed`
 * and the search query live here: built inline in the sidebar, the compiler
 * could not tell they leave `mobile` untouched and dropped the sidebar's
 * manual memoization.
 */
function NavRows({
  items,
  query,
  selected,
  collapsed,
  secondaryMatch,
}: {
  items: DashboardNavItem[];
  query: string;
  selected: string;
  collapsed: boolean;
  /** Whether Support or Settings matches, so "No results" only shows when nothing does. */
  secondaryMatch: boolean;
}) {
  const localize = useTemplateCopy();
  const shown = items.filter((item) => item.label.toLocaleLowerCase().includes(query));
  if (shown.length === 0 && !secondaryMatch && !collapsed) {
    return localize(<p className="px-2 py-3 text-body-regular text-text-tertiary">No results</p>);
  }
  return shown.map((item) => {
      const isSelected = selected === item.key;
      return (
        <NavItem
          key={item.key}
          icon={item.icon}
          label={item.label}
          href={item.href}
          isSelected={isSelected}
          collapsed={collapsed}
          badge={
            item.badge !== undefined ? (
              <Badge color={isSelected ? "primary" : "neutral"}>{item.badge}</Badge>
            ) : undefined
          }
        />
      );
    });
}

export function DashboardSidebar({
  mobile = false,
  onClose,
  fluid = false,
  showThemeToggle = true,
  selected = "home",
  items = DASHBOARD_NAV,
  flat = false,
  onNewChat,
  newChatBusy = false,
  sidebarSlot,
  className,
}: {
  /** Rendered inside the mobile drawer: always expanded, close button instead of collapse. */
  mobile?: boolean;
  onClose?: () => void;
  fluid?: boolean;
  showThemeToggle?: boolean;
  selected?: DashboardNavKey;
  items?: DashboardNavItem[];
  flat?: boolean;
  /** Called when the sidebar's "New chat" button is clicked; navigates to `/` if omitted. */
  onNewChat?: () => void;
  /** Disables New chat while streaming. */
  newChatBusy?: boolean;
  /** Optional embedded section rendered below the primary nav when expanded (e.g. recent chats). */
  sidebarSlot?: ReactNode;
  className?: string;
} = {}) {
  const localize = useTemplateCopy();
  const router = useRouter();
  const [collapsedState, setCollapsed] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [newChatShimmer, setNewChatShimmer] = useState(false);
  const [searchActive, setSearchActive] = useState(false);
  const [query, setQuery] = useState("");
  const searchTriggerRef = useRef<HTMLButtonElement>(null);
  const searchFieldRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const shimmerTimerRef = useRef<number | null>(null);
  const collapsed = mobile ? false : collapsedState;
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const secondaryMatch = false;

  useEffect(() => {
    return () => {
      if (shimmerTimerRef.current !== null) window.clearTimeout(shimmerTimerRef.current);
    };
  }, []);

  const handleNewChat = useCallback(() => {
    if (newChatBusy) return;
    setNewChatShimmer(true);
    if (shimmerTimerRef.current !== null) window.clearTimeout(shimmerTimerRef.current);
    shimmerTimerRef.current = window.setTimeout(() => {
      shimmerTimerRef.current = null;
      setNewChatShimmer(false);
    }, 950);
    if (onNewChat) {
      onNewChat();
    } else {
      router.push("/");
    }
  }, [newChatBusy, onNewChat, router]);

  const activateSearch = useCallback(() => {
    if (!mobile) setCollapsed(false);
    setSearchActive(true);
  }, [mobile]);

  const deactivateSearch = useCallback((restoreFocus: boolean) => {
    setQuery("");
    setSearchActive(false);
    if (restoreFocus) {
      window.requestAnimationFrame(() => searchTriggerRef.current?.focus());
    }
  }, []);

  useEffect(() => {
    if (!searchActive) return;
    const frame = window.requestAnimationFrame(() => searchInputRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [searchActive]);

  useEffect(() => {
    if (!searchActive) return;

    const onOutsideClick = (event: MouseEvent) => {
      const target = event.target;
      if (target instanceof Node && searchFieldRef.current?.contains(target)) return;
      deactivateSearch(false);
    };

    document.addEventListener("click", onOutsideClick);
    return () => document.removeEventListener("click", onOutsideClick);
  }, [deactivateSearch, searchActive]);

  useEffect(() => {
    const onShortcut = (event: KeyboardEvent) => {
      if (event.key.toLocaleLowerCase() === "l" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        activateSearch();
      }
    };

    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, [activateSearch]);

  return localize((
    <aside
      className={cx(
        "flex h-full shrink-0 flex-col justify-between overflow-hidden",
        flat
          ? "bg-background-full"
          : "rounded-3xl border border-border-button-white bg-background-secondary-default shadow-sidebar",
        "transition-[width] duration-300 ease-in-out",
        // Collapsed rail keeps the 60px spec: 1px border + 11px padding on each
        // side leaves an exactly 36px column so the w-9 (36px) icon items center.
        collapsed
          ? "w-[60px] px-[11px] py-3"
          : fluid
            ? "w-full p-3 lg:w-[260px]"
            : "w-[260px] p-3",
        className,
      )}
    >
      {/* `overflow-y: auto` forces the x axis to clip too, and this box hugs
          its contents on every side — so the selected item's 1px ring, the
          profile's hover pill (which outsets 6px) and focus rings all landed
          outside it. Padding moves the clip edge out; the matching negative
          margin borrows that space back from the rail's own padding, leaving
          every child exactly where it was. */}
      <div
        className="-m-2 flex min-h-0 w-[calc(100%+16px)] flex-1 flex-col gap-3 overflow-y-auto p-2 [scrollbar-width:none]"
      >
        {/* Top bar: Codely logo left, search + collapse right (ChatGPT-style in Codely design language) */}
        <div
          className={cx(
            "flex w-full items-center transition-[gap] duration-300 ease-in-out",
            collapsed
              ? "flex-col items-center justify-center gap-2.5"
              : "flex-row justify-between px-1 pt-0.5",
          )}
        >
          <Link
            href="/"
            aria-label="Codely home"
            className="flex items-center rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring"
          >
            {collapsed ? <Logo size={24} /> : <CodelyWordmark height={20} />}
          </Link>

          <div className={cx("flex items-center gap-1", collapsed && "flex-col gap-2")}>
            {!flat && (
              <button
                ref={searchTriggerRef}
                type="button"
                aria-label="Search chats and navigation"
                title="Quick Search (⌘L)"
                onClick={activateSearch}
                className="flex size-7 cursor-pointer items-center justify-center rounded-lg text-foreground-icon-secondary transition-colors hover:bg-background-secondary-hover hover:text-foreground-icon-primary"
              >
                <RiSearchLine className="size-[18px]" aria-hidden />
              </button>
            )}
            {mobile ? (
              <button
                type="button"
                aria-label="Close sidebar"
                onClick={onClose}
                className="flex size-7 cursor-pointer items-center justify-center rounded-lg text-foreground-icon-secondary transition-colors hover:bg-background-secondary-hover hover:text-foreground-icon-primary"
              >
                <RiCloseLine className="size-5" aria-hidden />
              </button>
            ) : (
              <button
                type="button"
                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                aria-expanded={!collapsed}
                onClick={() => {
                  const isExpanding = collapsedState;
                  if (!isExpanding) deactivateSearch(false);
                  setCollapsed(!collapsedState);
                }}
                className="flex size-7 cursor-pointer items-center justify-center rounded-lg text-foreground-icon-secondary transition-colors hover:bg-background-secondary-hover hover:text-foreground-icon-primary"
              >
                <RiSideBarFill
                  className={cx("size-[18px] transition-transform duration-300 ease-in-out", collapsed ? "rtl:-scale-x-100" : "-scale-x-100 rtl:scale-x-100")}
                  aria-hidden
                />
              </button>
            )}
          </div>
        </div>

        {/* Inline search input when active */}
        {!flat && searchActive && !collapsed && (
          <div
            ref={searchFieldRef}
            className="flex w-full items-center gap-2 rounded-xl bg-background-tertiary-default px-2.5 py-1.5 ring-2 ring-inset ring-border-button-active"
          >
            <RiSearchLine className="size-4 shrink-0 text-foreground-icon-secondary" aria-hidden />
            <input
              ref={searchInputRef}
              type="search"
              aria-label="Filter navigation"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.preventDefault();
                  deactivateSearch(true);
                }
              }}
              placeholder="Search…"
              className="min-w-0 flex-1 bg-transparent text-body-2-medium text-text-primary outline-none placeholder:text-text-tertiary"
            />
            <CloseButton
              size="2xs"
              aria-label="Clear search"
              onClick={() => deactivateSearch(true)}
              className="bg-background-tertiary-hover"
            />
          </div>
        )}

        {/* Prominent New chat button (ChatGPT-style in Codely's surface language, with shimmer on click) */}
        <button
          type="button"
          onClick={handleNewChat}
          disabled={newChatBusy}
          aria-label="New chat"
          title={collapsed ? "New chat" : undefined}
          className={cx(
            "relative flex cursor-pointer items-center gap-2 overflow-hidden rounded-xl border p-2 text-start transition-all duration-200",
            "border-border-button-default bg-background-primary-default/90 hover:bg-background-primary-hover shadow-2xs",
            "disabled:cursor-not-allowed disabled:opacity-50",
            newChatShimmer && "border-accent-500/60 ring-2 ring-accent-500/20",
            collapsed ? "w-9 justify-center" : "w-full",
          )}
        >
          <RiEditBoxLine
            className={cx(
              "size-[18px] shrink-0 transition-colors",
              newChatShimmer ? "text-accent-500" : "text-foreground-icon-primary",
            )}
            aria-hidden
          />
          <Collapsible collapsed={collapsed}>
            <span
              className={cx(
                "text-body-medium whitespace-nowrap",
                newChatShimmer ? "agent-progress-loading-text" : "text-text-primary",
              )}
            >
              New chat
            </span>
          </Collapsible>
        </button>

        <div className="flex w-full min-h-0 flex-1 flex-col gap-3">
          {/* Primary nav */}
          <nav className={cx("flex w-full flex-col gap-1", !collapsed && "px-0.5")}>
            <NavRows
              items={items}
              query={normalizedQuery}
              selected={selected}
              collapsed={collapsed}
              secondaryMatch={secondaryMatch}
            />
          </nav>

          {!collapsed && sidebarSlot && (
            <div className="mt-1 flex min-h-0 flex-1 flex-col border-t border-separator-border pt-3">
              {sidebarSlot}
            </div>
          )}
        </div>
      </div>

      <div className="flex w-full shrink-0 flex-col gap-2.5 border-t border-separator-border pt-3">
        {showThemeToggle &&
          (collapsed ? (
            <ThemeToggle collapsed />
          ) : (
            <ThemeToggle
              appearance="sidebar-segmented"
              className={flat ? "!bg-background-secondary-default" : undefined}
            />
          ))}

        {/* User profile (opens Settings, Support, and team access) */}
        <div className={cx("flex items-center px-1 py-0.5", collapsed && "justify-center px-0")}>
          <DashboardUserMenu
            collapsed={collapsed}
            onOpenSettings={() => setSettingsOpen(true)}
            avatarClassName={
              flat
                ? "bg-background-tertiary-default dark:bg-background-secondary-default"
                : undefined
            }
          />
        </div>

        {/* Team card */}
        <DashboardTeamMenu
          collapsed={collapsed}
          className={flat ? "!bg-background-secondary-default" : undefined}
        />
      </div>

      <SettingsModal
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        planArtSrc="/templates/settings-plan-art.png"
      />
    </aside>
  ));
}
