# Moataz AI Railway No-DB Telegram Bot

بوت تيليجرام مبدئي يعمل على Railway فقط، بدون Prisma وبدون Supabase وبدون قاعدة بيانات.

## التشغيل

1. ارفع المشروع إلى GitHub.
2. اربطه بـ Railway.
3. أضف المتغيرات من `railway-env.json`.
4. أنشئ Public Domain من Railway Networking.
5. تأكد أن `PUBLIC_URL` يطابق رابط Railway.
6. افتح:

```txt
/admin?key=ADMIN_PANEL_KEY
```

ثم اضغط Set Webhook.

## الأوامر

```txt
/start
/ai سؤالك هنا
/provider openrouter
/provider gemini
/provider groq
/model
/status
```

## ملاحظات

- لا توجد قاعدة بيانات في هذه النسخة.
- الذاكرة مؤقتة فقط أثناء تشغيل السيرفر.
- المستخدمون المسموحون يحددون عبر `ALLOWED_USER_IDS` مفصولة بفواصل.
- لاحقًا يمكن إضافة Supabase/Prisma في نسخة منفصلة.
