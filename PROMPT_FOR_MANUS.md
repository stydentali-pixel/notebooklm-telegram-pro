أنت Senior Backend Engineer. المطلوب دمج خدمة تحميل الوسائط داخل مستودع بوت NotebookLM الحالي بدون إنشاء بوت ثانٍ وبدون Supabase الآن.

نفّذ بدقة:

1. اعمل pull لآخر نسخة من مستودع البوت الحالي.
2. انسخ ملفات حزمة الدمج فوق المستودع الحالي مع الاستبدال عند التعارض:
   - app/main.py
   - app/downloader.py
   - app/telegram.py
   - app/store.py
   - app/config.py
   - requirements.txt
   - nixpacks.toml
   - .env.example
   - docs/MERGE_DOWNLOADER.md
3. لا تحذف أوامر NotebookLM القديمة. يجب أن تبقى:
   /new /source /summary /ask /audio /video /slides /infographic /quiz /cards /mindmap /table /report /auth
4. أضف خدمة التحميل في نفس البوت عبر:
   /fetch URL
   /download URL
   وإرسال رابط مباشر بدون أمر يعرض خيارات التحميل.
5. اجعل /source فقط هو أمر إضافة الرابط إلى NotebookLM. أما الرابط المباشر فهو للتحميل.
6. لا تستخدم Prisma ولا Supabase الآن. استخدم التخزين المحلي JSON الحالي في /app/data/state.json.
7. ثبّت yt-dlp من requirements.txt و ffmpeg من nixpacks.toml.
8. تأكد من حذف خيار --quiet من app/notebook_cli.py لأنه غير مدعوم في النسخة الحالية من notebooklm CLI.
9. تأكد أن setWebhook يسمح بـ callback_query داخل allowed_updates.
10. فعّل health endpoints:
    /health
    /keepalive
11. أضف keepalive داخلي عبر KEEPALIVE_ENABLED=true، لكن لا تعتمد عليه وحده. أضف في README توصية باستخدام UptimeRobot أو Better Stack يضرب /health كل 5 دقائق.
12. شغّل فحص قبل الرفع:
    python -m py_compile app/*.py
13. ارفع إلى GitHub ثم اترك Railway يعمل Deploy.
14. بعد النشر، اضبط المتغيرات التالية في Railway:
    DOWNLOAD_MAX_FILE_MB=45
    DOWNLOAD_TIMEOUT_SECONDS=900
    EXTRACT_TIMEOUT_SECONDS=120
    KEEPALIVE_ENABLED=true
    KEEPALIVE_INTERVAL_SECONDS=240
15. اختبر:
    /start
    /fetch https://www.youtube.com/watch?v=VIDEO_ID
    /source https://example.com
    /summary

النتيجة المطلوبة: بوت واحد فقط على نفس Telegram token ونفس webhook. لا تنشئ بوت جديد. لا تشغل خدمة Node منفصلة. لا تضف قاعدة بيانات الآن.
