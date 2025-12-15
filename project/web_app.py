import hashlib
import hmac
import json
import logging
import os
import urllib.parse
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db.sqlite_store import (
    init_db,
    create_dialog,
    list_dialogs,
    get_dialog,
    get_dialog_messages,
    update_dialog_state,
    add_dialog_message,
    delete_dialog,
    rename_dialog,
    get_dialog_by_owner,
    link_dialog_owner,
)
from gigachat_api import get_access_token
from main import process_user_message, create_initial_state, normalize_state
from utils.ocr_space import parse_image_with_ocr_space, OCRSpaceError


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lumira.web")

ACCESS_TOKEN = get_access_token()
init_db()

app = FastAPI(title="Lumira Web API")
app.mount("/static", StaticFiles(directory="static"), name="static")

GREETING_TEXT = "Привет! Я готова помочь с учёбой."
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


class ChatRequest(BaseModel):
    dialog_id: int
    message: str


class ChatResponse(BaseModel):
    answer: str


class CreateDialogRequest(BaseModel):
    title: Optional[str] = None


class RenameDialogRequest(BaseModel):
    title: str


class TelegramSessionRequest(BaseModel):
    init_data: str


def create_dialog_with_greeting(
    title: Optional[str] = None,
    owner: Optional[tuple[str, str]] = None,
):
    dialog = create_dialog(title, create_initial_state())
    add_dialog_message(dialog["id"], "assistant", GREETING_TEXT)
    if owner:
        link_dialog_owner(dialog["id"], owner[0], owner[1])
    return dialog


def get_or_create_owner_dialog(
    provider: str,
    external_id: str,
    title: Optional[str] = None,
):
    existing = get_dialog_by_owner(provider, external_id)
    if existing:
        return existing
    return create_dialog_with_greeting(title, owner=(provider, external_id))


def ensure_default_dialog() -> None:
    if not list_dialogs():
        create_dialog_with_greeting("Новый диалог")


ensure_default_dialog()


def verify_telegram_init_data(init_data: str) -> dict:
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="TELEGRAM_BOT_TOKEN не настроен на сервере.",
        )
    if not init_data:
        raise HTTPException(status_code=400, detail="Пустые данные Telegram.")

    parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    init_hash = parsed.pop("hash", None)
    if not init_hash:
        raise HTTPException(status_code=400, detail="Нет hash в initData.")

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )
    secret_key = hashlib.sha256(TELEGRAM_BOT_TOKEN.encode()).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, init_hash):
        raise HTTPException(status_code=403, detail="Неверная подпись Telegram.")

    user_json = parsed.get("user")
    if not user_json:
        raise HTTPException(status_code=400, detail="Нет user в initData.")

    try:
        user = json.loads(user_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Некорректный JSON user.") from exc

    return user


def get_telegram_user_from_request(request: Request) -> Optional[str]:
    init_data = request.headers.get("X-Telegram-Init-Data")
    if not init_data:
        return None
    user = verify_telegram_init_data(init_data)
    user_id = str(user.get("id"))
    if not user_id:
        raise HTTPException(status_code=400, detail="Некорректные данные Telegram.")
    return user_id

HTML_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <title>Lumira</title>
  <link rel="stylesheet" href="/static/style.css" />
  <script>
    window.MathJax = {
      tex: {
        inlineMath: [['$', '$'], ['\\(', '\\)']],
        displayMath: [['$$', '$$'], ['\\[', '\\]']],
      },
      options: {
        skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'],
      },
    };
  </script>
  <script async id="MathJax-script" src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="brand">
          <div class="logo-circle">L</div>
          <div class="brand-text">
            <span>Lumira</span>
            <small>Учебный помощник</small>
          </div>
        </div>
        <button class="primary" id="new-dialog">+ Новый диалог</button>
      </div>
      <div class="dialogs-list" id="dialogs-list"></div>
    </aside>

    <div class="main-area">
      <header class="main-header">
        <div>
          <p class="hint">Активный диалог</p>
          <h1 id="dialog-title">Lumira</h1>
        </div>
        <button id="rename-dialog" class="ghost">Переименовать</button>
      </header>

      <div class="chat-window" id="chat-window"></div>

      <form id="chat-form" class="input-area" enctype="multipart/form-data">
        <textarea id="message" name="message" placeholder="Спросите что угодно…"></textarea>
        <div class="attachment-row">
          <label class="file-upload">
            <input type="file" id="attach-file" name="file" accept="image/png,image/jpeg,application/pdf" />
            <span>📎 Прикрепить файл (PNG/JPEG/PDF)</span>
          </label>
          <select id="file-language" name="language">
            <option value="rus" selected>Русский текст</option>
            <option value="eng">English text</option>
            <option value="ukr">Українська</option>
          </select>
          <span id="file-name" class="file-name">Файл не выбран</span>
        </div>
        <div class="actions">
          <span class="hint">Shift + Enter — перенос строки</span>
          <button type="submit">Отправить</button>
        </div>
      </form>
    </div>
  </div>

  <script>
    const chatWindow = document.getElementById('chat-window');
    const dialogsList = document.getElementById('dialogs-list');
    const messageInput = document.getElementById('message');
    const form = document.getElementById('chat-form');
    const newDialogBtn = document.getElementById('new-dialog');
    const renameDialogBtn = document.getElementById('rename-dialog');
    const dialogTitleEl = document.getElementById('dialog-title');
    const fileInput = document.getElementById('attach-file');
    const fileLanguage = document.getElementById('file-language');
    const fileNameLabel = document.getElementById('file-name');

    let dialogs = [];
    let activeDialogId = null;
    let isSending = false;

    if (fileInput && fileNameLabel) {
      fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
          fileNameLabel.textContent = fileInput.files[0].name;
        } else {
          fileNameLabel.textContent = 'Файл не выбран';
        }
      });
    }

    function renderMath(element) {
      if (window.MathJax?.typesetPromise) {
        MathJax.typesetPromise([element]).catch(() => {});
      }
    }

    function appendMessage(role, text) {
      const wrapper = document.createElement('div');
      wrapper.className = `message ${role}`;

      const title = document.createElement('div');
      title.className = 'message-title';
      title.textContent = role === 'user' ? 'Вы' : 'Lumira';

      const body = document.createElement('div');
      body.className = 'message-body';
      body.textContent = text;

      wrapper.appendChild(title);
      wrapper.appendChild(body);
      chatWindow.appendChild(wrapper);
      chatWindow.scrollTop = chatWindow.scrollHeight;
      renderMath(body);
      return body;
    }

    function renderDialogs() {
      dialogsList.innerHTML = '';
      dialogs.forEach((dialog) => {
        const item = document.createElement('div');
        item.className = 'dialog-item' + (dialog.id === activeDialogId ? ' active' : '');
        const updatedLabel = dialog.updated_at ? dialog.updated_at.replace('T', ' ') : '';
        item.innerHTML = `
          <div class="dialog-info">
            <div class="dialog-title-text">${dialog.title}</div>
            <div class="dialog-date">${updatedLabel}</div>
          </div>
          <button class="icon-button" title="Удалить" data-dialog="${dialog.id}">✕</button>
        `;

        item.addEventListener('click', (event) => {
          if (event.target.matches('.icon-button')) {
            return;
          }
          if (dialog.id !== activeDialogId) {
            selectDialog(dialog.id);
          }
        });

        const deleteBtn = item.querySelector('.icon-button');
        deleteBtn.addEventListener('click', async (event) => {
          event.stopPropagation();
          await deleteDialog(dialog.id);
        });

        item.addEventListener('dblclick', async (event) => {
          event.stopPropagation();
          const newTitle = prompt('Введите название диалога', dialog.title);
          if (newTitle && newTitle.trim()) {
            await renameDialog(dialog.id, newTitle.trim());
          }
        });

        dialogsList.appendChild(item);
      });
    }

    async function loadDialogs() {
      const response = await fetch('/dialogs');
      dialogs = await response.json();
      if (!dialogs.length) {
        await createDialog();
        return;
      }
      if (!activeDialogId) {
        activeDialogId = dialogs[0].id;
        dialogTitleEl.textContent = dialogs[0].title;
        await loadMessages(activeDialogId);
      }
      renderDialogs();
    }

    async function selectDialog(id) {
      activeDialogId = id;
      const dialog = dialogs.find((d) => d.id === id);
      if (dialog) {
        dialogTitleEl.textContent = dialog.title;
      }
      renderDialogs();
      await loadMessages(id);
    }

    async function loadMessages(id) {
      chatWindow.innerHTML = '';
      try {
        const response = await fetch(`/dialogs/${id}/messages`);
        if (!response.ok) {
          chatWindow.textContent = 'Не удалось загрузить сообщения.';
          return;
        }
        const data = await response.json();
        dialogTitleEl.textContent = data.dialog.title;
        data.messages.forEach((msg) => {
          appendMessage(msg.role === 'user' ? 'user' : 'assistant', msg.content);
        });
        if (data.messages.length === 0) {
          appendMessage('assistant', 'Привет! Я готова помочь с учёбой.');
        }
      } catch (err) {
        chatWindow.textContent = 'Ошибка загрузки: ' + err;
      }
    }

    async function createDialog() {
      const response = await fetch('/dialogs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
      const dialog = await response.json();
      await loadDialogs();
      await selectDialog(dialog.id);
    }

    async function deleteDialog(id) {
      await fetch(`/dialogs/${id}`, { method: 'DELETE' });
      activeDialogId = null;
      await loadDialogs();
    }

    async function renameDialog(id, title) {
      await fetch(`/dialogs/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
      });
      await loadDialogs();
      await selectDialog(id);
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (isSending) {
        return;
      }
      const userText = messageInput.value.trim();
      const hasFile = fileInput && fileInput.files.length > 0;
      const selectedFile = hasFile ? fileInput.files[0] : null;
      const selectedLanguage = fileLanguage ? fileLanguage.value : 'rus';
      if (!userText && !hasFile) {
        return;
      }
      if (!activeDialogId) {
        await createDialog();
      }

      console.log('Sending chat request', {
        dialogId: activeDialogId,
        hasFile: Boolean(selectedFile),
        fileName: selectedFile?.name || null,
        fileSize: selectedFile?.size || null,
        fileType: selectedFile?.type || null,
        language: selectedLanguage,
        hasText: Boolean(userText),
      });

      const fileLabel = selectedFile
        ? `📎 ${selectedFile.name}`
        : '';
      const displayText = userText || fileLabel;
      appendMessage('user', displayText);
      messageInput.value = '';
      const pendingBody = appendMessage('assistant', 'Обработка...');

      isSending = true;
      try {
        let response;
        if (selectedFile) {
          const formData = new FormData();
          formData.append('dialog_id', activeDialogId);
          formData.append('message', userText);
          formData.append('language', selectedLanguage);
          formData.append('file', selectedFile, selectedFile.name);
          response = await fetch('/chat', { method: 'POST', body: formData });
        } else {
          response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dialog_id: activeDialogId, message: userText }),
          });
        }

        if (fileInput) {
          fileInput.value = '';
          if (fileNameLabel) {
            fileNameLabel.textContent = 'Файл не выбран';
          }
        }

        const data = await response.json();
        if (!response.ok) {
          pendingBody.textContent = data.detail || 'Ошибка запроса.';
          console.error('Chat request failed', data, response.status);
        } else {
          pendingBody.textContent = data.answer;
          await loadDialogs();
        }
        renderMath(pendingBody);
      } catch (err) {
        pendingBody.textContent = 'Ошибка подключения: ' + err;
        renderMath(pendingBody);
      } finally {
        isSending = false;
      }
    });

    newDialogBtn.addEventListener('click', async () => {
      await createDialog();
    });

    renameDialogBtn.addEventListener('click', async () => {
      if (!activeDialogId) {
        return;
      }
      const current = dialogs.find((d) => d.id === activeDialogId);
      const title = prompt('Введите название диалога', current ? current.title : '');
      if (title && title.trim()) {
        await renameDialog(activeDialogId, title.trim());
      }
    });

    messageInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        form.dispatchEvent(new Event('submit', { cancelable: true }));
      }
    });

    loadDialogs();
  </script>
</body>
</html>
"""

TELEGRAM_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Lumira Telegram</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script>
    window.MathJax = window.MathJax || {};
    window.MathJax.tex = {
      inlineMath: [['$', '$'], ['\\(', '\\)']],
      displayMath: [['$$', '$$'], ['\\[', '\\]']],
    };
    window.MathJax.options = {
      skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'],
    };
  </script>
  <script async id="MathJax-script" src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
  <style>
    body {
      font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
      background: #0a0f1f;
      margin: 0;
      color: #f4f6ff;
      display: flex;
      flex-direction: column;
      min-height: 100vh;
    }
    .container {
      flex: 1;
      display: flex;
      flex-direction: column;
      padding: 16px;
    }
    .header {
      margin-bottom: 12px;
    }
    .header h1 {
      margin: 0;
      font-size: 1.25rem;
    }
    .status {
      font-size: 0.9rem;
      color: rgba(244, 246, 255, 0.75);
    }
    .chat {
      flex: 1;
      background: rgba(255, 255, 255, 0.06);
      border-radius: 18px;
      padding: 16px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 14px;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
    }
    .message {
      padding: 12px 16px;
      border-radius: 14px;
      line-height: 1.4;
      font-size: 0.95rem;
      max-width: 90%;
    }
    .message.user {
      align-self: flex-end;
      background: #4a6cf7;
    }
    .message.assistant {
      align-self: flex-start;
      background: rgba(255, 255, 255, 0.14);
    }
    form {
      margin-top: 12px;
      display: flex;
      gap: 8px;
    }
    textarea {
      flex: 1;
      border-radius: 14px;
      border: 1px solid rgba(255, 255, 255, 0.2);
      background: rgba(10, 15, 31, 0.85);
      color: #f4f6ff;
      padding: 12px;
      resize: none;
      min-height: 64px;
      font-size: 0.95rem;
      font-family: inherit;
    }
    button {
      border: none;
      border-radius: 14px;
      padding: 0 20px;
      background: #4a6cf7;
      color: #fff;
      font-weight: 600;
      font-size: 0.95rem;
      cursor: pointer;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>Lumira</h1>
      <div class="status" id="status">Подключение…</div>
    </div>
    <div class="chat" id="tg-chat"></div>
    <form id="tg-form">
      <textarea id="tg-message" placeholder="Напишите сообщение…" required></textarea>
      <button type="submit">Отправить</button>
    </form>
  </div>

  <script>
    const telegram = window.Telegram?.WebApp;
    if (telegram) {
      telegram.expand();
      telegram.disableVerticalSwipes();
    }

    const statusEl = document.getElementById('status');
    const chatWindow = document.getElementById('tg-chat');
    const form = document.getElementById('tg-form');
    const messageInput = document.getElementById('tg-message');

    let dialogId = null;
    let isSending = false;

    function renderMath(element) {
      if (window.MathJax?.typesetPromise) {
        MathJax.typesetPromise([element]).catch(() => {});
      }
    }

    function appendMessage(role, text) {
      const div = document.createElement('div');
      div.className = `message ${role}`;
      div.textContent = text;
      chatWindow.appendChild(div);
      chatWindow.scrollTop = chatWindow.scrollHeight;
      renderMath(div);
      return div;
    }

    async function initTelegramChat() {
      const initData = telegram?.initData || new URLSearchParams(window.location.search).get('tgWebAppData') || '';
      window.__tgInitData = initData;
      try {
        const response = await fetch('/telegram/session', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: initData }),
        });
        if (!response.ok) {
          const error = await response.json();
          statusEl.textContent = error.detail || 'Ошибка инициализации.';
          return;
        }
        const data = await response.json();
        dialogId = data.dialog_id;
        statusEl.textContent = data.title || 'Готово';
        await loadMessages();
      } catch (error) {
        statusEl.textContent = 'Ошибка подключения: ' + error;
      }
    }

    async function loadMessages() {
      if (!dialogId) {
        return;
      }
      chatWindow.innerHTML = '';
      const headers = window.__tgInitData
        ? { 'X-Telegram-Init-Data': window.__tgInitData }
        : {};
      const response = await fetch(`/dialogs/${dialogId}/messages`, { headers });
      if (!response.ok) {
        statusEl.textContent = 'Не удалось загрузить сообщения.';
        return;
      }
      const data = await response.json();
      data.messages.forEach((msg) => {
        appendMessage(msg.role === 'user' ? 'user' : 'assistant', msg.content);
      });
      if (data.messages.length === 0) {
        appendMessage('assistant', 'Привет! Я готова помочь с учёбой.');
      }
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (isSending || !dialogId) {
        return;
      }
      const text = messageInput.value.trim();
      if (!text) {
        return;
      }
      appendMessage('user', text);
      const pending = appendMessage('assistant', 'Обработка…');
      messageInput.value = '';
      isSending = true;
      try {
        const headers = {
          'Content-Type': 'application/json',
        };
        if (window.__tgInitData) {
          headers['X-Telegram-Init-Data'] = window.__tgInitData;
        }
        const response = await fetch('/chat', {
          method: 'POST',
          headers,
          body: JSON.stringify({ dialog_id: dialogId, message: text }),
        });
        const data = await response.json();
        if (!response.ok) {
          pending.textContent = data.detail || 'Ошибка запроса.';
        } else {
          pending.textContent = data.answer;
        }
        renderMath(pending);
      } catch (error) {
        pending.textContent = 'Ошибка: ' + error;
        renderMath(pending);
      } finally {
        isSending = false;
      }
    });

    messageInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        form.dispatchEvent(new Event('submit', { cancelable: true }));
      }
    });

    initTelegramChat();
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_PAGE


@app.get("/telegram", response_class=HTMLResponse)
def telegram_page():
    return TELEGRAM_PAGE


@app.get("/dialogs")
def read_dialogs():
    return list_dialogs()


@app.post("/dialogs")
def create_dialog_endpoint(request: CreateDialogRequest):
    dialog = create_dialog_with_greeting(request.title)
    return dialog


@app.get("/dialogs/{dialog_id}/messages")
def read_dialog_messages(dialog_id: int, request: Request):
    dialog = get_dialog(dialog_id)
    if not dialog:
        raise HTTPException(status_code=404, detail="Диалог не найден.")

    tg_user_id = get_telegram_user_from_request(request)
    if tg_user_id:
        owned = get_dialog_by_owner("telegram", tg_user_id)
        if not owned or owned["id"] != dialog_id:
            raise HTTPException(status_code=403, detail="Нет доступа к этому диалогу.")

    messages = get_dialog_messages(dialog_id)
    return {"dialog": {"id": dialog["id"], "title": dialog["title"]}, "messages": messages}


@app.delete("/dialogs/{dialog_id}")
def remove_dialog(dialog_id: int):
    dialog = get_dialog(dialog_id)
    if not dialog:
        raise HTTPException(status_code=404, detail="Диалог не найден.")
    delete_dialog(dialog_id)
    ensure_default_dialog()
    return {"status": "ok"}


@app.patch("/dialogs/{dialog_id}")
def rename_dialog_endpoint(dialog_id: int, request: RenameDialogRequest):
    dialog = get_dialog(dialog_id)
    if not dialog:
        raise HTTPException(status_code=404, detail="Диалог не найден.")
    rename_dialog(dialog_id, request.title.strip() or "Без названия")
    return {"status": "ok"}


@app.post("/telegram/session")
def telegram_session(request: TelegramSessionRequest):
    user = verify_telegram_init_data(request.init_data)
    user_id = str(user.get("id"))
    if not user_id:
        raise HTTPException(status_code=400, detail="Не удалось определить пользователя.")

    title = f"Telegram · {user.get('first_name', '')}".strip() or "Telegram диалог"
    dialog = get_or_create_owner_dialog("telegram", user_id, title=title)
    return {"dialog_id": dialog["id"], "title": dialog["title"], "user": user}


async def _process_uploaded_file(file: UploadFile, language: str) -> str:
    allowed_types = {"image/png", "image/jpeg", "image/jpg", "application/pdf"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Допустимы PNG, JPEG или PDF файлы.")

    content = await file.read()
    max_size = 5 * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail="Файл слишком большой (максимум 5 МБ).")

    logger.info(
        "OCR upload: name=%s content_type=%s size=%d lang=%s",
        file.filename,
        file.content_type,
        len(content),
        language,
    )

    try:
        text = parse_image_with_ocr_space(
            file.filename or "upload",
            content,
            language=language or "rus",
        )
    except OCRSpaceError as exc:
        raise HTTPException(status_code=502, detail=f"OCR ошибка: {exc}") from exc

    cleaned = (text or "").strip()
    if not cleaned:
        logger.warning("OCR upload %s produced empty text", file.filename)
        raise HTTPException(status_code=502, detail="Не удалось распознать текст в файле.")
    logger.info(
        "OCR upload %s successfully parsed %d characters",
        file.filename,
        len(cleaned),
    )
    return cleaned


@app.post("/chat", response_model=ChatResponse)
async def chat(req: Request):
    content_type = req.headers.get("content-type", "")
    dialog_id: Optional[int] = None
    message = ""
    upload: Optional[UploadFile] = None
    language = "rus"

    if content_type.startswith("application/json"):
        payload = await req.json()
        data = ChatRequest(**payload)
        dialog_id = data.dialog_id
        message = (data.message or "").strip()
    else:
        form = await req.form()
        logger.info("Multipart form keys: %s", list(form.keys()))
        for key, value in form.multi_items():
            logger.info(" - %s => %s", key, type(value).__name__)
        raw_dialog_id = form.get("dialog_id")
        message = (form.get("message") or "").strip()
        language = (form.get("language") or "rus").strip() or "rus"
        candidate = form.get("file")
        logger.info("Primary file candidate type: %s", type(candidate).__name__)
        if hasattr(candidate, "filename"):
            upload = candidate  # treat as UploadFile-like
        elif "file" in form:
            possible = form["file"]
            logger.info("Secondary file lookup type: %s", type(possible).__name__)
            if hasattr(possible, "filename"):
                upload = possible
        if upload is None:
            file_items = form.getlist("file")
            logger.info(
                "getlist('file') types: %s",
                [type(item).__name__ for item in file_items],
            )
            for item in file_items:
                if hasattr(item, "filename"):
                    upload = item
                    break
        if isinstance(raw_dialog_id, str) and raw_dialog_id.isdigit():
            dialog_id = int(raw_dialog_id)
        elif isinstance(raw_dialog_id, int):
            dialog_id = raw_dialog_id

    if dialog_id is None:
        raise HTTPException(status_code=400, detail="Не указан dialog_id.")

    if not message and upload is None:
        raise HTTPException(status_code=400, detail="Введите сообщение или прикрепите файл.")

    logger.info(
        "Chat request dialog=%s type=%s has_file=%s msg_len=%d lang=%s",
        dialog_id,
        content_type.split(";")[0],
        bool(upload),
        len(message),
        language,
    )

    dialog = get_dialog(dialog_id)
    if not dialog:
        raise HTTPException(status_code=404, detail="Диалог не найден.")

    tg_user_id = get_telegram_user_from_request(req)
    if tg_user_id:
        owned = get_dialog_by_owner("telegram", tg_user_id)
        if not owned or owned["id"] != dialog["id"]:
            raise HTTPException(status_code=403, detail="Нет доступа к этому диалогу.")

    state = normalize_state(dialog.get("state"))

    if upload is not None:
        ocr_text = await _process_uploaded_file(upload, language)
        snippet = ocr_text[:4000]
        prefix = (
            f"Пользователь загрузил файл «{upload.filename or 'без названия'}».\n"
            f"Распознанный текст:\n{snippet}"
        )
        if message:
            message = f"{prefix}\n\nДополнительный вопрос пользователя:\n{message}"
        else:
            message = prefix
        logger.info(
            "Dialog %s: appended OCR text (%d chars) to user message",
            dialog_id,
            len(snippet),
        )

    try:
        add_dialog_message(dialog_id, "user", message)
        answer, new_state = process_user_message(ACCESS_TOKEN, message, state)
        update_dialog_state(dialog_id, new_state)
        add_dialog_message(dialog_id, "assistant", answer)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return ChatResponse(answer=answer)
