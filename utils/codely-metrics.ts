export interface CodelyMetrics {
  vulnerabilitiesFixed: number;
  bugsCrushed: number;
  linesChanged: number;
  securityScore: number;
}

const METRICS_KEY = "codely:metrics";
const METRICS_EVENT = "codely:metrics-change";

export const DEFAULT_METRICS: CodelyMetrics = {
  vulnerabilitiesFixed: 142,
  bugsCrushed: 389,
  linesChanged: 48920,
  securityScore: 98.4,
};

export function readCodelyMetrics(): CodelyMetrics {
  if (typeof window === "undefined") return DEFAULT_METRICS;
  try {
    const raw = window.localStorage.getItem(METRICS_KEY);
    if (!raw) return DEFAULT_METRICS;
    const parsed = JSON.parse(raw) as Partial<CodelyMetrics>;
    return {
      vulnerabilitiesFixed: typeof parsed.vulnerabilitiesFixed === "number" ? parsed.vulnerabilitiesFixed : DEFAULT_METRICS.vulnerabilitiesFixed,
      bugsCrushed: typeof parsed.bugsCrushed === "number" ? parsed.bugsCrushed : DEFAULT_METRICS.bugsCrushed,
      linesChanged: typeof parsed.linesChanged === "number" ? parsed.linesChanged : DEFAULT_METRICS.linesChanged,
      securityScore: typeof parsed.securityScore === "number" ? parsed.securityScore : DEFAULT_METRICS.securityScore,
    };
  } catch {
    return DEFAULT_METRICS;
  }
}

export function recordCodelyScan(findingsCount: number, linesScanned = 320): void {
  if (typeof window === "undefined") return;
  const current = readCodelyMetrics();
  const next: CodelyMetrics = {
    vulnerabilitiesFixed: current.vulnerabilitiesFixed + Math.max(1, Math.floor(findingsCount / 2)),
    bugsCrushed: current.bugsCrushed + findingsCount,
    linesChanged: current.linesChanged + linesScanned,
    securityScore: Math.min(99.9, Number((current.securityScore + 0.1).toFixed(1))),
  };
  try {
    window.localStorage.setItem(METRICS_KEY, JSON.stringify(next));
    window.dispatchEvent(new CustomEvent(METRICS_EVENT, { detail: next }));
  } catch {
    // Best-effort persistence when storage is blocked.
  }
}

export function subscribeCodelyMetrics(onChange: (metrics: CodelyMetrics) => void): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = () => onChange(readCodelyMetrics());
  window.addEventListener(METRICS_EVENT, handler);
  window.addEventListener("storage", handler);
  return () => {
    window.removeEventListener(METRICS_EVENT, handler);
    window.removeEventListener("storage", handler);
  };
}
