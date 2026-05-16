import Fastify from "fastify";
import { env } from "../config/env.js";
import { bot } from "../bot/index.js";
import { prisma } from "../db/prisma.js";
import { registerAdminRoutes } from "./admin.js";
import { registerInternalRoutes } from "./internal.js";

export async function buildApp() {
  const app = Fastify({ logger: true });

  app.get("/", async () => ({
    ok: true,
    name: "Moataz AI Telegram Bot",
    health: "/health"
  }));

  app.get("/health", async () => {
    await prisma.$queryRaw`SELECT 1`;
    return {
      ok: true,
      service: "moataz-ai-telegram-bot",
      mode: "webhook",
      time: new Date().toISOString()
    };
  });

  app.post("/telegram/webhook/:secret", async (request, reply) => {
    const { secret } = request.params as { secret: string };
    if (secret !== env.TELEGRAM_WEBHOOK_SECRET) {
      return reply.code(401).send({ ok: false, error: "Invalid webhook secret" });
    }
    await bot.handleUpdate(request.body as any);
    return { ok: true };
  });

  await registerAdminRoutes(app);
  await registerInternalRoutes(app);

  return app;
}
