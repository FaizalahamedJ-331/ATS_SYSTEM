from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from candidates.forms import CandidateForm
from candidates.models import Application, ApplicationEvent, Candidate, Resume
from core.csv_utils import safe_csv_cell
from core.parsers import extract_text, parse_resume
from jobs.models import Job

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_RESUME_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".rtf"}


class ResumeValidationError(Exception):
    pass


def _validate_upload(uploaded):
    if uploaded.size > MAX_UPLOAD_SIZE:
        raise ResumeValidationError("Resume is too large (max 10 MB).")
    name = (uploaded.name or "").lower()
    if not name or not any(name.endswith(ext) for ext in ALLOWED_RESUME_EXTENSIONS):
        raise ResumeValidationError("Unsupported file type — please upload a PDF, DOCX or TXT file.")


def _merge_resume_into_candidate(candidate, resume):
    """Fill candidate fields from the parsed resume (only where blank or additive)."""
    parsed = resume.parsed or {}
    contact = parsed.get("contact", {}) or {}

    if not candidate.email and contact.get("emails"):
        candidate.email = contact["emails"][0]
    if not candidate.phone and contact.get("phones"):
        candidate.phone = contact["phones"][0]

    if not candidate.headline:
        lines = [l.strip() for l in (resume.raw_text or "").splitlines() if l.strip()]
        for line in lines[1:4]:
            if "@" in line or not any(ch.isalpha() for ch in line) or len(line) > 90:
                continue  # skip email / phone / noise lines
            candidate.headline = line[:160]
            break

    # Merge skills (additive)
    existing = set(candidate.skills or [])
    existing.update(parsed.get("skills", []) or [])
    candidate.skills = sorted(existing)

    if parsed.get("years_experience"):
        candidate.years_experience = parsed["years_experience"]

    edu = parsed.get("education", {}) or {}
    if not candidate.education:
        if edu.get("snippet"):
            candidate.education = edu["snippet"]
        elif edu.get("degrees"):
            candidate.education = ", ".join(edu["degrees"])


@login_required
def candidate_export_csv(request):
    """Export all candidates (with best score) as CSV."""
    import csv as _csv

    from django.http import HttpResponse

    candidates = (
        Candidate.objects.prefetch_related("applications__screening")
        .order_by("last_name", "first_name")
        .all()
    )
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="candidates.csv"'
    writer = _csv.writer(response)
    writer.writerow(["Name", "Email", "Headline", "Company", "Years exp", "Source", "Best score"])
    for c in candidates:
        scores = [a.score for a in c.applications.all() if a.score is not None]
        best = round(max(scores), 1) if scores else ""
        writer.writerow([
            safe_csv_cell(c.full_name), safe_csv_cell(c.email), safe_csv_cell(c.headline),
            safe_csv_cell(c.current_company), c.years_experience, c.get_source_display(), best,
        ])
    return response


@login_required
def candidate_list(request):
    candidates = (
        Candidate.objects.annotate(app_count=Count("applications"))
        .prefetch_related("applications__screening")
        .all()
    )
    source = request.GET.get("source", "")
    q = request.GET.get("q", "").strip()
    pinned_only = request.GET.get("pinned", "") == "1"

    if source in dict(Candidate.Source.choices):
        candidates = candidates.filter(source=source)
    if q:
        candidates = candidates.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
            | Q(headline__icontains=q)
        )
    if pinned_only:
        candidates = candidates.filter(pinned=True)

    # Pinned candidates always float to the top of the list
    candidates = candidates.order_by("-pinned", "-created_at")

    context = {
        "active_page": "candidates",
        "candidates": candidates,
        "source": source,
        "q": q,
        "pinned_only": pinned_only,
        "source_choices": Candidate.Source.choices,
    }
    return render(request, "candidates/list.html", context)


@login_required
def candidate_toggle_pin(request, pk):
    """Pin / unpin a candidate (JSON)."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST only"}, status=405)
    candidate = get_object_or_404(Candidate, pk=pk)
    candidate.pinned = not candidate.pinned
    candidate.save(update_fields=["pinned", "updated_at"])
    return JsonResponse({"ok": True, "pinned": candidate.pinned})


@login_required
def candidate_detail(request, pk):
    candidate = get_object_or_404(Candidate, pk=pk)
    resumes = candidate.resumes.all()
    applications = (
        candidate.applications.select_related("job", "screening", "resume")
        .prefetch_related("interviews", "events__user")
        .order_by("-created_at")
    )
    latest_resume = resumes.first()

    context = {
        "active_page": "candidates",
        "candidate": candidate,
        "resumes": resumes,
        "latest_resume": latest_resume,
        "applications": applications,
        "job_choices": Job.objects.filter(status=Job.Status.OPEN).exclude(
            pk__in=candidate.applications.values_list("job_id", flat=True)
        ),
    }
    return render(request, "candidates/detail.html", context)


@login_required
def candidate_create(request):
    if request.method == "POST":
        form = CandidateForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = request.FILES.get("resume_file")
            candidate = form.save()
            if uploaded:
                try:
                    _save_resume(candidate, uploaded)
                except ResumeValidationError as exc:
                    messages.error(request, str(exc))
                    return redirect("candidate_detail", pk=candidate.pk)
                candidate.refresh_from_db()
            messages.success(
                request,
                f"Candidate {candidate.full_name} added"
                + (" and resume parsed." if uploaded else "."),
            )
            return redirect("candidate_detail", pk=candidate.pk)
    else:
        form = CandidateForm()
    context = {"active_page": "candidates", "form": form}
    return render(request, "candidates/form.html", context)


def _save_resume(candidate, uploaded):
    _validate_upload(uploaded)
    uploaded.seek(0)
    raw_text = extract_text(uploaded)
    parsed = parse_resume(raw_text)
    resume = Resume.objects.create(
        candidate=candidate,
        file=uploaded,
        file_type=(uploaded.name or "").split(".")[-1].lower(),
        raw_text=raw_text,
        parsed=parsed,
    )
    _merge_resume_into_candidate(candidate, resume)
    try:
        candidate.save()
    except IntegrityError:
        candidate.refresh_from_db()
        candidate.skills = sorted(set(candidate.skills or []) | set(parsed.get("skills", []) or []))
        candidate.save()
    return resume


@login_required
def candidate_upload_resume(request, pk):
    candidate = get_object_or_404(Candidate, pk=pk)
    if request.method == "POST" and request.FILES.get("resume_file"):
        try:
            _save_resume(candidate, request.FILES["resume_file"])
        except ResumeValidationError as exc:
            messages.error(request, str(exc))
            return redirect("candidate_detail", pk=candidate.pk)
        for app in candidate.applications.select_related("job").all():
            app.log_event(
                ApplicationEvent.Kind.RESUME,
                f"New resume uploaded and parsed for {app.job.title}",
                request.user,
            )
        messages.success(request, f"Resume uploaded and parsed for {candidate.full_name}.")
    return redirect("candidate_detail", pk=candidate.pk)


@login_required
def candidate_apply(request, pk):
    """Apply a candidate to a job (used from job detail / candidate detail)."""
    candidate = get_object_or_404(Candidate, pk=pk)
    job_id = request.POST.get("job_id")
    if request.method == "POST" and job_id:
        job = get_object_or_404(Job, pk=job_id)
        app, created = Application.objects.get_or_create(
            job=job,
            candidate=candidate,
            defaults={"resume": candidate.resumes.first()},
        )
        if created:
            app.log_event(ApplicationEvent.Kind.APPLY, f"Applied to {job.title}", request.user)
            messages.success(request, f"{candidate.full_name} applied to “{job.title}”.")
        else:
            messages.info(request, f"{candidate.full_name} already applied to “{job.title}”.")
    return redirect("candidate_detail", pk=candidate.pk)


@login_required
@require_POST
def application_hired(request, pk):
    """Mark an application as Hired (POST) — fires the client-side celebration."""
    app = get_object_or_404(Application.objects.select_related("candidate"), pk=pk)
    if app.status != Application.Status.HIRED:
        previous = app.get_status_display()
        app.status = Application.Status.HIRED
        app.save(update_fields=["status", "updated_at"])
        app.log_event(
            ApplicationEvent.Kind.STATUS,
            f"Moved from {previous} to Hired",
            request.user,
        )
    # Tagged message: the front-end toast bootstrap turns this into confetti
    messages.success(request, app.candidate.full_name, extra_tags="hired")
    return redirect("candidate_detail", pk=app.candidate.pk)


@login_required
@require_POST
def application_note(request, pk):
    """Add a human note to an application's activity timeline."""
    app = get_object_or_404(Application, pk=pk)
    text = request.POST.get("text", "").strip()
    if text:
        app.log_event(ApplicationEvent.Kind.NOTE, text[:1000], request.user)
        messages.success(request, "Note added.")
    else:
        messages.warning(request, "Write something before saving a note.")
    return redirect("candidate_detail", pk=app.candidate.pk)


# ---------------------------------------------------------------------------
# Pipeline board
# ---------------------------------------------------------------------------
@login_required
def pipeline(request):
    applications = (
        Application.objects.select_related("candidate", "job", "screening", "resume")
        .prefetch_related("interviews")
        .order_by("-created_at")
        .all()
    )
    job_id = request.GET.get("job", "")
    if job_id and job_id.isdigit():
        applications = applications.filter(job_id=int(job_id))

    columns = {s.value: [] for s in Application.Status}
    for app in applications:
        columns[app.status].append(app)

    jobs = applications.values_list("job_id", "job__title").distinct()

    context = {
        "active_page": "pipeline",
        "columns": columns,
        "statuses": Application.Status,
        "job_id": job_id,
        "jobs": jobs,
    }
    return render(request, "pipeline.html", context)


@login_required
def application_status(request, pk):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST only"}, status=405)
    status = request.POST.get("status", "")
    if status not in dict(Application.Status.choices):
        return JsonResponse({"ok": False, "error": "Invalid status"}, status=400)
    app = get_object_or_404(Application, pk=pk)
    previous = app.get_status_display()
    app.status = status
    app.save(update_fields=["status", "updated_at"])
    app.log_event(
        ApplicationEvent.Kind.STATUS,
        f"Moved from {previous} to {Application.Status(status).label}",
        request.user,
    )
    return JsonResponse(
        {
            "ok": True,
            "status": status,
            "status_label": Application.Status(status).label,
            "hired": app.status == Application.Status.HIRED,
        }
    )
