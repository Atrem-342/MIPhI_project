import re
from typing import Tuple, Dict
from langsmith import traceable


@traceable(name="format_exam_parse")
def format_exam(exam_text: str) -> Tuple[str, Dict[int, str], str]:
    """
    Принимает текст от экзаменатора в формате:

    THEME: Planets of the Solar System
    ANSWERS: 1A 2B 3C 4D 5A

    QUESTIONS:
    1. ...
    A) ...
    ...

    Возвращает:
      1) questions_text — только блок вопросов (для показа пользователю)
      2) answers_dict   — словарь {номер: буква}
      3) theme          — строка с темой теста
    """

    # --- 1. ТЕМА ---
    theme_match = re.search(r"THEME:\s*(.+)", exam_text)
    if theme_match:
        theme = theme_match.group(1).strip()
    else:
        theme = "(не удалось определить тему)"

    # --- 2. ОТВЕТЫ ---
    answers_match = re.search(r"ANSWERS:\s*(.+)", exam_text)
    if not answers_match:
        return "Ошибка: экзаменатор не выдал строку ANSWERS.", {}, theme

    answers_str = answers_match.group(1).strip()

    answers_dict: Dict[int, str] = {}
    for pair in answers_str.split():
        # ожидаем формат типа '1A'
        if len(pair) < 2:
            continue
        try:
            num = int(pair[:-1])
            letter = pair[-1].upper()
            answers_dict[num] = letter
        except ValueError:
            continue

    # --- 3. ВОПРОСЫ ---
    questions_match = re.search(r"QUESTIONS:\s*(.+)", exam_text, re.DOTALL)
    if not questions_match:
        return "Ошибка: нет блока QUESTIONS.", {}, theme

    raw_questions_text = questions_match.group(1).strip()

    clean_lines = []
    for line in raw_questions_text.splitlines():
        stripped = line.strip()
        if stripped in {"A)", "B)", "C)", "D)"}:
            continue
        clean_lines.append(line)
    questions_text = "\n".join(clean_lines).strip()

    return questions_text, answers_dict, theme
