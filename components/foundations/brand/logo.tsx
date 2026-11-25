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
  className,
}: {
  size?: number;
  mono?: boolean;
  className?: string;
}) {
  return (
    <>
      <Image
        src="/logo/codely-icon-light.png"
        alt="Codely"
        width={size}
        height={size}
        className={cx("theme-logo-light shrink-0 object-contain", className)}
        priority
      />
      <Image
        src="/logo/codely-icon-dark.png"
        alt="Codely"
        width={size}
        height={size}
        className={cx("theme-logo-dark shrink-0 object-contain", className)}
        priority
      />
    </>
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
  const width = Math.round(height * 4.9);
  return (
    <>
      <Image
        src="/logo/codely-wordmark-light.png"
        alt="Codely"
        width={width}
        height={height}
        style={{ height, width: "auto" }}
        className={cx("theme-logo-light shrink-0 object-contain", className)}
        priority
      />
      <Image
        src="/logo/codely-wordmark-dark.png"
        alt="Codely"
        width={width}
        height={height}
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
