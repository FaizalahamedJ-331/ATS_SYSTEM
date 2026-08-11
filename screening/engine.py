"""
Hybrid screening engine.

1. Rule-based pass — always runs, offline, deterministic:
   - Skill matching against the job's required / nice-to-have skills
   - Keyword coverage extracted from the job description
   - Experience fit against the required seniority level
   - Education signals
   Produces a 0–100 ATS score, component scores, verdict, strengths, concerns.

2. Optional LLM pass — when LLM_API_KEY is configured, a deep analysis is
   requested from the configured chat-completions endpoint and the result is
   merged into the stored ScreeningResult (stage becomes "ai_enhanced").
"""
import re

from candidates.models import Application
from core import llm
from core.skills_data import SKILLS_TAXONOMY
from screening.models import ScreeningResult

STOPWORDS = set(
    """
    a an the and or but if then else for while of in on at to from by with
    about into over after before under between out up down off again further
    once here there all any both each few more most other some such no nor
    not only own same so than too very can will just should now
    our your their its his her our theirs yours its is are was were be been
    being have has had having do does did doing we they he she it you i
    this that these those as per via using used use with within across among
    working work experience ability strong excellent good great proven track
    record candidate responsibilities include includes including plus year
    years must should shall able knowledge understanding familiarity hands
    """.split()
)

WEIGHTS = {"skill": 0.45, "keyword": 0.20, "experience": 0.20, "education": 0.15}

RECOMMENDATIONS = {
    ScreeningResult.Verdict.STRONG: "Advance to interview",
    ScreeningResult.Verdict.GOOD: "Recommend phone screen",
    ScreeningResult.Verdict.POSSIBLE: "Manual review advised",
    ScreeningResult.Verdict.WEAK: "Low priority",
}


def _tokens(text):
    return re.findall(r"[a-z][a-z0-9+#.\-]{2,}", (text or "").lower())


def _generate_insight(job, candidate, matched_skills, missing_skills, years, required_years,
                      keyword_coverage, education_score, ats_score, verdict):
    """Compose a natural-language, rule-based assessment — no API key required."""
    name = candidate.first_name or candidate.full_name
    required_total = len(job.required_skills or [])
    skill_coverage = round(len(matched_skills) / max(1, required_total) * 100)

    if skill_coverage >= 80:
        skill_clause = f"a strong skills fit — {len(matched_skills)} of {required_total} required skills matched ({skill_coverage}% coverage)"
    elif skill_coverage >= 50:
        skill_clause = f"a reasonable skills base ({skill_coverage}% of required skills matched)"
    elif required_total:
        skill_clause = f"a partial skills profile — only {len(matched_skills)} of {required_total} required skills found"
    else:
        skill_clause = "no explicit required skills defined for the role"

    if years >= required_years:
        exp_clause = f"meets the {required_years}+ years requirement with {years:g} years"
    elif years > 0:
        exp_clause = f"falls short on experience at {years:g} years vs. the {required_years}+ required"
    else:
        exp_clause = "no verified professional experience found on the resume"

    if missing_skills:
        gap_clause = f"Main gaps to probe: {', '.join(missing_skills[:3])}."
    else:
        gap_clause = "No critical skill gaps identified."

    # Vary the phrasing so every candidate reads differently (deterministic pick)
    openers = [
        f"{name} presents {skill_clause}. {exp_clause}.",
        f"Looking at {name}'s resume: {skill_clause}. On experience, {exp_clause}.",
        f"{name}'s profile comes across as {skill_clause}. In terms of experience, {exp_clause}.",
    ]
    opening = openers[int(ats_score) % len(openers)]
    opening += f" Keyword coverage against the job description is {round(keyword_coverage * 100)}%."
    verdict_map = {
        ScreeningResult.Verdict.STRONG: "A strong overall match — low screening risk.",
        ScreeningResult.Verdict.GOOD: "A solid candidate who clears the screening bar.",
        ScreeningResult.Verdict.POSSIBLE: "Borderline fit — worth a human second look.",
        ScreeningResult.Verdict.WEAK: "Below the screening threshold for this role.",
    }
    return f"{opening} {gap_clause} {verdict_map[verdict]}"


def extract_job_keywords(job):
    """Extract discriminating keywords from the job description + requirements."""
    source = f"{job.title} {job.description} {job.responsibilities} {job.requirements} "
    source += " ".join(job.required_skills or [])
    tokens = _tokens(source)
    counts = {}
    for token in tokens:
        if token in STOPWORDS or len(token) < 4:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [t for t, _ in ranked[:25]]


def _contains_skill(text, alias):
    normalized = re.sub(r"\s+", " ", text.lower())
    if " " in alias:
        return alias in normalized
    return bool(re.search(rf"\b{re.escape(alias)}[a-z0-9\-+]*\b", normalized))


def match_skills(resume_text, skill_list):
    """Return (matched, missing) for a skill list against resume text."""
    matched, missing = [], []
    for skill in skill_list or []:
        aliases = SKILLS_TAXONOMY.get(skill.lower(), [skill.lower()])
        if any(_contains_skill(resume_text, a) for a in aliases):
            matched.append(skill)
        else:
            missing.append(skill)
    return matched, missing


def rule_based_screening(job, candidate, resume_text):
    """Compute the rule-based screening result dict (no DB writes)."""
    resume_text = resume_text or ""

    matched_skills, missing_skills = match_skills(resume_text, job.required_skills)
    matched_nice, _ = match_skills(resume_text, job.nice_to_have_skills)

    keywords = extract_job_keywords(job)
    resume_tokens = set(_tokens(resume_text))
    matched_keywords = [k for k in keywords if k in resume_tokens]
    missing_keywords = [k for k in keywords if k not in resume_tokens]

    # --- Component scores ---
    required_total = len(job.required_skills or [])
    if required_total:
        skill_score = round(len(matched_skills) / required_total * 100, 1)
    elif matched_keywords:
        skill_score = round(len(matched_keywords) / len(keywords) * 100, 1)
    else:
        skill_score = 0.0

    keyword_score = round(len(matched_keywords) / max(1, len(keywords)) * 100, 1)

    required_years = job.required_years
    years = candidate.years_experience or 0
    if years >= required_years:
        experience_score = 100.0
        if years > required_years * 2.5:
            experience_score = 85.0  # possible over-qualification
    elif years > 0:
        experience_score = round(years / required_years * 100, 1)
    else:
        experience_score = 0.0

    edu = candidate.education or ""
    edu_signal = bool(edu.strip())
    if edu_signal:
        education_score = 100.0
    else:
        education_score = 35.0
        if any(k in (job.requirements or "").lower() for k in ("bachelor", "degree", "master", "phd")):
            education_score = 20.0

    ats_score = round(
        WEIGHTS["skill"] * skill_score
        + WEIGHTS["keyword"] * keyword_score
        + WEIGHTS["experience"] * experience_score
        + WEIGHTS["education"] * education_score,
        1,
    )

    if ats_score >= 85:
        verdict = ScreeningResult.Verdict.STRONG
    elif ats_score >= 70:
        verdict = ScreeningResult.Verdict.GOOD
    elif ats_score >= 50:
        verdict = ScreeningResult.Verdict.POSSIBLE
    else:
        verdict = ScreeningResult.Verdict.WEAK

    strengths = []
    concerns = []

    if matched_skills:
        strengths.append(f"Matches {len(matched_skills)} required skill(s): {', '.join(matched_skills[:4])}")
    if years >= required_years:
        strengths.append(f"{years:g} years of experience meets the {required_years}+ year requirement")
    if matched_nice:
        strengths.append(f"Bonus: also has {', '.join(matched_nice[:3])}")
    if not strengths and matched_keywords:
        strengths.append(f"Good keyword coverage ({len(matched_keywords)} of {len(keywords)} terms)")

    if missing_skills:
        concerns.append(f"Missing required skill(s): {', '.join(missing_skills[:4])}")
    if years < required_years:
        concerns.append(f"Only {years:g} years of experience vs. {required_years}+ required")
    if not edu_signal:
        concerns.append("No education details found on resume")
    if not concerns:
        concerns.append("No major red flags detected in rule-based pass")

    insight = _generate_insight(
        job=job,
        candidate=candidate,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        years=years,
        required_years=required_years,
        keyword_coverage=len(matched_keywords) / max(1, len(keywords)) if keywords else 0.0,
        education_score=education_score,
        ats_score=ats_score,
        verdict=verdict,
    )

    return {
        "insight": insight,
        "recommendation": RECOMMENDATIONS[verdict],
        "ats_score": ats_score,
        "skill_score": skill_score,
        "keyword_score": keyword_score,
        "experience_score": experience_score,
        "education_score": education_score,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "matched_nice_to_have": matched_nice,
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "strengths": strengths,
        "concerns": concerns,
        "verdict": verdict,
    }


def _store(application, result):
    obj, _ = ScreeningResult.objects.update_or_create(
        application=application,
        defaults={
            "ats_score": result["ats_score"],
            "skill_score": result["skill_score"],
            "keyword_score": result["keyword_score"],
            "experience_score": result["experience_score"],
            "education_score": result["education_score"],
            "matched_skills": result["matched_skills"],
            "missing_skills": result["missing_skills"],
            "matched_nice_to_have": result["matched_nice_to_have"],
            "matched_keywords": result["matched_keywords"],
            "missing_keywords": result["missing_keywords"],
            "strengths": result["strengths"],
            "concerns": result["concerns"],
            "verdict": result["verdict"],
            "insight": result.get("insight", ""),
            "recommendation": result.get("recommendation", ""),
        },
    )
    return obj


def screen_application(application, use_llm=True):
    """
    Screen a single application. Writes/updates the ScreeningResult row.

    use_llm: run the optional LLM deep-analysis pass when configured.
    Returns the ScreeningResult instance.
    """
    job = application.job
    candidate = application.candidate
    # Prefer the application's resume; fall back to the candidate's latest one.
    resume = application.resume or candidate.resumes.first()
    resume_text = resume.raw_text if resume else ""

    result = rule_based_screening(job, candidate, resume_text)
    obj = _store(application, result)

    if use_llm:
        enhance_with_llm(obj, application, resume_text)

    return obj


def screen_job(job, use_llm=True):
    """Screen all applications for a job. Returns the list of results."""
    results = []
    apps = job.applications.select_related("candidate", "resume", "screening").prefetch_related(
        "candidate__resumes"
    )
    for app in apps.all():
        results.append(screen_application(app, use_llm=use_llm))
    return results


def enhance_with_llm(result, application, resume_text=None):
    """Run (or refresh) the LLM deep-analysis pass on an existing result."""
    if not llm.is_configured():
        return False
    if resume_text is None:
        resume_text = application.resume.raw_text if application.resume else ""
    analysis = llm.analyze_candidate(application.job, application.candidate, resume_text, {
        "ats_score": result.ats_score,
        "verdict": result.verdict,
    })
    if not analysis:
        return False

    new_score = max(0.0, min(100.0, result.ats_score + analysis["score_adjustment"]))
    result.ats_score = round(new_score, 1)
    result.ai_analysis = analysis["summary"]
    result.ai_verdict = analysis["verdict"]
    result.ai_score_adjustment = analysis["score_adjustment"]
    result.strengths = analysis["strengths"] or result.strengths
    result.concerns = analysis["concerns"] or result.concerns
    result.verdict = analysis["verdict"] or result.verdict
    result.stage = ScreeningResult.Stage.AI_ENHANCED
    result.save(update_fields=[
        "ats_score", "ai_analysis", "ai_verdict", "ai_score_adjustment",
        "strengths", "concerns", "verdict", "stage", "updated_at",
    ])
    return True
