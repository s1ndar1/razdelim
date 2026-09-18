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

    async def send_message(self, user_id: int, text: str, buttons: Optional[list] = None) -> httpx.Response:
        payload: Dict[str, Any] = {"text": text}
        if buttons:
            payload["attachments"] = [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]

        return await self.post(
            "/messages",
            params={"user_id": user_id, "access_token": self.config.access_token},
            json=payload,
        )

    async def send_text(self, user_id: int, text: str) -> httpx.Response:
        return await self.send_message(user_id=user_id, text=text)

    async def get_self(self) -> httpx.Response:
        return await self.get("/me", params={"access_token": self.config.access_token})

    async def get_user(self, user_id: int) -> httpx.Response:
        return await self.get(f"/users/{user_id}", params={"access_token": self.config.access_token})


class ParentMaxSDK:
    """Родительский SDK для окружения, в котором открыто мини-приложение."""

    def __init__(self, app_name: str = ""):
        self.app_name = app_name

    def build_start_link(self, start_param: str) -> str:
        if not self.app_name:
            return f"https://max.ru/?startapp={start_param}"
        return f"https://max.ru/{self.app_name}?startapp={start_param}"

    def build_parent_payload(self, event: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "type": event,
            "payload": payload or {},
            "source": "max-parent-sdk",
        }

    def read_init_data(self) -> Optional[str]:
        try:
            import js  # type: ignore

            return js.window.WebApp.initData if hasattr(js, "window") else None
        except Exception:
            return None


MaxApiSDK = MaxSDK
max_api_sdk = MaxSDK()
parent_max_sdk = ParentMaxSDK()
