import { createOpenAI } from "@ai-sdk/openai";
import { createGoogleGenerativeAI } from "@ai-sdk/google";
import { createGroq } from "@ai-sdk/groq";
import type { LanguageModel } from "ai";
import { env } from "../config/env.js";

export type ProviderName = "OpenRouter" | "Gemini" | "Groq";

export type AiSelection = {
  provider: ProviderName;
  model: string;
};

export function getDefaultSelection(): AiSelection {
  if (env.DEFAULT_AI_PROVIDER === "Gemini") return { provider: "Gemini", model: env.GEMINI_MODEL };
  if (env.DEFAULT_AI_PROVIDER === "Groq") return { provider: "Groq", model: env.GROQ_MODEL };
  return { provider: "OpenRouter", model: env.OPENROUTER_MODEL };
}

export function getProviderModel(provider: ProviderName, model?: string): LanguageModel {
  if (provider === "OpenRouter") {
    if (!env.OPENROUTER_API_KEY) throw new Error("OPENROUTER_API_KEY is missing");
    const openrouter = createOpenAI({
      apiKey: env.OPENROUTER_API_KEY,
      baseURL: env.OPENROUTER_BASE_URL,
      headers: {
        "HTTP-Referer": env.OPENROUTER_SITE_URL || env.PUBLIC_URL,
        "X-Title": env.OPENROUTER_APP_NAME
      }
    });
    return openrouter(model || env.OPENROUTER_MODEL);
  }

  if (provider === "Gemini") {
    if (!env.GEMINI_API_KEY) throw new Error("GEMINI_API_KEY is missing");
    const google = createGoogleGenerativeAI({ apiKey: env.GEMINI_API_KEY });
    return google(model || env.GEMINI_MODEL);
  }

  if (provider === "Groq") {
    if (!env.GROQ_API_KEY) throw new Error("GROQ_API_KEY is missing");
    const groq = createGroq({ apiKey: env.GROQ_API_KEY });
    return groq(model || env.GROQ_MODEL);
  }

  throw new Error(`Unsupported provider: ${provider}`);
}

export function listConfiguredProviders() {
  return [
    { provider: "OpenRouter", model: env.OPENROUTER_MODEL, ready: Boolean(env.OPENROUTER_API_KEY) },
    { provider: "Gemini", model: env.GEMINI_MODEL, ready: Boolean(env.GEMINI_API_KEY) },
    { provider: "Groq", model: env.GROQ_MODEL, ready: Boolean(env.GROQ_API_KEY) }
  ] as const;
}
