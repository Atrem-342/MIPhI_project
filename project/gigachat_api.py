# gigachat_api.py
import requests
import urllib3
import base64
from langsmith import traceable

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==== НАСТРОЙКИ ====
# Твои client_id и client_secret из Сбера
CLIENT_ID = "9bae76f2-8b96-494d-a3f3-e575c0523495"
CLIENT_SECRET = "5b6f3176-15d4-416b-bd07-cc5baaf580df"

# Какие права нужны
SCOPE = "GIGACHAT_API_PERS"   # или другой scope, если так выдали

# Какая модель GigaChat
MODEL = "GigaChat"  # можно взять любую из /api/v1/models


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
        "RqUID": "fd648f05-0e2b-41bf-8753-5c197c62e598",  # можно любой UUID
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


def chat_with_gigachat(access_token: str,user_message: str) -> str:
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

