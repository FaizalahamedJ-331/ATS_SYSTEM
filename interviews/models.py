from django.db import models

from core.models import BaseModel


class Interview(BaseModel):
    class Type(models.TextChoices):
        PHONE = "phone", "Phone Screen"
        VIDEO = "video", "Video Call"
        ONSITE = "onsite", "On-site"
        TECHNICAL = "technical", "Technical Interview"
        PANEL = "panel", "Panel Interview"

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    application = models.ForeignKey(
        "candidates.Application", on_delete=models.CASCADE, related_name="interviews"
    )
    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=45)
    interview_type = models.CharField(max_length=20, choices=Type.choices, default=Type.VIDEO)
    interviewer = models.CharField(max_length=160, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    feedback = models.TextField(blank=True, default="")
    rating = models.PositiveSmallIntegerField(null=True, blank=True)  # 1–5

    class Meta:
        ordering = ["scheduled_at"]

    def __str__(self):
        return f"{self.interview_type} — {self.application}"

    @property
    def candidate(self):
        return self.application.candidate
