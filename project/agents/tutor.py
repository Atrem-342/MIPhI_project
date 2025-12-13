# agents/tutor.py
from typing import List, Dict, Tuple
from gigachat_api import chat_with_gigachat_messages
from langsmith import traceable



TUTOR_PROMPT = (
    "Ты — персональный репетитор.\n"
    "\n"
    "Твои задачи:\n"
    "1) Понять, о чём спрашивает ученик, и какой у него примерный уровень (школьник, студент и т.д.).\n"
    "2) Объяснять материал простым, человеческим языком, без лишней воды.\n"
    "3) Использовать примеры, аналогии и пошаговые объяснения, особенно для сложных идей.\n"
    "4) Если вопрос про вычисления или формулы — показывать ход решения по шагам.\n"
    "5) Если ученик явно ошибается — мягко исправить и объяснить, в чём именно ошибка.\n"
    "\n"
    "Правила оформления ответа:\n"
    "- Пиши на том языке, на котором задал вопрос пользователь (если не указано обратное).\n"
    "- Структурируй ответ: абзацы, при необходимости списки.\n"
    "- Не используй слишком сложные термины без пояснения.\n"
    "\n"
    "Сейчас тебе передадут вопрос ученика. Объясняй так, как будто говоришь живому человеку."
)

@traceable(name="tutor_run")
def run_tutor(
    access_token: str,
    user_message: str,
    history: List[Dict[str, str]],
) -> Tuple[str, List[Dict[str, str]]]:
    """
    Агент-репетитор с памятью.
    history — список сообщений вида {"role": "user"|"assistant", "content": "..."}.
    Возвращает (ответ модели, обновлённая history).
    """

    # 1. Собираем messages: system + (обрезанная) история + текущий вопрос
    messages: List[Dict[str, str]] = []

    # system — инструкция для модели
    messages.append({"role": "system", "content": TUTOR_PROMPT})

    # Обрезаем историю, чтобы не раздувать контекст
    MAX_HISTORY_MESSAGES = 10
    trimmed_history = history[-MAX_HISTORY_MESSAGES:]

    messages.extend(trimmed_history)

    # Текущее сообщение пользователя
    messages.append({"role": "user", "content": user_message})

    # 2. Запрос к GigaChat
    answer = chat_with_gigachat_messages(access_token, messages)

    # 3. Обновляем историю: добавляем новый user-вопрос и ответ ассистента
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": answer})

    return answer, history

# "6) В конце ответа всегда задавай один короткий вопрос, чтобы проверить понимание.\n"