from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render

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

    context = {
        "active_page": "jobs",
        "job": job,
        "ranked": ranked,
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
            messages.success(
                request,
                f"Screened {len(results)} application(s) for “{job.title}” — "
                f"{ai_enhanced} enhanced with AI deep analysis.",
            )
    return redirect("job_detail", pk=pk)
