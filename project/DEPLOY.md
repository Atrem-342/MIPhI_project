## Переменные окружения

Скопируйте `.env.example` в `.env` и заполните:

- `GIGACHAT_CLIENT_ID`
- `GIGACHAT_CLIENT_SECRET`
- (опционально) `GIGACHAT_SCOPE`, `GIGACHAT_MODEL`, `GIGACHAT_RQUID`

На хостингах эти значения нужно задать через UI/CLI (неcommитить с реальными данными).

## Railway (рекомендуемый старт)

1. Закоммитьте `requirements.txt` и `Procfile`. Убедитесь, что `.env` исключён из git (`.gitignore`).
2. Загрузите код на GitHub.
3. В Railway → New Project → Deploy from GitHub → выберите репозиторий.
4. После первого билда укажите переменные окружения: Settings → Variables → `GIGACHAT_CLIENT_ID`, `GIGACHAT_CLIENT_SECRET`, и т.д.
5. Railway автоматически запустит команду из `Procfile` (`python3 -m uvicorn web_app:app ...`). Сервис будет доступен по сгенерированному домену.
6. Чтобы база SQLite не терялась при перезапусках, добавьте Volume или подключите Railway PostgreSQL и перенесите таблицы.

## Render (альтернатива)

1. Render → New Web Service → подключите GitHub‑репозиторий.
2. Build Command: `pip install -r requirements.txt`
3. Start Command: `python3 -m uvicorn web_app:app --host 0.0.0.0 --port $PORT`
4. Укажите переменные окружения в разделе Environment.
5. Render создаст постоянный веб‑сервис; при бездействии бесплатный план “усыпляет” приложение.

## Railway + Managed Postgres

Если хотите хранить диалоги вне локального диска:

1. В проекте Railway добавьте PostgreSQL (Add Service → Database).
2. Скопируйте строку подключения в переменную `DATABASE_URL`.
3. Мигрируйте таблицы `dialogs`, `dialog_messages`, `test_results` в Postgres (например, через Alembic или вручную).
4. Обновите код для работы через SQLAlchemy или `asyncpg`. (В текущей версии используется SQLite, так что для Postgres потребуется рефакторинг.)

## Deta Space (самый быстрый способ показать)

1. Создайте Space, установите Deta CLI (`curl -fsSL https://get.deta.dev/cli.sh | sh`).
2. В `Spacefile` укажите команду запуска `python3 -m uvicorn web_app:app --host 0.0.0.0 --port 8080`.
3. `deta deploy` и задайте переменные окружения через интерфейс Space.
4. Ограничения: нет постоянного локального хранилища; нужно хранить диалоги в Deta Base или другом внешнем сервисе.

## Fly.io / Docker (самое гибкое, но сложнее)

1. Напишите `Dockerfile` (например, на базе `python:3.11-slim`, копируете код, устанавливаете зависимости).
2. `fly launch` → укажите, что использовать Dockerfile, настройте регион.
3. Задайте переменные окружения: `fly secrets set GIGACHAT_CLIENT_ID=...`
4. При необходимости создайте Volume для хранения `lumira.db`.
5. `fly deploy` — приложение поднимется во “флай”-клауде и получит глобальный адрес.

## Общие шаги для других сервисов

1. Убедитесь, что Python ≥3.10 доступен.
2. Установите зависимости `pip install -r requirements.txt`.
3. Запустите `python3 -m uvicorn web_app:app --host 0.0.0.0 --port $PORT`.
4. Пропишите переменные окружения для GigaChat ключей.
5. Настройте HTTPS/домен в панели управления, если нужно.
