export type ResearchMode = "thinking" | "research" | "building";
export type ResearchStatus = "running" | "complete" | "aborted" | "error";

export interface ResearchStep {
  title: string;
  detail: string;
  status?: "running" | "done";
}

export interface ResearchPlan {
  mode: ResearchMode;
  headline: string;
  workingLabel: string;
  steps: ResearchStep[];
}

export interface ResearchLogPartData {
  mode: ResearchMode;
  headline: string;
  workingLabel: string;
  status: ResearchStatus;
  steps: ResearchStep[];
  startedAt: number;
  completedAt?: number;
  durationMs?: number;
}

export interface ChatMessageMetadata {
  startedAt?: number;
  completedAt?: number;
  durationMs?: number;
  status?: "streaming" | "complete" | "aborted" | "error";
}

export const PRESET_PLANS: { match: RegExp; plan: ResearchPlan }[] = [
  {
    match: /structured thinking|thinking while a scan|composer.?loader|agent.?thinking/i,
    plan: {
      mode: "thinking",
      headline: "Structured thinking pipeline",
      workingLabel: "Evaluating thinking components…",
      steps: [
        {
          title: "ComposerLoader rim light activated",
          detail: "4-stop iridescent sweep orbiting the pill rim at 450ms fade-in",
        },
        {
          title: "AgentThinking wave matrix synced",
          detail: "3×3 dot wavefront + shimmering status label and elapsed timer",
        },
        {
          title: "Reduced-motion & token check passed",
          detail: "Semantic foreground tones verified across light and dark modes",
        },
      ],
    },
  },
  {
    match: /multi-step security audits|architectural comparisons|agent.?log|scanner/i,
    plan: {
      mode: "research",
      headline: "Deep research & audit trail",
      workingLabel: "Researching security & architecture rules…",
      steps: [
        {
          title: "Indexed repository & dependency manifest",
          detail: "Mapped source modules, imports, and lockfile CVE advisories",
        },
        {
          title: "Evaluated OWASP Top 10 security vectors",
          detail: "Checked injection sinks, secret patterns, and CSRF guards",
        },
        {
          title: "Compared boundaries against Clean Architecture",
          detail: "Detected circular imports and cross-layer coupling hotspots",
        },
        {
          title: "Compiled AgentLog tree & severity findings",
          detail: "Paced row reveal + curved RowConnector guide",
        },
      ],
    },
  },
  {
    match: /showcase their codely usage|dashboard|vulnerabilities edited|bugs crushed|line changes/i,
    plan: {
      mode: "building",
      headline: "Dashboard telemetry synthesis",
      workingLabel: "Aggregating security flex metrics…",
      steps: [
        {
          title: "Read live codely:metrics store",
          detail: "Synced vulnerabilities edited & fixed, bugs crushed, and line counts",
        },
        {
          title: "Built KPI StatCards with delta chips",
          detail: "Mapped 142 fixed CVEs, 389 bugs crushed, and 48,920 line changes",
        },
        {
          title: "Configured Lines Hardened & Bugs Crushed charts",
          detail: "Rendered 12-month comparisons via RevenueChartCard & OrdersChartCard",
        },
      ],
    },
  },
];

export function matchResearchPlan(prompt: string | undefined): ResearchPlan | null {
  if (!prompt) return null;
  return PRESET_PLANS.find((entry) => entry.match.test(prompt))?.plan ?? null;
}

const DEEP_RESEARCH_RE =
  /deep research|research|security audit|vulnerabilit|owasp|cve|exploit|injection|xss|csrf|audit|architect|compar|dependency|dependencies|scan|analy[sz]e/i;

const THINKING_RE =
  /think|reason|debug|bug|refactor|explain|how (does|do|to|can)|why\b|plan|review|dashboard|metrics/i;

/**
 * Classifies live API prompts into an appropriate thinking or deep-research
 * workflow plan so `/api/chat` emits structured lifecycle progress and accurate
 * completion timing for both preset questions and real user prompts.
 */
export function classifyApiResearchPrompt(prompt: string | undefined): ResearchPlan | null {
  if (!prompt) return null;
  const preset = matchResearchPlan(prompt);
  if (preset) return preset;

  if (DEEP_RESEARCH_RE.test(prompt)) {
    return {
      mode: "research",
      headline: "Deep research & analysis",
      workingLabel: "Researching security & architecture context…",
      steps: [
        {
          title: "Scoped security & architecture query",
          detail: "Identified threat vectors, modules, and evaluation criteria",
        },
        {
          title: "Evaluated patterns & risk boundaries",
          detail: "Checked vulnerabilities, dependencies, and architectural trade-offs",
        },
        {
          title: "Synthesizing findings & recommendations",
          detail: "Preparing structured response from live model output",
        },
      ],
    };
  }

  if (THINKING_RE.test(prompt)) {
    return {
      mode: "thinking",
      headline: "Structured thinking",
      workingLabel: "Analyzing prompt & reasoning…",
      steps: [
        {
          title: "Parsed request & constraints",
          detail: "Identified technical context and key questions",
        },
        {
          title: "Evaluating implementation details",
          detail: "Checking edge cases, patterns, and correctness",
        },
        {
          title: "Composing structured response",
          detail: "Formatting clear explanation and actionable guidance",
        },
      ],
    };
  }

  return null;
}
