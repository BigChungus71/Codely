import { createAnthropic } from "@ai-sdk/anthropic";
import { createGoogleGenerativeAI } from "@ai-sdk/google";
import { createOpenAI } from "@ai-sdk/openai";
import { createGateway, type LanguageModel } from "ai";

export type KnownProviderId =
  | "anthropic"
  | "openrouter"
  | "openai"
  | "google"
  | "gateway"
  | "groq"
  | "xai"
  | "mistral"
  | "deepseek";

/** "custom" is any OpenAI-compatible server named by AI_BASE_URL alone. */
export type ProviderId = KnownProviderId | "custom";

interface ProviderSpec {
  label: string;
  /** The variable the provider's own SDK and docs use — the explicit form. */
  envKey: string;
  /** Prefix the provider mints its keys with, for reading AI_API_KEY. Absent
   *  when the keys have no recognisable shape and AI_PROVIDER must say. */
  prefix?: string;
  defaultModel: string;
  /** Chat-completions endpoint, for providers spoken to over the OpenAI wire
   *  format rather than a native SDK. */
  baseURL?: string;
}

/**
 * Order matters twice over: "sk-ant-" and "sk-or-" must be tried before the
 * plain "sk-" OpenAI shape they extend, and when several explicit variables
 * are set the first one here wins (set AI_PROVIDER to be exact).
 */
const PROVIDERS: Record<KnownProviderId, ProviderSpec> = {
  anthropic: {
    label: "Anthropic",
    envKey: "ANTHROPIC_API_KEY",
    prefix: "sk-ant-",
    defaultModel: "claude-haiku-4-5",
  },
  openrouter: {
    label: "OpenRouter",
    envKey: "OPENROUTER_API_KEY",
    prefix: "sk-or-",
    defaultModel: "openai/gpt-5-nano",
    baseURL: "https://openrouter.ai/api/v1",
  },
  openai: {
    label: "OpenAI",
    envKey: "OPENAI_API_KEY",
    prefix: "sk-",
    defaultModel: "gpt-5.4-mini",
  },
  google: {
    label: "Google",
    envKey: "GOOGLE_GENERATIVE_AI_API_KEY",
    prefix: "AIza",
    defaultModel: "gemini-2.5-flash",
  },
  gateway: {
    label: "Vercel AI Gateway",
    envKey: "AI_GATEWAY_API_KEY",
    prefix: "vck_",
    defaultModel: "openai/gpt-5-nano",
  },
  groq: {
    label: "Groq",
    envKey: "GROQ_API_KEY",
    prefix: "gsk_",
    defaultModel: "llama-3.3-70b-versatile",
    baseURL: "https://api.groq.com/openai/v1",
  },
  xai: {
    label: "xAI",
    envKey: "XAI_API_KEY",
    prefix: "xai-",
    defaultModel: "grok-4-fast-non-reasoning",
    baseURL: "https://api.x.ai/v1",
  },
  mistral: {
    label: "Mistral",
    envKey: "MISTRAL_API_KEY",
    defaultModel: "mistral-small-latest",
    baseURL: "https://api.mistral.ai/v1",
  },
  deepseek: {
    label: "DeepSeek",
    envKey: "DEEPSEEK_API_KEY",
    defaultModel: "deepseek-chat",
    baseURL: "https://api.deepseek.com/v1",
  },
};

const PROVIDER_IDS = Object.keys(PROVIDERS) as KnownProviderId[];

export type Provider = {
  id: ProviderId;
  /** Surfaced to the UI so the composer can show what is answering. */
  label: string;
  modelId: string;
  model: LanguageModel;
};

/** Either a usable provider or the one sentence explaining why there is none. */
export type Resolution = { provider: Provider; reason?: undefined } | { provider: null; reason: string };

/** Empty and whitespace-only values count as unset — a blank field in a deploy
 *  wizard should not read as a key. */
function env(name: string): string | undefined {
  const value = process.env[name]?.trim();
  return value ? value : undefined;
}

function buildModel(id: ProviderId, apiKey: string, modelId: string, baseURL?: string): LanguageModel {
  switch (id) {
    case "openai":
      return createOpenAI({ apiKey, baseURL })(modelId);
    case "anthropic":
      return createAnthropic({ apiKey, baseURL })(modelId);
    case "google":
      return createGoogleGenerativeAI({ apiKey, baseURL })(modelId);
    case "gateway":
      return createGateway({ apiKey, baseURL })(modelId);
    default:
      // Everyone else speaks OpenAI's chat-completions format. `.chat` is
      // deliberate: the bare provider call targets the Responses API, which
      // most compatible servers do not serve.
      return createOpenAI({
        apiKey,
        baseURL: baseURL ?? (id === "custom" ? undefined : PROVIDERS[id].baseURL),
      }).chat(modelId);
  }
}

export function resolveProvider(): Resolution {
  const single = env("AI_API_KEY");
  const named = env("AI_PROVIDER")?.toLowerCase();
  const baseURL = env("AI_BASE_URL");
  const modelOverride = env("CHAT_MODEL");

  const build = (id: ProviderId, apiKey: string, defaultModel: string, label: string): Resolution => {
    const modelId = modelOverride ?? defaultModel;
    return { provider: { id, label, modelId, model: buildModel(id, apiKey, modelId, baseURL) } };
  };

  // 1. Named outright. The only way to reach a provider whose keys carry no
  //    recognisable prefix, and the tie-breaker when several keys are set.
  if (named) {
    if (named === "custom") {
      if (!baseURL) return { provider: null, reason: "AI_PROVIDER=custom needs AI_BASE_URL to say where the server is." };
    } else if (!(named in PROVIDERS)) {
      return {
        provider: null,
        reason: `Unknown AI_PROVIDER "${named}". Use one of: ${PROVIDER_IDS.join(", ")}, custom.`,
      };
    } else {
      const spec = PROVIDERS[named as KnownProviderId];
      const apiKey = env(spec.envKey) ?? single;
      if (!apiKey) return { provider: null, reason: `AI_PROVIDER is ${named} but neither ${spec.envKey} nor AI_API_KEY is set.` };
      return build(named as KnownProviderId, apiKey, spec.defaultModel, spec.label);
    }
  }

  // 2. A provider's own conventional variable.
  if (!named) {
    for (const id of PROVIDER_IDS) {
      const apiKey = env(PROVIDERS[id].envKey);
      if (apiKey) return build(id, apiKey, PROVIDERS[id].defaultModel, PROVIDERS[id].label);
    }
  }

  // 3. The single key, read by its shape.
  if (single && !named) {
    for (const id of PROVIDER_IDS) {
      const prefix = PROVIDERS[id].prefix;
      if (prefix && single.startsWith(prefix)) {
        return build(id, single, PROVIDERS[id].defaultModel, PROVIDERS[id].label);
      }
    }
  }

  // 4. Any OpenAI-compatible server by URL. Local ones (Ollama, LM Studio)
  //    take no key at all, so a placeholder keeps the SDK from demanding one.
  if (baseURL) {
    if (!modelOverride) {
      return { provider: null, reason: "AI_BASE_URL is set but CHAT_MODEL is not. Name the model the server should run." };
    }
    return build("custom", single ?? "none", modelOverride, "Custom endpoint");
  }

  if (single) {
    return {
      provider: null,
      reason: "AI_API_KEY is set but its shape is not one this route recognises. Add AI_PROVIDER to name the provider.",
    };
  }
  return {
    provider: null,
    reason:
      "No model provider key found. Set AI_API_KEY to a key from OpenAI, Anthropic, Google, OpenRouter, Groq, xAI, or Vercel AI Gateway, then redeploy.",
  };
}
