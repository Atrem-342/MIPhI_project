from typing import Optional

from fastapi import FastAPI, HTTPException
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
)
from gigachat_api import get_access_token
from main import process_user_message, create_initial_state, normalize_state


ACCESS_TOKEN = get_access_token()
init_db()

app = FastAPI(title="Lumira Web API")
app.mount("/static", StaticFiles(directory="static"), name="static")

GREETING_TEXT = "Привет! Я готова помочь с учёбой."


class ChatRequest(BaseModel):
    dialog_id: int
    message: str


class ChatResponse(BaseModel):
    answer: str


class CreateDialogRequest(BaseModel):
    title: Optional[str] = None


class RenameDialogRequest(BaseModel):
    title: str


def create_dialog_with_greeting(title: Optional[str] = None):
    dialog = create_dialog(title, create_initial_state())
    add_dialog_message(dialog["id"], "assistant", GREETING_TEXT)
    return dialog


def ensure_default_dialog() -> None:
    if not list_dialogs():
        create_dialog_with_greeting("Новый диалог")


ensure_default_dialog()

HTML_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <title>Lumira</title>
  <link rel="stylesheet" href="/static/style.css" />
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

      <form id="chat-form" class="input-area">
        <textarea id="message" name="message" placeholder="Спросите что угодно…" required></textarea>
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

    let dialogs = [];
    let activeDialogId = null;
    let isSending = false;

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
      if (!userText) {
        return;
      }
      if (!activeDialogId) {
        await createDialog();
      }

      appendMessage('user', userText);
      messageInput.value = '';
      const pendingBody = appendMessage('assistant', 'Обработка...');

      isSending = true;
      try {
        const response = await fetch('/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ dialog_id: activeDialogId, message: userText }),
        });

        const data = await response.json();
        if (!response.ok) {
          pendingBody.textContent = data.detail || 'Ошибка запроса.';
        } else {
          pendingBody.textContent = data.answer;
          await loadDialogs();
        }
      } catch (err) {
        pendingBody.textContent = 'Ошибка подключения: ' + err;
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


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_PAGE


@app.get("/dialogs")
def read_dialogs():
    return list_dialogs()


@app.post("/dialogs")
def create_dialog_endpoint(request: CreateDialogRequest):
    dialog = create_dialog_with_greeting(request.title)
    return dialog


@app.get("/dialogs/{dialog_id}/messages")
def read_dialog_messages(dialog_id: int):
    dialog = get_dialog(dialog_id)
    if not dialog:
        raise HTTPException(status_code=404, detail="Диалог не найден.")
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


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Введите сообщение.")

    dialog = get_dialog(request.dialog_id)
    if not dialog:
        raise HTTPException(status_code=404, detail="Диалог не найден.")

    state = normalize_state(dialog.get("state"))

    try:
        add_dialog_message(request.dialog_id, "user", message)
        answer, new_state = process_user_message(ACCESS_TOKEN, message, state)
        update_dialog_state(request.dialog_id, new_state)
        add_dialog_message(request.dialog_id, "assistant", answer)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return ChatResponse(answer=answer)
