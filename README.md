# Moataz AI Telegram Bot

بوت Telegram مستقل يعمل Webhook على Railway، يستخدم Vercel AI SDK ويدعم OpenRouter وGemini وGroq، مع Prisma/PostgreSQL ومسارات جاهزة لاحقًا للربط مع موقع Vercel.

## التشغيل السريع

1. ارفع المشروع إلى GitHub.
2. اربطه بـ Railway.
3. أضف المتغيرات من `.env.example` في Railway Variables.
4. افتح `/health` للتأكد من التشغيل.
5. فعّل الويبهوك:

```bash
curl -X POST "https://YOUR-RAILWAY-DOMAIN.up.railway.app/admin/set-webhook?key=ADMIN_PANEL_KEY"
```

## المسارات

- `GET /health`
- `GET /admin?key=ADMIN_PANEL_KEY`
- `POST /admin/set-webhook?key=ADMIN_PANEL_KEY`
- `POST /telegram/webhook/:secret`
- `GET /api/internal/status` مع header `x-internal-api-key`
- `POST /api/internal/chat` مع header `x-internal-api-key`

## أوامر البوت

- `/start`
- `/ai اكتب سؤالك`
- `/model`
- `/provider OpenRouter|Gemini|Groq`
- `/reset`
- `/status`

## إضافة مزود جديد

افتح `src/ai/provider.ts` وأضف provider جديد، ثم وسّع enum في `prisma/schema.prisma` إذا أردت تسجيله في قاعدة البيانات.
