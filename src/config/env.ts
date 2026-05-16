import "dotenv/config";
import { z } from "zod";

const envSchema = z.object({
  NODE_ENV: z.string().default("production"),
  PORT: z.coerce.number().default(3000),
  PUBLIC_URL: z.string().url(),
  SITE_URL: z.string().optional(),

  TELEGRAM_BOT_TOKEN: z.string().min(20),
  TELEGRAM_OWNER_ID: z.string().min(1),
  TELEGRAM_WEBHOOK_SECRET: z.string().min(8),

  ADMIN_PANEL_KEY: z.string().min(8),
  INTERNAL_API_KEY: z.string().min(8).optional(),

  DATABASE_URL: z.string().min(1),
  DIRECT_URL: z.string().min(1),

  SUPABASE_URL: z.string().optional(),
  SUPABASE_ANON_KEY: z.string().optional(),
  SUPABASE_SERVICE_ROLE_KEY: z.string().optional(),

  DEFAULT_AI_PROVIDER: z.enum(["OpenRouter", "Gemini", "Groq"]).default("OpenRouter"),

  OPENROUTER_API_KEY: z.string().optional(),
  OPENROUTER_MODEL: z.string().default("openai/gpt-4o-mini"),
  OPENROUTER_BASE_URL: z.string().url().default("https://openrouter.ai/api/v1"),
  OPENROUTER_APP_NAME: z.string().default("Moataz AI Telegram Bot"),
  OPENROUTER_SITE_URL: z.string().optional(),

  GEMINI_API_KEY: z.string().optional(),
  GEMINI_MODEL: z.string().default("gemini-1.5-flash"),

  GROQ_API_KEY: z.string().optional(),
  GROQ_MODEL: z.string().default("llama-3.1-8b-instant"),

  MAX_PROMPT_CHARS: z.coerce.number().default(4000),
  MAX_OUTPUT_TOKENS: z.coerce.number().default(1200),
  ALLOW_ALL_USERS: z.coerce.boolean().default(false)
});

export const env = envSchema.parse(process.env);
