import { z } from "zod";

const envSchema = z.object({
  NODE_ENV: z.string().default("production"),
  PORT: z.coerce.number().default(3000),
  PUBLIC_URL: z.string().url(),

  TELEGRAM_BOT_TOKEN: z.string().min(20),
  TELEGRAM_OWNER_ID: z.string().min(3),
  TELEGRAM_WEBHOOK_SECRET: z.string().min(8),

  ADMIN_PANEL_KEY: z.string().min(8),
  INTERNAL_API_KEY: z.string().min(12).optional().default(""),

  DEFAULT_AI_PROVIDER: z.enum(["openrouter", "gemini", "groq"]).default("openrouter"),
  OPENROUTER_API_KEY: z.string().optional().default(""),
  OPENROUTER_MODEL: z.string().default("openai/gpt-4o-mini"),
  GEMINI_API_KEY: z.string().optional().default(""),
  GEMINI_MODEL: z.string().default("gemini-1.5-flash"),
  GROQ_API_KEY: z.string().optional().default(""),
  GROQ_MODEL: z.string().default("llama-3.1-8b-instant"),

  BOT_NAME: z.string().default("Moataz AI"),
  MAX_PROMPT_CHARS: z.coerce.number().default(4000),
  REQUEST_TIMEOUT_MS: z.coerce.number().default(60000),
  ALLOWED_USER_IDS: z.string().optional().default("")
});

export const env = envSchema.parse(process.env);

export function allowedUserIds(): Set<string> {
  const ids = env.ALLOWED_USER_IDS.split(",").map((x) => x.trim()).filter(Boolean);
  ids.push(env.TELEGRAM_OWNER_ID);
  return new Set(ids);
}
