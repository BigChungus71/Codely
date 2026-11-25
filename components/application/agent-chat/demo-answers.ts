/**
 * What Codely says when there is no model behind it.
 *
 * Demo mode exists so a fresh deploy can be tried before a key is added: the
 * screen, the streaming, the history all behave as they do with a model, and
 * only the words are canned.
 */

type DemoAnswer = { match: RegExp; reply: string };

const ANSWERS: DemoAnswer[] = [
  {
    match: /thinking|composer.?loader|agent.?thinking|shimmer|indicator/i,
    reply:
      "Codely pairs `AgentThinking` (four animated states: wave, spin, stars, infinity with a shimmering status label) and `ComposerLoader` (an orbiting 4-stop iridescent rim light around the pill composer) so users get immediate, calm visual feedback while code scans or reasoning streams run.",
  },
  {
    match: /agent.?log|research|stream|transcript|reveal/i,
    reply:
      "Our `AgentLog` engine paces multi-step research and build logs one unit at a time — blurring each row in over 0.42s with a soft bottom mask while a curved tree guide draws alongside it, keeping long security audits readable without layout jumps.",
  },
  {
    match: /dashboard|flex|vulnerabilities fixed|bugs crushed|lines changed/i,
    reply:
      "Your Codely Dashboard tracks 142 vulnerabilities fixed, 389 bugs crushed, 48,920 lines hardened to date, and a 98.4% security score using `StatCards`, `RevenueChartCard`, and `OrdersChartCard` — built to flex your team's security impact at a glance.",
  },
  {
    match: /starter|what (is|does) this|about this app|codely/i,
    reply:
      "This is Codely — your AI-powered code security scanner and architecture reviewer. Drop a file or paste a GitHub link, and I'll scan for vulnerabilities, dependency risks, and architectural flaws so you can crush every bug like a pro. Right now I'm in demo mode, so this answer is scripted. Connect a model key to unlock full analysis.",
  },
  {
    match: /product update|announcement|release notes|changelog/i,
    reply:
      "Here's a Codely update in three sentences. This release adds real-time vulnerability scanning for uploaded files and GitHub repos, an OWASP-mapped findings view with severity chips, and a conversational fix-suggestion flow powered by your own model. Every result is explained in plain language so your whole team can act on it immediately.",
  },
  {
    match: /names?\b.*\b(app|product|scheduling|startup|company)|name ideas|suggest.*names/i,
    reply:
      "Five names for a security-first dev tool: ShieldScript, VaultCode, PatchForge, BugCrusher, and SentinelCI. ShieldScript signals protection, VaultCode implies safety, PatchForge suggests active fixing, BugCrusher echoes the Codely slogan, and SentinelCI fits the CI/CD pipeline context.",
  },
  {
    match: /\b(hello|hi|hey)\b|good (morning|afternoon|evening)/i,
    reply:
      "Hello! I'm Codely — here to help you crush every bug like a pro. Drop a file, paste a GitHub link, or just ask me a security question to get started.",
  },
  {
    match: /vulnerabilit|security|owasp|cve|exploit|injection|xss|csrf/i,
    reply:
      "Great question. Codely scans for OWASP Top 10 issues (injection, broken auth, XSS, IDOR, misconfigurations, and more), known CVEs in your dependency tree, hardcoded secrets, and insecure API patterns. Drop a file or repo link to see a prioritised findings list.",
  },
  {
    match: /architect|pattern|monolith|microservice|hexagonal|clean/i,
    reply:
      "Codely compares your project's layer structure against reference architectures — Clean Architecture, Hexagonal, MVC, and more. It flags circular dependencies, boundary violations, and over-coupled modules, then suggests concrete refactoring steps to bring your design back on track.",
  },
  {
    match: /scan|upload|github|repo|repository/i,
    reply:
      "To run a scan, paste a GitHub repo URL or drop a file (zip, tar.gz, or individual source files) into the scanner. Codely will check for security issues, outdated dependencies, and architectural smells, then walk you through the findings conversationally.",
  },
];

const FALLBACK =
  "I'm Codely, here to crush every bug like a pro. Try asking me to scan a repo, explain a vulnerability, or review your architecture. You can also drop a file or paste a GitHub link to start a live analysis.";

export function pickDemoAnswer(prompt: string): string {
  return ANSWERS.find((answer) => answer.match.test(prompt))?.reply ?? FALLBACK;
}
