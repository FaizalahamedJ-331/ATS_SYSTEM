from django.db import models

from core.models import BaseModel


class Job(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "Full-time"
        PART_TIME = "part_time", "Part-time"
        CONTRACT = "contract", "Contract"
        INTERNSHIP = "internship", "Internship"

    class ExperienceLevel(models.TextChoices):
        ENTRY = "entry", "Entry Level"
        JUNIOR = "junior", "Junior"
        MID = "mid", "Mid-level"
        SENIOR = "senior", "Senior"
        LEAD = "lead", "Lead / Manager"

    EXPERIENCE_YEARS = {
        ExperienceLevel.ENTRY: 1,
        ExperienceLevel.JUNIOR: 2,
        ExperienceLevel.MID: 4,
        ExperienceLevel.SENIOR: 6,
        ExperienceLevel.LEAD: 8,
    }

    title = models.CharField(max_length=200)
    department = models.CharField(max_length=120, blank=True, default="")
    location = models.CharField(max_length=120, blank=True, default="")
    employment_type = models.CharField(
        max_length=20, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME
    )
    experience_level = models.CharField(
        max_length=20, choices=ExperienceLevel.choices, default=ExperienceLevel.MID
    )
    min_salary = models.PositiveIntegerField(null=True, blank=True)
    max_salary = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True, default="")
    responsibilities = models.TextField(blank=True, default="")
    required_skills = models.JSONField(default=list, blank=True)
    nice_to_have_skills = models.JSONField(default=list, blank=True)
    requirements = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "jobs"

    def __str__(self):
        return self.title

    @property
    def salary_range(self):
        if self.min_salary and self.max_salary:
            return f"${self.min_salary:,} – ${self.max_salary:,}"
        if self.min_salary:
            return f"from ${self.min_salary:,}"
        return "Not disclosed"

    @property
    def required_years(self):
        return self.EXPERIENCE_YEARS.get(self.experience_level, 4)

    @property
    def applicant_count(self):
        return self.applications.count()

    @property
    def average_score(self):
        scores = [
            app.screening.ats_score
            for app in self.applications.select_related("screening").all()
            if hasattr(app, "screening") and app.screening.ats_score is not None
        ]
        if not scores:
            return None
        return round(sum(scores) / len(scores), 1)
