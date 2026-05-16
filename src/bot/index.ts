import { Telegraf } from "telegraf";
import { env } from "../config/env.js";
import { prisma } from "../db/prisma.js";
import { askAi } from "../ai/chat.js";
import { getDefaultSelection, listConfiguredProviders, type ProviderName } from "../ai/provider.js";
import { escapeHtml, truncateText } from "../utils/safe.js";
import { canUseBot, upsertTelegramUser } from "./user.js";
import { mainKeyboard, providersKeyboard } from "./keyboard.js";

export const bot = new Telegraf(env.TELEGRAM_BOT_TOKEN);

bot.start(async (ctx) => {
  const user = await upsertTelegramUser(ctx);
  const allowed = await canUseBot(ctx);

  if (!allowed) {
    await ctx.reply(
      `مرحبًا. تم تسجيل طلبك.\n\nأرسل هذا الرقم للمالك لتفعيلك:\n${ctx.from?.id}`
    );
    return;
  }

  await ctx.reply(
    `أهلاً ${user?.firstName || "بك"}.\n\nهذا بوت Moataz AI التجريبي.\nاكتب /ai ثم سؤالك، أو اضغط الزر.`,
    mainKeyboard
  );
});

bot.command("status", async (ctx) => {
  if (!(await canUseBot(ctx))) return ctx.reply("غير مصرح لك باستخدام البوت حاليًا.");
  const providers = listConfiguredProviders()
    .map((p) => `${p.ready ? "✅" : "⚠️"} ${p.provider}: ${p.model}`)
    .join("\n");
  await ctx.reply(`حالة البوت: يعمل ✅\n\nالمزودون:\n${providers}`);
});

bot.command("model", async (ctx) => {
  if (!(await canUseBot(ctx))) return ctx.reply("غير مصرح لك باستخدام البوت حاليًا.");
  await ctx.reply("اختر مزود الذكاء الاصطناعي:", providersKeyboard);
});

bot.command("provider", async (ctx) => {
  if (!(await canUseBot(ctx))) return ctx.reply("غير مصرح لك باستخدام البوت حاليًا.");
  const value = ctx.message.text.split(/\s+/)[1] as ProviderName | undefined;
  if (!value || !["OpenRouter", "Gemini", "Groq"].includes(value)) {
    return ctx.reply("استخدم: /provider OpenRouter أو /provider Gemini أو /provider Groq");
  }
  await prisma.botUser.update({
    where: { telegramId: String(ctx.from.id) },
    data: { currentProvider: value, currentModel: null }
  });
  await ctx.reply(`تم اختيار المزود: ${value}`);
});

bot.command("reset", async (ctx) => {
  if (!(await canUseBot(ctx))) return ctx.reply("غير مصرح لك باستخدام البوت حاليًا.");
  await ctx.reply("تم مسح السياق المؤقت. النسخة الحالية لا تحتفظ بسياق طويل افتراضيًا.");
});

bot.command("ai", async (ctx) => {
  if (!(await canUseBot(ctx))) return ctx.reply("غير مصرح لك باستخدام البوت حاليًا.");
  const prompt = ctx.message.text.replace(/^\/ai\s*/i, "").trim();
  if (!prompt) return ctx.reply("اكتب سؤالك بعد الأمر. مثال:\n/ai اكتب لي خطة مشروع بوت تيليجرام");
  await handlePrompt(ctx, prompt);
});

bot.action("back_home", async (ctx) => {
  await ctx.answerCbQuery();
  await ctx.editMessageText("القائمة الرئيسية:", mainKeyboard);
});

bot.action("ai_help", async (ctx) => {
  await ctx.answerCbQuery();
  await ctx.reply("أرسل سؤالك بهذا الشكل:\n\n/ai اكتب هنا سؤالك أو طلبك");
});

bot.action("models", async (ctx) => {
  await ctx.answerCbQuery();
  await ctx.reply("اختر المزود:", providersKeyboard);
});

bot.action("status", async (ctx) => {
  await ctx.answerCbQuery();
  const providers = listConfiguredProviders()
    .map((p) => `${p.ready ? "✅" : "⚠️"} ${p.provider}: ${p.model}`)
    .join("\n");
  await ctx.reply(`حالة البوت: يعمل ✅\n\n${providers}`);
});

bot.action("reset", async (ctx) => {
  await ctx.answerCbQuery("تم");
  await ctx.reply("تم مسح السياق المؤقت.");
});

bot.action(/^provider:(OpenRouter|Gemini|Groq)$/, async (ctx) => {
  if (!ctx.from) return;
  const provider = ctx.match[1] as ProviderName;
  await prisma.botUser.update({
    where: { telegramId: String(ctx.from.id) },
    data: { currentProvider: provider, currentModel: null }
  });
  await ctx.answerCbQuery(`تم اختيار ${provider}`);
  await ctx.reply(`تم اختيار المزود: ${provider}`);
});

bot.on("text", async (ctx) => {
  if (!(await canUseBot(ctx))) return ctx.reply("غير مصرح لك باستخدام البوت حاليًا.");
  const text = ctx.message.text.trim();
  if (text.startsWith("/")) return;
  await ctx.reply("لطرح سؤال استخدم:\n/ai " + text.slice(0, 100));
});

async function handlePrompt(ctx: any, prompt: string) {
  const user = await upsertTelegramUser(ctx);
  const cleanPrompt = prompt.slice(0, env.MAX_PROMPT_CHARS);
  const selection = user?.currentProvider
    ? { provider: user.currentProvider as ProviderName, model: user.currentModel || undefined }
    : getDefaultSelection();

  const waiting = await ctx.reply("جاري التفكير…");

  try {
    const result = await askAi(cleanPrompt, selection);
    await prisma.aiMessage.create({
      data: {
        telegramId: String(ctx.from.id),
        userId: user?.id,
        provider: result.provider,
        model: result.model,
        prompt: cleanPrompt,
        response: result.text,
        status: "OK",
        tokens: typeof result.usage?.totalTokens === "number" ? result.usage.totalTokens : null
      }
    });

    await ctx.telegram.editMessageText(
      ctx.chat.id,
      waiting.message_id,
      undefined,
      `<b>${escapeHtml(result.provider)} / ${escapeHtml(result.model)}</b>\n\n${escapeHtml(truncateText(result.text, 3800))}`,
      { parse_mode: "HTML" }
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    await prisma.aiMessage.create({
      data: {
        telegramId: String(ctx.from.id),
        userId: user?.id,
        provider: selection.provider,
        model: selection.model || "default",
        prompt: cleanPrompt,
        status: "ERROR",
        error: message
      }
    });
    await ctx.telegram.editMessageText(
      ctx.chat.id,
      waiting.message_id,
      undefined,
      `فشل طلب الذكاء الاصطناعي.\n\nالسبب: ${message}`
    );
  }
}
