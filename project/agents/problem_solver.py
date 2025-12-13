# agents/problem_solver.py

from typing import Dict, List, Tuple
import json

from gigachat_api import chat_with_gigachat_messages
from langsmith import traceable



PROBLEM_SOLVER_PROMPT = (
    "Ты — Problem Solver, пошаговый объясняющий ассистент.\n"
    "\n"
    "Твоя задача: разбить сложную тему на 3 коротких логичных шага и объяснить каждый шаг простым языком.\n"
    "\n"
    "Формат ответа ДОЛЖЕН быть строго таким (JSON):\n"
    "{\n"
    "  \"steps\": [\n"
    "    \"Короткое объяснение шага 1\",\n"
    "    \"Короткое объяснение шага 2\",\n"
    "    \"Короткое объяснение шага 3\"\n"
    "  ]\n"
    "}\n"
    "\n"
    "Требования к шагам:\n"
    "- Каждый шаг должен быть законченным и понятным объяснением одной части темы.\n"
    "- Объясняй на том же языке, на котором задаёт вопрос пользователь.\n"
    "- Не пиши ничего, кроме JSON, без комментариев и текста вокруг.\n"
)


def _generate_steps(access_token: str, user_question: str) -> List[str]:
    """
    Запрашивает у GigaChat план из 3 шагов и возвращает список строк.
    """
    messages = [
        {"role": "system", "content": PROBLEM_SOLVER_PROMPT},
        {"role": "user", "content": user_question},
    ]

    raw_answer = chat_with_gigachat_messages(access_token, messages)

    # Пытаемся распарсить JSON
    try:
        data = json.loads(raw_answer)
        steps = data.get("steps", [])
        if isinstance(steps, list) and len(steps) >= 1:
            # Берём максимум 3 шага
            return [str(s) for s in steps[:3]]
    except Exception:
        pass

    # Фолбэк: если модель не дала JSON — всё равно отдаём один шаг
    return [raw_answer.strip()]

def _simplify_step(access_token: str, topic: str, current_explanation: str) -> str:
    """
    Просим модель объяснить тот же шаг проще, другими словами.
    """

    system_prompt = (
        "Ты помогаешь разобрать сложный материал по шагам.\n"
        "Тебе дают один шаг объяснения, и ты должен объяснить ТО ЖЕ самое, "
        "но проще, короче и другими словами, чтобы это понял ученик.\n"
        "Не добавляй новых фактов, только переформулируй.\n"
    )

    user_content = (
        f"Тема: {topic}\n\n"
        f"Текущий текст шага:\n{current_explanation}\n\n"
        "Переформулируй этот шаг проще и понятнее, чтобы было легче понять."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    new_text = chat_with_gigachat_messages(access_token, messages)
    return new_text.strip()

@traceable(name="problem_solver_start")
def start_problem_solver(access_token: str, user_question: str) -> Tuple[str, Dict]:
    """
    Старт Problem Solver-а:
    - запрашивает у модели 3 шага,
    - возвращает текст для пользователя и состояние problem_solver.
    """
    steps = _generate_steps(access_token, user_question)

    # Гарантируем не менее 1 шага
    if not steps:
        steps = ["Пока не удалось сформулировать план, попробуй переформулировать вопрос."]

    state = {
        "active": True,
        "topic": user_question,
        "steps": steps,
        "current_step": 0,
    }

    current_step_index = state["current_step"]
    text = (
        "Давай разберём это по шагам.\n\n"
        f"Шаг {current_step_index + 1}:\n{steps[current_step_index]}\n\n"
        "Понятно ли это? (да/нет)"
    )

    return text, state

@traceable(name="continue_problem_solver")
def continue_problem_solver(access_token: str, problem_state: Dict, user_reply: str):
    """
    Продолжение Problem Solver-а:
    - если пользователь ответил 'да' → переходим к следующему шагу (или завершаем),
    - если 'нет' → переформулируем текущий шаг проще и показываем обновлённый текст.
    """
    if not problem_state.get("active"):
        return "Сейчас нет активного пошагового объяснения. Задай новую тему.", problem_state

    steps: List[str] = problem_state.get("steps", [])
    current_step = problem_state.get("current_step", 0)
    topic = problem_state.get("topic", "")

    ans = user_reply.strip().lower()
    yes_words = {"yes", "y", "да", "ага", "понял", "поняла", "понял.", "поняла."}
    no_words = {"no", "n", "нет", "неа", "не", "не понял", "не поняла"}

    # --- ПОЛЬЗОВАТЕЛЬ СКАЗАЛ "ДА" ---
    if ans in yes_words:
        current_step += 1

        if current_step < len(steps):
            problem_state["current_step"] = current_step
            text = (
                f"Отлично! Тогда переходим дальше.\n\n"
                f"Шаг {current_step + 1}:\n{steps[current_step]}\n\n"
                "Понятно ли это? (да/нет)"
            )
            return text, problem_state
        else:
            problem_state["active"] = False
            text = (
                "Здорово! Мы разобрали все части плана.\n"
                "Если что-то ещё осталось непонятно — задай новый вопрос."
            )
            return text, problem_state

    # --- ПОЛЬЗОВАТЕЛЬ СКАЗАЛ "НЕТ" ---
    if ans in no_words:
        if 0 <= current_step < len(steps):
            # просим модель переформулировать текущий шаг проще
            new_expl = _simplify_step(access_token, topic, steps[current_step])
            steps[current_step] = new_expl
            problem_state["steps"] = steps

            text = (
                "Хорошо, давай попробуем объяснить этот шаг по-другому:\n\n"
                f"Шаг {current_step + 1}:\n{new_expl}\n\n"
                "Теперь понятнее? (да/нет)"
            )
            return text, problem_state

    # --- Любой другой ответ ---
    text = (
        "Ответь, пожалуйста, 'да' или 'нет', чтобы я понял, переходить дальше "
        "или объяснить этот шаг ещё раз по-другому."
    )
    return text, problem_state
