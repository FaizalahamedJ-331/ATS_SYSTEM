from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from candidates.models import Application, ApplicationEvent
from interviews.models import Interview


@login_required
def interview_list(request):
    upcoming = Interview.objects.filter(
        status=Interview.Status.SCHEDULED, scheduled_at__gte=timezone.now()
    ).select_related("application", "application__candidate", "application__job")
    past = Interview.objects.filter(
        status__in=[Interview.Status.COMPLETED, Interview.Status.CANCELLED]
    ).select_related("application", "application__candidate", "application__job")[:20]

    schedule_candidates = Application.objects.filter(
        status__in=[Application.Status.SCREENING, Application.Status.INTERVIEW]
    ).select_related("candidate", "job").order_by("job__title")

    context = {
        "active_page": "interviews",
        "upcoming": upcoming,
        "past": past,
        "schedule_candidates": schedule_candidates,
        "interview_types": Interview.Type.choices,
        "now": timezone.now(),
    }
    return render(request, "interviews/list.html", context)


@login_required
def interview_schedule(request):
    if request.method == "POST":
        application_id = request.POST.get("application_id")
        scheduled_at = request.POST.get("scheduled_at")
        if not (application_id and scheduled_at):
            messages.error(request, "Please choose a candidate and a date/time.")
            return redirect("interview_list")
        app = get_object_or_404(Application, pk=application_id)
        try:
            when = timezone.datetime.fromisoformat(scheduled_at)
        except ValueError:
            messages.error(request, "Please enter a valid date and time.")
            return redirect("interview_list")
        if timezone.is_naive(when):
            when = timezone.make_aware(when)
        if when <= timezone.now():
            messages.error(request, "Interview time must be in the future.")
            return redirect("interview_list")
        Interview.objects.create(
            application=app,
            scheduled_at=when,
            duration_minutes=int(request.POST.get("duration_minutes") or 45),
            interview_type=request.POST.get("interview_type", Interview.Type.VIDEO),
            interviewer=request.POST.get("interviewer", "").strip(),
        )
        app.status = Application.Status.INTERVIEW
        app.save(update_fields=["status", "updated_at"])
        app.log_event(
            ApplicationEvent.Kind.INTERVIEW,
            f"Interview scheduled ({dict(Interview.Type.choices).get(request.POST.get('interview_type', ''), 'Video call')}, {when.strftime('%b %d at %H:%M')})",
            request.user,
        )
        messages.success(request, f"Interview scheduled with {app.candidate.full_name}.")
    return redirect("interview_list")


@login_required
def interview_complete(request, pk):
    interview = get_object_or_404(Interview, pk=pk)
    if request.method == "POST":
        feedback = request.POST.get("feedback", "").strip()
        rating = request.POST.get("rating")
        interview.feedback = feedback
        interview.rating = int(rating) if rating and rating.isdigit() and 1 <= int(rating) <= 5 else None
        interview.status = Interview.Status.COMPLETED
        interview.save(update_fields=["feedback", "rating", "status", "updated_at"])

        # Auto-move the application forward on a positive outcome
        app = interview.application
        if interview.rating and interview.rating >= 4 and app.status == Application.Status.INTERVIEW:
            app.status = Application.Status.OFFER
            app.save(update_fields=["status", "updated_at"])
            app.log_event(
                ApplicationEvent.Kind.STATUS,
                f"Interview rated {interview.rating}/5 — moved to Offer",
                request.user,
            )
            messages.success(request, f"Interview completed. {app.candidate.full_name} moved to Offer.")
        else:
            app.log_event(
                ApplicationEvent.Kind.INTERVIEW,
                f"Interview completed" + (f" (rated {interview.rating}/5)" if interview.rating else ""),
                request.user,
            )
            messages.success(request, "Interview feedback saved.")
    return redirect("interview_list")


@login_required
def interview_cancel(request, pk):
    interview = get_object_or_404(Interview, pk=pk)
    if request.method == "POST":
        interview.status = Interview.Status.CANCELLED
        interview.save(update_fields=["status", "updated_at"])
        interview.application.log_event(
            ApplicationEvent.Kind.INTERVIEW, "Interview cancelled", request.user
        )
        messages.info(request, "Interview cancelled.")
    return redirect("interview_list")
