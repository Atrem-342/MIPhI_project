# agents/summarizer.py

from gigachat_api import chat_with_gigachat_messages

SUMMARIZER_PROMPT = (
    "You are a Summarizer agent.\n"
    "The user will send a large text (article, OCR output, lecture, etc.).\n"
    "Your goal is to extract the main information in a concise but informative way.\n"
    "\n"
    "Instructions:\n"
    "1) Provide a short summary of the text (5–10 lines) highlighting the essential ideas.\n"
    "2) After the summary, list the main topics/insights as bullet points.\n"
    "3) If parts of the text are missing or unclear, mention it briefly in the summary.\n"
    "\n"
    "Output format:\n"
    "Summary:\n"
    "<your 5–10 line summary>\n"
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
