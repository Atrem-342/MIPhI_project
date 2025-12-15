import os
from typing import Optional

import requests
from langsmith import traceable

OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY")
OCR_SPACE_API_URL = os.getenv("OCR_SPACE_API_URL", "https://api.ocr.space/parse/image")


class OCRSpaceError(Exception):
    """Raised when OCR.Space returns an error."""


@traceable(name="ocr_space_parse")
def parse_image_with_ocr_space(
    filename: str,
    content: bytes,
    language: str = "eng",
    engine: int = 2,
) -> str:
    if not OCR_SPACE_API_KEY:
        raise OCRSpaceError("OCR_SPACE_API_KEY is not configured.")

    files = {
        "file": (filename or "upload", content),
    }
    data = {
        "language": language,
        "isOverlayRequired": False,
        "OCREngine": engine,
    }
    headers = {"apikey": OCR_SPACE_API_KEY}

    try:
        response = requests.post(
            OCR_SPACE_API_URL,
            files=files,
            data=data,
            headers=headers,
            timeout=60,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OCRSpaceError(f"OCR request failed: {exc}") from exc

    payload = response.json()
    if payload.get("IsErroredOnProcessing"):
        errors = payload.get("ErrorMessage") or payload.get("ErrorDetails") or ["Unknown error"]
        if isinstance(errors, list):
            error_text = "; ".join(map(str, errors))
        else:
            error_text = str(errors)
        raise OCRSpaceError(error_text)

    parsed_results = payload.get("ParsedResults")
    if not parsed_results:
        return ""

    text = parsed_results[0].get("ParsedText", "")
    return text or ""
