import requests

from config import Config


def telegram_api_url(method: str) -> str:
    token = str(getattr(Config, "TELEGRAM_TOKEN", "") or "")
    clean_method = str(method or "").strip("/")
    return f"https://api.telegram.org/bot{token}/{clean_method}"


def sanitize_telegram_error(error) -> str:
    msg = str(error)
    token = str(getattr(Config, "TELEGRAM_TOKEN", "") or "")
    if token:
        msg = msg.replace(token, "***")
    return msg


def telegram_get_json(method: str, *, params=None, timeout=10):
    try:
        response = requests.get(
            telegram_api_url(method),
            params=params,
            timeout=timeout,
        )
        return response.json()
    except Exception as error:
        raise RuntimeError(sanitize_telegram_error(error)) from error


def telegram_post(method: str, *, data=None, json=None, files=None, timeout=10):
    try:
        response = requests.post(
            telegram_api_url(method),
            data=data,
            json=json,
            files=files,
            timeout=timeout,
        )
        return response
    except Exception as error:
        raise RuntimeError(sanitize_telegram_error(error)) from error
