from typing import Optional

import httpx

from app.max_sdk import MaxSDK


sdk = MaxSDK()


async def send_message(chat_id: int, text: str, buttons: Optional[list] = None) -> None:
    """Шлёт сообщение пользователю. Работает только если он уже стартовал бота."""
    try:
        await sdk.send_message(chat_id=chat_id, text=text, buttons=buttons)
    except httpx.HTTPError:
        # в проде здесь нужен лог/ретрай — для прототипа достаточно не падать
        pass
