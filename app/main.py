from __future__ import annotations

import asyncio
import json
import re
import shlex
import time
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Header, HTTPException, Query, Request

from .config import get_settings
from .download_quality import (
    handle_download_quality_callback,
    is_direct_download_url,
    start_download_quality_flow,
    trim_video_url,
)
from .notebook_cli import (
    GENERATE_SPECS,
    add_source,
    ask,
    auth_check,
    create_notebook,
    delete_notebook,
    generate_artifact,
    list_notebooks,
    summary,
)
from .store import create_job, get_job, get_user, recent_jobs, update_job, update_user
from .telegram import (
    answer_callback_query,
    download_telegram_file,
    get_chat_id,
    get_document,
    get_text,
    get_user_id,
    html_escape,
    send_document,
    send_message,
    set_webhook,
)

try:
    from .openrouter_ai import OpenRouterError, ask_openrouter
except Exception:  # optional feature
    OpenRouterError = RuntimeError  # type: ignore
    ask_openrouter = None  # type: ignore


app = FastAPI(title='NotebookLM + Media Telegram Pro')
URL_RE = re.compile(r'https?://\S+')


def _is_admin(user_id: int | None) -> bool:
    settings = get_settings()
    return bool(user_id and user_id in settings.admins)


def _main_menu_text() -> str:
    return """أهلًا بك 👋

اختر القسم الذي تريد استخدامه:

📚 قسم NotebookLM
لإضافة المصادر، التلخيص، الأسئلة، الشرائح، الكويز، البطاقات، التقرير، الصوت، الفيديو، الإنفوجرافيك، الخريطة الذهنية، والجداول.

⬇️ قسم التحميل
تحميل الوسائط من الروابط، اختيار الجودة، التحويل إلى MP3، وتقطيع الفيديو.

اضغط أحد الأزرار بالأسفل أو استخدم:
/notebooklm
/downloads
"""


def _main_menu_keyboard() -> dict[str, Any]:
    return {
        'inline_keyboard': [
            [
                {'text': '📚 قسم NotebookLM', 'callback_data': 'menu:notebooklm'},
                {'text': '⬇️ قسم التحميل', 'callback_data': 'menu:downloads'},
            ],
            [
                {'text': '📌 الحالة', 'callback_data': 'menu:status'},
                {'text': '🧾 المهام', 'callback_data': 'menu:jobs'},
            ],
        ]
    }


def _notebooklm_menu_text() -> str:
    return """📚 قسم NotebookLM

/new عنوان الدفتر
/source رابط أو أرسل ملف PDF/DOCX/TXT/صوت/فيديو
/summary ملخص سريع
/ask سؤالك عن المصدر
/audio بودكاست قصير
/video فيديو شرح مختصر
/slides عرض شرائح PPTX
/infographic إنفوجرافيك PNG
/quiz اختبار Markdown
/cards بطاقات مراجعة Markdown
/mindmap خريطة ذهنية JSON
/table جدول CSV
/report تقرير دراسة Markdown

إدارة:
/jobs آخر المهام
/status حالة الجلسة
/auth فحص جلسة NotebookLM للأدمن
/setwebhook ضبط Webhook للأدمن
"""


def _downloads_menu_text() -> str:
    return """⬇️ قسم التحميل

/fetch رابط
/download رابط
يعرض اختيار النوع ثم الدقة أو نوع الصوت.

/trim رابط بداية نهاية
لتقطيع الفيديو. أمثلة:
<code>/trim https://youtu.be/ID 00:00:10 00:00:30</code>
<code>/trim https://youtu.be/ID 10 30</code>

يمكنك أيضًا إرسال رابط مباشر بدون أمر ليتم فتح قائمة التحميل.

يدعم حسب yt-dlp:
YouTube، TikTok، Instagram، X/Twitter، Facebook، SoundCloud، وروابط MP4/MP3 المباشرة.

ملاحظات:
- /source رابط خاص بـ NotebookLM فقط.
- يوتيوب قد يحتاج YTDLP_COOKIES_TXT في Railway.
"""


def _commands() -> str:
    return _main_menu_text()


async def _handle_menu_callback(data: dict[str, Any]) -> bool:
    callback = data.get('callback_query')
    if not callback:
        return False
    callback_data = callback.get('data', '')
    if not callback_data.startswith('menu:'):
        return False

    callback_id = callback.get('id', '')
    message = callback.get('message') or {}
    chat = message.get('chat') or {}
    chat_id = chat.get('id')
    if not chat_id:
        return True

    if callback_data == 'menu:notebooklm':
        await answer_callback_query(callback_id, 'فتح قسم NotebookLM')
        await send_message(chat_id, _notebooklm_menu_text())
        return True
    if callback_data == 'menu:downloads':
        await answer_callback_query(callback_id, 'فتح قسم التحميل')
        await send_message(chat_id, _downloads_menu_text())
        return True
    if callback_data == 'menu:status':
        await answer_callback_query(callback_id, 'الحالة')
        await _send_status(chat_id)
        return True
    if callback_data == 'menu:jobs':
        await answer_callback_query(callback_id, 'المهام')
        await _send_jobs(chat_id)
        return True

    await answer_callback_query(callback_id)
    return True


@app.get('/')
async def root() -> Dict[str, Any]:
    settings = get_settings()
    return {
        'app': settings.app_name,
        'status': 'ok',
        'health': '/health',
        'telegram_webhook': '/telegram/webhook',
        'features': list(GENERATE_SPECS.keys()) + ['summary', 'ask', 'source', 'file-upload', 'downloader', 'quality-picker', 'trim'],
    }


@app.get('/health')
async def health() -> Dict[str, Any]:
    return {'status': 'ok', 'ok': True}


@app.get('/health/notebooklm')
async def health_notebooklm(secret: str = Query(default='')) -> Dict[str, Any]:
    settings = get_settings()
    if settings.telegram_webhook_secret and secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail='Invalid secret')
    return {'ok': True, 'auth': await auth_check()}


@app.get('/set-telegram-webhook')
async def set_telegram_webhook(secret: str = Query(default='')) -> Dict[str, Any]:
    settings = get_settings()
    if not settings.telegram_webhook_secret or secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail='Invalid secret')
    return await set_webhook()


async def ensure_notebook(chat_id: int, title: str = '') -> str:
    user = get_user(chat_id)
    nb = user.get('notebook_id')
    if nb:
        return nb
    nb = await create_notebook(title or f'Telegram Notebook {chat_id}')
    update_user(chat_id, notebook_id=nb, notebook_title=title or 'Telegram Notebook')
    return nb


async def run_generation_job(job_id: str, chat_id: int, kind: str, notebook_id: str, description: str) -> None:
    update_job(job_id, status='running')
    try:
        await send_message(chat_id, f'بدأت مهمة <b>{html_escape(kind)}</b>. قد تستغرق من دقيقة إلى عدة دقائق.')
        result = await generate_artifact(notebook_id, kind, description)
        path = result['path']
        update_job(job_id, status='done', result_path=path, finished_at=time.time())
        await send_document(chat_id, path, caption=f'تم إنشاء <b>{html_escape(kind)}</b> بنجاح.')
    except Exception as exc:
        update_job(job_id, status='failed', error=str(exc), finished_at=time.time())
        await send_message(chat_id, f'فشلت مهمة <b>{html_escape(kind)}</b>:\n<code>{html_escape(str(exc))}</code>')


async def handle_document(chat_id: int, update: Dict[str, Any]) -> None:
    doc = get_document(update)
    if not doc:
        return
    settings = get_settings()
    size_mb = int(doc.get('file_size') or 0) / (1024 * 1024)
    if size_mb > settings.max_telegram_file_mb:
        await send_message(chat_id, f'الملف كبير جدًا. الحد الحالي {settings.max_telegram_file_mb}MB.')
        return
    file_name = doc.get('file_name') or f'telegram-file-{doc.get("file_unique_id", int(time.time()))}'
    safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', file_name)
    target = str(Path(settings.upload_dir) / f'{chat_id}_{int(time.time())}_{safe_name}')
    await send_message(chat_id, 'استلمت الملف. جارٍ تحميله وإضافته إلى NotebookLM...')
    await download_telegram_file(doc['file_id'], target)
    nb = await ensure_notebook(chat_id, f'Telegram Uploads {chat_id}')
    src = await add_source(nb, target, title=file_name)
    update_user(chat_id, notebook_id=nb, last_source_id=src, last_file=target)
    await send_message(chat_id, f'تمت إضافة الملف.\nNotebook: <code>{html_escape(nb)}</code>\nSource: <code>{html_escape(src)}</code>\n\nاستخدم /summary أو /ask أو /slides أو /quiz.')


async def _send_status(chat_id: int) -> None:
    user = get_user(chat_id)
    safe_user = {k: v for k, v in user.items() if 'token' not in k.lower() and 'cookie' not in k.lower()}
    await send_message(chat_id, '<b>حالة الجلسة:</b>\n<code>' + html_escape(json.dumps(safe_user, ensure_ascii=False, indent=2)) + '</code>')


async def _send_jobs(chat_id: int) -> None:
    jobs = recent_jobs(chat_id)
    if not jobs:
        await send_message(chat_id, 'لا توجد مهام بعد.')
        return
    body = '\n\n'.join([f"<b>{html_escape(j['kind'])}</b> | <code>{html_escape(j['id'])}</code> | {html_escape(j.get('status'))}" for j in jobs])
    await send_message(chat_id, body)


def _parse_trim_command(text: str) -> tuple[str, str, str] | None:
    try:
        parts = shlex.split(text)
    except Exception:
        parts = text.split()
    if len(parts) < 4:
        return None
    # /trim url start end
    if is_direct_download_url(parts[1]):
        return parts[1], parts[2], parts[3]
    # /trim start end url
    if len(parts) >= 4 and is_direct_download_url(parts[3]):
        return parts[3], parts[1], parts[2]
    return None


@app.post('/telegram/webhook')
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> Dict[str, bool]:
    settings = get_settings()
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail='Invalid Telegram secret token')

    update: Dict[str, Any] = await request.json()

    if await _handle_menu_callback(update):
        return {'ok': True}
    if await handle_download_quality_callback(update, send_message):
        return {'ok': True}

    chat_id = get_chat_id(update)
    user_id = get_user_id(update)
    text = get_text(update).strip()
    if not chat_id:
        return {'ok': True}

    try:
        if get_document(update):
            await handle_document(chat_id, update)
            return {'ok': True}

        if text.startswith('/start') or text.startswith('/help'):
            await send_message(chat_id, _main_menu_text(), reply_markup=_main_menu_keyboard())
            return {'ok': True}

        if text.startswith('/notebooklm'):
            await send_message(chat_id, _notebooklm_menu_text())
            return {'ok': True}

        if text.startswith('/downloads') or text.startswith('/download_help'):
            await send_message(chat_id, _downloads_menu_text())
            return {'ok': True}

        if text.startswith('/fetch') or text.startswith('/download'):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await send_message(chat_id, 'أرسل الرابط بهذا الشكل:\n<code>/fetch https://example.com/video</code>')
            else:
                await start_download_quality_flow(chat_id, parts[1].strip(), send_message)
            return {'ok': True}

        if text.startswith('/trim'):
            parsed = _parse_trim_command(text)
            if not parsed:
                await send_message(chat_id, 'استخدم الأمر هكذا:\n<code>/trim الرابط 00:00:10 00:00:30</code>\nأو:\n<code>/trim الرابط 10 30</code>')
                return {'ok': True}
            url, start, end = parsed
            await trim_video_url(chat_id, url, start, end, send_message)
            return {'ok': True}

        # رابط مباشر = قسم التحميل. /source فقط يذهب إلى NotebookLM.
        if text and is_direct_download_url(text):
            await start_download_quality_flow(chat_id, text, send_message)
            return {'ok': True}

        if text.startswith('/setwebhook'):
            if not _is_admin(user_id):
                await send_message(chat_id, 'هذا الأمر للأدمن فقط.')
                return {'ok': True}
            result = await set_webhook()
            await send_message(chat_id, f'نتيجة ضبط الويب هوك:\n<code>{html_escape(json.dumps(result, ensure_ascii=False))}</code>')
            return {'ok': True}

        if text.startswith('/auth'):
            if not _is_admin(user_id):
                await send_message(chat_id, 'هذا الأمر للأدمن فقط.')
                return {'ok': True}
            await send_message(chat_id, 'جارٍ فحص جلسة NotebookLM...')
            result = await auth_check()
            await send_message(chat_id, '<code>' + html_escape(json.dumps(result, ensure_ascii=False, indent=2)) + '</code>')
            return {'ok': True}

        if text.startswith('/status'):
            await _send_status(chat_id)
            return {'ok': True}

        if text.startswith('/list'):
            if not _is_admin(user_id):
                await send_message(chat_id, 'هذا الأمر للأدمن فقط.')
                return {'ok': True}
            result = await list_notebooks()
            await send_message(chat_id, '<code>' + html_escape(json.dumps(result, ensure_ascii=False)[:3500]) + '</code>')
            return {'ok': True}

        if text.startswith('/jobs'):
            await _send_jobs(chat_id)
            return {'ok': True}

        if text.startswith('/job'):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await send_message(chat_id, 'اكتب: /job JOB_ID')
                return {'ok': True}
            job = get_job(parts[1].strip())
            await send_message(chat_id, '<code>' + html_escape(json.dumps(job or {}, ensure_ascii=False, indent=2)) + '</code>')
            return {'ok': True}

        if text.startswith('/ai'):
            prompt = text.removeprefix('/ai').strip()
            if not prompt:
                await send_message(chat_id, 'اكتب سؤالك هكذا:\n<code>/ai اشرح لي هذا الموضوع</code>')
                return {'ok': True}
            if ask_openrouter is None:
                await send_message(chat_id, 'ميزة OpenRouter غير مفعلة في هذه النسخة.')
                return {'ok': True}
            await send_message(chat_id, 'جاري التفكير عبر OpenRouter...')
            try:
                answer = await ask_openrouter(prompt)
            except OpenRouterError as exc:
                await send_message(chat_id, 'فشل OpenRouter:\n<code>' + html_escape(str(exc)) + '</code>')
                return {'ok': True}
            for i in range(0, len(answer), 3500):
                await send_message(chat_id, html_escape(answer[i:i + 3500]))
            return {'ok': True}

        if text.startswith('/new'):
            title = text.removeprefix('/new').strip() or f'Telegram Notebook {chat_id}'
            nb = await create_notebook(title)
            update_user(chat_id, notebook_id=nb, notebook_title=title, last_source_id='')
            await send_message(chat_id, f'تم إنشاء دفتر جديد:\n<b>{html_escape(title)}</b>\n<code>{html_escape(nb)}</code>\n\nأرسل /source مع رابط أو ارفع ملفًا.')
            return {'ok': True}

        if text.startswith('/source'):
            payload = text.removeprefix('/source').strip()
            if not payload:
                await send_message(chat_id, 'اكتب: /source https://example.com أو أرسل ملف PDF.')
                return {'ok': True}
            nb = await ensure_notebook(chat_id)
            await send_message(chat_id, 'جارٍ إضافة المصدر إلى NotebookLM...')
            src = await add_source(nb, payload)
            update_user(chat_id, notebook_id=nb, last_source_id=src)
            await send_message(chat_id, f'تمت إضافة المصدر.\nNotebook: <code>{html_escape(nb)}</code>\nSource: <code>{html_escape(src)}</code>')
            return {'ok': True}

        if text.startswith('/summary'):
            nb = await ensure_notebook(chat_id)
            await send_message(chat_id, 'جارٍ إنشاء الملخص...')
            result = await summary(nb)
            await send_message(chat_id, html_escape(result))
            return {'ok': True}

        if text.startswith('/ask'):
            q = text.removeprefix('/ask').strip()
            if not q:
                await send_message(chat_id, 'اكتب السؤال بعد الأمر. مثال:\n<code>/ask لخّص أهم النقاط</code>')
                return {'ok': True}
            nb = await ensure_notebook(chat_id)
            await send_message(chat_id, 'جارٍ سؤال NotebookLM...')
            result = await ask(nb, q)
            await send_message(chat_id, html_escape(result))
            return {'ok': True}

        for kind in GENERATE_SPECS:
            if text.startswith('/' + kind):
                nb = await ensure_notebook(chat_id)
                description = text.removeprefix('/' + kind).strip()
                job = create_job(chat_id, kind, nb, description)
                await send_message(chat_id, f'تم إنشاء مهمة <b>{html_escape(kind)}</b>.\nJob: <code>{job["id"]}</code>')
                asyncio.create_task(run_generation_job(job['id'], chat_id, kind, nb, description))
                return {'ok': True}

        await send_message(chat_id, _main_menu_text(), reply_markup=_main_menu_keyboard())
        return {'ok': True}

    except Exception as exc:
        await send_message(chat_id, 'حدث خطأ:\n<code>' + html_escape(str(exc)) + '</code>')
        return {'ok': True}
