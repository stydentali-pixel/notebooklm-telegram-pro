import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { z } from "zod";
import { env } from "../config/env.js";
import { askAi } from "../ai/chat.js";
import { prisma } from "../db/prisma.js";

function requireInternal(request: FastifyRequest, reply: FastifyReply) {
  if (!env.INTERNAL_API_KEY) {
    reply.code(503).send({ ok: false, error: "INTERNAL_API_KEY is not configured" });
    return false;
  }
  if (request.headers["x-internal-api-key"] !== env.INTERNAL_API_KEY) {
    reply.code(401).send({ ok: false, error: "Unauthorized" });
    return false;
  }
  return true;
}

export async function registerInternalRoutes(app: FastifyInstance) {
  app.get("/api/internal/status", async (request, reply) => {
    if (!requireInternal(request, reply)) return;
    return {
      ok: true,
      service: "moataz-ai-telegram-bot",
      time: new Date().toISOString()
    };
  });

  app.post("/api/internal/chat", async (request, reply) => {
    if (!requireInternal(request, reply)) return;
    const schema = z.object({
      prompt: z.string().min(1).max(env.MAX_PROMPT_CHARS),
      provider: z.enum(["OpenRouter", "Gemini", "Groq"]).optional(),
      model: z.string().optional(),
      telegramId: z.string().optional()
    });
    const body = schema.parse(request.body);
    const result = await askAi(body.prompt, body.provider ? { provider: body.provider, model: body.model } : undefined);

    await prisma.aiMessage.create({
      data: {
        telegramId: body.telegramId || "internal",
        provider: result.provider,
        model: result.model,
        prompt: body.prompt,
        response: result.text,
        status: "OK",
        tokens: typeof result.usage?.totalTokens === "number" ? result.usage.totalTokens : null
      }
    });

    return { ok: true, ...result };
  });
}
