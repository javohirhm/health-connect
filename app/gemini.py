"""Thin wrapper around the Gemini REST API for daily summaries, total
insights, and multi-turn chat."""
from __future__ import annotations

import json
import logging
from typing import Optional

import requests

from .config import config

logger = logging.getLogger("health-api.gemini")

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
TIMEOUT_SECONDS = 30


def is_configured() -> bool:
    """True if a Gemini API key is set in the environment."""
    return bool(config.GEMINI_API_KEY)


# ── Internal call helper ──────────────────────────────────────────────

def _call_gemini(
    contents: list,
    system_instruction: Optional[str] = None,
    max_tokens: int = 400,
) -> Optional[str]:
    """Single round-trip to Gemini. Returns text or None on any failure."""
    url = f"{GEMINI_BASE_URL}/{config.GEMINI_MODEL}:generateContent"

    body: dict = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": max_tokens,
            # Disable internal "thinking" — would otherwise eat the token
            # budget before producing visible text on Gemini 2.5+.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    if system_instruction:
        body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    try:
        response = requests.post(
            url,
            params={"key": config.GEMINI_API_KEY},
            json=body,
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        logger.error("Gemini request failed: %s", e)
        return None

    if response.status_code != 200:
        logger.error("Gemini returned %s: %s", response.status_code, response.text[:300])
        return None

    try:
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, ValueError) as e:
        logger.error("Could not parse Gemini response: %s", e)
        return None


# ── Public generators ─────────────────────────────────────────────────

_DAILY_PROMPT = """You are a fitness coach analyzing one day of biometric data
for an athlete. Read the JSON below and write a friendly 2–3 sentence summary
that highlights what stands out today (positive trends, anomalies, recovery
signals from HRV, activity balance). Be specific — use the actual numbers.
Do not include disclaimers, headings, or markdown. Plain text only.

Today's data:
{summary_json}
"""


def generate_daily_insight(summary: dict) -> Optional[str]:
    """2-3 sentence summary of today's data."""
    if not is_configured():
        return None
    prompt = _DAILY_PROMPT.format(summary_json=json.dumps(summary, default=str))
    return _call_gemini(
        contents=[{"parts": [{"text": prompt}]}],
        max_tokens=400,
    )


_TOTAL_PROMPT = """You are a fitness coach reviewing the last {days} days of
biometric data for an athlete. Identify trends and notable patterns across
heart rate, HRV, activity, sleep, and ECG. Be specific — reference actual
numbers and the time window. Write 3-4 sentences, plain text only, no
markdown or headings.

Aggregated data:
{history_json}
"""


def generate_total_insight(history: dict) -> Optional[str]:
    """3-4 sentence holistic summary of the last N days."""
    if not is_configured():
        return None
    prompt = _TOTAL_PROMPT.format(
        days=history.get("days_covered", 30),
        history_json=json.dumps(history, default=str, indent=2),
    )
    return _call_gemini(
        contents=[{"parts": [{"text": prompt}]}],
        max_tokens=500,
    )


def generate_chat_response(today: dict, history: dict, messages: list) -> Optional[str]:
    """Multi-turn chat. `messages` is a list of {role, content} dicts in user
    order. Today's + history data is injected as a system instruction so the
    model can answer trend questions without us dumping the data into every
    turn."""
    if not is_configured():
        return None

    system = (
        "You are a friendly health coach helping an athlete understand their data "
        "from a Galaxy Watch and HealthConnect. Answer questions based on the "
        "actual numbers below. Be specific, helpful, and concise (2–4 sentences "
        "usually). If the user asks about something not present in the data, "
        "say so honestly. Plain text, no markdown.\n\n"
        f"TODAY:\n{json.dumps(today, default=str, indent=2)}\n\n"
        f"LAST {history.get('days_covered', 30)} DAYS:\n"
        f"{json.dumps(history, default=str, indent=2)}"
    )

    # Convert {role: 'user'|'assistant', content} → Gemini's {role: 'user'|'model', parts}
    contents = []
    for m in messages:
        role = "user" if m.get("role") == "user" else "model"
        text = m.get("content", "")
        if not text:
            continue
        contents.append({"role": role, "parts": [{"text": text}]})

    if not contents:
        return None

    return _call_gemini(
        contents=contents,
        system_instruction=system,
        max_tokens=600,
    )
