import Fastify from "fastify";
import cors from "@fastify/cors";
import { env } from "./config/env.js";
import { handleUpdate } from "./telegram/handler.js";
import { adminRoutes } from "./routes/admin.js";
import { internalRoutes } from "./routes/internal.js";
import type { TelegramUpdate } from "./telegram/types.js";

const app = Fastify({ logger: true, trustProxy: true });
await app.register(cors, { origin: true });

app.get("/", async () => ({ ok: true, name: env.BOT_NAME, service: "telegram-ai-bot", db: false }));
app.get("/health", async () => ({ ok: true, time: new Date().toISOString(), db: false, provider: env.DEFAULT_AI_PROVIDER }));

app.post(`/telegram/webhook/${env.TELEGRAM_WEBHOOK_SECRET}`, async (request, reply) => {
  const update = request.body as TelegramUpdate;
  await handleUpdate(update);
  return reply.send({ ok: true });
});

await app.register(adminRoutes);
await app.register(internalRoutes);

app.listen({ port: env.PORT, host: "0.0.0.0" }).catch((err) => {
  app.log.error(err);
  process.exit(1);
});
