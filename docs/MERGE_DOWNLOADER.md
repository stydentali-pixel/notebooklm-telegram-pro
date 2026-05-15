# دمج خدمة التحميل مع بوت NotebookLM

هذه النسخة تجعل البوت واحدًا فقط:

- أوامر NotebookLM كما هي.
- روابط الفيديو والصوت تتحول إلى خدمة تحميل عبر yt-dlp.
- لا تستخدم Supabase أو Prisma الآن.
- تحفظ الحالة والكاش البسيط في `/app/data/state.json`.
- تحتوي endpoint صحة و keepalive.

## أوامر التحميل

- `/fetch رابط` استخراج الجودات.
- `/download رابط` نفس `/fetch`.
- إرسال رابط مباشر بدون أمر يعرض خيارات التحميل.
- الأزرار تعرض: أفضل جودة، MP3، ودقات الفيديو المتاحة.

## متغيرات Railway الإضافية

```env
DOWNLOAD_MAX_FILE_MB=45
DOWNLOAD_TIMEOUT_SECONDS=900
EXTRACT_TIMEOUT_SECONDS=120
KEEPALIVE_ENABLED=true
KEEPALIVE_INTERVAL_SECONDS=240
```

## منع النوم

يوجد self-ping داخلي يضرب `/health` كل عدة دقائق إذا كان `KEEPALIVE_ENABLED=true`.
لكن لو المنصة أوقفت الحاوية تمامًا، فلا يستطيع التطبيق إيقاظ نفسه. الأفضل إضافة مراقب خارجي مثل UptimeRobot أو Better Stack يضرب:

```txt
https://YOUR-RAILWAY-URL/health
```

كل 5 دقائق.
