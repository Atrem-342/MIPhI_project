# gigachat_api.py
import base64
import os
from typing import Optional

import requests
import urllib3
from dotenv import load_dotenv
from langsmith import traceable

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Environment variable '{name}' is not set. "
            "Add it to your .env or hosting platform configuration."
        )
    return value


# ==== НАСТРОЙКИ ====
CLIENT_ID = _require_env("GIGACHAT_CLIENT_ID")
CLIENT_SECRET = _require_env("GIGACHAT_CLIENT_SECRET")
SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat")
RQUID = os.getenv("GIGACHAT_RQUID", "fd648f05-0e2b-41bf-8753-5c197c62e598")


def get_access_token() -> str:
    """
    Получаем OAuth-токен у NGW.
    """
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

    # grant_type ОБЯЗАТЕЛЕН
    payload = f"scope={SCOPE}&grant_type=client_credentials"

    # client_id:client_secret → base64 (но здесь кладём уже готовые)
    auth_bytes = f"{CLIENT_ID}:{CLIENT_SECRET}".encode("utf-8")
    auth_b64 = base64.b64encode(auth_bytes).decode("ascii")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": RQUID,
        "Authorization": f"Basic {auth_b64}",
    }

    resp = requests.post(url, headers=headers, data=payload, verify=False, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # Обычно токен лежит в поле access_token
    return data["access_token"]

def chat_with_gigachat_messages(access_token: str, messages: list[dict]) -> str:
    """
    Общая функция: отправляет список messages в GigaChat и возвращает ответ ассистента.
    messages — это список словарей вида {"role": "...", "content": "..."}.
    """
    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "model": MODEL,
        "messages": messages,
    }

    resp = requests.post(url, headers=headers, json=payload, verify=False, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    return data["choices"][0]["message"]["content"]


def chat_with_gigachat(access_token: str, user_message: str) -> str:
    """
    Отправляем сообщение в GigaChat и получаем ответ .
    """
    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Ты дружелюбный помощник.",
            },
            {
                "role": "user",
                "content": user_message,
            },
        ],
    }

    resp = requests.post(url, headers=headers, json=payload, verify=False, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    return data["choices"][0]["message"]["content"]
