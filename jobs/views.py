import csv
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from candidates.models import Application, ApplicationEvent
from core.csv_utils import safe_csv_cell
from jobs.forms import JobForm
from jobs.models import Job
from screening.engine import screen_job
from screening.models import ScreeningResult


@login_required
def job_list(request):
    jobs = Job.objects.annotate(app_count=Count("applications")).select_related().all()
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()

    if status in dict(Job.Status.choices):
        jobs = jobs.filter(status=status)
    if q:
        jobs = jobs.filter(
            Q(title__icontains=q) | Q(department__icontains=q) | Q(location__icontains=q)
        )

    # Attach average score per job efficiently
    avg_rows = {
        r["application__job_id"]: r["avg"]
        for r in ScreeningResult.objects.values("application__job_id").annotate(avg=Avg("ats_score"))
    }
    for job in jobs:
        job.avg_score = avg_rows.get(job.pk)

    context = {
        "active_page": "jobs",
        "jobs": jobs,
        "status": status,
        "q": q,
        "status_choices": Job.Status.choices,
    }
    return render(request, "jobs/list.html", context)


@login_required
def job_detail(request, pk):
    job = get_object_or_404(Job, pk=pk)
    applications = (
        job.applications.select_related("candidate", "resume", "screening")
        .prefetch_related("interviews")
        .order_by("candidate__first_name")
    )
    ranked = sorted(applications, key=lambda a: (a.score is None, -(a.score or 0)))

    # Verdict distribution for the screening summary
    verdict_counts = {v.value: 0 for v in ScreeningResult.Verdict}
    for app in applications:
        s = getattr(app, "screening", None)
        if s and s.verdict in verdict_counts:
            verdict_counts[s.verdict] += 1

    context = {
        "active_page": "jobs",
        "job": job,
        "ranked": ranked,
        "verdict_counts": verdict_counts,
    }
    return render(request, "jobs/detail.html", context)


@login_required
def job_create(request):
    return _job_form(request)


@login_required
def job_edit(request, pk):
    return _job_form(request, pk)


def _job_form(request, pk=None):
    job = get_object_or_404(Job, pk=pk) if pk else None
    if request.method == "POST":
        form = JobForm(request.POST, instance=job)
        if form.is_valid():
            form.save()
            messages.success(request, f"Job “{form.instance.title}” saved successfully.")
            return redirect("job_detail", pk=form.instance.pk)
    else:
        form = JobForm(instance=job)
    context = {
        "active_page": "jobs",
        "form": form,
        "job": job,
    }
    return render(request, "jobs/form.html", context)


@login_required
def job_toggle_status(request, pk):
    job = get_object_or_404(Job, pk=pk)
    if request.method == "POST":
        target = request.POST.get("status")
        if target in dict(Job.Status.choices):
            job.status = target
            job.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Job “{job.title}” is now {job.get_status_display().lower()}.")
        else:
            messages.error(request, "Invalid status.")
    return redirect("job_detail", pk=pk)


@login_required
def job_screen(request, pk):
    """Run the hybrid screening engine across all applications for a job."""
    job = get_object_or_404(Job, pk=pk)
    if request.method == "POST":
        count = job.applications.count()
        if count == 0:
            messages.warning(request, f"No applications to screen for “{job.title}” yet.")
        else:
            results = screen_job(job, use_llm=True)
            ai_enhanced = sum(1 for r in results if r.stage == ScreeningResult.Stage.AI_ENHANCED)
            for r in results:
                r.application.log_event(
                    ApplicationEvent.Kind.SCREEN,
                    f"Screening completed — {r.ats_score:.0f}/100 ({r.get_verdict_display()})",
                    request.user,
                )
            messages.success(
                request,
                f"Screened {len(results)} application(s) for “{job.title}” — "
                f"{ai_enhanced} enhanced with AI deep analysis.",
            )
    return redirect("job_detail", pk=pk)


@login_required
def job_advance(request, pk):
    """Bulk-advance top matches: strong/good matches move forward one stage."""
    job = get_object_or_404(Job, pk=pk)
    if request.method == "POST":
        moved = 0
        for app in job.applications.select_related("candidate", "screening").filter(
            screening__ats_score__gte=70
        ):
            target = None
            if app.status == Application.Status.NEW:
                target = Application.Status.SCREENING
            elif app.status == Application.Status.SCREENING:
                target = Application.Status.INTERVIEW
            if target:
                previous = app.get_status_display()
                app.status = target
                app.save(update_fields=["status", "updated_at"])
                app.log_event(
                    ApplicationEvent.Kind.STATUS,
                    f"Auto-advanced from {previous} to {Application.Status(target).label} (top match)",
                    request.user,
                )
                moved += 1
        if moved:
            messages.success(request, f"Advanced {moved} top match(es) to the next stage.")
        else:
            messages.info(request, "No eligible candidates to advance right now.")
    return redirect("job_detail", pk=pk)


@login_required
def job_export_csv(request, pk):
    """Export a job's applicants (with scores) as CSV."""
    job = get_object_or_404(Job, pk=pk)
    apps = job.applications.select_related("candidate", "screening").order_by("-screening__ats_score")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    safe_title = re.sub(r'[\r\n\"]', "", job.title or "job").strip() or "job"
    response["Content-Disposition"] = f'attachment; filename="{safe_title}.csv"'
    writer = csv.writer(response)
    writer.writerow(["Candidate", "Email", "Stage", "ATS score", "Verdict", "Applied on"])
    for a in apps:
        writer.writerow([
            safe_csv_cell(a.candidate.full_name),
            safe_csv_cell(a.candidate.email),
            safe_csv_cell(a.get_status_display()),
            a.score if a.score is not None else "",
            a.screening.get_verdict_display() if hasattr(a, "screening") and a.screening else "",
            a.created_at.strftime("%Y-%m-%d"),
        ])
    return response
