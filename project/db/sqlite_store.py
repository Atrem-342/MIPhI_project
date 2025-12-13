# db/sqlite_store.py

import json
import sqlite3
from typing import List, Dict, Optional, Any
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent / "lumira.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """
    Создаёт таблицы, если их ещё нет.
    """
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            topic TEXT,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            percent INTEGER NOT NULL,
            user_answers TEXT
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS dialogs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            state_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS dialog_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dialog_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(dialog_id) REFERENCES dialogs(id) ON DELETE CASCADE
        );
        """)
        conn.commit()


def save_test_result(topic: Optional[str], score: int, total: int, percent: int, user_answers: str) -> None:
    """
    Сохраняет один результат теста.
    """
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO test_results (topic, score, total, percent, user_answers)
        VALUES (?, ?, ?, ?, ?);
        """, (topic, score, total, percent, user_answers))
        conn.commit()


def load_test_results(limit: int = 100, topic: Optional[str] = None) -> List[Dict]:
    """
    Загружает последние результаты тестов.
    Если topic передан, фильтрует по подстроке в названии темы (LIKE %topic%).
    """
    with get_conn() as conn:
        if topic:
            pattern = f"%{topic}%"
            rows = conn.execute("""
            SELECT id, created_at, topic, score, total, percent, user_answers
            FROM test_results
            WHERE topic LIKE ?
            ORDER BY id DESC
            LIMIT ?;
            """, (pattern, limit)).fetchall()
        else:
            rows = conn.execute("""
            SELECT id, created_at, topic, score, total, percent, user_answers
            FROM test_results
            ORDER BY id DESC
            LIMIT ?;
            """, (limit,)).fetchall()

    return [dict(r) for r in rows]


def calc_average(results: List[Dict]) -> Dict:
    """
    Считает средний результат по списку результатов.
    """
    total_correct = sum(r.get("score", 0) for r in results)
    total_questions = sum(r.get("total", 0) for r in results)
    avg_percent = int(total_correct / total_questions * 100) if total_questions else 0
    return {
        "correct": total_correct,
        "total": total_questions,
        "percent": avg_percent
    }


# --------- DIALOG STORAGE ----------

def create_dialog(title: Optional[str], state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Создаёт новый диалог и возвращает его данные.
    """
    title = title or "Новый диалог"
    state_json = json.dumps(state, ensure_ascii=False)
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO dialogs (title, state_json)
            VALUES (?, ?);
            """,
            (title, state_json),
        )
        dialog_id = cur.lastrowid
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM dialogs WHERE id = ?;",
            (dialog_id,),
        ).fetchone()

    return dict(row)


def list_dialogs() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM dialogs
            ORDER BY updated_at DESC, id DESC;
            """
        ).fetchall()
    return [dict(r) for r in rows]


def get_dialog(dialog_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, title, created_at, updated_at, state_json
            FROM dialogs
            WHERE id = ?;
            """,
            (dialog_id,),
        ).fetchone()

    if row is None:
        return None

    data = dict(row)
    try:
        data["state"] = json.loads(data.pop("state_json"))
    except Exception:
        data["state"] = None
    return data


def update_dialog_state(dialog_id: int, state: Dict[str, Any]) -> None:
    state_json = json.dumps(state, ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE dialogs
            SET state_json = ?, updated_at = datetime('now')
            WHERE id = ?;
            """,
            (state_json, dialog_id),
        )
        conn.commit()


def rename_dialog(dialog_id: int, title: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE dialogs
            SET title = ?, updated_at = datetime('now')
            WHERE id = ?;
            """,
            (title, dialog_id),
        )
        conn.commit()


def delete_dialog(dialog_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM dialogs WHERE id = ?;", (dialog_id,))
        conn.commit()


def add_dialog_message(dialog_id: int, role: str, content: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO dialog_messages (dialog_id, role, content)
            VALUES (?, ?, ?);
            """,
            (dialog_id, role, content),
        )
        conn.execute(
            "UPDATE dialogs SET updated_at = datetime('now') WHERE id = ?;",
            (dialog_id,),
        )
        conn.commit()


def get_dialog_messages(dialog_id: int, limit: int = 200) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content, created_at
            FROM dialog_messages
            WHERE dialog_id = ?
            ORDER BY id ASC
            LIMIT ?;
            """,
            (dialog_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]
