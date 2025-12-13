# main.py
from dotenv import load_dotenv
load_dotenv()


from gigachat_api import get_access_token, chat_with_gigachat, chat_with_gigachat_messages
# SQLite storage
from db.sqlite_store import init_db, save_test_result, load_test_results, calc_average
from typing import Optional, Tuple, Dict, Any

# ALL agents which are used
from agents.moderator import run_moderator
from agents.tutor import run_tutor
from agents.examiner import run_examiner
from agents.analyser import run_analyser 
from agents.problem_solver import start_problem_solver, continue_problem_solver
from agents.summarizer import run_summarizer



#ALL utils which are used
from utils.format_exam import format_exam


#ALL memories which are used
def create_initial_state() -> Dict[str, Any]:
    """
    Создаёт чистое состояние диалога.
    """
    return {
        "tutor_history": [],
        "last_topic": None,
        "current_test": None,
        "problem_solver": {
            "active": False,
            "topic": None,
            "steps": [],
            "current_step": 0,
        },
    }


def normalize_state(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Гарантирует наличие всех ключей в состоянии (для старых диалогов).
    """
    base = create_initial_state()
    if not isinstance(state, dict):
        return base

    for key, default_value in base.items():
        if key not in state:
            state[key] = default_value
        elif isinstance(default_value, dict):
            # рекурсивно дополняем словари
            for nested_key, nested_default in default_value.items():
                if nested_key not in state[key]:
                    state[key][nested_key] = nested_default

    current_test = state.get("current_test")
    if isinstance(current_test, dict):
        normalized_test: Dict[int, str] = {}
        for key, value in current_test.items():
            try:
                normalized_test[int(key)] = str(value).upper()
            except (ValueError, TypeError):
                continue
        state["current_test"] = normalized_test if normalized_test else None

    return state


def _parse_progress_command(user_text: str) -> Tuple[bool, Optional[str]]:
    """
    Возвращает (is_progress_command, topic_filter).
    """
    lowered = user_text.lower().strip()
    if not lowered.startswith("progress"):
        return False, None

    parts = user_text.split(maxsplit=1)
    topic_filter = parts[1].strip() or None if len(parts) > 1 else None
    return True, topic_filter


def show_progress(topic_filter: Optional[str] = None) -> str:
    """
    Показывает историю результатов из SQLite + среднее.
    Если передан topic_filter, показывает только результаты по темам,
    где topic содержит эту подстроку.
    Например: progress planets → только темы, где есть 'planets'.
    """
    results = load_test_results(limit=200, topic=topic_filter)

    lines = []
    if not results:
        if topic_filter:
            return f"Пока нет ни одного теста по теме, содержащей: '{topic_filter}'."
        return "Пока нет ни одного завершённого теста."

    if topic_filter:
        lines.append(f"История тестов (фильтр по теме: '{topic_filter}'):")
    else:
        lines.append("История тестов:")

    for i, r in enumerate(reversed(results), start=1):  # показываем от старых к новым
        topic = r.get("topic") or "(неизвестная тема)"
        score = r.get("score", 0)
        total = r.get("total", 0)
        percent = r.get("percent", 0)
        lines.append(f"{i}. Тема: {topic} — результат: {score}/{total} ({percent}%)")

    avg = calc_average(results)
    lines.append(
        f"\nСредний результат: {avg['correct']}/{avg['total']} ({avg['percent']}%)"
    )
    return "\n".join(lines)


def process_user_message(access_token: str, user_text: str, state: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """
    Обрабатывает один запрос пользователя и возвращает текст ответа.
    Эту функцию можно вызывать из CLI или из веб-интерфейса.
    """
    state = normalize_state(state)

    if not user_text:
        return "Пожалуйста, введите запрос.", state

    request_text = user_text.strip()

    # Команда прогресса
    is_progress, topic_filter = _parse_progress_command(request_text)
    if is_progress:
        return show_progress(topic_filter), state

    # --- Если активен Problem Solver и пользователь отвечает "да/нет" ---
    if state["problem_solver"]["active"]:
        normalized = request_text.lower()
        yes_words = {"yes", "y", "да", "ага", "понял", "поняла", "понял.", "поняла."}
        no_words = {"no", "n", "нет", "неа", "не", "не понял", "не поняла"}

        if normalized in yes_words or normalized in no_words:
            answer, state["problem_solver"] = continue_problem_solver(
                access_token,
                state["problem_solver"],
                request_text,
            )
            return answer, state

    # пустой ввод после trim
    if not request_text:
        return "Пожалуйста, введите запрос.", state

    agent_id, change_topic = run_moderator(access_token, request_text)

    if change_topic == 1:
        state["last_topic"] = request_text

    if agent_id == 1:
        # ---- TUTOR ----
        answer, state["tutor_history"] = run_tutor(
            access_token,
            request_text,
            state["tutor_history"],
        )

    elif agent_id == 2:
        # ---- EXAMINER ----
        instructions = (
            "\nКак отвечать на тесты\n"
            "Пишите только в формате:\n"
            "1a 2c 3b 4d 5a\n"
            "Где:\n"
            "число — номер вопроса,\n"
            "буква — выбранный вариант ответа."
        )
        if state["last_topic"] is None:
            topic = request_text
            state["last_topic"] = topic
        else:
            topic = state["last_topic"]

        raw_test = run_examiner(access_token, topic)
        questions_text, answers_dict, theme = format_exam(raw_test)

        state["last_topic"] = theme
        state["current_test"] = answers_dict

        answer = f"{instructions}\n\n{questions_text}"

    elif agent_id == 3:
        # ---- Analyzer ----
        if state["current_test"] is None:
            answer = "Нет теста для проверки!"
        else:
            report_text, score, total = run_analyser(state["current_test"], request_text)
            percent = int(score / total * 100) if total > 0 else 0
            save_test_result(
                topic=state["last_topic"],
                score=score,
                total=total,
                percent=percent,
                user_answers=request_text,
            )
            state["current_test"] = None
            answer = report_text

    elif agent_id == 4:
        # ---- PROBLEM SOLVER ----
        answer, ps_state = start_problem_solver(access_token, request_text)
        state["problem_solver"] = ps_state

    elif agent_id == 5:
        # ---- SUMMARIZER ----
        answer = run_summarizer(access_token, request_text)
    else:
        answer = "Неизвестный режим, модератор вернул странный код."

    return answer, state






if __name__ == "__main__":
    # 1. Берём токен
    token = get_access_token()
    # Инициализация SQLite (создание таблиц)
    init_db()
    print("\n\nДобро пожаловать в Lumira!\nLumira — это умный учебный помощник, который может объяснять темы, тренировать тебя с помощью тестов, анализировать ответы и помогать решать задачи.")

    state = create_initial_state()

    while True:

        user_text = input("\nНапиши свой запрос: ")
        
        if user_text == 'exit':
            print("Bye-bye")
            break

        if not user_text:
            continue

        answer, state = process_user_message(token, user_text, state)
        print("\nОтвет модели:\n")
        print(answer)
