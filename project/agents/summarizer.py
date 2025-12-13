# agents/summarizer.py

from gigachat_api import chat_with_gigachat_messages

SUMMARIZER_PROMPT = (
    "You are a Summarizer agent.\n"
    "The user will send a large text.\n"
    "Your job:\n"
    "1) Write a short summary (5–10 lines).\n"
    "2) List the main topics as bullet points (5–12 bullets).\n"
    "3) If the text is too long, still summarize the visible part and say what may be missing.\n"
    "\n"
    "Output format:\n"
    "Summary:\n"
    "<your summary>\n"
    "\n"
    "Main topics:\n"
    "- topic 1\n"
    "- topic 2\n"
    "- ...\n"
)

def run_summarizer(access_token: str, user_text: str) -> str:
    """
    Summarizer agent: takes large text and returns summary + main topics.
    """
    messages = [
        {"role": "system", "content": SUMMARIZER_PROMPT},
        {"role": "user", "content": user_text},
    ]

    return chat_with_gigachat_messages(access_token, messages)
