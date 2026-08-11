from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from candidates.models import Candidate
from jobs.models import Job


@login_required
@require_GET
def command_search(request):
    """Global search for the command palette.

    Returns matching candidates, jobs and static quick actions as JSON so the
    front-end can render an instant, keyboard-navigable palette.
    """
    q = (request.GET.get("q") or "").strip()
    limit = 6

    candidates = []
    if q:
        candidates = list(
            Candidate.objects.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(email__icontains=q)
                | Q(headline__icontains=q)
            )
            .order_by("-created_at")[:limit]
        )

    jobs = []
    if q:
        jobs = list(
            Job.objects.filter(
                Q(title__icontains=q)
                | Q(department__icontains=q)
                | Q(location__icontains=q)
            )
            .order_by("-created_at")[:limit]
        )

    actions = [
        {"label": "Dashboard", "hint": "Go to overview", "url": "/"},
        {"label": "Jobs", "hint": "All open positions", "url": "/jobs/"},
        {"label": "Candidates", "hint": "Talent pool", "url": "/candidates/"},
        {"label": "Pipeline", "hint": "Kanban board", "url": "/pipeline/"},
        {"label": "Interviews", "hint": "Scheduled interviews", "url": "/interviews/"},
        {"label": "New job", "hint": "Create a requisition", "url": "/jobs/new/"},
        {"label": "Add candidate", "hint": "Create a profile", "url": "/candidates/new/"},
    ]
    if q:
        actions = [
            a for a in actions
            if q.lower() in a["label"].lower() or q.lower() in a["hint"].lower()
        ]

    return JsonResponse({
        "query": q,
        "actions": actions,
        "candidates": [
            {
                "label": c.full_name,
                "hint": f"{c.headline or 'Candidate'} · {c.email}",
                "url": f"/candidates/{c.pk}/",
                "meta": "candidate",
                "initials": c.initials,
            }
            for c in candidates
        ],
        "jobs": [
            {
                "label": j.title,
                "hint": f"{j.department or 'General'} · {j.location or 'Remote'}",
                "url": f"/jobs/{j.pk}/",
                "meta": "job",
            }
            for j in jobs
        ],
    })
