from django.db import models

from core.models import BaseModel


class ScreeningResult(BaseModel):
    class Verdict(models.TextChoices):
        STRONG = "strong_match", "Strong Match"
        GOOD = "good_match", "Good Match"
        POSSIBLE = "possible_match", "Possible Match"
        WEAK = "weak_match", "Weak Match"

    class Stage(models.TextChoices):
        RULE_BASED = "rule_based", "Rule-based"
        AI_ENHANCED = "ai_enhanced", "AI-enhanced"

    application = models.OneToOneField(
        "candidates.Application", on_delete=models.CASCADE, related_name="screening"
    )
    ats_score = models.FloatField(default=0, db_index=True)
    skill_score = models.FloatField(default=0)
    keyword_score = models.FloatField(default=0)
    experience_score = models.FloatField(default=0)
    education_score = models.FloatField(default=0)
    matched_skills = models.JSONField(default=list, blank=True)
    missing_skills = models.JSONField(default=list, blank=True)
    matched_nice_to_have = models.JSONField(default=list, blank=True)
    matched_keywords = models.JSONField(default=list, blank=True)
    missing_keywords = models.JSONField(default=list, blank=True)
    strengths = models.JSONField(default=list, blank=True)
    concerns = models.JSONField(default=list, blank=True)
    verdict = models.CharField(max_length=20, choices=Verdict.choices, default=Verdict.POSSIBLE)
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.RULE_BASED)

    # --- Smart screening outputs (rule-based, no API key needed) ---
    insight = models.TextField(blank=True, default="")
    recommendation = models.CharField(max_length=80, blank=True, default="")

    # --- Optional AI analysis ---
    ai_analysis = models.TextField(blank=True, default="")
    ai_verdict = models.CharField(max_length=20, choices=Verdict.choices, blank=True, default="")
    ai_score_adjustment = models.IntegerField(default=0)

    class Meta:
        ordering = ["-ats_score"]
        indexes = [models.Index(fields=["-created_at"], name="screen_created_idx")]

    def __str__(self):
        return f"Screening for {self.application} — {self.ats_score:.0f}/100"

    @property
    def breakdown(self):
        return {
            "skill": self.skill_score,
            "keyword": self.keyword_score,
            "experience": self.experience_score,
            "education": self.education_score,
        }
