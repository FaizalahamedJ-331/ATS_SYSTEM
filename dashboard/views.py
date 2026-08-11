import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.shortcuts import render
from django.utils import timezone

from candidates.models import Application, Candidate
from interviews.models import Interview
from jobs.models import Job
from screening.models import ScreeningResult


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

    # --- Chart: pipeline funnel ---
    status_counts = {
        s.value: Application.objects.filter(status=s.value).count()
        for s in Application.Status
    }
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

    # --- Chart: applications over last 14 days ---
    days = []
    day_counts = []
    for offset in range(13, -1, -1):
        day = (today - timedelta(days=offset)).date()
        days.append(day.strftime("%b %d"))
        day_counts.append(
            Application.objects.filter(created_at__date=day).count()
        )
    applications_over_time = {"labels": days, "data": day_counts}

    # --- Chart: candidate sources ---
    source_rows = Candidate.objects.values("source").annotate(count=Count("id"))
    source_map = dict(Candidate.Source.choices)
    sources = {
        "labels": [source_map.get(r["source"], r["source"]) for r in source_rows],
        "data": [r["count"] for r in source_rows],
    }

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

    context = {
        "active_page": "dashboard",
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
    }
    return render(request, "dashboard/dashboard.html", context)
