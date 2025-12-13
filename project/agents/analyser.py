# agents/analyser.py

import re
from typing import Dict, List
from langsmith import traceable



ANALYSER_PROMPT = (
    "Ты — аналитик результатов теста (Analyzer).\n"
    "\n"
    "Тебе будет передан JSON с результатами теста. В JSON будет информация примерно такого вида:\n"
    "{\n"
    "  \"questions\": [\n"
    "    {\n"
    "      \"id\": 1,\n"
    "      \"text\": \"Текст вопроса\",\n"
    "      \"options\": {\"A\": \"...\", \"B\": \"...\", \"C\": \"...\", \"D\": \"...\"},\n"
    "      \"correct\": \"B\"\n"
    "    },\n"
    "    ...\n"
    "  ],\n"
    "  \"user_answers\": {\n"
    "    \"1\": \"A\",\n"
    "    \"2\": \"D\",\n"
    "    ...\n"
    "  }\n"
    "}\n"
    "\n"
    "Твои задачи:\n"
    "1) Для каждого вопроса определить, верно ли ответил пользователь.\n"
    "2) Если ответ неверный — кратко объяснить, почему и как правильно.\n"
    "3) Посчитать итоговый результат: количество правильных ответов и процент.\n"
    "4) В конце дать рекомендации: какие темы стоит повторить, на что обратить внимание.\n"
    "\n"
    "Формат ответа:\n"
    "- Сначала общий итог: \"Правильно X из Y (Z%)\".\n"
    "- Затем по каждому вопросу: номер, правильно/неправильно, короткий комментарий.\n"
    "- В конце 3–5 предложений с рекомендациями.\n"
    "\n"
    "Пиши на понятном, дружелюбном языке. Не перечисляй исходный JSON целиком, используй его только для анализа."
)


def parse_answers(text: str, question_count: int) -> Dict[int, str]:
    """
    Простой парсер ответов.
    Понимает ТОЛЬКО формат вида:
    '1a 2a 3d 4b 5c' (номер вопроса + буква ответа A–D, между ними может быть пробел).

    Примеры валидных строк:
    - '1a 2b 3c'
    - '1 a 2 c 3 d'
    - '1a, 2a, 3d, 4b, 5c'
    """
    text_clean = text.replace(",", " ").replace(";", " ").strip().lower()

    # Ищем все вхождения "число + (пробелы) + буква a-d"
    matches = re.findall(r"(\d+)\s*([a-d])", text_clean)

    if not matches:
        return {}

    result: Dict[int, str] = {}
    for qid_str, ans in matches:
        qid = int(qid_str)
        if 1 <= qid <= question_count:
            result[qid] = ans.upper()  # приводим к верхнему регистру: a -> A

    return result



@traceable(name="analyser_check_test")
def run_analyser(correct_answers: Dict[int, str], user_answers: str):
    """
    correct_answers — словарь {номер_вопроса: 'A'|'B'|'C'|'D'}
    user_answers — строка вида '1a 2b 3c 4d 5a'

    Возвращает:
      - report_text: строка с отчётом
      - score: число правильных
      - total: всего вопросов
    """
    if not correct_answers:
        return "Ошибка: нет теста для проверки.", 0, 0

    total = len(correct_answers)

    parsed = parse_answers(user_answers, total)

    if not parsed:
        return (
            "Не удалось распознать ответы.\n"
            "Используй формат: '1a 2b 3c 4d 5a'."
        ), 0, total

    score = 0
    lines = []

    # проходим по всем вопросам по номерам
    for qid in range(1, total + 1):
        correct = correct_answers.get(qid, "?").upper()
        user = parsed.get(qid, "—")

        if user == correct:
            score += 1
            lines.append(f"{qid}. ✔ Ваш ответ: {user}")
        else:
            lines.append(f"{qid}. ✘ Ваш ответ: {user} | Правильный: {correct}")

    report_text = f"Результат: {score}/{total}\n\n" + "\n".join(lines)
    return report_text, score, total
