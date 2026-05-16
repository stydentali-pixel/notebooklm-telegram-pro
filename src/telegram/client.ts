import { env } from "../config/env.js";

const API = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}`;

type TelegramResponse<T> = { ok: true; result: T } | { ok: false; description?: string; error_code?: number };

async function tg<T>(method: string, payload?: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${API}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload ?? {})
  });
  const data = (await res.json()) as TelegramResponse<T>;
  if (!data.ok) throw new Error(data.description || `Telegram ${method} failed`);
  return data.result;
}

export async function sendMessage(chatId: number | string, text: string, extra: Record<string, unknown> = {}) {
  return tg("sendMessage", {
    chat_id: chatId,
    text,
    parse_mode: "HTML",
    disable_web_page_preview: true,
    ...extra
  });
}

export async function sendTyping(chatId: number | string) {
  return tg("sendChatAction", { chat_id: chatId, action: "typing" });
}

export async function setWebhook() {
  const url = `${env.PUBLIC_URL.replace(/\/$/, "")}/telegram/webhook/${env.TELEGRAM_WEBHOOK_SECRET}`;
  return tg("setWebhook", {
    url,
    allowed_updates: ["message", "callback_query"],
    drop_pending_updates: true
  });
}

export async function deleteWebhook() {
  return tg("deleteWebhook", { drop_pending_updates: false });
}

export async function getWebhookInfo() {
  return tg("getWebhookInfo");
}
