from django import forms
from django.contrib.auth import forms as auth_forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User


class SignupForm(UserCreationForm):
    """Self-registration form.

    New accounts are always created as **Recruiters** - the Admin role is
    reserved and managed by existing admins from the Users page.
    """

    first_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "First name"}),
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "Last name"}),
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"placeholder": "you@company.com"}),
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "username", "password1", "password2")
        widgets = {
            "username": forms.TextInput(attrs={"placeholder": "Choose a username"}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"].strip().lower()
        if commit:
            user.save()
        return user

from django.contrib.auth.forms import AuthenticationForm


class LoginForm(AuthenticationForm):
    """Login form that explains *why* a login failed when the account has
    not yet verified its email, instead of the generic credentials error.
    """

    error_messages = {
        **AuthenticationForm.error_messages,
        "unverified": "Please verify your email first — check your inbox for the link we sent.",
    }

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        # Defensive: a profile is created for every user by a post_save
        # signal, but login must never 500 — treat a missing profile as
        # verified so the account stays usable.
        if not getattr(getattr(user, "profile", None), "is_verified", True):
            raise forms.ValidationError(
                self.error_messages["unverified"],
                code="unverified",
            )


class ResendVerificationForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"placeholder": "you@company.com"}),
    )


class PasswordResetForm(auth_forms.PasswordResetForm):
    """Forgot-password form that sends through TalentPulse's own email
    system (branded templates, SITE_URL absolute links) instead of Django's
    default plain templates. Keeps Django's anti-enumeration behavior: the
    form never reveals whether an email has an account.
    """

    def save(
        self,
        domain_override=None,
        subject_template_name="registration/password_reset_subject.txt",
        email_template_name="registration/password_reset_email.html",
        use_https=False,
        token_generator=None,
        from_email=None,
        request=None,
        html_email_template_name=None,
        extra_email_context=None,
    ):
        # Remember the request so send_mail() can build absolute links.
        self._reset_request = request
        return super().save(
            domain_override=domain_override,
            subject_template_name=subject_template_name,
            email_template_name=email_template_name,
            use_https=use_https,
            token_generator=token_generator,
            from_email=from_email,
            request=request,
            html_email_template_name=html_email_template_name,
            extra_email_context=extra_email_context,
        )

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        from core.email_utils import send_password_reset_email

        send_password_reset_email(
            context["user"],
            context["uid"],
            context["token"],
            request=getattr(self, "_reset_request", None),
        )
