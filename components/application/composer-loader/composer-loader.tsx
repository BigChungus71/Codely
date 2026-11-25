"use client";

import { useTemplateCopy } from "@/components/foundations/template-copy/template-copy";

import { useEffect, useId, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { cx } from "@/utils/cx";

/**
 * Composer Loader — a loading state that wraps a chat composer while the agent
 * works: a smooth luminous light band surrounding the entire pill's outer rim
 * and radiating outward rather than inward.
 *
 * The glow sits behind the opaque pill surface in an expanded SVG canvas so
 * the outer blur never clips, while the pill surface itself covers the inner
 * edge cleanly so the text box stays crisp.
 *
 * `active` fades the whole effect in and out (450ms) and stops the pulse
 * animation when inactive, so toggling it on send / completion reads as the
 * composer lighting up and resting cleanly.
 */

export interface ComposerLoaderProps {
  children: ReactNode;
  /** Show the light. Fades in/out — flip it while awaiting a response. */
  active?: boolean;
  /** Four gradient colors distributed smoothly around the perimeter. */
  colors?: [string, string, string, string];
  /** Seconds per full pulse/orbit cycle. */
  speed?: number;
  /** Overall light opacity. */
  intensity?: number;
  /** How far the bloom radiates outward from the rim, px. */
  bloom?: number;
  /** Bloom layer opacity. */
  bloomStrength?: number;
  /** How much of the perimeter the band occupies, degrees (of 360). */
  arc?: number;
  /** Reverse the travel direction when `arc < 360`. */
  reverse?: boolean;
  /** Corner radius, px. Defaults to a full pill. */
  radius?: number;
  /** Width of the crisp outer rim, px; the tight glow scales with it. */
  line?: number;
  /** Draw the wide bloom alone, no line or tight glow: a soft wash for a beam to lead. */
  bloomOnly?: boolean;
  /** Paint the pill surface in front of the outward glow (on by default). */
  surface?: boolean;
  /**
   * Fade the band's two ends instead of cutting them when `arc < 360`, 0–1.
   */
  taper?: number;
  /** How the light composites over what's beneath, e.g. `screen` to read as light on a surface. */
  blend?: CSSProperties["mixBlendMode"];
  /**
   * Moves the band forward along the lap, as a fraction of the perimeter (0–1).
   */
  offset?: number;
  className?: string;
}

const DEFAULT_COLORS: [string, string, string, string] = [
  "#2563eb",
  "#3b82f6",
  "#60a5fa",
  "#1d4ed8",
];

export function ComposerLoader({
  children,
  active = true,
  colors = DEFAULT_COLORS,
  speed = 2.6,
  intensity = 0.9,
  bloom = 14,
  bloomStrength = 0.55,
  arc = 360,
  reverse = false,
  radius,
  line = 2.5,
  bloomOnly = false,
  surface = true,
  taper = 0,
  blend,
  offset = 0,
  className,
}: ComposerLoaderProps) {
  const localize = useTemplateCopy();
  const gradientId = `bui-cl-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const pillRef = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState({ w: 640, h: 52 });

  useEffect(() => {
    const el = pillRef.current;
    if (!el) return;
    const measure = () =>
      setBox({ w: Math.max(1, el.clientWidth), h: Math.max(1, el.clientHeight) });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const [c0, c1, c2, c3] = colors;
  const isFullRing = arc >= 360;
  const band = (Math.min(360, arc) / 360) * 100;
  const rx = radius ?? box.h / 2;
  const cornerRadius = radius ?? 9999;
  const direction = reverse ? "reverse" : "normal";

  // Extra margin around the pill so the outward Gaussian blur never clips.
  const pad = Math.max(36, Math.ceil(bloom * 2.5));
  const svgW = box.w + pad * 2;
  const svgH = box.h + pad * 2;

  const cornerR = Math.min(rx, box.w / 2, box.h / 2);
  const perimeter = Math.max(1, 2 * (box.w + box.h) - 8 * cornerR + 2 * Math.PI * cornerR);
  const pxUnits = (px: number) => (px * 100) / perimeter;
  const dashPhase = (len: number, backPx: number) =>
    (reverse ? pxUnits(backPx) : len - band + pxUnits(backPx)) - offset * 100;

  const TAPER_STEPS = 14;
  const CRISP_BLUR = taper > 0 ? Math.max(0.5, line * 0.8) : 0.75;

  const stroke = (width: number, blur: number, opacity: number, dashLen: number, backPx: number) => {
    if (isFullRing) {
      return (
        <rect
          x={pad}
          y={pad}
          width={box.w}
          height={box.h}
          rx={rx}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={width}
          filter={blur > 0 ? `url(#${gradientId}-b${String(blur).replace(".", "_")})` : undefined}
          style={{ opacity }}
        />
      );
    }

    const copies = taper > 0 ? TAPER_STEPS : 1;
    return Array.from({ length: copies }, (_, index) => {
      const len = dashLen * (1 - (taper * index) / copies);
      const phase = dashPhase(dashLen, backPx) - (dashLen - len) / 2;
      return (
        <rect
          key={index}
          x={pad}
          y={pad}
          width={box.w}
          height={box.h}
          rx={rx}
          pathLength={100}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={width}
          strokeLinecap="round"
          strokeDasharray={`${len} ${100 - len}`}
          className="bui-composer-loader-rect"
          data-active={active ? "true" : "false"}
          filter={blur > 0 ? `url(#${gradientId}-b${String(blur).replace(".", "_")})` : undefined}
          style={{
            opacity: opacity / copies,
            animation: active
              ? `bui-composer-loader-dash ${speed}s linear ${(phase * speed) / 100}s infinite ${direction}`
              : "none",
          }}
        />
      );
    });
  };

  /** One feGaussianBlur per blur radius the layers use. */
  const blurFilter = (blurRadius: number) => (
    <filter
      key={blurRadius}
      id={`${gradientId}-b${String(blurRadius).replace(".", "_")}`}
      x="-50%"
      y="-50%"
      width="200%"
      height="200%"
    >
      <feGaussianBlur stdDeviation={blurRadius} />
    </filter>
  );

  return localize((
    <div className={cx("relative", className)}>
      {/* Outward surrounding glow behind the pill surface */}
      <span
        aria-hidden
        data-active={active ? "true" : "false"}
        className="pointer-events-none absolute"
        style={{
          inset: -pad,
          opacity: active ? 1 : 0,
          transition: "opacity 450ms ease",
          mixBlendMode: blend,
        }}
      >
        <span
          className={cx("block h-full w-full", isFullRing && active && "bui-composer-glow-pulse")}
          style={{
            animationDuration: isFullRing && active ? `${speed}s` : undefined,
          }}
        >
          <svg
            width={svgW}
            height={svgH}
            viewBox={`0 0 ${svgW} ${svgH}`}
            className="block h-full w-full"
            style={{ opacity: intensity }}
          >
            <defs>
              <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor={c0} />
                <stop offset="25%" stopColor={c1} />
                <stop offset="50%" stopColor={c2} />
                <stop offset="75%" stopColor={c3} />
                <stop offset="100%" stopColor={c0} />
              </linearGradient>
              {[11, 5, CRISP_BLUR].map(blurFilter)}
            </defs>
            {/* Wide soft bloom radiating outward */}
            {bloom > 0 && stroke(bloom * 1.6, 11, bloomStrength, band * 0.9, bloom + 16)}
            {/* Medium outward halo */}
            {!bloomOnly && stroke(line * 3.4, 5, 0.7, band * 0.95, 10)}
            {/* Crisp smooth outer rim */}
            {!bloomOnly && stroke(line, CRISP_BLUR, 0.95, band, 0)}
          </svg>
        </span>
      </span>

      {/* Solid pill surface covers the inner half of the strokes so zero glow bleeds inward */}
      {surface && (
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-background-primary-default shadow-xs"
          style={{ borderRadius: cornerRadius }}
        />
      )}

      <div ref={pillRef} className="relative">
        {children}
      </div>
    </div>
  ));
}
