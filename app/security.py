import hashlib
import hmac
import json
import time
from typing import Optional
from urllib.parse import unquote


def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 86400,
) -> Optional[dict]:
    """
    Проверяет подлинность initData мини-приложения MAX.
    Алгоритм: https://dev.max.ru/docs/webapps/validation

    init_data — это строка вида "user=...&auth_date=...&hash=...",
    которую мини-приложение читает из window.WebApp.initData.

    Возвращает распарсенные параметры (с раскодированным полем "user"),
    либо None, если подпись неверна или данные повреждены.
    """
    if not init_data:
        return None

    pairs = [p.split("=", 1) for p in init_data.split("&") if "=" in p]

    hashes = [v for k, v in pairs if k == "hash"]
    if len(hashes) != 1:
        return None
    original_hash = hashes[0]

    decoded = [(k, unquote(v)) for k, v in pairs if k != "hash"]
    decoded.sort(key=lambda kv: kv[0])
    launch_params = "\n".join(f"{k}={v}" for k, v in decoded)

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, launch_params.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(signature, original_hash):
        return None

    result = dict(decoded)
    try:
        auth_date = int(result["auth_date"])
    except (KeyError, TypeError, ValueError):
        return None
    current_time = int(time.time())
    if auth_date > current_time + 60 or current_time - auth_date > max_age_seconds:
        return None

    if "user" in result:
        try:
            result["user"] = json.loads(result["user"])
        except json.JSONDecodeError:
            pass
    return result
