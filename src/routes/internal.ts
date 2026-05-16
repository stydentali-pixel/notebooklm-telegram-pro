import type { FastifyInstance, FastifyRequest } from "fastify";
import { env } from "../config/env.js";
import { generateAnswer, ProviderName } from "../ai/providers.js";

function checkInternal(req: FastifyRequest): boolean {
  if (!env.INTERNAL_API_KEY) return false;
  return req.headers["x-internal-api-key"] === env.INTERNAL_API_KEY;
}

export async function internalRoutes(app: FastifyInstance) {
  app.get("/api/internal/status", async (req, reply) => {
    if (!checkInternal(req)) return reply.code(401).send({ ok: false, error: "Unauthorized" });
    return { ok: true, service: "moataz-ai-railway-nodb-bot", db: false, provider: env.DEFAULT_AI_PROVIDER, time: new Date().toISOString() };
  });

  app.post("/api/internal/chat", async (req, reply) => {
    if (!checkInternal(req)) return reply.code(401).send({ ok: false, error: "Unauthorized" });
    const body = req.body as { prompt?: string; provider?: ProviderName };
    if (!body?.prompt) return reply.code(400).send({ ok: false, error: "prompt is required" });
    const result = await generateAnswer(body.prompt, body.provider || env.DEFAULT_AI_PROVIDER);
    return { ok: true, result };
  });
}
