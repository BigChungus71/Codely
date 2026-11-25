import Image from "next/image";
import { cx } from "@/utils/cx";

/** Codely mark. Renders the theme-aware brand logo (`/logo/2.png` in light mode,
 *  `/logo/1.png` in dark mode) via `.theme-logo-light` / `.theme-logo-dark`. */
export function Logo({
  size = 32,
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
        src="/logo/2.png"
        alt="Codely"
        width={size}
        height={size}
        className={cx("theme-logo-light shrink-0 object-cover", className)}
        priority
      />
      <Image
        src="/logo/1.png"
        alt="Codely"
        width={size}
        height={size}
        className={cx("theme-logo-dark shrink-0 object-cover", className)}
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
        src="/logo/2.png"
        alt={alt}
        width={size}
        height={size}
        className={cx("theme-logo-light shrink-0 object-cover", className)}
        priority={priority}
      />
      <Image
        src="/logo/1.png"
        alt={alt}
        width={size}
        height={size}
        className={cx("theme-logo-dark shrink-0 object-cover", className)}
        priority={priority}
      />
    </>
  );
}
