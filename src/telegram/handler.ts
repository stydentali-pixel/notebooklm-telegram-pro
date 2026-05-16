import { allowedUserIds, env } from "../config/env.js";
import { generateAnswer, ProviderName } from "../ai/providers.js";
import { chunkText, safeMessage } from "../utils/text.js";
import { sendMessage, sendTyping } from "./client.js";
import type { TelegramUpdate } from "./types.js";

const userProvider = new Map<string, ProviderName>();

function isAllowed(userId: number): boolean {
  const allowed = allowedUserIds();
  return allowed.has(String(userId));
}

function mainKeyboard() {
  return {
    reply_markup: {
      inline_keyboard: [
        [{ text: "🤖 اسأل الذكاء الاصطناعي", callback_data: "help_ai" }],
        [
          { text: "OpenRouter", callback_data: "provider:openrouter" },
          { text: "Gemini", callback_data: "provider:gemini" },
          { text: "Groq", callback_data: "provider:groq" }
        ],
        [{ text: "📊 الحالة", callback_data: "status" }]
      ]
    }
  };
}

async function answerAi(chatId: number, userId: number, prompt: string) {
  const clean = prompt.trim().slice(0, env.MAX_PROMPT_CHARS);
  if (!clean) {
    await sendMessage(chatId, "اكتب السؤال بعد الأمر هكذا:\n<code>/ai ما هو أفضل تصميم للبوت؟</code>");
    return;
  }

  await sendTyping(chatId);
  const provider = userProvider.get(String(userId)) || env.DEFAULT_AI_PROVIDER;
  const result = await generateAnswer(clean, provider);
  const full = `🤖 <b>${result.provider}</b> / <code>${result.model}</code>\n\n${result.text}`;
  for (const part of chunkText(full)) await sendMessage(chatId, part);
}

export async function handleUpdate(update: TelegramUpdate) {
  const message = update.message;
  const callback = update.callback_query;

  if (callback?.message?.chat?.id && callback.from?.id) {
    const chatId = callback.message.chat.id;
    const userId = callback.from.id;
    if (!isAllowed(userId)) return sendMessage(chatId, "⛔ هذا البوت خاص. اطلب من المالك إضافتك.");

    const data = callback.data || "";
    if (data.startsWith("provider:")) {
      const provider = data.split(":")[1] as ProviderName;
      userProvider.set(String(userId), provider);
      await sendMessage(chatId, `✅ تم اختيار المزود: <b>${provider}</b>`);
      return;
    }
    if (data === "help_ai") {
      await sendMessage(chatId, "اكتب:\n<code>/ai سؤالك هنا</code>\n\nمثال:\n<code>/ai اكتب خطة لتطوير بوت تيليجرام</code>");
      return;
    }
    if (data === "status") {
      await sendMessage(chatId, `✅ البوت يعمل\nالمزود الافتراضي: <b>${env.DEFAULT_AI_PROVIDER}</b>`);
      return;
    }
  }

  if (!message?.chat?.id || !message.from?.id) return;

  const chatId = message.chat.id;
  const userId = message.from.id;
  const text = message.text?.trim() || "";

  if (!isAllowed(userId)) {
    await sendMessage(chatId, "⛔ هذا البوت خاص للاستخدام الشخصي/العائلي. أرسل ID الخاص بك للمالك لإضافتك.");
    await sendMessage(env.TELEGRAM_OWNER_ID, `محاولة دخول غير مصرح بها:\nID: <code>${userId}</code>\nName: ${message.from.first_name || ""}\nUsername: @${message.from.username || ""}`);
    return;
  }

  try {
    if (text === "/start") {
      await sendMessage(chatId, `أهلًا بك في <b>${env.BOT_NAME}</b>\n\nبوت AI شخصي يعمل على Railway بدون قاعدة بيانات.`, mainKeyboard());
      return;
    }

    if (text === "/status") {
      await sendMessage(chatId, `✅ يعمل\nProvider: <b>${userProvider.get(String(userId)) || env.DEFAULT_AI_PROVIDER}</b>\nDB: <b>disabled</b>`);
      return;
    }

    if (text === "/model") {
      await sendMessage(chatId, `النماذج الحالية:\nOpenRouter: <code>${env.OPENROUTER_MODEL}</code>\nGemini: <code>${env.GEMINI_MODEL}</code>\nGroq: <code>${env.GROQ_MODEL}</code>`);
      return;
    }

    if (text.startsWith("/provider")) {
      const p = text.split(/\s+/)[1]?.toLowerCase() as ProviderName | undefined;
      if (!p || !["openrouter", "gemini", "groq"].includes(p)) {
        await sendMessage(chatId, "استخدم:\n<code>/provider openrouter</code>\n<code>/provider gemini</code>\n<code>/provider groq</code>");
        return;
      }
      userProvider.set(String(userId), p);
      await sendMessage(chatId, `✅ تم اختيار المزود: <b>${p}</b>`);
      return;
    }

    if (text.startsWith("/ai")) {
      await answerAi(chatId, userId, text.replace(/^\/ai\s*/i, ""));
      return;
    }

    if (text) {
      await answerAi(chatId, userId, text);
    }
  } catch (error) {
    const msg = safeMessage(error);
    await sendMessage(chatId, `❌ حدث خطأ:\n<code>${msg.slice(0, 1200)}</code>`);
    await sendMessage(env.TELEGRAM_OWNER_ID, `⚠️ خطأ في البوت:\n<code>${msg.slice(0, 3000)}</code>`).catch(() => undefined);
  }
}
