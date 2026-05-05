"""Thin wrapper around the Gemini REST API for daily-summary insights."""
from __future__ import annotations

import json
import logging
from typing import Optional

import requests

from .config import config

logger = logging.getLogger("health-api.gemini")

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
TIMEOUT_SECONDS = 30

_PROMPT_TEMPLATE = """You are a fitness coach analyzing a single day of biometric data
for an athlete. Read the JSON below and write a friendly 2–3 sentence summary
that highlights what stands out today (positive trends, anomalies, recovery
signals from HRV, activity balance). Be specific — use the actual numbers.
Do not include disclaimers, headings, or markdown. Plain text only.

Today's data:
{summary_json}
"""


def is_configured() -> bool:
    """True if a Gemini API key is set in the environment."""
    return bool(config.GEMINI_API_KEY)


def generate_daily_insight(summary: dict) -> Optional[str]:
    """Send `summary` to Gemini and return the generated text. None on failure."""
    if not is_configured():
        return None

    prompt = _PROMPT_TEMPLATE.format(summary_json=json.dumps(summary, default=str))
    url = f"{GEMINI_BASE_URL}/{config.GEMINI_MODEL}:generateContent"

    try:
        response = requests.post(
            url,
            params={"key": config.GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 400,
                    # Gemini 2.5+ "thinking" eats the token budget before
                    # producing visible output. We don't need reasoning for a
                    # 2–3 sentence summary, so disable it.
                    "thinkingConfig": {"thinkingBudget": 0},
                },
            },
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        logger.error("Gemini request failed: %s", e)
        return None

    if response.status_code != 200:
        logger.error("Gemini returned %s: %s", response.status_code, response.text[:200])
        return None

    try:
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return text.strip()
    except (KeyError, IndexError, ValueError) as e:
        logger.error("Could not parse Gemini response: %s", e)
        return None
