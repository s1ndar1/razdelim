from typing import Optional

import httpx

from app.config import BOT_TOKEN, MAX_API_BASE


async def send_message(user_id: int, text: str, buttons: Optional[list] = None) -> None:
    """Шлёт сообщение пользователю. Работает только если он уже стартовал бота."""
    payload: dict = {"text": text}
    if buttons:
        payload["attachments"] = [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(
                f"{MAX_API_BASE}/messages",
                params={"user_id": user_id, "access_token": BOT_TOKEN},
                json=payload,
            )
        except httpx.HTTPError:
            # в проде здесь нужен лог/ретрай — для прототипа достаточно не падать
            pass
