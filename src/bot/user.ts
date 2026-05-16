import type { Context } from "telegraf";
import { env } from "../config/env.js";
import { prisma } from "../db/prisma.js";

export async function upsertTelegramUser(ctx: Context) {
  const from = ctx.from;
  if (!from) return null;

  const isOwner = String(from.id) === env.TELEGRAM_OWNER_ID;

  return prisma.botUser.upsert({
    where: { telegramId: String(from.id) },
    create: {
      telegramId: String(from.id),
      username: from.username || null,
      firstName: from.first_name || null,
      lastName: from.last_name || null,
      role: isOwner ? "OWNER" : "USER",
      isAllowed: isOwner || env.ALLOW_ALL_USERS
    },
    update: {
      username: from.username || null,
      firstName: from.first_name || null,
      lastName: from.last_name || null,
      ...(isOwner ? { role: "OWNER" as const, isAllowed: true } : {})
    }
  });
}

export async function canUseBot(ctx: Context) {
  const user = await upsertTelegramUser(ctx);
  if (!user) return false;
  if (user.role === "BLOCKED") return false;
  return user.isAllowed || user.role === "OWNER" || user.role === "ADMIN" || user.role === "FAMILY";
}
