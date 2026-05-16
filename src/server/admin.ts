import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { env } from "../config/env.js";
import { prisma } from "../db/prisma.js";
import { bot } from "../bot/index.js";

function requireAdmin(request: FastifyRequest, reply: FastifyReply) {
  const key = (request.query as Record<string, string | undefined>).key || request.headers["x-admin-key"];
  if (key !== env.ADMIN_PANEL_KEY) {
    reply.code(401).send({ ok: false, error: "Unauthorized" });
    return false;
  }
  return true;
}

export async function registerAdminRoutes(app: FastifyInstance) {
  app.get("/admin", async (request, reply) => {
    if (!requireAdmin(request, reply)) return;
    const users = await prisma.botUser.count();
    const messages = await prisma.aiMessage.count();
    const errors = await prisma.aiMessage.count({ where: { status: "ERROR" } });

    reply.type("text/html; charset=utf-8").send(`
<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Moataz AI Bot Admin</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Tahoma,Arial;background:#0f172a;color:#e5e7eb;margin:0;padding:32px}
.card{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);border-radius:20px;padding:22px;margin:0 0 16px;box-shadow:0 20px 60px rgba(0,0,0,.25)}
a,button{color:#fff;background:rgba(56,189,248,.22);border:1px solid rgba(125,211,252,.35);padding:10px 14px;border-radius:12px;text-decoration:none;display:inline-block;margin:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}.num{font-size:34px;font-weight:800}
</style>
</head>
<body>
<h1>لوحة Moataz AI Bot</h1>
<div class="grid">
<div class="card"><div>المستخدمون</div><div class="num">${users}</div></div>
<div class="card"><div>رسائل AI</div><div class="num">${messages}</div></div>
<div class="card"><div>الأخطاء</div><div class="num">${errors}</div></div>
</div>
<div class="card">
<a href="/health">Health</a>
<a href="/admin/set-webhook?key=${encodeURIComponent(env.ADMIN_PANEL_KEY)}">Set Webhook</a>
<a href="/admin/stats?key=${encodeURIComponent(env.ADMIN_PANEL_KEY)}">Stats JSON</a>
</div>
</body>
</html>`);
  });

  app.get("/admin/stats", async (request, reply) => {
    if (!requireAdmin(request, reply)) return;
    const [users, allowedUsers, messages, errors, lastMessages] = await Promise.all([
      prisma.botUser.count(),
      prisma.botUser.count({ where: { isAllowed: true } }),
      prisma.aiMessage.count(),
      prisma.aiMessage.count({ where: { status: "ERROR" } }),
      prisma.aiMessage.findMany({ orderBy: { createdAt: "desc" }, take: 10 })
    ]);
    return { ok: true, users, allowedUsers, messages, errors, lastMessages };
  });

  app.get("/admin/set-webhook", async (request, reply) => {
    if (!requireAdmin(request, reply)) return;
    const url = `${env.PUBLIC_URL.replace(/\/$/, "")}/telegram/webhook/${env.TELEGRAM_WEBHOOK_SECRET}`;
    await bot.telegram.setWebhook(url, {
      allowed_updates: ["message", "callback_query"]
    });
    return { ok: true, webhookUrl: url };
  });
}
