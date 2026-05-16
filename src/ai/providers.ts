import { env } from "../config/env.js";

export type ProviderName = "openrouter" | "gemini" | "groq";

export interface AiResult {
  provider: ProviderName;
  model: string;
  text: string;
}

function withTimeout(ms: number): AbortSignal {
  const controller = new AbortController();
  setTimeout(() => controller.abort(), ms).unref();
  return controller.signal;
}

async function postJson<T>(url: string, headers: Record<string, string>, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
    signal: withTimeout(env.REQUEST_TIMEOUT_MS)
  });

  const text = await res.text();
  if (!res.ok) throw new Error(`AI API error ${res.status}: ${text.slice(0, 800)}`);
  return JSON.parse(text) as T;
}

async function openRouter(prompt: string): Promise<AiResult> {
  if (!env.OPENROUTER_API_KEY) throw new Error("OPENROUTER_API_KEY is missing");
  const data = await postJson<any>(
    "https://openrouter.ai/api/v1/chat/completions",
    {
      authorization: `Bearer ${env.OPENROUTER_API_KEY}`,
      "http-referer": env.PUBLIC_URL,
      "x-title": env.BOT_NAME
    },
    {
      model: env.OPENROUTER_MODEL,
      messages: [
        { role: "system", content: "أنت مساعد عربي دقيق ومباشر. أجب بوضوح وبدون إطالة غير ضرورية." },
        { role: "user", content: prompt }
      ]
    }
  );
  return { provider: "openrouter", model: env.OPENROUTER_MODEL, text: data?.choices?.[0]?.message?.content || "لم يصل رد من النموذج." };
}

async function groq(prompt: string): Promise<AiResult> {
  if (!env.GROQ_API_KEY) throw new Error("GROQ_API_KEY is missing");
  const data = await postJson<any>(
    "https://api.groq.com/openai/v1/chat/completions",
    { authorization: `Bearer ${env.GROQ_API_KEY}` },
    {
      model: env.GROQ_MODEL,
      messages: [
        { role: "system", content: "أنت مساعد عربي دقيق ومباشر. أجب بوضوح وبدون إطالة غير ضرورية." },
        { role: "user", content: prompt }
      ]
    }
  );
  return { provider: "groq", model: env.GROQ_MODEL, text: data?.choices?.[0]?.message?.content || "لم يصل رد من النموذج." };
}

async function gemini(prompt: string): Promise<AiResult> {
  if (!env.GEMINI_API_KEY) throw new Error("GEMINI_API_KEY is missing");
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(env.GEMINI_MODEL)}:generateContent?key=${env.GEMINI_API_KEY}`;
  const data = await postJson<any>(url, {}, {
    contents: [{ role: "user", parts: [{ text: prompt }] }],
    systemInstruction: { parts: [{ text: "أنت مساعد عربي دقيق ومباشر. أجب بوضوح وبدون إطالة غير ضرورية." }] }
  });
  const text = data?.candidates?.[0]?.content?.parts?.map((p: any) => p.text).filter(Boolean).join("\n") || "لم يصل رد من النموذج.";
  return { provider: "gemini", model: env.GEMINI_MODEL, text };
}

export async function generateAnswer(prompt: string, provider: ProviderName = env.DEFAULT_AI_PROVIDER): Promise<AiResult> {
  if (provider === "openrouter") return openRouter(prompt);
  if (provider === "gemini") return gemini(prompt);
  return groq(prompt);
}
