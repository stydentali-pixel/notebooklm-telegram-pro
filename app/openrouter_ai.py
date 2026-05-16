from __future__ import annotations

import os
from typing import Any

import httpx


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(RuntimeError):
    pass


async def ask_openrouter(prompt: str) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise OpenRouterError("OPENROUTER_API_KEY غير موجود في Railway Variables.")

    model = os.getenv("OPENROUTER_MODEL", "openrouter/free")

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "أنت مساعد عربي ذكي داخل بوت تيليجرام. "
                    "أجب بإيجاز ووضوح، وقدم خطوات عملية عند الحاجة."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 900,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("APP_PUBLIC_URL", "https://railway.app"),
        "X-OpenRouter-Title": os.getenv("APP_NAME", "NotebookLM Telegram Pro"),
    }

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(OPENROUTER_URL, headers=headers, json=payload)

    if response.status_code >= 400:
        raise OpenRouterError(response.text[-1500:])

    data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise OpenRouterError(f"رد OpenRouter غير مفهوم: {data}") from exc

    if isinstance(content, list):
        return "\n".join(str(part.get("text", part)) if isinstance(part, dict) else str(part) for part in content)

    return str(content).strip() or "لم يصل رد من النموذج."
