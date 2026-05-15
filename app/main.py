from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Dict

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request

from .config import get_settings
from .downloader import (
    DownloadError,
    build_choices,
    cleanup_old_downloads,
    describe_info,
    download_media,
    extract_info,
    first_url,
    is_probably_url,
)
from .notebook_cli import (
    GENERATE_SPECS,
    NotebookCLIError,
    add_source,
    ask,
    auth_check,
    create_notebook,
    delete_notebook,
    generate_artifact,
    list_notebooks,
    summary,
)
from .store import create_job, get_cache, get_job, get_user, recent_jobs, set_cache, update_job, update_user
from .telegram import (
    answer_callback_query,
    download_telegram_file,
    get_callback_query,
    get_chat_id,
    get_document,
    get_text,
    get_user_id,
    html_escape,
    send_document,
    send_message,
    set_webhook,
    telegram_api,
)

app = FastAPI(title='NotebookLM Telegram Pro + Downloader')
URL_RE = re.compile(r'https?://\S+')


def _is_admin(user_id: int | None) -> bool:
    settings = get_settings()
    return bool(user_id and user_id in settings.admins)


def _commands() -> str:
    return (
        '<b>أوامر البوت الواحد:</b>\n\n'
        '<b>NotebookLM:</b>\n'
        '/new عنوان الدفتر\n'
        '/source رابط أو أرسل ملف PDF/DOCX/TXT/صوت/فيديو لإضافته إلى NotebookLM\n'
        '/summary ملخص سريع\n'
        '/ask سؤالك عن المصدر\n'
        '/audio بودكاست قصير\n'
        '/video فيديو شرح مختصر\n'
        '/slides عرض شرائح PPTX\n'
        '/infographic إنفوجرافيك PNG\n'
        '/quiz اختبار Markdown\n'
        '/cards بطاقات مراجعة Markdown\n'
        '/mindmap خريطة ذهنية JSON\n'
        '/table جدول CSV\n'
        '/report تقرير دراسة Markdown\n\n'
        '<b>التحميل:</b>\n'
        '/fetch رابط أو /download رابط لاستخراج الجودات والتحويل إلى MP3\n'
        'إرسال رابط مباشر بدون أمر سيعرض خيارات التحميل. استخدم /source إذا أردته كمصدر NotebookLM.\n\n'
        '<b>إدارة:</b>\n'
        '/jobs آخر المهام\n'
        '/status حالة الجلسة\n'
        '/auth فحص جلسة NotebookLM للأدمن\n'
        '/setwebhook ضبط Webhook للأدمن\n'
    )


@app.on_event('startup')
async def startup_tasks() -> None:
    settings = get_settings()
    if settings.keepalive_enabled and settings.base_url:
        asyncio.create_task(_keepalive_loop())


async def _keepalive_loop() -> None:
    settings = get_settings()
    await asyncio.sleep(20)
    while True:
        try:
            cleanup_old_downloads()
            async with httpx.AsyncClient(timeout=20) as client:
                await client.get(settings.base_url.rstrip('/') + '/health')
        except Exception:
            pass
        await asyncio.sleep(max(60, int(settings.keepalive_interval_seconds)))


@app.get('/')
async def root() -> Dict[str, Any]:
    settings = get_settings()
    return {
        'app': settings.app_name,
        'status': 'ok',
        'health': '/health',
        'telegram_webhook': '/telegram/webhook',
        'features': list(GENERATE_SPECS.keys()) + ['summary', 'ask', 'source', 'file-upload', 'fetch', 'download', 'yt-dlp'],
    }


@app.get('/health')
async def health() -> Dict[str, Any]:
    return {'status': 'ok', 'time': int(time.time())}


@app.get('/keepalive')
async def keepalive() -> Dict[str, Any]:
    cleanup_old_downloads()
    return {'ok': True, 'status': 'awake', 'time': int(time.time())}


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


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode('utf-8')).hexdigest()[:16]


def _download_keyboard(url_hash: str, choices: list[dict[str, str]]) -> Dict[str, Any]:
    rows = []
    for item in choices[:10]:
        rows.append([{'text': item['label'], 'callback_data': f'dl:{url_hash}:{item["id"]}'}])
    return {'inline_keyboard': rows}


async def handle_fetch(chat_id: int, text: str) -> None:
    url = first_url(text)
    if not url:
        await send_message(chat_id, 'أرسل رابطًا هكذا:\n<code>/fetch https://example.com/video</code>')
        return
    await send_message(chat_id, '🔎 أفحص الرابط وأستخرج الجودات...')
    info = await extract_info(url)
    choices = build_choices(info)
    url_hash = _hash_url(url)
    user = get_user(chat_id)
    media = user.get('media') or {}
    media[url_hash] = {
        'url': url,
        'title': info.get('title') or 'media',
        'choices': choices,
        'updated_at': time.time(),
    }
    update_user(chat_id, media=media, last_media_hash=url_hash)
    await send_message(
        chat_id,
        '✅ تم استخراج الرابط:\n<code>' + html_escape(describe_info(info)) + '</code>\n\nاختر الجودة:',
        reply_markup=_download_keyboard(url_hash, choices),
    )


async def run_download_job(job_id: str, chat_id: int, url_hash: str, choice: str) -> None:
    update_job(job_id, status='running')
    try:
        user = get_user(chat_id)
        media = (user.get('media') or {}).get(url_hash)
        if not media:
            raise DownloadError('لم أجد الرابط. أرسله مرة أخرى.')
        url = media['url']
        title = media.get('title') or 'media'
        cache_key = f'{url_hash}:{choice}'
        cached = get_cache(cache_key)
        if cached and cached.get('telegram_file_id'):
            await telegram_api('sendDocument', {'chat_id': chat_id, 'document': cached['telegram_file_id'], 'caption': '⚡ من الكاش'})
            update_job(job_id, status='done', cached=True, finished_at=time.time())
            return

        await send_message(chat_id, f'⬇️ بدأ التحميل: <b>{html_escape(choice)}</b>\nقد يستغرق حسب الحجم والمنصة.')
        path = await download_media(url, choice, title)
        result = await send_document(chat_id, path, caption='✅ تم التحميل بنجاح.')
        file_id = (((result.get('result') or {}).get('document') or {}).get('file_id'))
        if file_id:
            set_cache(cache_key, {'telegram_file_id': file_id, 'title': title, 'choice': choice})
        update_job(job_id, status='done', result_path=path, finished_at=time.time())
    except Exception as exc:
        update_job(job_id, status='failed', error=str(exc), finished_at=time.time())
        await send_message(chat_id, '❌ فشل التحميل:\n<code>' + html_escape(str(exc)) + '</code>')


async def handle_download_callback(chat_id: int, update: Dict[str, Any]) -> None:
    cb = get_callback_query(update)
    data = cb.get('data') or ''
    await answer_callback_query(cb.get('id', ''), 'بدأت المعالجة...')
    _, url_hash, choice = data.split(':', 2)
    job = create_job(chat_id, f'download:{choice}', '', url_hash)
    asyncio.create_task(run_download_job(job['id'], chat_id, url_hash, choice))
    await send_message(chat_id, f'تم إنشاء مهمة تحميل: <code>{html_escape(job["id"])}</code>\nتابعها عبر /job {html_escape(job["id"])}')


@app.post('/telegram/webhook')
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> Dict[str, bool]:
    settings = get_settings()
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail='Invalid Telegram secret token')

    update: Dict[str, Any] = await request.json()
    chat_id = get_chat_id(update)
    user_id = get_user_id(update)
    text = get_text(update).strip()
    if not chat_id:
        return {'ok': True}

    try:
        cb = get_callback_query(update)
        if cb and (cb.get('data') or '').startswith('dl:'):
            await handle_download_callback(chat_id, update)
            return {'ok': True}

        if get_document(update):
            await handle_document(chat_id, update)
            return {'ok': True}

        if text.startswith('/start') or text.startswith('/help'):
            await send_message(chat_id, 'أهلًا بك. هذا بوت واحد يجمع NotebookLM وخدمة تحميل الوسائط على Railway.\n\n' + _commands())
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
            user = get_user(chat_id)
            await send_message(chat_id, '<b>حالة الجلسة:</b>\n<code>' + html_escape(json.dumps(user, ensure_ascii=False, indent=2)[:3500]) + '</code>')
            return {'ok': True}

        if text.startswith('/list'):
            if not _is_admin(user_id):
                await send_message(chat_id, 'هذا الأمر للأدمن فقط.')
                return {'ok': True}
            result = await list_notebooks()
            await send_message(chat_id, '<code>' + html_escape(json.dumps(result, ensure_ascii=False)[:3500]) + '</code>')
            return {'ok': True}

        if text.startswith('/jobs'):
            jobs = recent_jobs(chat_id)
            if not jobs:
                await send_message(chat_id, 'لا توجد مهام بعد.')
                return {'ok': True}
            body = '\n\n'.join([f"<b>{html_escape(j['kind'])}</b> | <code>{html_escape(j['id'])}</code> | {html_escape(j.get('status'))}" for j in jobs])
            await send_message(chat_id, body)
            return {'ok': True}

        if text.startswith('/job'):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await send_message(chat_id, 'اكتب: /job JOB_ID')
                return {'ok': True}
            job = get_job(parts[1].strip())
            await send_message(chat_id, '<code>' + html_escape(json.dumps(job or {}, ensure_ascii=False, indent=2)) + '</code>')
            return {'ok': True}

        if text.startswith('/fetch') or text.startswith('/download') or (text and is_probably_url(text) and not text.startswith('/source')):
            await handle_fetch(chat_id, text)
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

        command = text.split()[0].lstrip('/').lower() if text.startswith('/') else ''
        alias = {'flashcards': 'cards', 'card': 'cards', 'mind-map': 'mindmap', 'data-table': 'table', 'slide': 'slides'}
        kind = alias.get(command, command)
        if kind in GENERATE_SPECS:
            nb = await ensure_notebook(chat_id)
            desc = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ''
            job = create_job(chat_id, kind, nb, desc)
            asyncio.create_task(run_generation_job(job['id'], chat_id, kind, nb, desc))
            await send_message(chat_id, f'تم إنشاء المهمة: <code>{html_escape(job["id"])}</code>\nتابعها عبر /job {html_escape(job["id"])}')
            return {'ok': True}

        await send_message(chat_id, 'لم أفهم الأمر.\n\n' + _commands())
        return {'ok': True}

    except NotebookCLIError as exc:
        await send_message(chat_id, 'فشل NotebookLM:\n<code>' + html_escape(str(exc)) + '</code>')
        return {'ok': True}
    except DownloadError as exc:
        await send_message(chat_id, 'فشل التحميل:\n<code>' + html_escape(str(exc)) + '</code>')
        return {'ok': True}
    except Exception as exc:
        await send_message(chat_id, 'حدث خطأ:\n<code>' + html_escape(str(exc)) + '</code>')
        return {'ok': True}
