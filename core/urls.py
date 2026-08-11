from django.contrib.auth import views as auth_views
from django.urls import path

from core import views as core_views

urlpatterns = [
    path("login/", core_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("signup/", core_views.signup, name="signup"),
    path(
        "password-reset/",
        core_views.PasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        core_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "password-reset/confirm/<uidb64>/<token>/",
        core_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        core_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("settings/password/", core_views.PasswordChangeView.as_view(), name="password_change"),
    path("settings/alerts/toggle/", core_views.login_alerts_toggle, name="login_alerts_toggle"),
    path("settings/security/", core_views.security_log, name="security_log"),
    path("settings/security/sign-out/", core_views.sign_out_other_sessions, name="sign_out_other_sessions"),
    path("settings/2fa/", core_views.TotpSetupView.as_view(), name="totp_setup"),
    path("settings/2fa/disable/", core_views.totp_disable, name="totp_disable"),
    path("settings/2fa/recovery/", core_views.totp_recovery_codes, name="totp_recovery_codes"),
    path("settings/2fa/recovery/regenerate/", core_views.totp_recovery_codes_regenerate, name="totp_recovery_codes_regenerate"),
    path("settings/2fa/trust/<int:pk>/revoke/", core_views.totp_trust_revoke, name="totp_trust_revoke"),
    path("settings/2fa/trust/revoke-all/", core_views.totp_trust_revoke_all, name="totp_trust_revoke_all"),
    path("2fa/challenge/", core_views.TotpChallengeView.as_view(), name="totp_challenge"),
    path("verify-email/sent/", core_views.verify_email_sent, name="verify_email_sent"),
    path("verify-email/resend/", core_views.verify_email_resend, name="verify_email_resend"),
    path("verify-email/<str:token>/", core_views.verify_email, name="verify_email"),
    path("users/", core_views.user_list, name="user_list"),
    path("users/<int:pk>/toggle-role/", core_views.user_toggle_role, name="user_toggle_role"),
    path("users/<int:pk>/toggle-active/", core_views.user_toggle_active, name="user_toggle_active"),
    path("search/", core_views.command_search, name="command_search"),
]
