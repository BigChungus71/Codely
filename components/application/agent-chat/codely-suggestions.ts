/**
 * Codely — Starter phrases shown in the empty-state suggestion pills.
 *
 * All 25 phrases are friendly, security / code-quality focused, and
 * on-brand with the Codely slogan "crush every bug like a pro."
 * Five are shown at a time, shuffled on each new thread.
 */

export const CODELY_SUGGESTIONS = [
  "Hello Team, what shall we build today?",
  "Let's crush every bug like a pro — what's first?",
  "Show me the top vulnerabilities in this repo.",
  "Compare my architecture against Clean Architecture principles.",
  "Which dependencies are out of date or have known CVEs?",
  "Walk me through the biggest security risks in my codebase.",
  "Help me refactor this module for better separation of concerns.",
  "What are the most common OWASP issues in this project?",
  "Give me a code review checklist for my pull request.",
  "Where are the performance bottlenecks in this code?",
  "Explain the architectural flaws you found.",
  "Suggest a plan to migrate from a monolith to microservices.",
  "Which files have the highest cyclomatic complexity?",
  "Find all hardcoded secrets or credentials in this repository.",
  "What tests are missing for the core business logic?",
  "Help me write a security patch for the top critical finding.",
  "Generate a threat model for this application.",
  "What's the fastest win I can make to improve code quality?",
  "Show me all deprecated APIs used in this project.",
  "Scan my latest push and summarise the new issues.",
  "How does my project compare to industry best practices?",
  "Create a prioritised fix roadmap from the scan results.",
  "What would a senior code reviewer flag in this file?",
  "Let's start a new scan — drop a file or paste a GitHub link.",
  "What can Codely help me build — or protect — today?",
] as const;

/** Returns `count` unique suggestions in a random order. */
export function pickSuggestions(count = 5): string[] {
  return [...CODELY_SUGGESTIONS]
    .sort(() => Math.random() - 0.5)
    .slice(0, count);
}
