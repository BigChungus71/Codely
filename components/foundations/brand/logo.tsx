import Image from "next/image";
import { cx } from "@/utils/cx";

/**
 * Codely square icon mark (`<>`).
 * Automatically swaps between `/logo/codely-icon-light.png` (light mode)
 * and `/logo/codely-icon-dark.png` (dark mode) via `.theme-logo-light` / `.theme-logo-dark`.
 */
export function Logo({
  size = 28,
  mono: _mono = false,
  showDot = false,
  className,
}: {
  size?: number;
  mono?: boolean;
  showDot?: boolean;
  className?: string;
}) {
  const images = (
    <>
      <Image
        src="/logo/codely-icon-light.png"
        alt="Codely"
        width={size}
        height={size}
        className={cx("theme-logo-light shrink-0 object-contain", !showDot && className)}
        priority
      />
      <Image
        src="/logo/codely-icon-dark.png"
        alt="Codely"
        width={size}
        height={size}
        className={cx("theme-logo-dark shrink-0 object-contain", !showDot && className)}
        priority
      />
    </>
  );

  if (!showDot) return images;

  const dotSize = Math.max(4, Math.round(size * 0.22));
  // Matches the wordmark's bottom-right baseline alignment with `<>`.
  const dotBaselineOffset = Math.round(size * 0.29);

  return (
    <span
      dir="ltr"
      className={cx("inline-flex shrink-0 items-end", className)}
      style={{ gap: Math.max(1, Math.round(size * 0.05)) }}
    >
      <span className="relative inline-flex shrink-0" style={{ width: size, height: size }}>
        {images}
      </span>
      <span
        aria-hidden
        className="shrink-0 rounded-full bg-accent-600"
        style={{
          width: dotSize,
          height: dotSize,
          marginBottom: dotBaselineOffset,
        }}
      />
    </span>
  );
}

/**
 * Full Codely horizontal wordmark (`<> codely.`).
 * Automatically swaps between `/logo/codely-wordmark-light.png` and
 * `/logo/codely-wordmark-dark.png` for crisp rendering in both themes.
 */
export function CodelyWordmark({
  height = 22,
  className,
}: {
  height?: number;
  className?: string;
}) {
  return (
    <>
      <Image
        src="/logo/codely-wordmark-light.png"
        alt="Codely"
        width={707}
        height={143}
        style={{ height, width: "auto" }}
        className={cx("theme-logo-light shrink-0 object-contain", className)}
        priority
      />
      <Image
        src="/logo/codely-wordmark-dark.png"
        alt="Codely"
        width={685}
        height={141}
        style={{ height, width: "auto" }}
        className={cx("theme-logo-dark shrink-0 object-contain", className)}
        priority
      />
    </>
  );
}

/** Theme-aware Codely mark (alias for ProLogo). */
export function ProLogo({
  size = 36,
  className,
  decorative = false,
  priority = false,
}: {
  size?: number;
  className?: string;
  decorative?: boolean;
  priority?: boolean;
}) {
  const alt = decorative ? "" : "Codely";

  return (
    <>
      <Image
        src="/logo/codely-icon-light.png"
        alt={alt}
        width={size}
        height={size}
        className={cx("theme-logo-light shrink-0 object-contain", className)}
        priority={priority}
      />
      <Image
        src="/logo/codely-icon-dark.png"
        alt={alt}
        width={size}
        height={size}
        className={cx("theme-logo-dark shrink-0 object-contain", className)}
        priority={priority}
      />
    </>
  );
}
