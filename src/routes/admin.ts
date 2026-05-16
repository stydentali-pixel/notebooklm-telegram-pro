import type { FastifyInstance, FastifyRequest } from "fastify";
import { env } from "../config/env.js";
import { getWebhookInfo, setWebhook } from "../telegram/client.js";

function checkAdmin(req: FastifyRequest): boolean {
  const key = (req.query as any)?.key || req.headers["x-admin-key"];
  return key === env.ADMIN_PANEL_KEY;
}

export async function adminRoutes(app: FastifyInstance) {
  app.get("/admin", async (req, reply) => {
    if (!checkAdmin(req)) return reply.code(401).send("Unauthorized");
    return reply.type("text/html; charset=utf-8").send(`<!doctype html>
<html lang="ar" dir="rtl">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${env.BOT_NAME}</title>
<style>body{font-family:system-ui;background:#0b1020;color:#eef;margin:0;padding:30px}.card{max-width:780px;margin:auto;background:#121a33;border:1px solid #26345f;border-radius:22px;padding:24px;box-shadow:0 15px 45px #0005}a,button{display:inline-block;margin:8px 0;padding:12px 16px;border-radius:14px;background:#355cff;color:white;text-decoration:none;border:0}code{background:#071022;padding:3px 7px;border-radius:8px}</style></head>
<body><div class="card"><h1>${env.BOT_NAME}</h1><p>بوت AI يعمل على Railway بدون قاعدة بيانات.</p><p><b>Provider:</b> <code>${env.DEFAULT_AI_PROVIDER}</code></p><p><b>Public URL:</b> <code>${env.PUBLIC_URL}</code></p><a href="/health">Health</a> <a href="/admin/webhook-info?key=${env.ADMIN_PANEL_KEY}">Webhook Info</a> <a href="/admin/set-webhook?key=${env.ADMIN_PANEL_KEY}">Set Webhook</a></div></body></html>`);
  });

  app.get("/admin/set-webhook", async (req, reply) => {
    if (!checkAdmin(req)) return reply.code(401).send({ ok: false, error: "Unauthorized" });
    const result = await setWebhook();
    return reply.send({ ok: true, result });
  });

  app.get("/admin/webhook-info", async (req, reply) => {
    if (!checkAdmin(req)) return reply.code(401).send({ ok: false, error: "Unauthorized" });
    const result = await getWebhookInfo();
    return reply.send({ ok: true, result });
  });
}
