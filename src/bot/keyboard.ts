import { Markup } from "telegraf";

export const mainKeyboard = Markup.inlineKeyboard([
  [Markup.button.callback("🤖 اسأل الذكاء", "ai_help")],
  [Markup.button.callback("🧠 النماذج", "models"), Markup.button.callback("📊 الحالة", "status")],
  [Markup.button.callback("🧹 مسح السياق", "reset")]
]);

export const providersKeyboard = Markup.inlineKeyboard([
  [Markup.button.callback("OpenRouter", "provider:OpenRouter")],
  [Markup.button.callback("Gemini", "provider:Gemini"), Markup.button.callback("Groq", "provider:Groq")],
  [Markup.button.callback("رجوع", "back_home")]
]);
