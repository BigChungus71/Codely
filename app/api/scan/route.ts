import { generateText } from "ai";
import { z } from "zod";
import { resolveProvider } from "@/app/api/_lib/ai-provider";
import type { ScanFinding } from "@/components/application/scanner/scanner-results";

export const maxDuration = 30;

const ScanRequestSchema = z.object({
  githubUrl: z.string().trim().max(500).optional().default(""),
  files: z
    .array(
      z.object({
        name: z.string().trim().min(1).max(260),
        size: z.number().int().nonnegative().optional(),
        content: z.string().max(24_000).optional(),
      }),
    )
    .max(20)
    .optional()
    .default([]),
  config: z.object({
    security: z.boolean(),
    dependencies: z.boolean(),
    architecture: z.boolean(),
    comparison: z.boolean(),
    baseline: z.string().trim().max(80),
  }),
});

const FindingsArraySchema = z.array(
  z.object({
    id: z.string().optional(),
    severity: z.enum(["critical", "high", "medium", "low", "info"]),
    title: z.string().min(1),
    description: z.string().min(1),
    file: z.string().optional(),
    line: z.number().int().positive().optional(),
    recommendation: z.string().optional(),
  }),
);

function extractJsonArray(raw: string): unknown {
  const fenced = raw.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const candidate = (fenced ? fenced[1] : raw).trim();
  const start = candidate.indexOf("[");
  const end = candidate.lastIndexOf("]");
  if (start === -1 || end === -1 || end <= start) return [];
  return JSON.parse(candidate.slice(start, end + 1));
}

export async function POST(req: Request) {
  const startedAt = Date.now();
  const { provider, reason } = resolveProvider();
  if (!provider) {
    return Response.json({ configured: false, error: "missing_api_key", message: reason }, { status: 503 });
  }

  let rawBody: unknown;
  try {
    rawBody = await req.json();
  } catch {
    return Response.json({ error: "invalid_body", message: "Expected JSON payload." }, { status: 400 });
  }

  const parsed = ScanRequestSchema.safeParse(rawBody);
  if (!parsed.success) {
    return Response.json({ error: "invalid_scan_request", message: parsed.error.message }, { status: 400 });
  }

  const { githubUrl, files, config } = parsed.data;
  if (githubUrl || !files.some((file) => file.content?.trim())) {
    return Response.json(
      { error: "missing_target", message: "Provide a supported text file for AI review. Use the repository scanner for configured checkouts." },
      { status: 400 },
    );
  }

  const enabledChecks = [
    config.security && "Security vulnerabilities (OWASP Top 10, injection, secrets, XSS, CSRF)",
    config.dependencies && "Dependency & lockfile CVE risks",
    config.architecture && "Architecture quality (coupling, circular dependencies, boundaries)",
    config.comparison && `Architecture comparison against ${config.baseline} baseline`,
  ]
    .filter(Boolean)
    .join("\n- ");

  const filesSummary = files
    .map((f) =>
      f.content
        ? `### File: ${f.name}\n\`\`\`\n${f.content}\n\`\`\``
        : `### File: ${f.name} (${f.size ?? 0} bytes, binary or preview unavailable)`,
    )
    .join("\n\n");

  const prompt = [
    "Offer only defensive review suggestions grounded in the submitted text. Do not propose exploits or reproduction steps.",
    enabledChecks ? `Enabled checks:\n- ${enabledChecks}` : "Enabled checks: general static review",
    filesSummary ? `\nSubmitted files:\n${filesSummary}` : "",
    "",
    "Respond ONLY with a valid JSON array of finding objects matching:",
    `[{"severity":"critical|high|medium|low|info","title":"...","description":"...","file":"optional/path","line":12,"recommendation":"..."}]`,
    "Only cite specific files or line numbers that were actually provided in the submitted files.",
  ]
    .filter(Boolean)
    .join("\n");

  const result = await generateText({
    model: provider.model,
    system:
      "You are Codely's static security and architecture analysis engine. Return strictly a JSON array of findings with accurate severity, clear descriptions, and actionable recommendations.",
    prompt,
    abortSignal: req.signal,
  });

  let findings: ScanFinding[];
  try {
    const validated = FindingsArraySchema.parse(extractJsonArray(result.text));
    const provided = new Map(files.filter((file) => file.content).map((file) => [file.name, file.content!]));
    findings = validated.map((item, index) => {
      if (item.file && !provided.has(item.file)) throw new Error("Unknown source path");
      if (item.line !== undefined && (!item.file || !Number.isInteger(item.line) || item.line < 1
          || item.line > provided.get(item.file)!.split("\n").length)) throw new Error("Invalid source line");
      return { ...item, id: item.id || `review-${index + 1}` };
    });
  } catch {
    return Response.json({ error: "invalid_review", message: "The AI provider did not return a source-grounded review." }, { status: 502 });
  }

  const completedAt = Date.now();
  return Response.json({
    configured: true,
    provider: provider.label,
    model: provider.modelId,
    findings,
    durationMs: Math.max(0, completedAt - startedAt),
  });
}
