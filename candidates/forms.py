from django import forms

from candidates.models import Candidate
from core.parsers import extract_text, parse_resume


class CandidateForm(forms.ModelForm):
    skills_input = forms.CharField(
        required=False, label="Skills", help_text="Separate with commas", widget=forms.Textarea(attrs={"rows": 2})
    )
    resume_file = forms.FileField(
        required=False,
        label="Upload resume",
        help_text="PDF, DOCX or TXT — we'll auto-extract details",
    )

    class Meta:
        model = Candidate
        fields = [
            "first_name", "last_name", "email", "phone", "location",
            "headline", "current_company", "years_experience", "education",
            "summary", "source",
        ]
        widgets = {
            "years_experience": forms.NumberInput(attrs={"step": "0.5", "min": "0"}),
            "education": forms.Textarea(attrs={"rows": 2}),
            "summary": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get("instance")
        if instance and instance.pk:
            self.fields["skills_input"].initial = ", ".join(instance.skills or [])

    @staticmethod
    def _parse_skills(value):
        if not value:
            return []
        seen = []
        for raw in value.replace(";", ",").replace("\n", ",").split(","):
            skill = raw.strip()
            if skill and skill not in seen:
                seen.append(skill)
        return seen

    def clean(self):
        cleaned = super().clean()
        cleaned["skills"] = self._parse_skills(cleaned.get("skills_input"))
        email = cleaned.get("email") or ""

        # If no email was typed, try to pull one from the uploaded resume.
        resume_file = self.files.get("resume_file")
        if not email and resume_file:
            try:
                raw = extract_text(resume_file)
                parsed = parse_resume(raw)
                emails = (parsed.get("contact") or {}).get("emails") or []
                if emails:
                    email = emails[0]
                    cleaned["email"] = email
                    # The required-field error was already recorded before
                    # clean(); drop it now that the resume supplied an email.
                    self._errors.pop("email", None)
                resume_file.seek(0)  # allow re-read when the file is saved later
            except Exception:
                email = ""

        if not email:
            self.add_error("email", "An email address is required (or provided by the uploaded resume).")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.skills = self.cleaned_data.get("skills", [])
        if commit:
            instance.save()
        return instance
