"""
Optional LLM-powered deep analysis for the hybrid screening engine.

Uses any OpenAI-compatible chat-completions endpoint (OpenAI, Azure, Groq,
Together, Ollama, etc.) configured via environment variables. If no API key
is configured, screening falls back to the rule-based engine alone.
"""
import json
import logging
import re

import requests

from django.conf import settings

logger = logging.getLogger(__name__)


def is_configured():
    return bool(settings.LLM_API_KEY)


def _strip_code_fences(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def chat_completion(system, user, temperature=0.2, max_tokens=1200, timeout=90):
    """Call the configured chat-completions endpoint. Returns raw text or None."""
    if not is_configured():
        return None
    payload = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            f"{settings.LLM_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM call failed: %s", exc)
        return None


def analyze_candidate(job, candidate, resume_text, rule_result):
    """
    Ask the LLM for a deep screening analysis of one candidate vs a job.

    Returns a dict with: verdict, adjusted_score (delta applied to the
    rule-based score), strengths, concerns, summary. Returns None when the
    LLM is not configured or the call fails.
    """
    resume_excerpt = (resume_text or "")[:12000]

    system = (
        "You are a senior technical recruiter performing a rigorous, unbiased "
        "candidate screening. You compare a candidate's resume against a job "
        "description and return ONLY valid JSON with this exact schema:\n"
        "{\n"
        '  "verdict": "strong_match" | "good_match" | "possible_match" | "weak_match",\n'
        '  "score_adjustment": <integer between -15 and 15>,\n'
        '  "strengths": [<2-4 short strings>],\n'
        '  "concerns": [<1-3 short strings>],\n'
        '  "summary": "<2-3 sentence professional assessment>"\n'
        "}\n"
        "The score_adjustment is a small delta on top of the rule-based ATS score; "
        "it should be positive for clear over-qualification or exceptional fit and "
        "negative for red flags (gaps, mismatched seniority, visa issues, etc.)."
    )

    user = (
        f"JOB TITLE: {job.title}\n"
        f"DEPARTMENT: {job.department}\n"
        f"EXPERIENCE LEVEL: {job.get_experience_level_display()}\n"
        f"JOB DESCRIPTION:\n{job.description[:6000]}\n\n"
        f"REQUIRED SKILLS: {', '.join(job.required_skills or [])}\n"
        f"NICE-TO-HAVE: {', '.join(job.nice_to_have_skills or [])}\n\n"
        f"CANDIDATE NAME: {candidate.full_name}\n"
        f"CURRENT ROLE: {candidate.headline or 'N/A'} at {candidate.current_company or 'N/A'}\n"
        f"YEARS EXPERIENCE (rule-based estimate): {candidate.years_experience}\n"
        f"DECLARED SKILLS: {', '.join(candidate.skills or [])}\n"
        f"RULE-BASED ATS SCORE: {rule_result['ats_score']}/100\n"
        f"RULE-BASED VERDICT: {rule_result['verdict']}\n\n"
        f"RESUME TEXT:\n{resume_excerpt}\n"
    )

    raw = chat_completion(system, user)
    if not raw:
        return None
    try:
        payload = json.loads(_strip_code_fences(raw))
        verdict = payload.get("verdict", "possible_match")
        if verdict not in ("strong_match", "good_match", "possible_match", "weak_match"):
            verdict = "possible_match"
        adjustment = int(payload.get("score_adjustment", 0))
        adjustment = max(-15, min(15, adjustment))
        return {
            "verdict": verdict,
            "score_adjustment": adjustment,
            "strengths": [str(s) for s in payload.get("strengths", [])][:4],
            "concerns": [str(c) for c in payload.get("concerns", [])][:3],
            "summary": str(payload.get("summary", "")),
        }
    except (ValueError, TypeError, json.JSONDecodeError):
        logger.warning("LLM returned unparseable JSON: %s", raw[:200])
        return None
