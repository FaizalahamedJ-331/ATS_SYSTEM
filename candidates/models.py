from django.db import models

from core.models import BaseModel


class Candidate(BaseModel):
    class Source(models.TextChoices):
        LINKEDIN = "linkedin", "LinkedIn"
        REFERRAL = "referral", "Referral"
        WEBSITE = "website", "Company Website"
        JOB_BOARD = "job_board", "Job Board"
        AGENCY = "agency", "Recruitment Agency"
        EVENT = "event", "Event / Conference"
        OTHER = "other", "Other"

    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=40, blank=True, default="")
    location = models.CharField(max_length=120, blank=True, default="")
    headline = models.CharField(max_length=160, blank=True, default="")
    current_company = models.CharField(max_length=120, blank=True, default="")
    years_experience = models.FloatField(default=0, blank=True)
    education = models.TextField(blank=True, default="")
    skills = models.JSONField(default=list, blank=True)
    summary = models.TextField(blank=True, default="")
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.OTHER)
    pinned = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def initials(self):
        parts = [p for p in (self.first_name, self.last_name) if p]
        return "".join(p[0].upper() for p in parts)[:2] or "?"


class Resume(BaseModel):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="resumes")
    file = models.FileField(upload_to="resumes/%Y/%m/", blank=True, null=True)
    file_type = models.CharField(max_length=10, blank=True, default="")
    raw_text = models.TextField(blank=True, default="")
    parsed = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Resume for {self.candidate.full_name}"

    @property
    def skills(self):
        return self.parsed.get("skills", []) or []


class Application(BaseModel):
    class Status(models.TextChoices):
        NEW = "new", "New"
        SCREENING = "screening", "Screening"
        INTERVIEW = "interview", "Interview"
        OFFER = "offer", "Offer"
        HIRED = "hired", "Hired"
        REJECTED = "rejected", "Rejected"

    PIPELINE_ORDER = {
        Status.NEW: 0,
        Status.SCREENING: 1,
        Status.INTERVIEW: 2,
        Status.OFFER: 3,
        Status.HIRED: 4,
        Status.REJECTED: 5,
    }

    job = models.ForeignKey("jobs.Job", on_delete=models.CASCADE, related_name="applications")
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="applications")
    resume = models.ForeignKey(
        Resume, on_delete=models.SET_NULL, null=True, blank=True, related_name="applications"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NEW, db_index=True
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"], name="app_created_idx")]
        constraints = [
            models.UniqueConstraint(fields=["job", "candidate"], name="unique_job_candidate")
        ]

    def __str__(self):
        return f"{self.candidate.full_name} → {self.job.title}"

    @property
    def score(self):
        result = getattr(self, "screening", None)
        return result.ats_score if result and result.ats_score is not None else None

    @property
    def verdict(self):
        result = getattr(self, "screening", None)
        return result.verdict if result else None

    def log_event(self, kind, text, user=None):
        """Record an activity or note against this application."""
        ApplicationEvent.objects.create(
            application=self, kind=kind, text=text, user=user
        )


class ApplicationEvent(BaseModel):
    class Kind(models.TextChoices):
        NOTE = "note", "Note"
        STATUS = "status", "Stage change"
        SCREEN = "screen", "Screening"
        RESUME = "resume", "Resume"
        INTERVIEW = "interview", "Interview"
        APPLY = "apply", "Application"

    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="events"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.NOTE)
    text = models.TextField(default="")
    user = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"], name="event_created_idx")]
        verbose_name = "application event"

    def __str__(self):
        return f"{self.kind}: {self.text[:60]}"
