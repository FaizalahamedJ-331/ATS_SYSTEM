import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.timesince import timesince
from django.views.decorators.http import require_GET

from candidates.models import Application, ApplicationEvent, Candidate
from interviews.models import Interview
from jobs.models import Job
from screening.models import ScreeningResult


def _greeting(hour):
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    if 17 <= hour < 22:
        return "Good evening"
    return "Working late"


@login_required
def dashboard(request):
    today = timezone.now()
    week_ago = today - timedelta(days=7)

    # --- Stat cards ---
    open_jobs = Job.objects.filter(status=Job.Status.OPEN).count()
    total_candidates = Candidate.objects.count()
    total_applications = Application.objects.count()
    avg_score = ScreeningResult.objects.aggregate(avg=Avg("ats_score"))["avg"] or 0
    interviews_this_week = Interview.objects.filter(
        status=Interview.Status.SCHEDULED, scheduled_at__gte=week_ago
    ).count()
    hires = Application.objects.filter(status=Application.Status.HIRED).count()

    # --- Chart: applications per job ---
    job_rows = (
        Job.objects.annotate(count=Count("applications"))
        .order_by("-count", "-created_at")[:8]
    )
    applications_per_job = {
        "labels": [j.title[:24] for j in job_rows],
        "data": [j.count for j in job_rows],
    }

    # --- Chart: pipeline funnel (single GROUP BY query) ---
    status_counts = {s.value: 0 for s in Application.Status}
    for row in Application.objects.values("status").annotate(n=Count("id")):
        if row["status"] in status_counts:
            status_counts[row["status"]] = row["n"]
    pipeline = {
        "labels": [Application.Status(s).label for s in status_counts],
        "data": [status_counts[s] for s in status_counts],
    }

    # --- Chart: ATS score distribution ---
    buckets = [0, 0, 0, 0, 0]
    for score in ScreeningResult.objects.values_list("ats_score", flat=True):
        idx = min(4, int(score // 20))
        buckets[idx] += 1
    score_distribution = {
        "labels": ["0–19", "20–39", "40–59", "60–79", "80–100"],
        "data": buckets,
    }

    # --- Chart: applications over last 14 days (single query + in-memory fill) ---
    start_day = (today - timedelta(days=13)).date()
    rows = (
        Application.objects.filter(created_at__date__gte=start_day)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(n=Count("id"))
    )
    day_map = {r["day"]: r["n"] for r in rows}
    days = []
    day_counts = []
    for offset in range(13, -1, -1):
        day = (today - timedelta(days=offset)).date()
        days.append(day.strftime("%b %d"))
        day_counts.append(day_map.get(day, 0))
    applications_over_time = {"labels": days, "data": day_counts}

    # --- Chart: candidate sources ---
    source_rows = Candidate.objects.values("source").annotate(count=Count("id"))
    source_map = dict(Candidate.Source.choices)
    sources = {
        "labels": [source_map.get(r["source"], r["source"]) for r in source_rows],
        "data": [r["count"] for r in source_rows],
    }

    # --- AI hiring insights (reuses data already queried above) ---
    ai_insights = _build_insights(
        today,
        total_candidates=total_candidates,
        source_rows=source_rows,
    )

    # --- Recent applications ---
    recent_applications = (
        Application.objects.select_related("candidate", "job", "screening")
        .prefetch_related("interviews")
        .order_by("-created_at")[:6]
    )

    # --- Top screened candidates (open jobs) ---
    top_results = (
        ScreeningResult.objects.filter(
            application__job__status=Job.Status.OPEN
        )
        .select_related("application", "application__candidate", "application__job")
        .order_by("-ats_score")[:5]
    )

    # --- Activity feed (human touch) ---
    recent_events = (
        ApplicationEvent.objects.select_related(
            "application", "application__candidate", "application__job", "user"
        )
        .order_by("-created_at")[:10]
    )

    name = request.user.get_full_name() or request.user.get_username()
    greeting = _greeting(today.hour)
    today_label = today.strftime("%A, %B %d")

    context = {
        "active_page": "dashboard",
        "greeting": greeting,
        "user_name": name.split()[0],
        "today_label": today_label,
        "recent_events": recent_events,
        "stats": {
            "open_jobs": open_jobs,
            "total_candidates": total_candidates,
            "total_applications": total_applications,
            "avg_score": round(avg_score, 1),
            "interviews_this_week": interviews_this_week,
            "hires": hires,
        },
        "applications_per_job": json.dumps(applications_per_job),
        "pipeline": json.dumps(pipeline),
        "score_distribution": json.dumps(score_distribution),
        "applications_over_time": json.dumps(applications_over_time),
        "sources": json.dumps(sources),
        "recent_applications": recent_applications,
        "top_results": top_results,
        "ai_insights": ai_insights,
    }
    return render(request, "dashboard/dashboard.html", context)


@login_required
@require_GET
def activity_feed(request):
    """JSON feed of the latest activity events for live polling."""
    events = (
        ApplicationEvent.objects.select_related(
            "application", "application__candidate", "application__job", "user"
        )
        .order_by("-created_at")[:10]
    )

    icons = {
        ApplicationEvent.Kind.NOTE: "💬",
        ApplicationEvent.Kind.STATUS: "↗",
        ApplicationEvent.Kind.SCREEN: "✦",
        ApplicationEvent.Kind.RESUME: "📄",
        ApplicationEvent.Kind.INTERVIEW: "🗓",
        ApplicationEvent.Kind.APPLY: "📥",
    }

    data = []
    for e in events:
        meta = (
            f"{e.application.candidate.full_name} · {e.application.job.title} · "
            f"{timesince(e.created_at)} ago"
        )
        if e.user:
            meta += f" · {e.user.get_username()}"
        data.append({
            "id": e.pk,
            "kind": e.kind,
            "icon": icons.get(e.kind, "📥"),
            "text": e.text,
            "meta": meta,
        })

    return JsonResponse({"events": data})


def _build_insights(today, total_candidates=0, source_rows=None):
    """Derive natural-language hiring insights from the live dataset."""
    if total_candidates == 0:
        return []
    insights = []

    # Strongest source of candidates (reuses the query the dashboard already ran)
    top_source = max(source_rows or [], key=lambda r: r["count"]) if source_rows else None
    if top_source and top_source["count"] > 0:
        label = dict(Candidate.Source.choices).get(top_source["source"], top_source["source"])
        insights.append({
            "tone": "violet",
            "title": "Top talent source",
            "text": f"{label} delivers the most candidates ({top_source['count']}) — double down your efforts there.",
        })

    # Hottest job
    hottest = (
        Job.objects.filter(status=Job.Status.OPEN)
        .annotate(count=Count("applications"))
        .order_by("-count")
        .first()
    )
    if hottest and hottest.count:
        insights.append({
            "tone": "indigo",
            "title": "Highest demand",
            "text": f"“{hottest.title}” has {hottest.count} applicant{'s' if hottest.count != 1 else ''} — consider moving strong matches to interview fast.",
        })

    # Screening verdict breakdown (single query)
    verdict_rows = ScreeningResult.objects.values("verdict").annotate(n=Count("id"))
    verdict_map = {r["verdict"]: r["n"] for r in verdict_rows}
    strong = verdict_map.get(ScreeningResult.Verdict.STRONG, 0)
    weak = verdict_map.get(ScreeningResult.Verdict.WEAK, 0)
    insights.append({
        "tone": "green",
        "title": "Screening quality",
        "text": f"{strong} candidates are strong matches, {weak} are weak. Strong matches should be interviewed this week.",
    })

    # Follow-up queue: strong-ish candidates still waiting in 'new'
    follow_up = (
        Application.objects.filter(status=Application.Status.NEW, screening__ats_score__gte=70)
        .select_related("candidate", "job")[:5]
    )
    if follow_up:
        names = ", ".join(a.candidate.first_name for a in follow_up)
        insights.append({
            "tone": "amber",
            "title": "Follow-up queue",
            "text": f"{follow_up.count()} highly-scored candidate(s) still in New — {names} — move them into screening.",
        })

    # Upcoming interviews
    upcoming_interviews = Interview.objects.filter(
        status=Interview.Status.SCHEDULED, scheduled_at__gte=today
    ).count()
    insights.append({
        "tone": "blue",
        "title": "Interview load",
        "text": f"{upcoming_interviews} interview(s) scheduled ahead. Keep a 24h buffer for feedback capture.",
    })

    return insights
