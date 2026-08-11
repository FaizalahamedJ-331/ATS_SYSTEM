from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from candidates.models import ApplicationEvent
from core import llm
from screening.engine import enhance_with_llm, screen_application
from screening.models import ScreeningResult


def _interview_questions(result, job, candidate):
    """Rule-based 'what to ask' suggestions — makes screening actionable."""
    questions = []
    if result.missing_skills:
        questions.append(
            f"Probe experience with {', '.join(result.missing_skills[:3])} — a key requirement for this role."
        )
    if result.matched_skills:
        questions.append(
            f"Validate depth in their strongest area ({', '.join(result.matched_skills[:2])}) with a practical scenario."
        )
    years = candidate.years_experience or 0
    if years < job.required_years:
        questions.append(
            f"They list {years:g} years vs the {job.required_years}+ required — ask how they've taken ownership early in their career."
        )
    if not (candidate.education or "").strip():
        questions.append("Education isn't detailed — clarify their background and any certifications.")
    if result.keyword_score < 50:
        questions.append(
            "Resume wording has limited overlap with the job description — check for transferable skills that keywords missed."
        )
    if not questions:
        questions.append("Strong all-round profile — use the interview to assess culture fit and motivation.")
    return questions[:4]


@login_required
def screening_detail(request, pk):
    result = get_object_or_404(
        ScreeningResult.objects.select_related(
            "application", "application__candidate", "application__job", "application__resume"
        ),
        pk=pk,
    )
    context = {
        "active_page": "candidates",
        "result": result,
        "app": result.application,
        "resume_text": result.application.resume.raw_text if result.application.resume else "",
        "radar_data": {
            "labels": ["Skills", "Keywords", "Experience", "Education"],
            "data": [
                round(result.skill_score, 1),
                round(result.keyword_score, 1),
                round(result.experience_score, 1),
                round(result.education_score, 1),
            ],
        },
        "interview_questions": _interview_questions(
            result, result.application.job, result.application.candidate
        ),
    }
    return render(request, "screening/detail.html", context)


@login_required
def screening_rerun(request, pk):
    """Re-run rule-based screening (+ LLM if configured) for an application."""
    from candidates.models import Application
    app = get_object_or_404(Application, pk=pk)
    if request.method == "POST":
        result = screen_application(app, use_llm=True)
        stage = "AI-enhanced" if result.stage == ScreeningResult.Stage.AI_ENHANCED else "rule-based"
        app.log_event(
            ApplicationEvent.Kind.SCREEN,
            f"Screening refreshed — {result.ats_score:.0f}/100 ({result.get_verdict_display()})",
            request.user,
        )
        messages.success(request, f"Screening refreshed — score {result.ats_score:.0f}/100 ({stage}).")
        return redirect("screening_detail", pk=result.pk)
    # GET: just show the current report
    result = getattr(app, "screening", None) or screen_application(app, use_llm=False)
    return redirect("screening_detail", pk=result.pk)


@login_required
def screening_ai(request, pk):
    """Manually trigger the LLM deep-analysis pass on an application's screening."""
    result = get_object_or_404(ScreeningResult, pk=pk)
    if request.method == "POST":
        if not llm.is_configured():
            messages.warning(
                request,
                "LLM deep analysis is not configured. Set LLM_API_KEY in your .env "
                "file to enable AI-powered screening.",
            )
        else:
            if enhance_with_llm(result, result.application):
                messages.success(
                    request,
                    f"AI deep analysis complete — score adjusted by {result.ai_score_adjustment:+d} "
                    f"to {result.ats_score:.0f}/100.",
                )
            else:
                messages.error(request, "The AI analysis call failed. Please check your API key.")
    return redirect("screening_detail", pk=result.pk)
