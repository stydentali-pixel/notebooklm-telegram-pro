from __future__ import annotations

import asyncio
import json
import re
import shlex
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .config import get_settings


class NotebookCLIError(RuntimeError):
    pass


def _extract_json_or_text(stdout: str) -> Any:
    text = stdout.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        # Some commands print log lines before JSON. Try to locate final JSON object.
        match = re.search(r'(\{.*\}|\[.*\])\s*$', text, re.S)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
        return {'text': text}


def _pick_id(data: Any) -> Optional[str]:
    if isinstance(data, dict):
        for key in ['id', 'notebook_id', 'active_notebook_id', 'source_id', 'task_id', 'artifact_id']:
            if data.get(key):
                return str(data[key])
        for key in ['notebook', 'source', 'artifact', 'result']:
            value = data.get(key)
            found = _pick_id(value)
            if found:
                return found
    if isinstance(data, list) and data:
        return _pick_id(data[0])
    return None


async def run_cli(args: list[str], *, input_text: str | None = None, timeout: int | None = None, notebook_id: str | None = None) -> Any:
    settings = get_settings()
    env = settings.notebook_env()
    if notebook_id:
        env['NOTEBOOKLM_NOTEBOOK'] = notebook_id
    cmd = ['notebooklm', '--quiet'] + args
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if input_text is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        out_b, err_b = await asyncio.wait_for(
            proc.communicate(input_text.encode('utf-8') if input_text is not None else None),
            timeout=timeout or settings.job_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise NotebookCLIError(f'NotebookLM command timed out: {shlex.join(cmd)}') from exc
    except FileNotFoundError as exc:
        raise NotebookCLIError('notebooklm CLI is not installed. Check requirements.txt and Railway build logs.') from exc

    stdout = out_b.decode('utf-8', errors='replace')
    stderr = err_b.decode('utf-8', errors='replace')
    if proc.returncode != 0:
        message = stderr.strip() or stdout.strip() or f'exit code {proc.returncode}'
        raise NotebookCLIError(message[:3500])
    return _extract_json_or_text(stdout)


async def auth_check() -> Any:
    return await run_cli(['auth', 'check', '--test', '--json'], timeout=120)


async def list_notebooks() -> Any:
    return await run_cli(['list', '--json'], timeout=120)


async def create_notebook(title: str) -> str:
    data = await run_cli(['create', title, '--json'], timeout=120)
    nb_id = _pick_id(data)
    if not nb_id:
        raise NotebookCLIError(f'Could not parse notebook id from: {data}')
    return nb_id


async def delete_notebook(notebook_id: str) -> None:
    await run_cli(['delete', '-n', notebook_id, '-y'], timeout=90)


async def add_source(notebook_id: str, content: str, title: str | None = None) -> str:
    args = ['source', 'add', content, '-n', notebook_id, '--timeout', str(get_settings().source_timeout_seconds), '--json']
    if title:
        args += ['--title', title]
    data = await run_cli(args, timeout=get_settings().source_timeout_seconds + 30)
    src_id = _pick_id(data)
    return src_id or ''


async def summary(notebook_id: str) -> str:
    data = await run_cli(['summary', '-n', notebook_id], timeout=180)
    return data.get('text', json.dumps(data, ensure_ascii=False)) if isinstance(data, dict) else str(data)


async def ask(notebook_id: str, question: str) -> str:
    data = await run_cli(['ask', '-', '-n', notebook_id, '--timeout', '180'], input_text=question, timeout=210)
    if isinstance(data, dict):
        if data.get('answer'):
            return str(data['answer'])
        if data.get('text'):
            return str(data['text'])
    return str(data)


GENERATE_SPECS: Dict[str, Dict[str, Any]] = {
    'audio': {'download': 'audio', 'file': 'audio.mp4', 'args': ['--format', 'brief', '--length', 'short', '--language', 'ar']},
    'video': {'download': 'video', 'file': 'video.mp4', 'args': ['--format', 'brief', '--style', 'whiteboard', '--language', 'ar'], 'timeout': 1800},
    'slides': {'gen': 'slide-deck', 'download': 'slide-deck', 'file': 'slides.pptx', 'args': ['--format', 'detailed', '--length', 'short', '--language', 'ar'], 'download_args': ['--format', 'pptx']},
    'infographic': {'download': 'infographic', 'file': 'infographic.png', 'args': ['--orientation', 'portrait', '--detail', 'standard', '--style', 'professional', '--language', 'ar']},
    'quiz': {'download': 'quiz', 'file': 'quiz.md', 'args': ['--difficulty', 'medium', '--quantity', 'standard'], 'download_args': ['--format', 'markdown']},
    'cards': {'gen': 'flashcards', 'download': 'flashcards', 'file': 'flashcards.md', 'args': ['--difficulty', 'medium', '--quantity', 'standard'], 'download_args': ['--format', 'markdown']},
    'mindmap': {'gen': 'mind-map', 'download': 'mind-map', 'file': 'mindmap.json', 'args': ['--instructions', 'أنشئ خريطة ذهنية عربية واضحة ومنظمة.']},
    'table': {'gen': 'data-table', 'download': 'data-table', 'file': 'table.csv', 'args': ['--language', 'ar']},
    'report': {'download': 'report', 'file': 'report.md', 'args': ['--format', 'study-guide', '--language', 'ar']},
}


async def generate_artifact(notebook_id: str, kind: str, description: str = '') -> Dict[str, Any]:
    settings = get_settings()
    spec = GENERATE_SPECS[kind]
    gen_type = spec.get('gen', kind)
    timeout = int(spec.get('timeout', settings.job_timeout_seconds))
    desc = description or 'أنشئ نتيجة عربية واضحة ومنظمة من المصادر.'

    if gen_type == 'mind-map':
        args = ['generate', gen_type, '-n', notebook_id, '--json'] + spec.get('args', [])
    else:
        args = ['generate', gen_type, desc, '-n', notebook_id, '--wait', '--timeout', str(timeout), '--retry', '2', '--json'] + spec.get('args', [])
    gen_data = await run_cli(args, timeout=timeout + 60)

    output_dir = Path(settings.download_dir) / f'{int(time.time())}_{kind}'
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / spec['file']
    download_args = ['download', spec['download'], str(output_path), '-n', notebook_id, '--force', '--json'] + spec.get('download_args', [])
    dl_data = await run_cli(download_args, timeout=300)

    return {
        'kind': kind,
        'notebook_id': notebook_id,
        'generated': gen_data,
        'downloaded': dl_data,
        'path': str(output_path),
    }
