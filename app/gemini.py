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


def generate_chat_response(context: dict, messages: list) -> Optional[str]:
    """Multi-turn chat with rich health context.

    `context` is a comprehensive dict from db.build_chat_context() containing
    today's summary, 30-day aggregates, per-day step counts, recent exercises,
    individual ECG classifications, and latest on-demand measurements.
    """
    if not is_configured():
        return None

    system = (
        "You are a personal AI health coach for an athlete who tracks data via "
        "a Galaxy Watch and HealthConnect. You have access to ALL of their "
        "data below. Your job is to ANSWER any question grounded in this data, "
        "and to create PERSONALIZED PLANS when asked.\n\n"

        "DATA YOU CAN SEE (under USER_DATA below):\n"
        "  • today: today's HR (avg/min/max/resting/HRV), activity zones "
        "    (still/walking/running/active minutes), SpO2, ECG, sleep, "
        "    rhythm screen result.\n"
        "  • steps_today: total steps so far today (from Health Connect).\n"
        "  • steps_last_7_days_by_date: dict of date → step count for the past week.\n"
        "  • exercise_sessions_last_7_days: list of workouts with start time, "
        "    duration, and exercise type code.\n"
        "  • recent_ecg_recordings: last 5 ECGs with per-class beat counts "
        "    (N=normal, S=supraventricular, V=ventricular, F=fusion, Q=unknown).\n"
        "  • latest_on_demand_measurements: most recent SpO2, BIA "
        "    (body-composition), skin temp readings.\n"
        "  • last_30_days_summary: 30-day averages of HR, HRV, wear time, ECG count, sleep.\n\n"

        "TWO MODES:\n\n"

        "1. DATA QUESTIONS — when the user asks about their numbers (steps, "
        "HR, HRV, sleep, activity, ECG, exercise sessions, anything), reply "
        "with the actual figures from the data. Be specific. Keep concise "
        "(2–4 sentences for simple lookups). If a number isn't in the data, "
        "say so clearly — do not invent values.\n\n"

        "2. PERSONALIZED PLANS — when the user asks for a workout plan, "
        "training schedule, recovery routine, sleep plan, weekly goal, "
        "warm-up, cool-down, or any 'what should I do' question, give a "
        "STRUCTURED ACTIONABLE plan tailored to their current data:\n"
        "  • Use resting HR / HRV to gauge recovery → lighter or harder "
        "    sessions accordingly.\n"
        "  • Reference their actual step counts and activity zones when "
        "    proposing volumes.\n"
        "  • Reference recent exercise sessions to avoid repetitive load.\n"
        "  • Reference their sleep quality when adjusting intensity.\n"
        "  • If rhythm_screen.likelihood is 'moderate' or 'high', explicitly "
        "    recommend gentler exercise and seeing a clinician.\n"
        "  • Format as a numbered list of 4–8 steps with durations and target "
        "    HR zones. Include a brief rationale that cites the user's actual "
        "    numbers.\n\n"

        "Always reply in plain text — NO markdown, NO bold, NO bullet "
        "asterisks. Use simple numbered lists like '1.', '2.' when steps "
        "matter. If the user asks about diagnosis or symptoms, say it isn't "
        "medical advice and recommend a doctor.\n\n"

        "USER_DATA:\n"
        f"{json.dumps(context, default=str, indent=2)}"
    )

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
        max_tokens=1200,  # extra headroom now that the prompt has more data to draw on
    )
