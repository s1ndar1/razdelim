from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from app.config import BOT_TOKEN, MAX_API_BASE


@dataclass
class MaxApiConfig:
    base_url: str = MAX_API_BASE
    access_token: str = BOT_TOKEN
    timeout: float = 10.0


class BaseMaxSDK:
    """Базовый SDK с общими HTTP-методами и настройками."""

    def __init__(self, config: Optional[MaxApiConfig] = None):
        self.config = config or MaxApiConfig()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            return await client.request(
                method,
                f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}",
                params=params,
                json=json,
                **kwargs,
            )

    async def get(self, path: str, *, params: Optional[Dict[str, Any]] = None, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", path, params=params, **kwargs)

    async def post(self, path: str, *, params: Optional[Dict[str, Any]] = None, json: Optional[Dict[str, Any]] = None, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", path, params=params, json=json, **kwargs)


class MaxSDK(BaseMaxSDK):
    """Обычный SDK для работы с MAX API на сервере."""

    async def send_message(
        self,
        user_id: Optional[int] = None,
        text: str = "",
        buttons: Optional[list] = None,
        *,
        chat_id: Optional[int] = None,
    ) -> httpx.Response:
        if (user_id is None) == (chat_id is None):
            raise ValueError("Укажите ровно один идентификатор: user_id или chat_id")

        payload: Dict[str, Any] = {"text": text}
        if buttons:
            payload["attachments"] = [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]

        return await self.post(
            "/messages",
            params={"user_id": user_id} if user_id is not None else {"chat_id": chat_id},
            json=payload,
            headers={"Authorization": self.config.access_token},
        )

    async def send_text(self, user_id: int, text: str) -> httpx.Response:
        return await self.send_message(user_id=user_id, text=text)

    async def get_self(self) -> httpx.Response:
        return await self.get("/me", headers={"Authorization": self.config.access_token})

    async def get_user(self, user_id: int) -> httpx.Response:
        return await self.get(
            f"/users/{user_id}",
            headers={"Authorization": self.config.access_token},
        )


MaxApiSDK = MaxSDK
