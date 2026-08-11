from django import forms

from jobs.models import Job

SKILL_HELP = "Separate skills with commas, e.g. Python, Django, AWS"


class JobForm(forms.ModelForm):
    required_skills_input = forms.CharField(
        required=False, label="Required skills", help_text=SKILL_HELP, widget=forms.Textarea(attrs={"rows": 3})
    )
    nice_to_have_skills_input = forms.CharField(
        required=False, label="Nice-to-have skills", help_text=SKILL_HELP, widget=forms.Textarea(attrs={"rows": 2})
    )

    class Meta:
        model = Job
        fields = [
            "title", "department", "location", "employment_type", "experience_level",
            "min_salary", "max_salary", "status", "description", "responsibilities",
            "requirements",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "responsibilities": forms.Textarea(attrs={"rows": 4}),
            "requirements": forms.Textarea(attrs={"rows": 3}),
            "min_salary": forms.NumberInput(),
            "max_salary": forms.NumberInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get("instance")
        if instance and instance.pk:
            self.fields["required_skills_input"].initial = ", ".join(instance.required_skills or [])
            self.fields["nice_to_have_skills_input"].initial = ", ".join(instance.nice_to_have_skills or [])

    @staticmethod
    def _parse_skills(value):
        if not value:
            return []
        seen = []
        for raw in value.replace(";", ",").replace("\n", ",").split(","):
            skill = raw.strip()
            if not skill:
                continue
            # Title-case words but keep acronyms (AWS, CI/CD, SaaS, SEO) intact
            skill = " ".join(w if w.isupper() and len(w) <= 5 else w.title() for w in skill.split())
            if skill not in seen:
                seen.append(skill)
        return seen

    def clean(self):
        cleaned = super().clean()
        cleaned["required_skills"] = self._parse_skills(cleaned.get("required_skills_input"))
        cleaned["nice_to_have_skills"] = self._parse_skills(cleaned.get("nice_to_have_skills_input"))
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.required_skills = self.cleaned_data["required_skills"]
        instance.nice_to_have_skills = self.cleaned_data["nice_to_have_skills"]
        if commit:
            instance.save()
        return instance
